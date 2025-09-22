"""Focused crawl orchestration pipeline executed via :mod:`JobRunner`."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence
from crawler.run import FocusedCrawler
from server.discover import DiscoveryEngine

from ..config import AppConfig
from ..indexer.incremental import incremental_index
from ..pipeline.normalize import normalize
from .runner import JobRunner
from server.learned_web_db import LearnedWebDB, get_db
from backend.app.search.embedding import embed_query

LOGGER = logging.getLogger(__name__)

DEFAULT_DISCOVERY_DEPTH = 4

if TYPE_CHECKING:  # pragma: no cover - typing only
    from crawler.frontier import Candidate


def run_focused_crawl(
    query: str,
    budget: int,
    use_llm: bool,
    model: Optional[str],
    *,
    config: AppConfig,
    extra_seeds: Optional[Sequence[str]] = None,
    manual_seeds: Optional[Sequence[str]] = None,
    frontier_depth: Optional[int] = None,
    query_embedding: Optional[Sequence[float]] = None,
    progress_callback: Optional[Callable[[str, dict], None]] = None,
    db: Optional[LearnedWebDB] = None,
) -> dict:
    """Execute the full focused crawl pipeline and return summary statistics."""

    def _emit(stage: str, **payload: object) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(stage, dict(payload))
        except Exception:  # pragma: no cover - defensive logging only
            LOGGER.exception("focused crawl progress callback failed", exc_info=True)

    start = time.perf_counter()
    start_ts = time.time()
    config.ensure_dirs()
    learned_db: Optional[LearnedWebDB]
    try:
        learned_db = db or get_db(config.learned_web_db_path)
    except Exception:  # pragma: no cover - defensive fallback
        LOGGER.exception("unable to open learned web database", exc_info=True)
        learned_db = None
    q = (query or "").strip()
    depth_value = frontier_depth if frontier_depth and frontier_depth > 0 else DEFAULT_DISCOVERY_DEPTH
    embedded_count = 0
    if q and learned_db is not None:
        try:
            vector = query_embedding or embed_query(q)
            learned_db.upsert_query_embedding(q, vector)
            embedded_count = 1 if vector else 0
        except Exception:  # pragma: no cover - logging only
            LOGGER.debug("failed to persist query embedding for '%s'", q, exc_info=True)
    discovery_mode = "manual" if manual_seeds else "discovery"
    manual_candidates = _build_manual_candidates(manual_seeds) if manual_seeds else []
    _emit("frontier_start", query=query, mode=discovery_mode, depth=depth_value, budget=budget)
    if manual_candidates:
        seeds = manual_candidates
    else:
        seeds = _get_seed_candidates(
            query,
            budget,
            use_llm,
            model,
            config,
            extra_seeds=extra_seeds,
            depth=depth_value,
        )

    seed_urls: List[str] = []
    source_counts: Dict[str, int] = {}
    for candidate in seeds:
        seed_urls.append(candidate.url)
        source = candidate.source or ("manual" if manual_candidates else "frontier")
        source_counts[source] = source_counts.get(source, 0) + 1

    print(
        f"[focused] query='{query}' budget={budget} depth={depth_value} mode={discovery_mode} seeds={len(seeds)}"
    )
    for candidate in seeds[:10]:
        print(f"[focused] seed -> {candidate.url} ({candidate.source})")

    crawl_id: Optional[int] = None
    new_domains = 0
    if learned_db is not None:
        try:
            crawl_id = learned_db.start_crawl(
                query=q,
                started_at=start_ts,
                budget=budget,
                seed_count=len(seeds),
                use_llm=use_llm,
                model=model,
            )
            for candidate in seeds:
                try:
                    record = learned_db.record_discovery(
                        q,
                        candidate.url,
                        reason="manual" if discovery_mode == "manual" else "frontier",
                        score=float(candidate.priority),
                        source=candidate.source,
                        discovered_at=start_ts,
                        crawl_id=crawl_id,
                    )
                    if record and record[1]:
                        new_domains += 1
                except Exception:  # pragma: no cover - logging only
                    LOGGER.debug("failed to persist frontier discovery for %s", candidate.url, exc_info=True)
        except Exception:  # pragma: no cover - logging only
            LOGGER.exception("failed to record crawl bootstrap", exc_info=True)

    _emit(
        "frontier_complete",
        seed_count=len(seeds),
        mode=discovery_mode,
        seeds=seed_urls,
        sources=source_counts,
        new_domains=new_domains,
        embedded=embedded_count,
        depth=depth_value,
        budget=budget,
    )

    _emit("crawl_start", seed_count=len(seeds))
    raw_path, pages = _crawl(query, budget, use_llm, model, config, seeds)
    _emit("crawl_complete", pages_fetched=len(pages), raw_path=str(raw_path) if raw_path else None)
    print(f"[focused] crawl fetched {len(pages)} page(s)")
    if raw_path:
        print(f"[focused] raw capture written to {raw_path}")

    normalized_docs = []
    if pages and raw_path:
        _emit("normalize_start", pages=len(pages))
        normalized_docs = normalize(
            config.crawl_raw_dir,
            config.normalized_path,
            append=True,
            sources=[raw_path],
        )
        _emit("normalize_complete", docs=len(normalized_docs))
        print(f"[focused] normalized {len(normalized_docs)} document(s)")
        _emit("index_start", docs=len(normalized_docs))
        added, skipped, deduped = incremental_index(
            config.index_dir,
            config.ledger_path,
            config.simhash_path,
            config.last_index_time_path,
            normalized_docs,
        )
        if learned_db is not None:
            try:
                urls_to_mark = [doc.get("url") for doc in normalized_docs if isinstance(doc.get("url"), str)]
                learned_db.mark_pages_indexed(urls_to_mark, indexed_at=time.time())
            except Exception:  # pragma: no cover - logging only
                LOGGER.debug("failed to mark pages indexed", exc_info=True)
        _emit(
            "index_complete",
            docs_indexed=added,
            skipped=skipped,
            deduped=deduped,
        )
    else:
        added = skipped = deduped = 0
        if not seeds:
            _emit("frontier_empty", mode=discovery_mode)
        else:
            _emit("index_skipped", reason="no_new_documents")

    if learned_db is not None:
        try:
            for page in pages:
                try:
                    simhash = getattr(page.fingerprint, "simhash", None)
                    md5 = getattr(page.fingerprint, "md5", None)
                    page_id = learned_db.record_page(
                        crawl_id,
                        url=page.url,
                        status=page.status,
                        title=page.title,
                        fetched_at=page.fetched_at,
                        fingerprint_simhash=simhash,
                        fingerprint_md5=md5,
                    )
                    if page_id:
                        learned_db.record_links(
                            page_id,
                            page.outlinks,
                            discovered_at=page.fetched_at,
                            crawl_id=crawl_id,
                        )
                except Exception:  # pragma: no cover - logging only
                    LOGGER.debug("failed to persist page %s", getattr(page, "url", "<unknown>"), exc_info=True)
            if crawl_id is not None:
                learned_db.complete_crawl(
                    crawl_id,
                    completed_at=time.time(),
                    pages_fetched=len(pages),
                    docs_indexed=added,
                    raw_path=str(raw_path) if raw_path else None,
                )
        except Exception:  # pragma: no cover - logging only
            LOGGER.exception("failed to persist crawl summary", exc_info=True)

    duration = time.perf_counter() - start
    stats = {
        "query": query,
        "pages_fetched": len(pages),
        "docs_indexed": added,
        "skipped": skipped,
        "deduped": deduped,
        "duration": duration,
        "normalized_docs": normalized_docs,
        "raw_path": str(raw_path) if raw_path else None,
        "crawl_id": crawl_id,
        "embedded": embedded_count,
        "new_domains": new_domains,
        "discovery": {
            "mode": discovery_mode,
            "seed_count": len(seeds),
            "sources": source_counts,
            "seeds": seed_urls,
            "budget": budget,
            "depth": depth_value,
        },
        "frontier_depth": depth_value,
    }
    print(f"[focused] completed in {duration:.2f}s -> indexed={added} skipped={skipped} deduped={deduped}")
    return stats


def _get_seed_candidates(
    query: str,
    budget: int,
    use_llm: bool,
    model: Optional[str],
    config: AppConfig,
    *,
    extra_seeds: Optional[Sequence[str]] = None,
    depth: Optional[int] = None,
) -> List[Candidate]:
    from crawler.frontier import Candidate

    q = (query or "").strip()
    if not q:
        return []
    llm_urls: List[str] = []
    if use_llm:
        try:
            from llm.seed_guesser import guess_urls

            llm_urls = guess_urls(q, model=model)
        except Exception as exc:  # pragma: no cover - log in job output
            print(f"[focused] LLM seed expansion failed: {exc}")
    merged_extra: List[str] = []
    for source in (extra_seeds or []):
        if source:
            merged_extra.append(source)
    merged_extra.extend(llm_urls)

    engine = DiscoveryEngine()
    depth_value = depth if depth and depth > 0 else DEFAULT_DISCOVERY_DEPTH
    limit = max(budget * depth_value, budget, 40)
    candidates = engine.discover(
        q,
        limit=limit,
        extra_seeds=merged_extra,
        use_llm=use_llm,
        model=model,
    )
    if not candidates:
        candidates = engine.registry_frontier(
            q,
            limit=limit,
            use_llm=use_llm,
            model=model,
        )
    if not candidates:
        fallback = [
            f"https://{q.replace(' ', '')}.com",
            f"https://{q.replace(' ', '')}.io",
        ]
        candidates = [
            Candidate(url=url, source="fallback", weight=0.1, score=0.1) for url in fallback
        ]
    return candidates


def _build_manual_candidates(seed_urls: Optional[Sequence[str]]) -> List[Candidate]:
    from crawler.frontier import Candidate

    if not seed_urls:
        return []
    candidates: List[Candidate] = []
    seen: set[str] = set()
    for raw in seed_urls:
        if not isinstance(raw, str):
            continue
        candidate = raw.strip()
        if not candidate:
            continue
        if not candidate.startswith(("http://", "https://")):
            candidate = "https://" + candidate.lstrip("/")
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(Candidate(url=candidate, source="manual", weight=1.0, score=1.0))
    return candidates


def _crawl(
    query: str,
    budget: int,
    use_llm: bool,
    model: Optional[str],
    config: AppConfig,
    seeds: Sequence[Candidate],
) -> tuple[Optional[Path], Sequence[object]]:
    if not seeds:
        return None, []

    async def _run() -> FocusedCrawler:
        crawler = FocusedCrawler(
            query=query,
            budget=budget,
            out_dir=config.crawl_raw_dir,
            use_llm=use_llm,
            model=model,
            initial_seeds=seeds,
        )
        await crawler.run()
        return crawler

    crawler = asyncio.run(_run())
    return crawler.last_output_path, list(crawler.results)


@dataclass
class FocusedCrawlManager:
    config: AppConfig
    runner: JobRunner
    db: LearnedWebDB

    def __post_init__(self) -> None:
        import threading

        self._lock = threading.Lock()
        self._history_path = self.config.crawl_raw_dir / "focused_history.json"
        self._history = self._load_history()

    def _load_history(self) -> dict[str, float]:
        if not self._history_path.exists():
            return {}
        try:
            data = json.loads(self._history_path.read_text("utf-8"))
        except Exception:
            return {}
        return {str(k): float(v) for k, v in data.items()}

    def _persist_history(self) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._history_path.write_text(json.dumps(self._history, indent=2, sort_keys=True), encoding="utf-8")

    def schedule(
        self,
        query: str,
        use_llm: bool,
        model: Optional[str],
        *,
        frontier_seeds: Optional[Sequence[str]] = None,
        query_embedding: Optional[Sequence[float]] = None,
    ) -> Optional[str]:
        q = (query or "").strip()
        if not q:
            return None
        if not self.config.focused_enabled:
            return None

        with self._lock:
            now = time.time()
            cooldown = self.config.smart_trigger_cooldown
            if cooldown > 0:
                last = self._history.get(q)
                if last and (now - last) < cooldown:
                    return None

            if query_embedding is not None:
                try:
                    self.db.upsert_query_embedding(q, query_embedding)
                except Exception:  # pragma: no cover - logging only
                    LOGGER.debug("failed to persist scheduled embedding for '%s'", q, exc_info=True)

            seeds: Optional[list[str]] = None
            if frontier_seeds:
                unique: list[str] = []
                for url in frontier_seeds:
                    if isinstance(url, str):
                        cleaned = url.strip()
                        if cleaned and cleaned not in unique:
                            unique.append(cleaned)
                if unique:
                    seeds = unique

            def _job() -> dict:
                try:
                    return run_focused_crawl(
                        q,
                        self.config.focused_budget,
                        use_llm,
                        model,
                        config=self.config,
                        extra_seeds=seeds,
                        query_embedding=query_embedding,
                        db=self.db,
                    )
                except TypeError as exc:
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    return run_focused_crawl(
                        q,
                        self.config.focused_budget,
                        use_llm,
                        model,
                        config=self.config,
                    )

            job_id = self.runner.submit(_job)
            self._history[q] = now
            self._persist_history()
        LOGGER.info("scheduled focused crawl for '%s' as job %s", q, job_id)
        return job_id

    def last_index_time(self) -> int:
        path = self.config.last_index_time_path
        if not path.exists():
            return 0
        try:
            return int(path.read_text("utf-8").strip() or 0)
        except Exception:
            return 0
