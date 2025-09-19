"""Blend Whoosh scores with authority metrics and optional LLM reranking."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Iterable, List

import requests

from .authority import AuthorityIndex

LOGGER = logging.getLogger(__name__)

DEFAULT_ALPHA = float(os.getenv("RANK_AUTH_ALPHA", "0.15"))
OLLAMA_HOST = os.getenv("OLLAMA_URL", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "12"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))


def blend_results(results: Iterable[dict], authority: AuthorityIndex | None = None, *, alpha: float = DEFAULT_ALPHA) -> List[dict]:
    """Return a copy of ``results`` with blended scores."""

    authority = authority or AuthorityIndex.load_default()
    blended: List[dict] = []
    for result in results:
        url = result.get("url", "")
        base = float(result.get("score", 0.0))
        host_score = authority.score_for(url)
        final = base + alpha * host_score
        enriched = dict(result)
        enriched["host_authority"] = host_score
        enriched["blended_score"] = final
        blended.append(enriched)
    blended.sort(key=lambda item: item.get("blended_score", item.get("score", 0.0)), reverse=True)
    return blended


def _rerank_prompt(query: str, docs: List[dict]) -> str:
    lines = ["You are a search ranking assistant for a private index.", f"Query: {query}", "Documents:"]
    for idx, doc in enumerate(docs, start=1):
        lines.append(f"{idx}. {doc.get('title') or doc.get('url')}")
        lines.append(f"URL: {doc.get('url')}")
        snippet = (doc.get("snippet") or "").replace("\n", " ")
        lines.append(f"Snippet: {snippet[:280]}")
        lines.append("")
    lines.append("Return a JSON array listing the URLs in the ideal relevance order.")
    return "\n".join(lines)


def maybe_rerank(
    query: str,
    results: List[dict],
    *,
    enabled: bool,
    model: str | None = None,
    top_n: int = RERANK_TOP_N,
    timeout: float = OLLAMA_TIMEOUT,
) -> List[dict]:
    """Rerank ``results`` using a local LLM when available."""

    if not enabled or not results or not OLLAMA_HOST:
        return results
    docs = results[: max(1, top_n)]
    prompt = _rerank_prompt(query, docs)
    payload = {"model": model or os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct"), "prompt": prompt, "stream": False}
    start = time.perf_counter()
    try:
        response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.debug("LLM rerank skipped: %s", exc)
        return results
    finally:
        duration = (time.perf_counter() - start) * 1000
        LOGGER.debug("LLM rerank attempt took %.1fms", duration)
    try:
        body = response.json()
    except ValueError:
        return results
    order_text = (body or {}).get("response", "").strip()
    if not order_text:
        return results
    try:
        ordered_urls = json.loads(order_text)
    except json.JSONDecodeError:
        LOGGER.debug("LLM rerank response not JSON: %s", order_text[:120])
        return results
    if not isinstance(ordered_urls, list):
        return results

    lookup = {doc.get("url"): doc for doc in docs}
    reordered: List[dict] = []
    used: set[str] = set()
    for candidate in ordered_urls:
        url = candidate if isinstance(candidate, str) else None
        if not url:
            continue
        doc = lookup.get(url)
        if doc and url not in used:
            reordered.append(doc)
            used.add(url)
    for doc in docs:
        url = doc.get("url")
        if isinstance(url, str) and url not in used:
            reordered.append(doc)
            used.add(url)
    reordered.extend(results[len(docs):])
    return reordered


__all__ = ["blend_results", "maybe_rerank"]
