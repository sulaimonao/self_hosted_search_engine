#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

from backend.app.io import coerce_directive, coerce_incident

base = Path("tests/golden")

incident_raw = {
    "id": " incident-001 ",
    "url": "https://example.com/app",
    "symptoms": {
        "bannerText": " Something went wrong ",
        "consoleErrors": [
            " TypeError: cannot read properties of undefined ",
            {"message": "ignored"},
        ],
        "networkErrors": [
            {"url": "https://example.com/api/data", "status": "500", "error": " Server error "},
            "noise",
        ],
    },
    "domSnippet": "<div class='error'>Something went wrong</div>",
}
expected_incident = json.loads((base / "incident_basic.json").read_text(encoding="utf-8"))
assert coerce_incident(incident_raw).as_payload() == expected_incident

plan_raw = json.loads((base / "directive_basic.json").read_text(encoding="utf-8"))
# introduce drift to ensure normalization
plan_raw_source = {
    "reason": plan_raw["reason"],
    "steps": [
        {"verb": " reload "},
        {"verb": "press", "text": "Retry"},
    ],
    "plan_confidence": plan_raw.get("plan_confidence", ""),
    "needs_user_permission": plan_raw.get("needs_user_permission", False),
    "ask_user": plan_raw.get("ask_user", []),
    "fallback": plan_raw.get("fallback"),
}
assert coerce_directive(plan_raw_source).as_payload() == plan_raw

headless_raw = json.loads((base / "directive_headless.json").read_text(encoding="utf-8"))
headless_source = {
    "reason": headless_raw["reason"],
    "steps": [
        {"type": "Navigate", "args": {"url": "https://example.com/login"}, "headless": True},
        {"type": "wait", "args": {"ms": "800"}, "headless": "true"},
    ],
    "plan_confidence": headless_raw.get("plan_confidence"),
    "needs_user_permission": headless_raw.get("needs_user_permission"),
    "fallback": headless_raw.get("fallback"),
}
assert coerce_directive(headless_source).as_payload() == headless_raw

print("✅ self-heal smoke passed")
PY
