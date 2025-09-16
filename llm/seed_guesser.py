"""Lightweight Ollama client used to propose crawl seeds."""

from __future__ import annotations

import json
import logging
import os
from typing import Iterable, List, Optional

import requests

LOGGER = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct")
DEFAULT_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "30"))

PROMPT_TEMPLATE = (
    """Suggest up to 10 authoritative URLs (home or docs pages) likely to answer:\n"
    '"{q}"\n'
    "Output a JSON array of strings (URLs only, no extra text)."""
)


def _sanitize_urls(values: Iterable[object]) -> List[str]:
    urls: List[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not candidate:
            continue
        if not candidate.startswith(("http://", "https://")):
            # Skip anything that doesn't look like a URL; crawling will fail otherwise.
            continue
        if candidate not in urls:
            urls.append(candidate)
    return urls


def guess_urls(query: str, model: Optional[str] = None, host: Optional[str] = None, timeout: Optional[float] = None) -> List[str]:
    """Ask a local Ollama instance to guess promising URLs for the query.

    Parameters
    ----------
    query:
        The end-user query driving the focused crawl.
    model:
        Optional explicit model name; falls back to ``OLLAMA_MODEL`` when omitted.
    host:
        Override the Ollama host. Defaults to ``OLLAMA_HOST``.
    timeout:
        Optional request timeout override in seconds.
    """

    q = (query or "").strip()
    if not q:
        return []

    llm_model = (model or DEFAULT_MODEL or "").strip()
    if not llm_model:
        LOGGER.debug("No Ollama model configured; skipping LLM seed guess")
        return []

    llm_host = (host or OLLAMA_HOST or "").rstrip("/")
    request_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

    payload = {
        "model": llm_model,
        "prompt": PROMPT_TEMPLATE.format(q=q),
        "stream": False,
    }

    try:
        response = requests.post(
            f"{llm_host}/api/generate",
            json=payload,
            timeout=request_timeout,
        )
        response.raise_for_status()
    except (requests.RequestException, ValueError) as exc:
        LOGGER.debug("Ollama request failed: %s", exc)
        return []

    try:
        body = response.json()
    except ValueError as exc:  # pragma: no cover - defensive
        LOGGER.debug("Invalid JSON from Ollama: %s", exc)
        return []

    text = (body or {}).get("response", "").strip()
    if not text:
        return []

    try:
        raw_urls = json.loads(text)
    except json.JSONDecodeError as exc:
        LOGGER.debug("Failed to decode Ollama response as JSON array: %s", exc)
        return []

    if not isinstance(raw_urls, list):
        LOGGER.debug("Ollama response was not a list; ignoring")
        return []

    return _sanitize_urls(raw_urls)


__all__ = ["guess_urls"]
