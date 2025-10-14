from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

import pytest

from backend.app.db import AppStateDB
from backend.app.services.source_follow import (
    BudgetExceeded,
    SourceBudget,
    SourceFollowConfig,
    SourceLink,
    extract_sources,
)
from crawler.frontier import Candidate
from crawler.run import FocusedCrawler, PageResult
from frontier import ContentFingerprint


def test_extract_sources_classifies_various_kinds() -> None:
    html = """
    <html>
      <body>
        <section id="references">
          <a href="https://example.com/paper.pdf">PDF Paper</a>
          <a href="https://doi.org/10.1234/foo">DOI Ref</a>
          <a href="https://arxiv.org/abs/1234.5678">ArXiv Ref</a>
          <a href="https://zenodo.org/record/12345">Dataset</a>
          <a href="https://example.com/blog" rel="citation">Blog Post</a>
        </section>
      </body>
    </html>
    """
    links = extract_sources(html, "https://example.com/article")
    kinds = {link.kind for link in links}
    assert {"pdf", "doi", "arxiv", "dataset", "html"} <= kinds


def test_source_budget_domain_and_total_limits() -> None:
    config = SourceFollowConfig(
        enabled=True,
        max_depth=1,
        max_sources_per_page=5,
        max_total_sources=2,
        allowed_domains=["example.com"],
        file_types=["pdf", "html"],
    )
    budget = SourceBudget(config)
    assert budget.can_follow(
        "https://parent", "https://example.com/paper.pdf", kind="pdf", depth=1
    )
    budget.record_follow()
    assert not budget.can_follow(
        "https://parent", "https://other.com/paper.pdf", kind="pdf", depth=1
    )
    budget.record_follow()
    with pytest.raises(BudgetExceeded):
        budget.can_follow(
            "https://parent", "https://example.com/second.pdf", kind="pdf", depth=1
        )


def _state_db(tmp_path: Path) -> AppStateDB:
    path = tmp_path / f"state-{uuid.uuid4().hex}.sqlite3"
    return AppStateDB(path)


def test_sources_config_roundtrip(tmp_path: Path) -> None:
    state_db = _state_db(tmp_path)
    config = state_db.get_sources_config()
    assert config.enabled is False
    updated = state_db.set_sources_config(
        {
            "enabled": True,
            "max_depth": 2,
            "max_sources_per_page": 3,
            "allowed_domains": ["example.com"],
            "file_types": ["pdf"],
        }
    )
    assert updated.enabled is True
    persisted = state_db.get_sources_config()
    assert persisted.enabled is True
    assert persisted.max_depth == 2
    assert persisted.allowed_domains == ["example.com"]


def test_missing_sources_tracking(tmp_path: Path) -> None:
    state_db = _state_db(tmp_path)
    state_db.record_missing_source(
        "https://parent", "https://example.com/missing.pdf", reason="timeout"
    )
    state_db.record_missing_source(
        "https://parent", "https://example.com/missing.pdf", reason="timeout"
    )
    records = state_db.list_missing_sources(limit=5)
    assert len(records) == 1
    entry = records[0]
    assert entry["retries"] >= 1
    state_db.resolve_missing_source("https://parent", "https://example.com/missing.pdf")
    assert state_db.list_missing_sources(limit=5) == []


def test_handle_sources_enqueues_and_limits(tmp_path: Path) -> None:
    recorded: list[tuple[str, list[SourceLink], bool]] = []

    def _record_links(parent: str, links: list[SourceLink], mark_enqueued: bool) -> None:
        recorded.append((parent, list(links), mark_enqueued))

    missing_records: list[tuple] = []

    def _record_missing(
        parent: str,
        source_url: str,
        reason: str,
        http_status: int | None,
        next_action: str | None,
        notes: str | None,
    ) -> None:
        missing_records.append((parent, source_url, reason, http_status, next_action, notes))

    config = SourceFollowConfig(
        enabled=True,
        max_depth=1,
        max_sources_per_page=2,
        max_total_sources=1,
        allowed_domains=["example.com"],
        file_types=["pdf"],
    )
    crawler = FocusedCrawler(
        query="test",
        budget=5,
        out_dir=tmp_path,
        use_llm=False,
        model=None,
        initial_seeds=None,
        source_config=config,
        record_source_links=_record_links,
        record_missing_source=_record_missing,
    )
    crawler._queued_urls.add("https://example.com/article")
    candidate = Candidate(url="https://example.com/article", source="seed", weight=1.0)
    fingerprint = ContentFingerprint.from_text("example page")
    sources = [
        SourceLink(url="https://example.com/paper.pdf", kind="pdf"),
        SourceLink(url="https://example.com/ignored.html", kind="html"),
    ]
    result = PageResult(
        url="https://example.com/article",
        status=200,
        html="<html></html>",
        title="",
        fetched_at=time.time(),
        fingerprint=fingerprint,
        outlinks=[],
        sources=sources,
        is_source=False,
        parent_url=None,
    )
    async def _run() -> Candidate:
        queue: asyncio.Queue[Candidate] = asyncio.Queue()
        await crawler._handle_sources(candidate, result, queue)
        assert queue.qsize() == 1
        queued_candidate = await queue.get()
        await crawler._handle_sources(candidate, result, queue)
        return queued_candidate

    queued = asyncio.run(_run())
    assert queued.is_source is True
    assert queued.parent_url == "https://example.com/article"
    assert crawler.source_stats["enqueued"] == 1
    assert recorded and recorded[0][0] == "https://example.com/article"
    assert recorded[0][2] is True
    assert crawler.source_stats["budget_exhausted"] is True
    assert missing_records == []
