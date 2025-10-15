"""Manual refresh API wiring the background worker into Flask."""

from __future__ import annotations

from typing import Any, Iterable, Sequence
from urllib.parse import urlunparse

from flask import Blueprint, current_app, jsonify, request

from backend.app.api import seeds as seeds_api

bp = Blueprint("refresh_api", __name__, url_prefix="/api/refresh")


def _get_worker():
    return current_app.config.get("REFRESH_WORKER")


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, (list, tuple, set)):
        cleaned: list[str] = []
        for item in value:
            if isinstance(item, str):
                candidate = item.strip()
                if candidate:
                    cleaned.append(candidate)
        return cleaned
    return []


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _resolve_seed_urls(seed_ids: Sequence[str]) -> tuple[list[str], list[str]]:
    if not seed_ids:
        return [], []

    with seeds_api._LOCK:
        registry, _ = seeds_api._read_registry()
    records = seeds_api._collect_seeds(registry)
    lookup = {str(entry.get("id")): entry for entry in records if entry.get("id")}

    urls: list[str] = []
    missing: list[str] = []
    for identifier in seed_ids:
        record = lookup.get(identifier)
        if not record:
            missing.append(identifier)
            continue
        url_value = record.get("url")
        if isinstance(url_value, str) and url_value.strip():
            urls.append(url_value.strip())
            continue
        entrypoints = record.get("entrypoints")
        resolved: str | None = None
        if isinstance(entrypoints, str) and entrypoints.strip():
            resolved = entrypoints.strip()
        elif isinstance(entrypoints, Sequence):
            for candidate in entrypoints:
                if isinstance(candidate, str) and candidate.strip():
                    resolved = candidate.strip()
                    break
        if resolved:
            urls.append(resolved)
        else:
            missing.append(identifier)
    return urls, missing


@bp.post("")
def trigger_refresh():
    worker = _get_worker()
    if worker is None:
        return jsonify({"error": "refresh_unavailable"}), 503

    payload = request.get_json(silent=True) or {}
    raw_query = payload.get("query")

    manual_seed_ids: list[str] = []
    manual_seed_urls: list[str] = []
    query_text: str | None = None

    if isinstance(raw_query, dict):
        manual_seed_ids.extend(_coerce_str_list(raw_query.get("seed_ids")))
        manual_seed_urls.extend(_coerce_str_list(raw_query.get("seed_urls")))
        text_candidate = raw_query.get("text") or raw_query.get("query") or raw_query.get("q")
        if isinstance(text_candidate, str):
            query_text = text_candidate.strip() or None
    elif isinstance(raw_query, str):
        query_text = raw_query.strip() or None
    elif raw_query is not None:
        return jsonify({"error": "invalid_query"}), 400

    manual_seed_ids = _dedupe_preserve_order([identifier.strip() for identifier in manual_seed_ids if identifier.strip()])

    seeds_value = payload.get("seeds")
    if seeds_value is not None and not isinstance(seeds_value, (str, list, tuple, set)):
        return jsonify({"error": "invalid_seeds"}), 400
    manual_seed_urls.extend(_coerce_str_list(seeds_value))

    resolved_seed_urls, missing_ids = _resolve_seed_urls(manual_seed_ids)
    if missing_ids:
        return jsonify({"error": "unknown_seed", "missing": missing_ids}), 400
    manual_seed_urls.extend(resolved_seed_urls)
    manual_seed_urls = _dedupe_preserve_order(
        [url.strip() for url in manual_seed_urls if isinstance(url, str) and url.strip()]
    )

    normalized_seeds: list[str] = []
    invalid_seeds: list[str] = []
    for url in manual_seed_urls:
        try:
            parsed = seeds_api.parse_http_url(url)
        except ValueError:
            invalid_seeds.append(url)
            continue
        normalized = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path or "", "", parsed.query, "")
        )
        normalized_seeds.append(normalized)

    if invalid_seeds:
        return jsonify({"error": "invalid_seed_url", "invalid": invalid_seeds}), 400

    manual_seed_urls = _dedupe_preserve_order(normalized_seeds)

    if query_text is None or not query_text.strip():
        if manual_seed_ids:
            canonical = ",".join(sorted(manual_seed_ids))
            query_text = f"seeds:{canonical}" if canonical else None
        elif manual_seed_urls:
            canonical = ",".join(sorted(url.lower() for url in manual_seed_urls))
            query_text = f"urls:{canonical}" if canonical else None

    if not query_text:
        return jsonify({"error": "missing_query"}), 400

    use_llm_raw = payload.get("use_llm")
    use_llm = bool(use_llm_raw) if use_llm_raw is not None else False
    model = payload.get("model")
    if isinstance(model, str):
        model = model.strip() or None
    else:
        model = None

    budget_raw = payload.get("budget")
    budget: int | None
    if budget_raw is None:
        budget = None
    else:
        try:
            budget = int(budget_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_budget"}), 400
        if budget <= 0:
            return jsonify({"error": "invalid_budget"}), 400

    depth_raw = payload.get("depth")
    depth: int | None
    if depth_raw is None:
        depth = None
    else:
        try:
            depth = int(depth_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_depth"}), 400
        if depth <= 0:
            return jsonify({"error": "invalid_depth"}), 400

    force_raw = payload.get("force")
    force = bool(force_raw) if force_raw is not None else False

    seeds = manual_seed_urls if manual_seed_urls else None

    try:
        job_id, status, created = worker.enqueue(
            query_text,
            use_llm=use_llm,
            model=model,
            budget=budget,
            depth=depth,
            force=force,
            seeds=seeds,
        )
    except ValueError as exc:
        return jsonify({"error": "invalid_query", "detail": str(exc)}), 400

    response: dict[str, Any] = {
        "status": "queued",
        "seed_ids": manual_seed_ids,
        "created": bool(created),
    }
    if job_id:
        response["job_id"] = job_id
    if not created:
        response["deduplicated"] = True
    if isinstance(status, dict):
        message = status.get("message")
        if isinstance(message, str) and message.strip():
            response["detail"] = message.strip()
    return jsonify(response), 202


@bp.get("/status")
def refresh_status():
    worker = _get_worker()
    if worker is None:
        return jsonify({"error": "refresh_unavailable"}), 503

    job_id = request.args.get("job_id")
    query = request.args.get("query")
    snapshot = worker.status(job_id=job_id, query=query)
    return jsonify(snapshot)
