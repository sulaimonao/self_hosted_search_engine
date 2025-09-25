"""Unit tests for telemetry redaction helpers."""

from __future__ import annotations

from backend.logging_utils import redact


def test_redact_limits() -> None:
    big = "x" * 10000
    redacted = redact(big)
    assert isinstance(redacted, dict)
    assert "sha256" in redacted
    assert "preview" in redacted


def test_redact_sensitive_keys() -> None:
    payload = {"password": "secret", "token": "abc", "html": "<html>hello</html>"}
    redacted = redact(payload)
    assert redacted["password"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["html"] != payload["html"]
