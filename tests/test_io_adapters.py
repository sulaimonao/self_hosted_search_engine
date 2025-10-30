from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.io import coerce_directive, coerce_incident, normalize_model

GOLDEN = Path(__file__).parent / "golden"


def load_golden(name: str) -> dict[str, object]:
    with (GOLDEN / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_coerce_incident_basic() -> None:
    raw = {
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
    incident = coerce_incident(raw)
    assert incident.as_payload() == load_golden("incident_basic.json")


def test_coerce_incident_minimal_defaults() -> None:
    raw = {"url": "https://example.com", "symptoms": None, "domSnippet": "   "}
    incident = coerce_incident(raw)
    assert incident.as_payload() == load_golden("incident_minimal.json")


def test_coerce_directive_basic() -> None:
    raw = {
        "reason": " Planned fix ",
        "steps": [
            {"verb": " reload "},
            {
                "verb": "Press",
                "text": "Retry",
                "headless": "false",
            },
        ],
        "plan_confidence": "MEDIUM",
        "needs_user_permission": "false",
        "ask_user": ["  Is the banner still visible?  "],
        "fallback": {"enabled": "true", "headless_hint": ["Run headless verification", "  "]},
    }
    directive = coerce_directive(raw)
    assert directive.as_payload() == load_golden("directive_basic.json")


def test_coerce_directive_headless() -> None:
    raw = {
        "reason": "Headless recovery",
        "steps": [
            {
                "type": "Navigate",
                "args": {"url": "https://example.com/login"},
                "headless": True,
            },
            {
                "type": "wait",
                "args": {"ms": "800"},
                "headless": "true",
            },
        ],
        "plan_confidence": "HIGH",
        "needs_user_permission": True,
        "fallback": {"enabled": False},
    }
    directive = coerce_directive(raw)
    assert directive.as_payload() == load_golden("directive_headless.json")


def test_coerce_directive_drops_invalid_steps() -> None:
    raw = {
        "reason": "Test",
        "steps": [
            {"verb": "unknown"},
            {"verb": "click", "selector": "#submit"},
        ],
    }
    directive = coerce_directive(raw)
    payload = directive.as_payload()
    assert payload["steps"][0]["type"] == "click"
    assert len(payload["steps"]) == 1


@pytest.mark.parametrize(
    "name,expected",
    [
        (" gemma:2b ", "gemma3"),
        ("GPT", "gpt-oss"),
        (None, "gpt-oss"),
    ],
)
def test_normalize_model_aliases(name: str | None, expected: str) -> None:
    result = normalize_model(name)
    assert result == expected
