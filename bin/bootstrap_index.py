#!/usr/bin/env python3
"""Bootstrap the vector index using configured cold-start queries."""

from __future__ import annotations

import logging
import os
import sys
from typing import Iterable


def _as_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _iter_queries(raw: Iterable[str]) -> Iterable[str]:
    for item in raw:
        text = (item or "").strip()
        if text:
            yield text


def main() -> int:
    os.environ.setdefault("CHROMADB_DISABLE_TELEMETRY", "1")

    try:
        from app import ENGINE_CONFIG, coldstart, embed_manager, embedder
    except Exception as exc:  # pragma: no cover - import failure should be obvious
        print(f"Failed to import application modules: {exc}", file=sys.stderr)
        return 2

    logger = logging.getLogger("bootstrap_index")
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    env_query = (os.getenv("Q") or "").strip()
    use_llm_env = os.getenv("USE_LLM")
    llm_model_env = (os.getenv("MODEL") or os.getenv("LLM_MODEL") or "").strip() or None

    bootstrap_cfg = ENGINE_CONFIG.bootstrap

    if env_query:
        queries = [env_query]
        use_llm = _as_bool(use_llm_env)
        llm_model = llm_model_env or (bootstrap_cfg.llm_model if bootstrap_cfg else None)
    elif bootstrap_cfg and bootstrap_cfg.queries:
        queries = list(bootstrap_cfg.queries)
        use_llm = _as_bool(use_llm_env) if use_llm_env is not None else bootstrap_cfg.use_llm
        llm_model = llm_model_env or bootstrap_cfg.llm_model
    else:
        print(
            "No bootstrap queries configured. Provide Q=\"your query\" to index manually.",
            file=sys.stderr,
        )
        return 0

    if not queries:
        print("No queries available for indexing; exiting.", file=sys.stderr)
        return 0

    logger.info("Preparing embedding model for bootstrap (model=%s)", llm_model or embedder.model)
    try:
        status = embed_manager.ensure(llm_model)
    except Exception as exc:  # pragma: no cover - network/ollama issues
        logger.error("Failed to ensure embedding model: %s", exc)
        return 1

    if status.get("state") != "ready":
        detail = status.get("detail") or status.get("error") or "embedding model unavailable"
        logger.warning("Embedding model not ready; skipping bootstrap (%s)", detail)
        return 0

    active_model = status.get("model") or embed_manager.active_model
    if active_model:
        embedder.set_model(str(active_model))
        logger.info("Using embedding model '%s'", active_model)

    total_indexed = 0
    for query in _iter_queries(queries):
        try:
            count = coldstart.build_index(query, use_llm=use_llm, llm_model=llm_model)
        except Exception as exc:  # pragma: no cover - crawling is inherently flaky
            logger.error("Failed to index query '%s': %s", query, exc)
            continue
        logger.info("Indexed %d pages for query: %s", count, query)
        total_indexed += count

    logger.info("Bootstrap complete. Total pages indexed: %d", total_indexed)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution script
    sys.exit(main())
