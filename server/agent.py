"""Planner agent orchestrating tool calls to satisfy research queries."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .llm import OllamaJSONClient
from .tools import ToolDispatcher

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the autonomous planner for a self-hosted search stack. "
    "Always respond with a single JSON object. "
    "When you need information use {\"type\": \"tool\", \"tool\": <name>, \"params\": {...}}. "
    "When you are ready to answer return {\"type\": \"final\", \"answer\": <summary>, \"sources\": []}. "
    "Do not include commentary outside the JSON object."
)

FEW_SHOT_MESSAGES: Sequence[Mapping[str, str]] = (
    {
        "role": "user",
        "content": json.dumps(
            {
                "type": "query",
                "query": "Find recent docs about crawling ethics",
            }
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "type": "tool",
                "tool": "index.search",
                "params": {"query": "crawling ethics", "k": 3},
            }
        ),
    },
    {
        "role": "tool",
        "name": "index.search",
        "content": json.dumps(
            {
                "ok": True,
                "tool": "index.search",
                "result": {"results": []},
            }
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "type": "final",
                "answer": "No indexed documents found. Recommend triggering a crawl.",
                "sources": [],
            }
        ),
    },
)


@dataclass
class PlannerAgent:
    llm: OllamaJSONClient
    tools: ToolDispatcher
    default_model: str | None = None
    max_iterations: int = 6
    logger: logging.Logger = field(default=LOGGER)

    def run(
        self,
        query: str,
        *,
        context: Mapping[str, Any] | None = None,
        model: str | None = None,
    ) -> Mapping[str, Any]:
        self.logger.info("planner starting query=%s", query)
        messages = list(self._bootstrap_messages(query, context))
        steps: list[dict[str, Any]] = []
        for iteration in range(1, self.max_iterations + 1):
            self.logger.debug("planner iteration=%s", iteration)
            response = self.llm.chat_json(messages, model=model or self.default_model)
            steps.append({"iteration": iteration, "response": response})
            self.logger.info("planner step %s response=%s", iteration, json.dumps(response))
            messages.append({"role": "assistant", "content": json.dumps(response)})
            message_type = response.get("type")
            if message_type == "tool":
                tool_name = response.get("tool")
                params = response.get("params") if isinstance(response.get("params"), Mapping) else {}
                tool_result = self.tools.execute(tool_name, params)
                steps[-1]["tool"] = tool_result
                self.logger.info(
                    "planner tool %s result=%s", tool_name, json.dumps(tool_result)
                )
                messages.append(
                    {
                        "role": "tool",
                        "name": str(tool_name),
                        "content": json.dumps(tool_result),
                    }
                )
                continue
            if message_type == "final":
                final_payload = self._normalize_final(response, steps)
                self.logger.info("planner completed query=%s", query)
                return final_payload
            error = {
                "ok": False,
                "tool": "planner",
                "error": "invalid response type",
                "received": response,
            }
            steps[-1]["error"] = error
            self.logger.warning("planner invalid response -> %s", json.dumps(error))
            messages.append(
                {
                    "role": "tool",
                    "name": "planner",
                    "content": json.dumps(error),
                }
            )
        self.logger.warning("planner hit iteration limit for query=%s", query)
        return {
            "type": "final",
            "answer": "",
            "sources": [],
            "error": "iteration limit reached",
            "steps": steps,
        }

    def _bootstrap_messages(
        self, query: str, context: Mapping[str, Any] | None
    ) -> Iterable[Mapping[str, Any]]:
        yield {"role": "system", "content": SYSTEM_PROMPT}
        yield from FEW_SHOT_MESSAGES
        payload = {
            "type": "query",
            "query": query,
            "context": dict(context or {}),
        }
        yield {"role": "user", "content": json.dumps(payload)}

    @staticmethod
    def _normalize_final(
        payload: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        final = {
            "type": "final",
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "context": payload.get("context", {}),
            "steps": list(steps),
        }
        if "error" in payload:
            final["error"] = payload["error"]
        return final


__all__ = ["PlannerAgent", "SYSTEM_PROMPT", "FEW_SHOT_MESSAGES"]
