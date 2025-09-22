import pytest

from server.seeds_loader import load_seed_registry


def test_load_seed_registry_normalizes(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
        sources:
          - id: Docs
            kind: CURATED
            strategy: Sitemap
            entrypoints:
              - https://example.com/docs
              - { url: https://example.com/docs }
              - https://example.com/docs?ref=dup
            trust: High
            notes: keep-me
          - id: numeric_trust
            kind: mirror
            strategy: manual
            entrypoints: https://example.net/api
            trust: 0.75
        """,
        encoding="utf-8",
    )

    entries = load_seed_registry(registry)
    assert len(entries) == 2

    docs_entry = entries[0]
    assert docs_entry.id == "Docs"
    assert docs_entry.kind == "curated"
    assert docs_entry.strategy == "sitemap"
    assert docs_entry.entrypoints == (
        "https://example.com/docs",
        "https://example.com/docs?ref=dup",
    )
    assert docs_entry.trust == "high"
    assert docs_entry.extras == {"notes": "keep-me"}

    numeric_entry = entries[1]
    assert numeric_entry.trust == pytest.approx(0.75)
    assert numeric_entry.entrypoints == ("https://example.net/api",)


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
        sources:
          - id: dup
            kind: curated
            strategy: crawl
            entrypoints:
              - https://example.com
            trust: low
          - id: dup
            kind: curated
            strategy: crawl
            entrypoints:
              - https://example.net
            trust: low
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
        sources:
          - id: bad
            kind: curated
            strategy: crawl
            entrypoints:
              - /relative/path
            trust: low
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_seed_registry(registry)
