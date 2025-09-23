import pytest

from server.seeds_loader import load_seed_registry


def test_load_seed_registry_normalizes(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
        version: 1
        crawl_defaults:
          strategy: Crawl
          trust: Medium
          tags:
            - Global
        directories:
          knowledge:
            defaults:
              kind: CURATED
              strategy: Sitemap
              tags:
                - Docs
            sources:
              - id: Docs
                entrypoints:
                  - https://example.com/docs
                  - { url: https://example.com/docs }
                  - https://example.com/docs?ref=dup
                trust: High
                notes: keep-me
                tags:
                  - Primary
              - id: numeric_trust
                entrypoints: https://example.net/api
                trust: 0.75
        sources:
          - id: legacy
            kind: aggregator
            strategy: feed
            entrypoints:
              - https://legacy.example.org
            trust: low
        """,
        encoding="utf-8",
    )

    entries = load_seed_registry(registry)
    assert len(entries) == 3
    by_id = {entry.id: entry for entry in entries}

    docs_entry = by_id["Docs"]
    assert docs_entry.kind == "curated"
    assert docs_entry.strategy == "sitemap"
    assert docs_entry.entrypoints == (
        "https://example.com/docs",
        "https://example.com/docs?ref=dup",
    )
    assert docs_entry.trust == "high"
    assert docs_entry.extras["notes"] == "keep-me"
    assert docs_entry.extras["collection"] == "knowledge"
    assert docs_entry.extras["tags"] == ["global", "docs", "primary"]

    numeric_entry = by_id["numeric_trust"]
    assert numeric_entry.strategy == "sitemap"
    assert numeric_entry.trust == pytest.approx(0.75)
    assert numeric_entry.entrypoints == ("https://example.net/api",)
    assert numeric_entry.extras["tags"] == ["global", "docs"]

    legacy_entry = by_id["legacy"]
    assert legacy_entry.kind == "aggregator"
    assert legacy_entry.strategy == "feed"
    assert legacy_entry.entrypoints == ("https://legacy.example.org",)
    assert "collection" not in legacy_entry.extras


def test_load_seed_registry_accepts_top_level_array(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
        - id: array
          kind: curated
          strategy: crawl
          entrypoints:
            - https://example.org
          trust: medium
        """,
        encoding="utf-8",
    )

    entries = load_seed_registry(registry)
    assert len(entries) == 1
    assert entries[0].id == "array"


def test_load_seed_registry_detects_duplicates(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
        version: 1
        directories:
          dup_one:
            defaults:
              kind: curated
              strategy: crawl
            sources:
              - id: dup
                entrypoints:
                  - https://example.com
          dup_two:
            defaults:
              kind: curated
              strategy: crawl
            sources:
              - id: dup
                entrypoints:
                  - https://example.net
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_seed_registry(registry)


def test_load_seed_registry_missing_file_returns_empty(tmp_path):
    registry = tmp_path / "missing.yaml"
    assert load_seed_registry(registry) == []


def test_load_seed_registry_rejects_relative_entrypoints(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
        version: 1
        directories:
          invalid:
            defaults:
              kind: curated
              strategy: crawl
            sources:
              - id: bad
                entrypoints:
                  - /relative/path
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_seed_registry(registry)
