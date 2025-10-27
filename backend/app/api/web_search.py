"""Lightweight search helper that exposes snippets to other services."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("web_search_api", __name__, url_prefix="/api")
_FALLBACK_RESULT = [
    {
        "title": "No live data retrieved",
        "url": "",
        "snippet": "Fallback response used.",
    }
]


def _search_service() -> Any:
    service = current_app.config.get("SEARCH_SERVICE")
    if service is not None and hasattr(service, "run_query"):
        return service
    return None


def _clip_text(value: Any, limit: int = 280) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def web_search(
    query: str,
    *,
    limit: int = 5,
    use_llm: bool | None = None,
    model: str | None = None,
) -> list[dict[str, str]]:
    """Execute a Whoosh-backed search and normalize the result cards."""

    q = (query or "").strip()
    if not q:
        return list(_FALLBACK_RESULT)

    service = _search_service()
    if service is None:
        return list(_FALLBACK_RESULT)

    limit = max(1, min(int(limit or 1), 20))
    try:
        hits, _job_id, _context = service.run_query(
            q,
            limit=limit,
            use_llm=use_llm,
            model=model,
        )
    except Exception:
        hits = []

    results: list[dict[str, str]] = []
    for hit in hits or []:
        title = str(hit.get("title") or hit.get("url") or "Untitled").strip()
        url = str(hit.get("url") or "").strip()
        snippet_source = next(
            (
                hit.get(field)
                for field in ("summary", "snippet", "description", "text", "content")
                if hit.get(field)
            ),
            "",
        )
        snippet = _clip_text(snippet_source)
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break

    return results or list(_FALLBACK_RESULT)


@bp.get("/web-search")
def web_search_endpoint():
    query = request.args.get("q", "", type=str)
    limit = request.args.get("limit", type=int) or 5
    use_llm = request.args.get("use_llm")
    model = request.args.get("model")

    def _coerce_flag(value: Any) -> bool | None:
        if value is None:
            return None
        lowered = str(value).strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return None

    results = web_search(
        query,
        limit=limit,
        use_llm=_coerce_flag(use_llm),
        model=model,
    )
    return jsonify({"query": query, "results": results})


__all__ = ["bp", "web_search"]
