"""Retrieval augmented generation agent using Ollama models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..data.store import RetrievedChunk
from ..llm.ollama_client import ChatMessage, OllamaClient, OllamaClientError


@dataclass(slots=True)
class RagResult:
    answer: str
    sources: list[dict]
    used: int


class RagAgent:
    """Orchestrates prompt construction, LLM invocation, and citation formatting."""

    def __init__(
        self,
        client: OllamaClient,
        primary_model: str,
        fallback_model: str | None = None,
    ) -> None:
        self._client = client
        self._primary_model = primary_model
        self._fallback_model = fallback_model

    def build_prompt(self, question: str, documents: Sequence[RetrievedChunk]) -> str:
        if documents:
            context_lines = []
            for idx, doc in enumerate(documents, 1):
                header = doc.title or doc.url or f"Source {idx}"
                snippet = doc.text.strip().replace("\n", " ")
                context_lines.append(f"[{idx}] {header}\n{snippet}")
            context_block = "\n\n".join(context_lines)
        else:
            context_block = "(no context available)"
        instructions = (
            "You are a retrieval augmented assistant. Use the provided context to answer the user question. "
            "Reference sources using [number] notation when you quote or paraphrase material. If the context does not "
            "contain the answer, reply that you do not know."
        )
        return f"{instructions}\n\nContext:\n{context_block}\n\nQuestion: {question.strip()}\n\nAnswer:"

    def _invoke(self, model: str, prompt: str) -> str:
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You produce grounded, concise answers and never fabricate citations. "
                    "Only cite sources listed in the context section."
                ),
            ),
            ChatMessage(role="user", content=prompt),
        ]
        return self._client.chat(model, messages)

    def run(self, question: str, documents: Sequence[RetrievedChunk]) -> RagResult:
        prompt = self.build_prompt(question, documents)
        try:
            answer = self._invoke(self._primary_model, prompt)
        except OllamaClientError:
            if not self._fallback_model:
                raise
            answer = self._invoke(self._fallback_model, prompt)
        answer = answer.strip()
        sources = self._format_sources(documents)
        return RagResult(answer=answer, sources=sources, used=len(documents))

    @staticmethod
    def _format_sources(documents: Sequence[RetrievedChunk]) -> list[dict]:
        formatted: list[dict] = []
        for idx, doc in enumerate(documents, 1):
            formatted.append(
                {
                    "id": idx,
                    "url": doc.url,
                    "title": doc.title,
                    "similarity": doc.similarity,
                }
            )
        return formatted


__all__ = ["RagAgent", "RagResult"]
