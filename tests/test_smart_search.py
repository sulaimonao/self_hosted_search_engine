"""Minimal coverage for the smart search wrapper."""

from __future__ import annotations

import search.smart_search as smart_search


def _reset_state(monkeypatch) -> None:
    monkeypatch.setattr(smart_search, "SMART_MIN_RESULTS", 5)
    monkeypatch.setattr(smart_search, "SMART_USE_LLM", False)
    monkeypatch.setattr(smart_search, "_TRIGGER_HISTORY", {})


def test_smart_search_triggers_focused_crawl(monkeypatch):
    _reset_state(monkeypatch)

    captured: list[tuple[str, bool, str | None]] = []

    def fake_schedule(query: str, *, use_llm: bool, model: str | None) -> bool:
        captured.append((query, use_llm, model))
        return True

    monkeypatch.setattr(smart_search, "_schedule_crawl", fake_schedule)
    monkeypatch.setattr(smart_search, "_mark_triggered", lambda query: None)
    monkeypatch.setattr(smart_search, "_should_trigger", lambda query: True)

    fake_results = [{"title": "placeholder", "url": "https://example.com", "score": 1.0}]
    monkeypatch.setattr(smart_search, "basic_search", lambda index, query, limit: fake_results)

    results = smart_search.smart_search(object(), "example query", limit=10, use_llm=True, model="llama")

    assert results == fake_results
    assert captured == [("example query", True, "llama")]


def test_smart_search_skips_when_results_sufficient(monkeypatch):
    _reset_state(monkeypatch)
    monkeypatch.setattr(smart_search, "SMART_MIN_RESULTS", 1)

    monkeypatch.setattr(smart_search, "basic_search", lambda index, query, limit: [
        {"title": "already indexed", "url": "https://example.com", "score": 1.0}
    ])

    def fake_schedule(*args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("Focused crawl should not run when threshold is met")

    monkeypatch.setattr(smart_search, "_schedule_crawl", fake_schedule)

    results = smart_search.smart_search(object(), "already indexed", limit=5, use_llm=False)
    assert results
