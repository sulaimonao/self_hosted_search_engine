"""Deep research API wiring requests into background jobs."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..config import AppConfig
from ..db import AppStateDB
from ..jobs.research import run_research
from ..jobs.focused_crawl import run_focused_crawl
from ..jobs.runner import JobRunner
from ..services.vector_index import VectorIndexService

bp = Blueprint("research_api", __name__, url_prefix="/api")


@bp.post("/research")
def research_endpoint():
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    model = (payload.get("model") or "").strip() or None

    budget_raw = payload.get("budget")
    budget = 20
    if budget_raw not in (None, ""):
        try:
            if isinstance(budget_raw, str):
                trimmed = budget_raw.strip()
                if trimmed:
                    budget = int(trimmed)
            else:
                budget = int(budget_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_budget"}), 400

    if not query:
        return jsonify({"error": "query is required"}), 400

    budget = max(1, min(100, budget))

    config: AppConfig = current_app.config["APP_CONFIG"]
    runner: JobRunner = current_app.config["JOB_RUNNER"]

    def _job():
        return run_research(query, model, budget, config=config)

    job_id = runner.submit(_job)
    return jsonify({"job_id": job_id})


def _coerce_urls(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        urls: list[str] = []
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                urls.append(entry.strip())
        return urls
    return []


@bp.post("/research/page")
def research_page():
    """Kick off a targeted crawl/index job for one or more URLs."""

    payload = request.get_json(silent=True) or {}
    url_values = _coerce_urls(payload.get("urls"))
    single_url = (payload.get("url") or "").strip()
    if single_url:
        url_values.append(single_url)
    seen_urls: set[str] = set()
    urls: list[str] = []
    for url in url_values:
        if url and url not in seen_urls:
            seen_urls.add(url)
            urls.append(url)
    if not urls:
        return jsonify({"error": "url_required"}), 400

    title = (payload.get("title") or "").strip()
    source = (payload.get("source") or "research_button").strip() or "research_button"
    budget_raw = payload.get("budget")
    try:
        budget = int(budget_raw) if budget_raw not in (None, "") else max(1, len(urls))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_budget"}), 400
    budget = max(1, min(50, budget))

    config: AppConfig = current_app.config["APP_CONFIG"]
    runner: JobRunner = current_app.config["JOB_RUNNER"]
    state_db: AppStateDB | None = current_app.config.get("APP_STATE_DB")
    vector_index: VectorIndexService | None = current_app.config.get("VECTOR_INDEX_SERVICE")

    job_ref: dict[str, str] = {}

    def _progress(stage: str, payload: dict) -> None:
        if state_db is None:
            return
        job_id = job_ref.get("id")
        if not job_id:
            return
        try:
            snapshot = state_db.record_crawl_event(job_id, stage, payload or {})
            state_db.upsert_job_status(
                job_id,
                url=payload.get("url") if isinstance(payload, dict) else None,
                phase=stage,
                steps_total=int(payload.get("steps_total") or 5) if isinstance(payload, dict) else 5,
                steps_completed=int(payload.get("steps_completed") or 0) if isinstance(payload, dict) else 0,
                retries=int(payload.get("retries") or 0) if isinstance(payload, dict) else 0,
                eta_seconds=payload.get("eta_seconds") if isinstance(payload, dict) else None,
                message=payload.get("message") if isinstance(payload, dict) else None,
            )
            if snapshot:
                state_db.record_crawl_event(job_id, "stats", snapshot)
        except Exception:  # pragma: no cover - defensive
            current_app.logger.debug("failed to record research progress", exc_info=True)

    def _job():
        job_id = job_ref.get("id")
        if state_db and job_id:
            state_db.update_crawl_status(job_id, "running")
        result = run_focused_crawl(
            title or urls[0],
            budget,
            use_llm=False,
            model=None,
            config=config,
            manual_seeds=urls,
            frontier_depth=1,
            query_embedding=None,
            progress_callback=_progress,
            state_db=state_db,
            job_id=job_id,
        )
        docs = result.get("normalized_docs") or []
        if vector_index is not None:
            for doc in docs:
                text = str(doc.get("body") or "").strip()
                if not text:
                    continue
                try:
                    vector_index.upsert_document(
                        text=text,
                        url=str(doc.get("url") or ""),
                        title=str(doc.get("title") or ""),
                        metadata={
                            "source": source,
                            "domain": doc.get("site"),
                            "temp": False,
                        },
                    )
                except Exception:  # pragma: no cover - defensive
                    current_app.logger.debug("vector index upsert failed", exc_info=True)
        stats_payload = {
            "pages_fetched": int(result.get("pages_fetched", 0) or 0),
            "docs_indexed": int(result.get("docs_indexed", 0) or 0),
            "skipped": int(result.get("skipped", 0) or 0),
            "deduped": int(result.get("deduped", 0) or 0),
        }
        if state_db and job_id:
            state_db.update_crawl_status(
                job_id,
                "success",
                stats=stats_payload,
                normalized_path=str(result.get("normalized_path") or config.normalized_path),
                preview=result.get("normalized_preview") or [],
            )
        return {"stats": stats_payload, "normalized_path": result.get("normalized_path")}

    job_id = runner.submit(_job)
    job_ref["id"] = job_id
    if state_db is not None:
        state_db.record_crawl_job(
            job_id,
            seed=urls[0],
            query=title or urls[0],
            normalized_path=str(config.normalized_path),
            reason=source,
            parent_url=None,
            is_source=bool(len(urls) > 1),
        )
    return jsonify({"job_id": job_id, "status": "queued", "urls": urls}), 202
