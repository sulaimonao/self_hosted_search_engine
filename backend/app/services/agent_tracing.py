"""Utilities for redacting and publishing agent tool traces."""

from __future__ import annotations

import re
import time
from typing import Any, Mapping

from flask import current_app

from .log_bus import AgentLogBus


SENSITIVE_KEY_PATTERN = re.compile(
    r"(token|key|secret|password|authorization)", re.IGNORECASE
)
SENSITIVE_VALUE_PATTERN = re.compile(r"(sk-|eyJhbGci|AIza|Bearer\s+[A-Za-z0-9_-]{10,})")


def redact_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if SENSITIVE_VALUE_PATTERN.search(value) or len(value) > 120:
            return "[redacted]"
        return value
    if isinstance(value, Mapping):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact_value(item) for item in value]
    return str(value)


def redact_args(arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    if not arguments:
        return {}
    redacted: dict[str, Any] = {}
    for key, value in arguments.items():
        if SENSITIVE_KEY_PATTERN.search(str(key)):
            redacted[str(key)] = "[redacted]"
        else:
            redacted[str(key)] = redact_value(value)
    return redacted


def excerpt_from_result(result: Any, *, limit: int = 400) -> str | None:
    if result is None:
        return None
    if isinstance(result, str):
        text = result.strip()
    else:
        text = str(result).strip()
    if not text:
        return None
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def publish_agent_step(
    *,
    tool: str,
    chat_id: str | None,
    message_id: str | None,
    args: Mapping[str, Any] | None,
    status: str,
    started_at: float | None = None,
    ended_at: float | None = None,
    token_in: int | None = None,
    token_out: int | None = None,
    excerpt: Any | None = None,
) -> None:
    bus: AgentLogBus | None = current_app.config.get("AGENT_LOG_BUS")
    if bus is None:
        return
    if not chat_id:
        # Do not broadcast steps without an associated chat thread
        return
    started = float(started_at) if started_at is not None else time.time()
    ended = float(ended_at) if ended_at is not None else time.time()
    duration_ms = max(0, int((ended - started) * 1000))
    payload = {
        "type": "agent_step",
        "chat_id": chat_id,
        "message_id": message_id,
        "tool": tool,
        "args_redacted": redact_args(dict(args) if args else {}),
        "status": status,
        "started_at": started,
        "ended_at": ended,
        "duration_ms": duration_ms,
        "token_in": token_in,
        "token_out": token_out,
        "excerpt": excerpt_from_result(excerpt),
    }
    bus.publish(payload)


__all__ = [
    "publish_agent_step",
    "redact_args",
    "redact_value",
    "excerpt_from_result",
]
