from __future__ import annotations

from types import SimpleNamespace

from backend.app.search.service import SearchRunResult, SearchService


def _config(tmp_path, **overrides):
    base = {
        "index_dir": tmp_path / "index",
        "search_max_limit": 20,
        "max_query_length": 256,
        "smart_min_results": 1,
        "smart_min_confidence": 0.4,
        "use_llm_rerank": True,
        "learned_seed_limit": 5,
        "learned_min_similarity": 0.3,
        "learned_web_db": tmp_path / "learned.sqlite3",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class StubManager:
    def __init__(self, *, job_ids: list[str | None] | None = None) -> None:
        self.calls: list[tuple[str, bool, str | None, tuple[str, ...]]] = []
        self._job_ids = list(job_ids or ["job-1"])

    def schedule(
        self,
        query: str,
        use_llm: bool,
        model: str | None,
        *,
        extra_seeds: list[str] | None = None,
    ) -> str | None:
        seeds = tuple(extra_seeds or ())
        self.calls.append((query, use_llm, model, seeds))
        if not self._job_ids:
            return None
        return self._job_ids.pop(0)

    def last_index_time(self) -> int:  # pragma: no cover - not exercised
        return 0


class StubLearnedStore:
    def __init__(self, results: list[str]) -> None:
        self.calls: list[tuple[str, int, float]] = []
        self._results = results

    def similar_urls(self, query: str, *, limit: int, min_similarity: float) -> list[str]:
        self.calls.append((query, limit, min_similarity))
        return list(self._results)


def _patch_search(monkeypatch, results):
    monkeypatch.setattr(
        "backend.app.search.service.query_module.search",
        lambda ix, query, limit, max_limit, max_query_length: results,
    )
    monkeypatch.setattr("backend.app.search.service.blend_results", lambda payload: payload)
    monkeypatch.setattr(
        "backend.app.search.service.maybe_rerank",
        lambda query, payload, enabled, model: payload,
    )
    monkeypatch.setattr("backend.app.search.service.metrics.record_search_latency", lambda ms: None)
    monkeypatch.setattr("backend.app.search.service.metrics.record_llm_usage_event", lambda count=1: None)


def test_run_query_triggers_when_no_hits(monkeypatch, tmp_path):
    config = _config(tmp_path)
    manager = StubManager()
    service = SearchService(config, manager)
    service._get_index = lambda: object()

    _patch_search(monkeypatch, [])

    recorded: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        "backend.app.search.service.metrics.record_query_event",
        lambda results_count, triggered, latency_ms: recorded.append((results_count, triggered)),
    )
    focused_calls: list[int] = []
    monkeypatch.setattr(
        "backend.app.search.service.metrics.record_focused_enqueue",
        lambda count=1: focused_calls.append(count),
    )

    run = service.run_query("docs", limit=5, use_llm=None, model="llama2")

    assert isinstance(run, SearchRunResult)
    assert run.triggered is True
    assert run.trigger_reason == "no_results"
    assert run.job_id == "job-1"
    assert manager.calls == [("docs", True, "llama2", ())]
    assert recorded and recorded[0] == (0, True)
    assert focused_calls == [1]


def test_run_query_skips_trigger_when_confident(monkeypatch, tmp_path):
    config = _config(tmp_path)
    manager = StubManager(job_ids=[])
    service = SearchService(config, manager)
    service._get_index = lambda: object()

    _patch_search(
        monkeypatch,
        [
            {
                "url": "https://example.com/a",
                "title": "A",
                "snippet": "",
                "score": 1.0,
                "lang": "en",
                "blended_score": 1.0,
            },
            {
                "url": "https://example.com/b",
                "title": "B",
                "snippet": "",
                "score": 0.5,
                "lang": "en",
                "blended_score": 0.5,
            },
        ],
    )

    recorded: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        "backend.app.search.service.metrics.record_query_event",
        lambda results_count, triggered, latency_ms: recorded.append((results_count, triggered)),
    )

    run = service.run_query("docs", limit=5, use_llm=None, model=None)

    assert run.triggered is False
    assert run.job_id is None
    assert run.trigger_attempted is False
    assert manager.calls == []
    assert recorded and recorded[0] == (2, False)


def test_run_query_uses_learned_web_seeds(monkeypatch, tmp_path):
    config = _config(tmp_path, smart_min_confidence=0.8, learned_seed_limit=3)
    manager = StubManager()
    learned_store = StubLearnedStore(["https://seed.one", "https://seed.two"])
    service = SearchService(config, manager, learned_store=learned_store)
    service._get_index = lambda: object()

    _patch_search(
        monkeypatch,
        [
            {
                "url": "https://example.com/a",
                "title": "A",
                "snippet": "",
                "score": 1.0,
                "lang": "en",
                "blended_score": 1.0,
            },
            {
                "url": "https://example.com/b",
                "title": "B",
                "snippet": "",
                "score": 1.0,
                "lang": "en",
                "blended_score": 1.0,
            },
        ],
    )

    focused_calls: list[int] = []
    monkeypatch.setattr(
        "backend.app.search.service.metrics.record_query_event",
        lambda results_count, triggered, latency_ms: None,
    )
    monkeypatch.setattr(
        "backend.app.search.service.metrics.record_focused_enqueue",
        lambda count=1: focused_calls.append(count),
    )

    run = service.run_query("docs", limit=5, use_llm=None, model=None)

    assert run.triggered is True
    assert run.trigger_reason == "low_confidence"
    assert run.frontier_seeds == ("https://seed.one", "https://seed.two")
    assert manager.calls == [
        ("docs", True, None, ("https://seed.one", "https://seed.two"))
    ]
    assert learned_store.calls == [("docs", 3, 0.3)]
    assert focused_calls == [1]
