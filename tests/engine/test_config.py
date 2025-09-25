"""Tests for engine configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.config import EngineConfig


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  llm_primary: test-primary
  llm_fallback: null
  embed: test-embed
ollama:
  base_url: http://localhost
retrieval:
  k: 1
  min_hits: 1
  similarity_threshold: 0.0
index:
  persist_dir: ./data/chroma
  db_path: ./data/index.duckdb
crawl:
  user_agent: test-agent
  request_timeout: 1
  read_timeout: 1
  max_pages: 1
  sleep_seconds: 0.0
""".strip()
    )
    return config_path


def test_blank_chroma_env_uses_config_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("CHROMA_PERSIST_DIR", "")
    monkeypatch.setenv("CHROMA_DB_PATH", " \t ")

    cfg = EngineConfig.from_yaml(config_path)

    assert cfg.index.persist_dir == config_path.parent / "data/chroma"
    assert cfg.index.db_path == config_path.parent / "data/index.duckdb"


def test_non_empty_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("CHROMA_PERSIST_DIR", "./custom/chroma")
    monkeypatch.setenv("CHROMA_DB_PATH", "./custom/index.duckdb")

    cfg = EngineConfig.from_yaml(config_path)

    assert cfg.index.persist_dir == config_path.parent / "custom/chroma"
    assert cfg.index.db_path == config_path.parent / "custom/index.duckdb"
