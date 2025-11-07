"""End-to-end chat loopback probe via Next (3100) to Flask (5050).

Sends a trivial prompt through the Next API route and asserts streaming frames
arrive in both SSE and NDJSON modes. Reports actionable hints if not.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe


def _http_post(url: str, body: dict, headers: dict[str, str]) -> str:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec - local dev only
        return resp.read().decode("utf-8", "ignore")


def _has_stream_frames(text: str) -> bool:
    # Accept either SSE (with data: prefix and JSON) or NDJSON lines
    if not text or not text.strip():
        return False
    # quick contains checks
    return (
        "\n\n" in text
        or text.startswith("data: ")
        or "\n{\"type\":" in text
        or '"type": "metadata"' in text
        or '"type": "delta"' in text
        or '"type": "complete"' in text
    )


@register_probe(
    "probe_chat_loopback",
    description="POST /api/chat via Next streams frames (SSE + NDJSON)",
    severity=Severity.HIGH,
)
def probe_chat_loopback(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    base = "http://127.0.0.1:3100"
    url = f"{base}/api/chat"
    payload = {"messages": [{"role": "user", "content": "ping"}], "model": "gpt-oss:20b"}

    # SSE
    try:
        sse_text = _http_post(
            url,
            payload,
            {
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        if not _has_stream_frames(sse_text):
            findings.append(
                Finding(
                    id="chat_loopback:sse-empty",
                    rule_id="probe_chat_loopback",
                    severity=Severity.HIGH,
                    summary="/api/chat SSE via Next did not return streaming frames.",
                    suggestion="Ensure frontend route proxies to /api/chat/stream and sets Content-Type: text/event-stream.",
                    file="frontend/src/app/api/chat/route.ts",
                )
            )
    except Exception as exc:  # best-effort network probe
        findings.append(
            Finding(
                id="chat_loopback:sse-error",
                rule_id="probe_chat_loopback",
                severity=Severity.HIGH,
                summary=f"SSE request failed: {exc}",
                suggestion="Confirm Next is running on :3100 and backend on :5050; check route.ts for proxy to /api/chat/stream.",
                file="frontend/src/app/api/chat/route.ts",
            )
        )

    # NDJSON
    try:
        ndjson_text = _http_post(
            url,
            payload,
            {
                "Content-Type": "application/json",
                "Accept": "application/x-ndjson",
            },
        )
        if not _has_stream_frames(ndjson_text):
            findings.append(
                Finding(
                    id="chat_loopback:ndjson-empty",
                    rule_id="probe_chat_loopback",
                    severity=Severity.MEDIUM,
                    summary="/api/chat NDJSON via Next did not return streaming lines.",
                    suggestion="Ensure route.ts forwards Accept: application/x-ndjson to backend /api/chat and returns same content-type.",
                    file="frontend/src/app/api/chat/route.ts",
                )
            )
    except Exception as exc:
        findings.append(
            Finding(
                id="chat_loopback:ndjson-error",
                rule_id="probe_chat_loopback",
                severity=Severity.MEDIUM,
                summary=f"NDJSON request failed: {exc}",
                suggestion="Check Next /api/chat route for NDJSON pass-through and ensure backend is reachable.",
                file="frontend/src/app/api/chat/route.ts",
            )
        )

    return findings
