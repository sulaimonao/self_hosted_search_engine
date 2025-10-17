"""Server-sent events for crawl progress."""

from __future__ import annotations

import json
import queue

from flask import Blueprint, Response, current_app, stream_with_context

from backend.app.services.progress_bus import ProgressBus

bp = Blueprint("progress_stream", __name__, url_prefix="/api")

_DIAGNOSTIC_JOB_ID = "__diagnostics__"


@bp.get("/progress/<job_id>/stream")
def progress_stream(job_id: str) -> Response:
    bus: ProgressBus = current_app.config["PROGRESS_BUS"]
    q = bus.subscribe(job_id)

    @stream_with_context
    def _generate():
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    event = q.get(timeout=25)
                except queue.Empty:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                if event is None:
                    break
                try:
                    payload = json.dumps(event, ensure_ascii=False)
                except (TypeError, ValueError):
                    payload = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {payload}\n\n"
        finally:
            bus.unsubscribe(job_id, q)

    response = Response(_generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/progress/stream")
def progress_default_stream() -> Response:
    """Fallback stream for diagnostics and generic monitoring."""

    return progress_stream(_DIAGNOSTIC_JOB_ID)


__all__ = ["bp", "progress_stream", "progress_default_stream"]
