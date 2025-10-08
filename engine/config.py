"""Configuration loader for the RAG engine."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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
class BootstrapConfig:
    enabled: bool
    queries: tuple[str, ...]
    use_llm: bool
    llm_model: str | None


@dataclass(frozen=True)
class PlannerConfig:
    enable_critique: bool = False
    max_steps: int = 6
    max_retries_per_step: int = 2


@dataclass(frozen=True)
class EngineConfig:
    models: ModelConfig
    ollama: OllamaConfig
    retrieval: RetrievalConfig
    index: IndexConfig
    crawl: CrawlConfig
    bootstrap: BootstrapConfig | None = None
    planner: PlannerConfig = field(default_factory=PlannerConfig)

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
        bootstrap = data.get("bootstrap")
        planner_section = data.get("planner")
        planner_cfg_raw = planner_section if isinstance(planner_section, dict) else {}

        primary_value = models.get("llm_primary", "gpt-oss")
        fallback_value = models.get("llm_fallback", "gemma3")
        embed_override = os.getenv("LLM_EMBEDDER") or os.getenv("EMBED_MODEL")
        if embed_override is not None and not str(embed_override).strip():
            embed_override = None
        embed_value = embed_override or models.get("embed", "embeddinggemma")
        primary_text = str(primary_value).strip() if primary_value else ""
        fallback_text = str(fallback_value).strip() if fallback_value else ""
        embed_text = str(embed_value).strip() if embed_value else ""
        model_cfg = ModelConfig(
            llm_primary=primary_text or "gpt-oss",
            llm_fallback=fallback_text or None,
            embed=embed_text or "embeddinggemma",
        )
        env_ollama = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_HOST")
        base_url_value = env_ollama or ollama.get("base_url") or "http://127.0.0.1:11434"
        ollama_cfg = OllamaConfig(base_url=str(base_url_value).rstrip("/"))
        retrieval_cfg = RetrievalConfig(
            k=int(retrieval.get("k", 5)),
            min_hits=int(retrieval.get("min_hits", 1)),
            similarity_threshold=float(retrieval.get("similarity_threshold", 0.2)),
        )
        persist_dir_env = os.getenv("CHROMA_PERSIST_DIR")
        if persist_dir_env is not None and not persist_dir_env.strip():
            persist_dir_env = None
        persist_dir_value = persist_dir_env or index.get("persist_dir", "data/chroma")

        db_path_env = os.getenv("CHROMA_DB_PATH")
        if db_path_env is not None and not db_path_env.strip():
            db_path_env = None
        db_path_value = db_path_env or index.get("db_path", "data/index.duckdb")
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

        bootstrap_cfg: BootstrapConfig | None = None
        if isinstance(bootstrap, dict):
            raw_queries = bootstrap.get("queries", [])
            if isinstance(raw_queries, str):
                raw_queries = [raw_queries]
            queries: list[str] = []
            if isinstance(raw_queries, (list, tuple, set)):
                for item in raw_queries:
                    text = str(item).strip()
                    if text:
                        queries.append(text)
            enabled = bool(bootstrap.get("enabled", bool(queries)))
            use_llm = bool(bootstrap.get("use_llm", True))
            llm_model_raw = bootstrap.get("llm_model")
            llm_model = str(llm_model_raw).strip() if llm_model_raw else None
            if queries:
                bootstrap_cfg = BootstrapConfig(
                    enabled=enabled,
                    queries=tuple(queries),
                    use_llm=use_llm,
                    llm_model=llm_model,
                )
            elif enabled:
                bootstrap_cfg = BootstrapConfig(
                    enabled=True,
                    queries=tuple(),
                    use_llm=use_llm,
                    llm_model=llm_model,
                )

        planner_cfg = PlannerConfig(
            enable_critique=bool(planner_cfg_raw.get("enable_critique", False)),
            max_steps=int(planner_cfg_raw.get("max_steps", 6)),
            max_retries_per_step=int(planner_cfg_raw.get("max_retries_per_step", 2)),
        )

        return cls(
            models=model_cfg,
            ollama=ollama_cfg,
            retrieval=retrieval_cfg,
            index=index_cfg,
            crawl=crawl_cfg,
            bootstrap=bootstrap_cfg,
            planner=planner_cfg,
        )


__all__ = [
    "EngineConfig",
    "PlannerConfig",
    "ModelConfig",
    "OllamaConfig",
    "RetrievalConfig",
    "IndexConfig",
    "CrawlConfig",
    "BootstrapConfig",
]
