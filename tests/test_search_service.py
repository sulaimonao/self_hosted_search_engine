from __future__ import annotations

from types import SimpleNamespace

from backend.app.search.service import SearchService


def _base_config(tmp_path, **overrides):
    defaults = {
        "index_dir": tmp_path / "index",
        "search_max_limit": 20,
        "max_query_length": 256,
        "smart_min_results": 1,
        "use_llm_rerank": True,
        "smart_confidence_threshold": 0.35,
        "smart_seed_min_similarity": 0.2,
        "smart_seed_limit": 5,
        "last_index_time_path": tmp_path / "state" / ".last_index_time",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _stub_search(monkeypatch, hits):
    monkeypatch.setattr(
        "backend.app.search.service.query_module.search",
        lambda ix, query, limit, max_limit, max_query_length: list(hits),
    )
    monkeypatch.setattr(
        "backend.app.search.service.blend_results",
        lambda results: list(results),
    )
    monkeypatch.setattr(
        "backend.app.search.service.maybe_rerank",
        lambda query, results, enabled, model: results,
    )


def _mute_metrics(monkeypatch):
    monkeypatch.setattr("backend.app.search.service.metrics.record_search_latency", lambda ms: None)
    monkeypatch.setattr("backend.app.search.service.metrics.record_llm_usage_event", lambda count=1: None)
    monkeypatch.setattr("backend.app.search.service.metrics.record_query_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.app.search.service.metrics.record_focused_enqueue", lambda count=1: None)


def test_run_query_triggers_when_no_results(monkeypatch, tmp_path):
    config = _base_config(tmp_path)

    class StubManager:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.db = SimpleNamespace(similar_discovery_seeds=lambda *args, **kwargs: ["https://seed.one"])

        def schedule(self, query, use_llm, model, *, frontier_seeds=None, query_embedding=None):
            self.calls.append(
                {
                    "query": query,
                    "use_llm": use_llm,
                    "model": model,
                    "frontier_seeds": list(frontier_seeds or []),
                    "embedding": list(query_embedding or []),
                }
            )
            return "job-1"

        def last_index_time(self) -> int:
            return 0

    manager = StubManager()
    service = SearchService(config, manager)
    service._get_index = lambda: object()

    _stub_search(monkeypatch, [])
    _mute_metrics(monkeypatch)

    results, job_id, context = service.run_query("docs", limit=5, use_llm=None, model="llama2")

    assert results == []
    assert job_id == "job-1"
    assert context["trigger_reason"] == "no_results"
    assert manager.calls and manager.calls[0]["frontier_seeds"] == ["https://seed.one"]


def test_run_query_skips_when_confident(monkeypatch, tmp_path):
    config = _base_config(tmp_path)

    class StubManager:
        def __init__(self) -> None:
            self.calls = []
            self.db = SimpleNamespace(similar_discovery_seeds=lambda *args, **kwargs: [])

        def schedule(self, *args, **kwargs):  # pragma: no cover - should not be called
            raise AssertionError("schedule should not be invoked for confident hits")

        def last_index_time(self) -> int:
            return 0

    manager = StubManager()
    service = SearchService(config, manager)
    service._get_index = lambda: object()

    hits = [
        {
            "url": "https://example.com",
            "title": "Example",
            "snippet": "",
            "score": 1.2,
            "blended_score": 1.2,
            "lang": "en",
        }
    ]
    _stub_search(monkeypatch, hits)
    _mute_metrics(monkeypatch)

    results, job_id, context = service.run_query("docs", limit=5, use_llm=None, model=None)

    assert job_id is None
    assert context["triggered"] is False
    assert context["confidence"] > config.smart_confidence_threshold


def test_run_query_triggers_for_low_confidence(monkeypatch, tmp_path):
    config = _base_config(tmp_path)

    class StubManager:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.db = SimpleNamespace(similar_discovery_seeds=lambda *args, **kwargs: ["https://seed.one", "https://seed.two"])

        def schedule(self, query, use_llm, model, *, frontier_seeds=None, query_embedding=None):
            self.calls.append(
                {
                    "query": query,
                    "frontier": list(frontier_seeds or []),
                    "embedding": list(query_embedding or []),
                }
            )
            return "job-low"

        def last_index_time(self) -> int:
            return 0

    manager = StubManager()
    service = SearchService(config, manager)
    service._get_index = lambda: object()

    hits = [
        {
            "url": "https://example.com",
            "title": "Example",
            "snippet": "",
            "score": 0.05,
            "blended_score": 0.05,
            "lang": "en",
        }
    ]

    _stub_search(monkeypatch, hits)
    _mute_metrics(monkeypatch)

    results, job_id, context = service.run_query("docs", limit=5, use_llm=None, model=None)

    assert job_id == "job-low"
    assert context["trigger_reason"] == "low_confidence"
    assert context["seed_count"] == 2
    assert manager.calls and manager.calls[0]["frontier"] == ["https://seed.one", "https://seed.two"]


def test_get_index_reloads_when_generation_changes(tmp_path):
    marker = tmp_path / "state" / ".last_index_time"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("1\n", encoding="utf-8")

    config = _base_config(tmp_path, last_index_time_path=marker)

    class StubManager:
        def __init__(self) -> None:
            self.db = SimpleNamespace(similar_discovery_seeds=lambda *args, **kwargs: [])

        def schedule(self, *args, **kwargs):  # pragma: no cover - not exercised here
            return None

        def last_index_time(self) -> int:
            return 0

    service = SearchService(config, StubManager())

    first = service._get_index()
    marker.write_text("2\n", encoding="utf-8")
    second = service._get_index()

    assert first is not second
