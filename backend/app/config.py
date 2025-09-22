"""Application configuration helpers."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import requests

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class AppConfig:
    """Runtime configuration resolved from environment variables."""

    index_dir: Path
    crawl_raw_dir: Path
    normalized_path: Path
    ledger_path: Path
    simhash_path: Path
    last_index_time_path: Path
    logs_dir: Path
    focused_enabled: bool
    focused_budget: int
    smart_min_results: int
    smart_trigger_cooldown: int
    smart_min_confidence: float
    search_default_limit: int
    search_max_limit: int
    max_query_length: int
    ollama_url: str
    crawl_use_playwright: str
    use_llm_rerank: bool
    learned_web_db: Path
    learned_seed_limit: int
    learned_min_similarity: float

    @classmethod
    def from_env(cls) -> "AppConfig":
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        crawl_root = Path(os.getenv("CRAWL_STORE", data_dir / "crawl"))
        crawl_raw_dir = crawl_root / "raw"
        normalized_path = Path(os.getenv("NORMALIZED_PATH", data_dir / "normalized.jsonl"))
        index_dir = Path(os.getenv("INDEX_DIR", data_dir / "index"))
        ledger_path = Path(os.getenv("INDEX_LEDGER", data_dir / "index_ledger.json"))
        simhash_path = Path(os.getenv("SIMHASH_PATH", data_dir / "simhash_index.json"))
        last_index_time_path = Path(os.getenv("LAST_INDEX_TIME_PATH", data_dir / ".last_index_time"))
        logs_dir = Path(os.getenv("LOGS_DIR", data_dir / "logs"))

        focused_enabled = os.getenv("FOCUSED_CRAWL_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
        focused_budget = max(1, int(os.getenv("FOCUSED_CRAWL_BUDGET", "10")))
        smart_min_results = max(0, int(os.getenv("SMART_MIN_RESULTS", "1")))
        smart_trigger_cooldown = max(0, int(os.getenv("SMART_TRIGGER_COOLDOWN", "900")))
        smart_min_confidence = float(os.getenv("SMART_MIN_CONFIDENCE", "0.35"))
        search_default_limit = max(1, int(os.getenv("SEARCH_DEFAULT_LIMIT", "20")))
        search_max_limit = max(search_default_limit, int(os.getenv("SEARCH_MAX_LIMIT", "50")))
        max_query_length = max(32, int(os.getenv("SEARCH_MAX_QUERY_LENGTH", "256")))
        ollama_url = os.getenv("OLLAMA_URL", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        crawl_use_playwright = os.getenv("CRAWL_USE_PLAYWRIGHT", "auto").lower()
        use_llm_rerank = os.getenv("USE_LLM_RERANK", "false").lower() in {"1", "true", "yes", "on"}
        learned_web_db = Path(os.getenv("LEARNED_WEB_DB", data_dir / "learned_web" / "discoveries.sqlite3"))
        learned_seed_limit = max(0, int(os.getenv("LEARNED_WEB_SEED_LIMIT", "10")))
        learned_min_similarity = float(os.getenv("LEARNED_WEB_MIN_SIMILARITY", "0.25"))

        return cls(
            index_dir=index_dir,
            crawl_raw_dir=crawl_raw_dir,
            normalized_path=normalized_path,
            ledger_path=ledger_path,
            simhash_path=simhash_path,
            last_index_time_path=last_index_time_path,
            logs_dir=logs_dir,
            focused_enabled=focused_enabled,
            focused_budget=focused_budget,
            smart_min_results=smart_min_results,
            smart_trigger_cooldown=smart_trigger_cooldown,
            smart_min_confidence=smart_min_confidence,
            search_default_limit=search_default_limit,
            search_max_limit=search_max_limit,
            max_query_length=max_query_length,
            ollama_url=ollama_url,
            crawl_use_playwright=crawl_use_playwright,
            use_llm_rerank=use_llm_rerank,
            learned_web_db=learned_web_db,
            learned_seed_limit=learned_seed_limit,
            learned_min_similarity=learned_min_similarity,
        )

    def ensure_dirs(self) -> None:
        """Ensure all required directories exist."""

        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.crawl_raw_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.simhash_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_index_time_path.parent.mkdir(parents=True, exist_ok=True)
        self.learned_web_db.parent.mkdir(parents=True, exist_ok=True)

    def log_summary(self) -> None:
        """Log environment-derived flags for observability."""

        payload: Dict[str, Any] = {
            "focused_enabled": self.focused_enabled,
            "focused_budget": self.focused_budget,
            "smart_min_results": self.smart_min_results,
            "smart_trigger_cooldown": self.smart_trigger_cooldown,
            "smart_min_confidence": round(self.smart_min_confidence, 3),
            "search_default_limit": self.search_default_limit,
            "search_max_limit": self.search_max_limit,
            "max_query_length": self.max_query_length,
            "ollama_url": self.ollama_url,
            "crawl_use_playwright": self.crawl_use_playwright,
            "use_llm_rerank": self.use_llm_rerank,
            "learned_web_db": str(self.learned_web_db),
            "learned_seed_limit": self.learned_seed_limit,
            "learned_min_similarity": round(self.learned_min_similarity, 3),
        }
        LOGGER.info("runtime configuration: %s", json.dumps(payload, sort_keys=True))

        if not self._ollama_reachable():
            LOGGER.warning("Ollama URL %s is not reachable; LLM enrichment disabled", self.ollama_url)

    def _ollama_reachable(self) -> bool:
        try:
            response = requests.get(self.ollama_url, timeout=1)
        except Exception:
            return False
        return response.status_code < 500
