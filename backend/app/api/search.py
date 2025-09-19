"""Search API blueprint."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..search.service import SearchService

bp = Blueprint("search_api", __name__, url_prefix="/api")


@bp.get("/search")
def search_endpoint():
    service: SearchService = current_app.config["SEARCH_SERVICE"]
    config = current_app.config["APP_CONFIG"]

    query = (request.args.get("q") or "").strip()
    limit = request.args.get("limit", type=int) or config.search_default_limit
    llm_param = (request.args.get("llm") or "").lower()
    if llm_param in {"1", "true", "yes", "on"}:
        use_llm = True
    elif llm_param in {"0", "false", "no", "off"}:
        use_llm = False
    else:
        use_llm = None
    model = (request.args.get("model") or "").strip() or None

    results, job_id = service.run_query(query, limit=limit, use_llm=use_llm, model=model)
    status = "focused_crawl_running" if job_id else "ok"
    payload = {
        "query": query,
        "results": results,
        "status": status,
        "last_index_time": service.last_index_time(),
    }
    if job_id:
        payload["job_id"] = job_id
    return jsonify(payload)
