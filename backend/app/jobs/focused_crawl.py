"""Focused crawl orchestration pipeline executed via :mod:`JobRunner`."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence
from crawler.run import FocusedCrawler
from server.discover import DiscoveryEngine

from backend.app.db import AppStateDB
from backend.app.services.categorizer import deterministic_categories
from backend.app.services.progress_bus import ProgressBus

from ..config import AppConfig
from ..indexer.incremental import incremental_index
from ..pipeline.normalize import normalize
from .runner import JobRunner
from server.learned_web_db import LearnedWebDB, get_db
from backend.app.search.embedding import embed_query
from observability import start_span

LOGGER = logging.getLogger(__name__)

DEFAULT_DISCOVERY_DEPTH = 4

if TYPE_CHECKING:  # pragma: no cover - typing only
    from crawler.frontier import Candidate


def _document_key(url: str, content_hash: str) -> str:
    payload = f"{url}\u0001{content_hash}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()


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
    state_db: Optional[AppStateDB] = None,
    job_id: Optional[str] = None,
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

    pipeline_inputs = {
        "query": q,
        "budget": budget,
        "use_llm": use_llm,
        "manual_seed_count": len(manual_seeds or []),
    }

    with start_span(
        "focused_crawl.pipeline",
        attributes={"crawl.model": model or "", "crawl.budget": budget},
        inputs=pipeline_inputs,
    ) as pipeline_span:
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

        if pipeline_span is not None:
            pipeline_span.set_attribute("focused.seed_count", len(seeds))
            pipeline_span.set_attribute("focused.depth", depth_value)

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
        with start_span(
            "focused_crawl.crawl",
            attributes={"seed.count": len(seeds), "crawl.depth": depth_value},
            inputs={"budget": budget, "use_llm": use_llm},
        ) as crawl_span:
            raw_path, pages = _crawl(query, budget, use_llm, model, config, seeds)
            if crawl_span is not None:
                crawl_span.set_attribute("crawl.pages", len(pages))
        _emit("crawl_complete", pages_fetched=len(pages), raw_path=str(raw_path) if raw_path else None)
        print(f"[focused] crawl fetched {len(pages)} page(s)")
        if raw_path:
            print(f"[focused] raw capture written to {raw_path}")

        normalized_docs: List[Dict[str, object]] = []
        preview_samples: List[Dict[str, object]] = []
        if pages and raw_path:
            _emit("normalize_start", pages=len(pages))
            with start_span(
                "focused_crawl.normalize",
                attributes={"pages": len(pages)},
                inputs={"raw_path": str(raw_path)},
            ) as normalize_span:
                normalized_docs = normalize(
                    config.crawl_raw_dir,
                    config.normalized_path,
                    append=True,
                    sources=[raw_path],
                )
                if normalize_span is not None:
                    normalize_span.set_attribute("docs", len(normalized_docs))
            enriched_docs: List[Dict[str, object]] = []
            for doc in normalized_docs:
                url_value = str(doc.get("url") or "")
                body = str(doc.get("body") or "")
                categories, site = deterministic_categories(url_value, body)
                tokens = len(body.split()) if body else 0
                content_hash = str(doc.get("content_hash") or "")
                doc["site"] = site
                doc["categories"] = categories
                doc["tokens"] = tokens
                doc["verification"] = {"hash": content_hash, "sample": body[:200]}
                enriched_docs.append(doc)
            normalized_docs = enriched_docs
            preview_samples = [
                {
                    "url": doc.get("url"),
                    "title": doc.get("title"),
                    "site": doc.get("site"),
                    "categories": doc.get("categories"),
                    "hash": doc.get("content_hash"),
                }
                for doc in normalized_docs[:5]
            ]
            _emit("normalize_complete", docs=len(normalized_docs), preview=preview_samples)
            print(f"[focused] normalized {len(normalized_docs)} document(s)")
            _emit("index_start", docs=len(normalized_docs))
            with start_span(
                "focused_crawl.index",
                attributes={"docs": len(normalized_docs)},
            ) as index_span:
                added, skipped, deduped = incremental_index(
                    config.index_dir,
                    config.ledger_path,
                    config.simhash_path,
                    config.last_index_time_path,
                    normalized_docs,
                )
                if index_span is not None:
                    index_span.set_attribute("index.added", added)
                    index_span.set_attribute("index.skipped", skipped)
                    index_span.set_attribute("index.deduped", deduped)
            if state_db is not None and job_id:
                for doc in normalized_docs:
                    url_value = str(doc.get("url") or "")
                    content_hash = str(doc.get("content_hash") or "")
                    if not url_value:
                        continue
                    doc_key = _document_key(url_value, content_hash or url_value)
                    description = str(doc.get("h1h2") or doc.get("body", "")[:160])
                    fetched_at = doc.get("fetched_at")
                    try:
                        fetched_ts = float(fetched_at) if fetched_at is not None else time.time()
                    except (TypeError, ValueError):
                        fetched_ts = time.time()
                    state_db.upsert_document(
                        job_id=job_id,
                        document_id=doc_key,
                        url=url_value,
                        canonical_url=str(doc.get("canonical_url") or url_value),
                        site=str(doc.get("site") or "") or None,
                        title=str(doc.get("title") or "") or None,
                        description=description or None,
                        language=str(doc.get("lang") or "") or None,
                        fetched_at=fetched_ts,
                        normalized_path=str(config.normalized_path),
                        text_len=len(str(doc.get("body") or "")),
                        tokens=int(doc.get("tokens") or 0),
                        content_hash=content_hash or None,
                        categories=doc.get("categories") or [],
                        labels=[],
                        source="focused_crawl",
                        verification=doc.get("verification") or {},
                    )
            if learned_db is not None:
                try:
                    urls_to_mark = [
                        doc.get("url") for doc in normalized_docs if isinstance(doc.get("url"), str)
                    ]
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

        if pipeline_span is not None:
            pipeline_span.set_attribute("focused.pages", len(pages))
            pipeline_span.set_attribute("focused.docs", len(normalized_docs))
            pipeline_span.set_attribute("focused.added", added)
            pipeline_span.set_attribute(
                "focused.duration_ms", int((time.perf_counter() - start) * 1000)
            )

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
        "normalized_preview": preview_samples,
        "normalized_path": str(config.normalized_path),
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
    state_db: AppStateDB | None = None
    progress_bus: ProgressBus | None = None

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

            job_id_holder: Dict[str, str] = {}

            def _job() -> dict:
                job_ref = job_id_holder.get("id")
                state_db = self.state_db
                progress_bus = self.progress_bus

                if state_db is not None and job_ref:
                    state_db.update_crawl_status(job_ref, "running")

                def _progress(stage: str, payload: dict) -> None:
                    payload_dict = dict(payload or {})
                    stats_snapshot = None
                    if state_db is not None and job_ref:
                        stats_snapshot = state_db.record_crawl_event(job_ref, stage, payload_dict)
                    event = dict(payload_dict)
                    event["stage"] = stage
                    if job_ref:
                        event["job_id"] = job_ref
                    if stats_snapshot is not None:
                        event["stats"] = stats_snapshot
                    if progress_bus is not None and job_ref:
                        progress_bus.publish(job_ref, event)

                try:
                    result = run_focused_crawl(
                        q,
                        self.config.focused_budget,
                        use_llm,
                        model,
                        config=self.config,
                        extra_seeds=seeds,
                        query_embedding=query_embedding,
                        progress_callback=_progress,
                        db=self.db,
                        state_db=self.state_db,
                        job_id=job_ref,
                    )
                except TypeError as exc:
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    result = run_focused_crawl(
                        q,
                        self.config.focused_budget,
                        use_llm,
                        model,
                        config=self.config,
                        progress_callback=_progress,
                        db=self.db,
                        state_db=self.state_db,
                        job_id=job_ref,
                    )
                except Exception as exc:
                    if state_db is not None and job_ref:
                        state_db.update_crawl_status(job_ref, "error", error=str(exc))
                        state_db.record_crawl_event(job_ref, "error", {"error": str(exc)})
                    if progress_bus is not None and job_ref:
                        progress_bus.publish(
                            job_ref,
                            {"stage": "error", "job_id": job_ref, "error": str(exc)},
                        )
                    raise

                stats_payload = {
                    "pages_fetched": int(result.get("pages_fetched", 0) or 0),
                    "docs_indexed": int(result.get("docs_indexed", 0) or 0),
                    "skipped": int(result.get("skipped", 0) or 0),
                    "deduped": int(result.get("deduped", 0) or 0),
                    "embedded": int(result.get("embedded", 0) or 0),
                    "new_domains": int(result.get("new_domains", 0) or 0),
                }
                preview_payload = result.get("normalized_preview") or []
                normalized_path = result.get("normalized_path")
                if state_db is not None and job_ref:
                    state_db.update_crawl_status(
                        job_ref,
                        "success",
                        stats=stats_payload,
                        preview=preview_payload,
                        normalized_path=str(normalized_path) if normalized_path else None,
                    )
                    state_db.record_crawl_event(job_ref, "done", {"stats": stats_payload})
                if progress_bus is not None and job_ref:
                    progress_bus.publish(
                        job_ref,
                        {"stage": "done", "job_id": job_ref, "stats": stats_payload},
                    )
                return result

            job_id = self.runner.submit(_job)
            job_id_holder["id"] = job_id
            if self.state_db is not None:
                primary_seed = seed_urls[0] if seed_urls else None
                self.state_db.record_crawl_job(
                    job_id,
                    seed=primary_seed,
                    query=q,
                    normalized_path=str(self.config.normalized_path),
                )
            if self.progress_bus is not None:
                self.progress_bus.ensure_queue(job_id)
                self.progress_bus.publish(
                    job_id,
                    {
                        "stage": "queued",
                        "job_id": job_id,
                        "query": q,
                        "seeds": seed_urls,
                    },
                )
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
