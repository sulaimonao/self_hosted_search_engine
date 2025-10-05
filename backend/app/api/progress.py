"""Server-sent events for crawl progress."""

from __future__ import annotations

import json
import queue

from flask import Blueprint, Response, current_app, stream_with_context

from backend.app.services.progress_bus import ProgressBus

bp = Blueprint("progress_stream", __name__, url_prefix="/api")


@bp.get("/progress/<job_id>/stream")
def progress_stream(job_id: str) -> Response:
    bus: ProgressBus = current_app.config["PROGRESS_BUS"]
    q = bus.subscribe(job_id)

    @stream_with_context
    def _generate():
        yield "retry: 2000\n\n"
        while True:
            try:
                event = q.get(timeout=25)
            except queue.Empty:
                yield "event: ping\ndata: {}\n\n"
                continue
            payload = json.dumps(event, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    response = Response(_generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-store"
    return response


__all__ = ["bp", "progress_stream"]
