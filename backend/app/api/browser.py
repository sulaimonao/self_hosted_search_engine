"""Browser-centric REST API: history, bookmarks, seeds, shadow, and graph."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, request

import time

from backend.app.db import AppStateDB

from .utils import coerce_chat_identifier
from ..services.agent_tracing import publish_agent_step
from ..services.fallbacks import smart_fetch

_ALLOWED_SHADOW_MODES = {"off", "visited_only", "visited_outbound"}

bp = Blueprint("browser", __name__, url_prefix="/api/browser")


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):
        abort(500, "app state database unavailable")
    return state_db


# ---------------------------------------------------------------------------
# History endpoints
# ---------------------------------------------------------------------------


def _parse_iso_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@bp.get("/history")
def get_history():
    state_db = _state_db()
    limit = request.args.get("limit", type=int) or 200
    query = request.args.get("query")
    start = _parse_iso_ts(request.args.get("from"))
    end = _parse_iso_ts(request.args.get("to"))
    items = state_db.query_history(limit=limit, query=query, start=start, end=end)
    return jsonify({"items": items})


@bp.post("/history")
def post_history():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    started_at = time.time()
    chat_id = coerce_chat_identifier(request.headers.get("X-Chat-Id"))
    message_id = coerce_chat_identifier(request.headers.get("X-Message-Id"))
    tab_id = str(payload.get("tab_id") or "").strip() or None
    url = str(payload.get("url") or "").strip()
    if not url:
        publish_agent_step(
            tool="browser.history",
            chat_id=chat_id,
            message_id=message_id,
            args={"tab_id": tab_id},
            status="error",
            started_at=started_at,
            ended_at=time.time(),
            excerpt="url is required",
        )
        abort(400, "url is required")
    title = payload.get("title")
    referrer = payload.get("referrer")
    status_code = payload.get("status_code")
    content_type = payload.get("content_type")
    history_id = state_db.add_history_entry(
        tab_id=tab_id,
        url=url,
        title=title,
        referrer=referrer,
        status_code=int(status_code) if status_code is not None else None,
        content_type=content_type,
    )
    mode = state_db.effective_shadow_mode(tab_id)
    enqueued = False
    job_id: str | None = None
    if mode != "off":
        priority = 10 if mode == "visited_only" else 8
        job_id = state_db.enqueue_crawl_job(url, priority=priority, reason="visited")
        state_db.mark_history_shadow_enqueued(history_id)
        enqueued = True
    response = {
        "id": history_id,
        "shadow_enqueued": enqueued,
        "shadow_job_id": job_id,
        "mode": mode,
    }
    publish_agent_step(
        tool="browser.history",
        chat_id=chat_id,
        message_id=message_id,
        args={"url": url, "tab_id": tab_id, "shadow": bool(mode != "off")},
        status="ok",
        started_at=started_at,
        ended_at=time.time(),
        excerpt=title or url,
    )
    return jsonify(response), 201


@bp.get("/fallback")
def get_fallback():
    url = request.args.get("url")
    if not url:
        abort(400, "url query parameter is required")
    query = request.args.get("query") or request.args.get("q")
    result = smart_fetch(url, query=query)
    return jsonify(result)


@bp.delete("/history/<int:history_id>")
def delete_history(history_id: int):
    state_db = _state_db()
    state_db.delete_history_entry(history_id)
    return jsonify({"deleted": history_id})


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------


@bp.get("/bookmarks")
def get_bookmarks():
    state_db = _state_db()
    folder_id = request.args.get("folder_id", type=int)
    bookmarks = state_db.list_bookmarks(folder_id)
    folders = state_db.list_bookmark_folders()
    return jsonify({"folders": folders, "bookmarks": bookmarks})


@bp.post("/bookmarks")
def post_bookmark():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    url = str(payload.get("url") or "").strip()
    if not url:
        abort(400, "url is required")
    title = payload.get("title")
    folder_id = payload.get("folder_id")
    tags = payload.get("tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = [token.strip() for token in tags.split(",") if token.strip()]
    bookmark_id = state_db.add_bookmark(
        url=url,
        title=title,
        folder_id=int(folder_id) if folder_id is not None else None,
        tags=tags if isinstance(tags, (list, tuple, set)) else None,
    )
    return jsonify({"id": bookmark_id}), 201


@bp.post("/bookmark-folders")
def post_bookmark_folder():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        abort(400, "name is required")
    parent_id = payload.get("parent_id")
    folder_id = state_db.create_bookmark_folder(
        name, parent_id=int(parent_id) if parent_id is not None else None
    )
    return jsonify({"id": folder_id}), 201


# ---------------------------------------------------------------------------
# Seed sources and suggestions
# ---------------------------------------------------------------------------


_SUGGESTED_SITES: dict[str, list[tuple[str, str]]] = {
    "news": [
        ("https://www.reuters.com", "Reuters"),
        ("https://www.apnews.com", "Associated Press"),
        ("https://www.bbc.com/news", "BBC News"),
        ("https://www.aljazeera.com", "Al Jazeera"),
        ("https://www.economist.com", "The Economist"),
    ],
    "music": [
        ("https://pitchfork.com", "Pitchfork"),
        ("https://www.npr.org/music", "NPR Music"),
        ("https://www.billboard.com", "Billboard"),
        ("https://www.rollingstone.com/music", "Rolling Stone"),
    ],
    "entertainment": [
        ("https://www.variety.com", "Variety"),
        ("https://www.hollywoodreporter.com", "Hollywood Reporter"),
        ("https://www.vulture.com", "Vulture"),
        ("https://www.ign.com", "IGN"),
    ],
    "art": [
        ("https://www.artnews.com", "ARTnews"),
        ("https://hyperallergic.com", "Hyperallergic"),
        ("https://www.artforum.com", "Artforum"),
    ],
    "tech": [
        ("https://www.theverge.com", "The Verge"),
        ("https://www.techcrunch.com", "TechCrunch"),
        ("https://www.wired.com", "WIRED"),
        ("https://www.semianalysis.com", "SemiAnalysis"),
        ("https://www.anandtech.com", "AnandTech"),
    ],
}


@bp.get("/seeds")
def get_seeds():
    state_db = _state_db()
    categories = state_db.list_source_categories()
    seeds = state_db.list_seed_sources()
    return jsonify({"categories": categories, "seeds": seeds})


@bp.post("/seeds/suggest")
def post_seed_suggest():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    category_key = str(payload.get("category_key") or "").strip()
    user_sites = payload.get("user_sites") or []
    if not category_key:
        abort(400, "category_key required")
    existing = {
        seed["url"]
        for seed in state_db.list_seed_sources()
        if seed["category_key"] == category_key
    }
    provided = {str(url).strip() for url in user_sites if str(url).strip()}
    baseline = _SUGGESTED_SITES.get(category_key, [])
    suggestions: list[dict[str, Any]] = []
    for url, title in baseline:
        if url in existing or url in provided:
            continue
        suggestions.append(
            {
                "url": url,
                "title": title,
                "category_key": category_key,
                "added_by": "llm",
            }
        )
        if len(suggestions) >= 10:
            break
    return jsonify({"suggestions": suggestions})


@bp.post("/seeds/bulk-upsert")
def post_seed_bulk_upsert():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    seeds = payload.get("seeds")
    if not isinstance(seeds, list):
        abort(400, "seeds must be a list")
    prepared: list[dict[str, Any]] = []
    for entry in seeds:
        if not isinstance(entry, dict):
            continue
        category_key = str(entry.get("category_key") or "").strip()
        url = str(entry.get("url") or "").strip()
        if not category_key or not url:
            continue
        prepared.append(
            {
                "category_key": category_key,
                "url": url,
                "title": entry.get("title"),
                "added_by": entry.get("added_by") or "user",
                "enabled": 1 if entry.get("enabled", True) else 0,
            }
        )
    count = state_db.bulk_upsert_seed_sources(prepared)
    return jsonify({"upserted": count})


# ---------------------------------------------------------------------------
# Crawl queue & shadow controls
# ---------------------------------------------------------------------------


@bp.post("/crawl/enqueue")
def post_crawl_enqueue():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    url = str(payload.get("url") or "").strip()
    if not url:
        abort(400, "url required")
    priority = int(payload.get("priority") or 0)
    reason = payload.get("reason")
    job_id = state_db.enqueue_crawl_job(url, priority=priority, reason=reason)
    return jsonify({"job_id": job_id}), 202


@bp.post("/crawl/enqueue-seeds")
def post_crawl_enqueue_seeds():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    category_keys = payload.get("category_keys") or []
    if not isinstance(category_keys, list):
        abort(400, "category_keys must be a list")
    priority = int(payload.get("priority") or 0)
    job_ids = state_db.enqueue_seed_jobs(
        [str(key) for key in category_keys], priority=priority
    )
    return jsonify({"job_ids": job_ids})


@bp.get("/crawl/status")
def get_crawl_status():
    state_db = _state_db()
    job_id = request.args.get("id")
    if job_id:
        status = state_db.crawl_job_status(job_id)
        if not status:
            abort(404, "job not found")
        return jsonify(status)
    overview = state_db.crawl_overview()
    return jsonify(overview)


@bp.post("/shadow/toggle")
def post_shadow_toggle():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    mode = str(payload.get("mode") or "off").strip() or "off"
    if mode not in _ALLOWED_SHADOW_MODES:
        abort(400, "invalid mode")
    enabled = bool(payload.get("enabled"))
    tab_id = payload.get("tab_id")
    response: dict[str, Any] = {}
    if tab_id:
        state_db.update_tab_shadow_mode(str(tab_id), mode if enabled else "off")
        response["tab"] = {"id": str(tab_id), "mode": mode if enabled else "off"}
    else:
        state_db.set_shadow_settings(enabled=enabled, mode=mode if enabled else "off")
    response["global"] = state_db.get_shadow_settings()
    return jsonify(response)


# ---------------------------------------------------------------------------
# Graph endpoints
# ---------------------------------------------------------------------------


@bp.get("/graph/summary")
def get_graph_summary():
    state_db = _state_db()
    summary = state_db.graph_summary()
    return jsonify(summary)


@bp.get("/graph/nodes")
def get_graph_nodes():
    state_db = _state_db()
    site = request.args.get("site")
    limit = request.args.get("limit", type=int) or 200
    min_degree = request.args.get("min_degree", type=int) or 0
    category = request.args.get("category")
    start = _parse_iso_ts(request.args.get("from"))
    end = _parse_iso_ts(request.args.get("to"))
    nodes = state_db.graph_nodes(
        site=site,
        limit=limit,
        min_degree=min_degree,
        category=category,
        start=start,
        end=end,
    )
    return jsonify({"nodes": nodes})


@bp.get("/graph/edges")
def get_graph_edges():
    state_db = _state_db()
    site = request.args.get("site")
    limit = request.args.get("limit", type=int) or 200
    edges = state_db.graph_edges(site=site, limit=limit)
    return jsonify({"edges": edges})


__all__ = ["bp"]
