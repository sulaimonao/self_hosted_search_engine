"""Server-Sent Events endpoint for agent tool traces."""

from __future__ import annotations

import json
import queue
import time

from flask import Blueprint, Response, current_app, request, stream_with_context

from ..routes.utils import coerce_chat_identifier, sse_format
from ..services.log_bus import AgentLogBus


bp = Blueprint("agent_logs", __name__, url_prefix="/api/agent")


@bp.get("/logs")
def stream_agent_logs() -> Response:
    bus: AgentLogBus | None = current_app.config.get("AGENT_LOG_BUS")
    if bus is None:
        return Response("Agent log bus unavailable", status=503)

    requested_chat = coerce_chat_identifier(request.args.get("chat_id"))
    queue_ref = bus.subscribe()

    @stream_with_context
    def _generator():
        try:
            yield sse_format("{}", retry=2500)
            idle_since = time.time()
            while True:
                try:
                    event = queue_ref.get(timeout=25)
                except queue.Empty:
                    # keep connection alive
                    yield sse_format("{}", event="ping")
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") != "agent_step":
                    continue
                if requested_chat and coerce_chat_identifier(event.get("chat_id")) != requested_chat:
                    continue
                payload = {
                    "type": "agent_step",
                    "chat_id": event.get("chat_id"),
                    "message_id": event.get("message_id"),
                    "tool": event.get("tool"),
                    "args_redacted": event.get("args_redacted"),
                    "status": event.get("status"),
                    "started_at": event.get("started_at"),
                    "ended_at": event.get("ended_at"),
                    "duration_ms": event.get("duration_ms"),
                    "token_in": event.get("token_in"),
                    "token_out": event.get("token_out"),
                    "excerpt": event.get("excerpt"),
                }
                try:
                    chunk = json.dumps(payload, ensure_ascii=False)
                except (TypeError, ValueError):
                    chunk = json.dumps({"error": "serialization_failed"})
                yield sse_format(chunk)
                idle_since = time.time()
        finally:
            bus.unsubscribe(queue_ref)

    response = Response(_generator(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-store"
    return response


__all__ = ["bp", "stream_agent_logs"]
