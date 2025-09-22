"""Focused crawl orchestration pipeline executed via :mod:`JobRunner`."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence
from urllib.parse import urlparse

from crawler.frontier import Candidate, build_frontier
from crawler.run import FocusedCrawler
from search.seeds import DEFAULT_SEEDS_PATH, get_top_domains

from ..config import AppConfig
from ..indexer.incremental import incremental_index
from ..pipeline.normalize import normalize
from .runner import JobRunner
from server.learned_web_db import LearnedWebDB, get_db

LOGGER = logging.getLogger(__name__)


def run_focused_crawl(
    query: str,
    budget: int,
    use_llm: bool,
    model: Optional[str],
    *,
    config: AppConfig,
    extra_seeds: Optional[Sequence[str]] = None,
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
    _emit("frontier_start", query=query)
    seeds = _get_seed_candidates(query, budget, use_llm, model, config, extra_seeds=extra_seeds)
    _emit("frontier_complete", seed_count=len(seeds))
    print(f"[focused] query='{query}' budget={budget} seeds={len(seeds)}")
    for candidate in seeds[:10]:
        print(f"[focused] seed -> {candidate.url} ({candidate.source})")

    crawl_id: Optional[int] = None
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
                    learned_db.record_discovery(
                        q,
                        candidate.url,
                        reason="frontier",
                        score=float(candidate.priority),
                        source=candidate.source,
                        discovered_at=start_ts,
                        crawl_id=crawl_id,
                    )
                except Exception:  # pragma: no cover - logging only
                    LOGGER.debug("failed to persist frontier discovery for %s", candidate.url, exc_info=True)
        except Exception:  # pragma: no cover - logging only
            LOGGER.exception("failed to record crawl bootstrap", exc_info=True)

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
            _emit("frontier_empty")
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
    }
    print(f"[focused] completed in {duration:.2f}s -> indexed={added} skipped={skipped} deduped={deduped}")
    return stats


def _load_curated_values(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    if not path.exists():
        return values
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                url = payload.get("url")
                if not isinstance(url, str):
                    continue
                domain = urlparse(url).netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                try:
                    score = float(payload.get("value_prior", 0.0))
                except (TypeError, ValueError):
                    score = 0.0
                values[domain] = max(values.get(domain, 0.0), score)
    except OSError:
        return values
    return values


def _get_seed_candidates(
    query: str,
    budget: int,
    use_llm: bool,
    model: Optional[str],
    config: AppConfig,
    *,
    extra_seeds: Optional[Sequence[str]] = None,
) -> List[Candidate]:
    q = (query or "").strip()
    if not q:
        return []
    try:
        seed_domains = get_top_domains(limit=25)
    except Exception:  # pragma: no cover - defensive
        seed_domains = []
    value_overrides: dict[str, float] = {}
    data_root = Path(os.getenv("DATA_DIR", "data"))
    value_overrides.update(_load_curated_values(data_root / "seeds" / "curated_seeds.jsonl"))
    try:
        with DEFAULT_SEEDS_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                domain = (payload.get("domain") or "").strip().lower()
                if not domain:
                    continue
                try:
                    score = float(payload.get("score", 0.0))
                except (TypeError, ValueError):
                    score = 0.0
                value_overrides[domain] = max(value_overrides.get(domain, 0.0), score)
    except OSError:
        pass
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

    candidates = build_frontier(
        q,
        extra_urls=merged_extra,
        seed_domains=seed_domains,
        budget=max(budget * 4, 40),
        value_overrides=value_overrides,
    )
    if not candidates:
        fallback = [
            f"https://{q.replace(' ', '')}.com",
            f"https://{q.replace(' ', '')}.io",
        ]
        candidates = [Candidate(url=url, source="fallback", weight=0.1) for url in fallback]
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

    def schedule(self, query: str, use_llm: bool, model: Optional[str]) -> Optional[str]:
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

            def _job() -> dict:
                try:
                    return run_focused_crawl(
                        q,
                        self.config.focused_budget,
                        use_llm,
                        model,
                        config=self.config,
                        db=self.db,
                    )
                except TypeError as exc:
                    if "unexpected keyword argument 'db'" not in str(exc):
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
