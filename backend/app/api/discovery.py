"""Local discovery API surface."""

from __future__ import annotations

import json
import queue
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from backend.app.services.local_discovery import DiscoveryRecord, LocalDiscoveryService


bp = Blueprint("discovery_api", __name__, url_prefix="/api/discovery")


def _service() -> LocalDiscoveryService | None:
    service = current_app.config.get("LOCAL_DISCOVERY_SERVICE")
    if isinstance(service, LocalDiscoveryService):
        return service
    return None


def _enabled() -> bool:
    return bool(current_app.config.get("FEATURE_LOCAL_DISCOVERY"))


def _serialize(record: DiscoveryRecord, *, include_text: bool) -> dict[str, Any]:
    service = _service()
    if service is None:  # pragma: no cover - guarded by caller
        raise RuntimeError("Local discovery unavailable")
    return service.to_dict(record, include_text=include_text)


@bp.get("/events")
@bp.get("/stream_events")
def stream_events() -> Response:
    if not _enabled():
        return Response(status=404)

    service = _service()
    if service is None:
        return jsonify({"error": "local_discovery_unavailable"}), 503

    def generate() -> Any:
        token, stream = service.subscribe()
        try:
            while True:
                try:
                    record = stream.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                if record is None:
                    break
                payload = json.dumps(_serialize(record, include_text=False))
                yield f"data: {payload}\n\n"
        finally:
            service.unsubscribe(token)

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@bp.get("/item/<string:record_id>")
def get_item(record_id: str):
    if not _enabled():
        return jsonify({"error": "local_discovery_disabled"}), 404

    service = _service()
    if service is None:
        return jsonify({"error": "local_discovery_unavailable"}), 503

    record = service.get(record_id)
    if record is None:
        return jsonify({"error": "not_found"}), 404

    return jsonify(_serialize(record, include_text=True)), 200


@bp.post("/confirm")
def confirm_item():
    if not _enabled():
        return jsonify({"error": "local_discovery_disabled"}), 404

    service = _service()
    if service is None:
        return jsonify({"error": "local_discovery_unavailable"}), 503

    payload = request.get_json(silent=True) or {}
    record_id_raw = payload.get("id")
    record_id = str(record_id_raw).strip() if isinstance(record_id_raw, str) else ""
    if not record_id:
        return jsonify({"error": "id_required"}), 400

    action_raw = payload.get("action")
    action = str(action_raw).strip() if isinstance(action_raw, str) else "included"

    if not service.confirm(record_id, action=action or "included"):
        return jsonify({"error": "not_found"}), 404

    return jsonify({"ok": True, "id": record_id, "action": action or "included"}), 200


__all__ = ["bp"]
