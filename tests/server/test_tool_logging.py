from __future__ import annotations

from typing import Any

import pytest

from server import tool_logging


def _capture_events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tool_logging, "write_event", lambda payload: events.append(payload)
    )
    monkeypatch.setattr(tool_logging, "add_run_log_line", lambda message: None)
    monkeypatch.setattr(tool_logging, "_get_context_attr", lambda name: None)
    return events


def test_log_tool_limits_result_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _capture_events(monkeypatch)

    @tool_logging.log_tool("embed.documents")
    def fake_embed() -> dict[str, Any]:
        return {
            "embeddings": [
                [float(i) for i in range(32)],
                [float(i) for i in range(16)],
            ],
            "count": 2,
            "note": "x" * 600,
        }

    fake_embed()

    end_events = [event for event in events if event["event"] == "tool.end"]
    assert end_events, "expected tool.end event"
    preview = end_events[-1]["meta"]["result_preview"]

    assert preview["count"] == 2
    note_preview = preview["note"]
    assert isinstance(note_preview, str)
    assert note_preview.endswith("...[truncated]")
    assert len(note_preview) <= 256 + len("...[truncated]")

    embeddings_preview = preview["embeddings"]
    assert isinstance(embeddings_preview, list)
    first_vector = embeddings_preview[0]
    assert first_vector["len"] == 32
    assert first_vector["truncated"] is True
    assert len(first_vector["sample"]) < first_vector["len"]
