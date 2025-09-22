from __future__ import annotations

from types import SimpleNamespace

from backend.app.search.service import SearchService


def test_run_query_always_schedules_refresh(monkeypatch, tmp_path):
    config = SimpleNamespace(
        index_dir=tmp_path / "index",
        search_max_limit=20,
        max_query_length=256,
        smart_min_results=1,
        use_llm_rerank=True,
    )

    class StubManager:
        def __init__(self) -> None:
            self.calls: list[tuple[str, bool, str | None]] = []

        def schedule(self, query: str, use_llm: bool, model: str | None):
            self.calls.append((query, use_llm, model))
            return f"job-{len(self.calls)}"

        def last_index_time(self) -> int:  # pragma: no cover - not exercised
            return 0

    manager = StubManager()
    service = SearchService(config, manager)
    service._get_index = lambda: object()

    monkeypatch.setattr(
        "backend.app.search.service.query_module.search",
        lambda ix, query, limit, max_limit, max_query_length: [
            {
                "url": "https://example.com",
                "title": "Example",
                "snippet": "",
                "score": 1.0,
                "lang": "en",
            }
        ],
    )
    monkeypatch.setattr("backend.app.search.service.blend_results", lambda results: results)
    monkeypatch.setattr(
        "backend.app.search.service.maybe_rerank",
        lambda query, results, enabled, model: results,
    )

    query_events: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        "backend.app.search.service.metrics.record_query_event",
        lambda results_count, triggered, latency_ms: query_events.append((results_count, triggered)),
    )
    focused_calls: list[int] = []
    monkeypatch.setattr(
        "backend.app.search.service.metrics.record_focused_enqueue",
        lambda count=1: focused_calls.append(count),
    )
    monkeypatch.setattr("backend.app.search.service.metrics.record_search_latency", lambda ms: None)
    monkeypatch.setattr("backend.app.search.service.metrics.record_llm_usage_event", lambda count=1: None)

    results, job_id = service.run_query("docs", limit=5, use_llm=None, model="llama2")

    assert results
    assert job_id == "job-1"
    assert manager.calls == [("docs", True, "llama2")]
    assert query_events and query_events[0][1] is True
    assert focused_calls == [1]
