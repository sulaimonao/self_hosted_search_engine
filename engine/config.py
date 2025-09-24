"""Configuration loader for the RAG engine."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass(frozen=True)
class ModelConfig:
    llm_primary: str
    llm_fallback: str | None
    embed: str


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str


@dataclass(frozen=True)
class RetrievalConfig:
    k: int
    min_hits: int
    similarity_threshold: float


@dataclass(frozen=True)
class IndexConfig:
    persist_dir: Path
    db_path: Path


@dataclass(frozen=True)
class CrawlConfig:
    user_agent: str
    request_timeout: int
    read_timeout: int
    max_pages: int
    sleep_seconds: float


@dataclass(frozen=True)
class EngineConfig:
    models: ModelConfig
    ollama: OllamaConfig
    retrieval: RetrievalConfig
    index: IndexConfig
    crawl: CrawlConfig

    @staticmethod
    def _resolve_path(path_value: str | Path, base_dir: Path) -> Path:
        path = Path(path_value)
        if not path.is_absolute():
            path = base_dir / path
        return path

    @classmethod
    def from_yaml(cls, path: Path) -> "EngineConfig":
        base_dir = path.resolve().parent
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        models = data.get("models", {})
        ollama = data.get("ollama", {})
        retrieval = data.get("retrieval", {})
        index = data.get("index", {})
        crawl = data.get("crawl", {})

        model_cfg = ModelConfig(
            llm_primary=str(models.get("llm_primary", "gemma2:latest")),
            llm_fallback=str(models.get("llm_fallback")) if models.get("llm_fallback") else None,
            embed=str(models.get("embed", "embeddinggemma")),
        )
        ollama_cfg = OllamaConfig(base_url=str(ollama.get("base_url", "http://localhost:11434")))
        retrieval_cfg = RetrievalConfig(
            k=int(retrieval.get("k", 5)),
            min_hits=int(retrieval.get("min_hits", 1)),
            similarity_threshold=float(retrieval.get("similarity_threshold", 0.2)),
        )
        persist_dir_value = os.getenv(
            "CHROMA_PERSIST_DIR", index.get("persist_dir", "data/chroma")
        )
        db_path_value = os.getenv("CHROMA_DB_PATH", index.get("db_path", "data/index.duckdb"))
        index_cfg = IndexConfig(
            persist_dir=cls._resolve_path(persist_dir_value, base_dir),
            db_path=cls._resolve_path(db_path_value, base_dir),
        )
        crawl_cfg = CrawlConfig(
            user_agent=str(crawl.get("user_agent", "SelfHostedSearchBot/0.1")),
            request_timeout=int(crawl.get("request_timeout", 15)),
            read_timeout=int(crawl.get("read_timeout", 30)),
            max_pages=int(crawl.get("max_pages", 5)),
            sleep_seconds=float(crawl.get("sleep_seconds", 1.0)),
        )
        return cls(
            models=model_cfg,
            ollama=ollama_cfg,
            retrieval=retrieval_cfg,
            index=index_cfg,
            crawl=crawl_cfg,
        )


__all__ = [
    "EngineConfig",
    "ModelConfig",
    "OllamaConfig",
    "RetrievalConfig",
    "IndexConfig",
    "CrawlConfig",
]
