"""Search helpers that auto-trigger focused crawling when needed."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

from search.seeds import get_top_domains

from .query import search as basic_search

LOGGER = logging.getLogger(__name__)

SMART_MIN_RESULTS = max(0, int(os.getenv("SMART_MIN_RESULTS", "5")))
SMART_USE_LLM = os.getenv("SMART_USE_LLM", "false").lower() in {"1", "true", "yes", "on"}
TRIGGER_COOLDOWN_SECONDS = max(0, int(os.getenv("SMART_TRIGGER_COOLDOWN", "60")))

_FOCUSED_SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "crawl_focused.py"
_CURATED_PATH = Path(os.getenv("CURATED_SEEDS_PATH", "data/seeds/curated_seeds.jsonl"))
_TRIGGER_HISTORY: dict[str, float] = {}
_TRIGGER_LOCK = threading.Lock()

__all__ = ["smart_search"]


def _should_trigger(query: str) -> bool:
    if TRIGGER_COOLDOWN_SECONDS <= 0:
        return True

    now = time.time()
    with _TRIGGER_LOCK:
        last = _TRIGGER_HISTORY.get(query)
        if last is None:
            return True
        return (now - last) >= TRIGGER_COOLDOWN_SECONDS


def _mark_triggered(query: str) -> None:
    with _TRIGGER_LOCK:
        _TRIGGER_HISTORY[query] = time.time()


def _load_curated_seeds(limit: int = 10) -> List[str]:
    if not _CURATED_PATH.exists():
        return []
    seeds: List[tuple[float, str]] = []
    try:
        with _CURATED_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                url = payload.get("url")
                if isinstance(url, str):
                    try:
                        value = float(payload.get("value_prior", 0.0))
                    except (TypeError, ValueError):
                        value = 0.0
                    seeds.append((value, url))
    except OSError:
        return []
    seeds.sort(reverse=True)
    return [url for _, url in seeds[:limit]]


def _schedule_crawl(query: str, *, use_llm: bool, model: Optional[str]) -> bool:
    if not _FOCUSED_SCRIPT.exists():
        LOGGER.warning("Focused crawl script missing at %s", _FOCUSED_SCRIPT)
        return False

    cmd = [sys.executable, str(_FOCUSED_SCRIPT), "--q", query]
    if use_llm:
        cmd.append("--use-llm")
        if model:
            cmd.extend(["--model", model])
    elif model:
        # Allow specifying a model even if the UI toggle is off for this request.
        cmd.extend(["--model", model])

    curated_urls = _load_curated_seeds(limit=8)
    for url in curated_urls:
        cmd.extend(["--extra-seed", url])

    for domain in get_top_domains(limit=5):
        cmd.extend(["--extra-seed", f"https://{domain}"])

    if _CURATED_PATH.exists():
        cmd.extend(["--curated-path", str(_CURATED_PATH)])

    try:
        subprocess.Popen(  # noqa: S603 - deliberate subprocess execution
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        LOGGER.info("Triggered focused crawl for query '%s' (use_llm=%s)", query, use_llm)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Failed to launch focused crawl for %s: %s", query, exc)
        return False


def smart_search(
    index,
    query: str,
    *,
    limit: int = 20,
    use_llm: Optional[bool] = None,
    model: Optional[str] = None,
) -> List[dict]:
    """Run a Whoosh query and optionally trigger a focused crawl."""

    results = basic_search(index, query, limit=limit)

    q = (query or "").strip()
    if not q:
        return results

    threshold = SMART_MIN_RESULTS
    if len(results) >= threshold:
        return results

    effective_use_llm = SMART_USE_LLM if use_llm is None else bool(use_llm)

    if not _should_trigger(q):
        return results

    if _schedule_crawl(q, use_llm=effective_use_llm, model=model):
        _mark_triggered(q)
        LOGGER.info("smart search triggered focused crawl for '%s' (llm=%s)", q, effective_use_llm)

    return results
