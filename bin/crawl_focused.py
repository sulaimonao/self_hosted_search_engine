#!/usr/bin/env python3
"""Run a small, query-specific crawl to enrich the search index."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from search import frontier, seeds

try:  # Optional dependency: Ollama integration may be disabled.
    from llm.seed_guesser import guess_urls as llm_guess_urls
except Exception:  # pragma: no cover - defensive
    llm_guess_urls = None

LOGGER = logging.getLogger(__name__)

DEFAULT_BUDGET = int(os.getenv("FOCUSED_CRAWL_BUDGET", "50"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Focused crawl for a single query")
    parser.add_argument("--q", required=True, help="The search query driving the crawl")
    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET,
        help="Maximum number of pages to crawl (defaults to FOCUSED_CRAWL_BUDGET)",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Leverage a local Ollama model to suggest additional seed URLs",
    )
    parser.add_argument("--model", help="Explicit Ollama model name to use when guessing seeds")
    parser.add_argument(
        "--seeds-path",
        type=Path,
        default=seeds.DEFAULT_SEEDS_PATH,
        help="Seed JSONL store used to persist discovered domains",
    )
    return parser.parse_args()


def _llm_urls(query: str, model: str | None) -> List[str]:
    if llm_guess_urls is None:
        return []
    try:
        return llm_guess_urls(query, model=model)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.debug("LLM seed guessing failed: %s", exc)
        return []


def _write_seeds_file(candidates: List[frontier.Candidate]) -> Path:
    tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt")
    try:
        for candidate in candidates:
            tmp.write(candidate.url + "\n")
        tmp.flush()
    finally:
        tmp.close()
    return Path(tmp.name)


def _run_crawl(seed_file: Path, budget: int) -> int:
    crawl_script = Path(__file__).with_name("crawl.py")
    cmd = [sys.executable, str(crawl_script), "--seeds-file", str(seed_file), "--max-pages", str(budget)]
    result = subprocess.run(cmd, check=False)  # noqa: S603, S607 - deliberate subprocess execution
    if result.returncode != 0:
        LOGGER.warning("Focused crawl exited with status %s", result.returncode)
    return result.returncode


def _record_domains(candidates: List[frontier.Candidate], query: str, *, path: Path, use_llm: bool) -> None:
    scores: Dict[str, float] = {}
    for candidate in candidates:
        domain = seeds.domain_from_url(candidate.url)
        if not domain:
            continue
        scores[domain] = max(scores.get(domain, 0.0), candidate.weight)

    reason = "focused-crawl-llm" if use_llm else "focused-crawl"
    seeds.record_domains(scores, query=query, reason=reason, path=path)


def main() -> None:
    args = parse_args()

    query = args.q.strip()
    if not query:
        LOGGER.info("Empty query provided; nothing to crawl")
        return

    budget = max(1, int(args.budget))
    top_domains = seeds.get_top_domains(limit=budget, path=args.seeds_path)

    extra_urls: List[str] = []
    if args.use_llm:
        extra_urls = _llm_urls(query, args.model)
        if extra_urls:
            LOGGER.info("LLM proposed %d candidate URL(s)", len(extra_urls))

    candidates = frontier.build_frontier(
        query,
        seed_domains=top_domains,
        extra_urls=extra_urls,
        budget=budget,
    )

    if not candidates:
        LOGGER.info("No candidates generated for query '%s'", query)
        return

    LOGGER.info("Running focused crawl for '%s' with %d candidates", query, len(candidates))
    seed_file = _write_seeds_file(candidates)

    try:
        _run_crawl(seed_file, budget)
    finally:
        try:
            seed_file.unlink()
        except FileNotFoundError:
            pass

    _record_domains(candidates, query, path=args.seeds_path, use_llm=args.use_llm)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    main()
