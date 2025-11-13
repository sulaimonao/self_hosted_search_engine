"""Shared helpers for API blueprints."""

from __future__ import annotations

from typing import Iterator

_SENTINEL_VALUES = {"", "null", "none", "undefined", "~"}


def coerce_chat_identifier(value: object | None) -> str | None:
    """Normalize inbound chat/message identifiers.

    HTTP headers and query parameters can be empty strings, literal
    "null"/"undefined", numbers, or even bytes.  The rest of the API only
    understands string identifiers or ``None``.  We normalise these
    variations into a safe ``str`` or ``None``.
    """

    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8", "ignore")  # type: ignore[assignment]
        except Exception:  # pragma: no cover - extremely defensive
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in _SENTINEL_VALUES:
        return None
    return text


def _format_data_lines(payload: str) -> Iterator[str]:
    if payload == "":
        yield "data:"
        return
    for line in payload.splitlines() or [payload]:
        yield f"data: {line}" if line else "data:"


def sse_format(
    data: str, *, event: str | None = None, retry: int | None = None
) -> bytes:
    """Render a Server-Sent Event frame.

    Flask's streaming responses accept either ``str`` or ``bytes``
    fragments.  We emit UTF-8 encoded bytes because the consumer in the
    frontend expects UTF-8 and this avoids accidental implicit
    conversions.
    """

    parts: list[str] = []
    if retry is not None:
        parts.append(f"retry: {int(retry)}")
    if event:
        parts.append(f"event: {event}")
    parts.extend(_format_data_lines(data))
    parts.append("")  # terminator line
    return ("\n".join(parts) + "\n").encode("utf-8")


__all__ = ["coerce_chat_identifier", "sse_format"]
