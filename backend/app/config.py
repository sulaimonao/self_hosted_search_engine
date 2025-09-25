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


REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(value: str | os.PathLike[str] | None, base: Path) -> Path:
    """Resolve ``value`` relative to ``base`` when not absolute."""

    if value is None:
        return base
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def _guard_directory(path: Path, *, label: str) -> Path:
    """Ensure ``path`` does not resolve to an unsafe location."""

    resolved = path.resolve()
    repo_root = REPO_ROOT.resolve()
    if resolved == repo_root:
        raise ValueError(f"{label} may not be the repository root ({resolved})")
    if resolved == Path(resolved.anchor):
        raise ValueError(f"{label} may not be the filesystem root ({resolved})")
    return path


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
    learned_web_db_path: Path
    frontier_db_path: Path
    agent_data_dir: Path
    agent_plans_dir: Path
    agent_sessions_dir: Path
    telemetry_dir: Path
    agent_max_fetch_per_turn: int
    agent_coverage_threshold: float
    focused_enabled: bool
    focused_budget: int
    smart_min_results: int
    smart_trigger_cooldown: int
    smart_confidence_threshold: float
    smart_seed_min_similarity: float
    smart_seed_limit: int
    search_default_limit: int
    search_max_limit: int
    max_query_length: int
    ollama_url: str
    crawl_use_playwright: str
    use_llm_rerank: bool
    chat_log_level: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        default_data_dir = REPO_ROOT / "data"
        data_dir = _resolve_path(os.getenv("DATA_DIR"), default_data_dir)
        data_dir = _guard_directory(data_dir, label="DATA_DIR")

        crawl_root_default = data_dir / "crawl"
        crawl_root = _resolve_path(os.getenv("CRAWL_STORE"), crawl_root_default)
        crawl_root = _guard_directory(crawl_root, label="CRAWL_STORE")
        crawl_raw_dir = _guard_directory(crawl_root / "raw", label="CRAWL_RAW_DIR")
        normalized_default = data_dir / "normalized" / "normalized.jsonl"
        normalized_path = _resolve_path(os.getenv("NORMALIZED_PATH"), normalized_default)
        _guard_directory(normalized_path.parent, label="NORMALIZED_PATH parent")
        index_dir_default = data_dir / "whoosh"
        index_dir = _resolve_path(os.getenv("INDEX_DIR"), index_dir_default)
        index_dir = _guard_directory(index_dir, label="INDEX_DIR")
        ledger_path = _resolve_path(os.getenv("INDEX_LEDGER"), data_dir / "index_ledger.json")
        _guard_directory(ledger_path.parent, label="INDEX_LEDGER parent")
        simhash_path = _resolve_path(os.getenv("SIMHASH_PATH"), data_dir / "simhash_index.json")
        _guard_directory(simhash_path.parent, label="SIMHASH_PATH parent")
        last_index_time_path = _resolve_path(
            os.getenv("LAST_INDEX_TIME_PATH"), data_dir / "state" / ".last_index_time"
        )
        _guard_directory(last_index_time_path.parent, label="LAST_INDEX_TIME_PATH parent")
        logs_dir = _guard_directory(
            _resolve_path(os.getenv("LOGS_DIR"), data_dir / "logs"), label="LOGS_DIR"
        )
        learned_web_db_path = _resolve_path(
            os.getenv("LEARNED_WEB_DB_PATH"), data_dir / "learned_web.sqlite3"
        )
        _guard_directory(learned_web_db_path.parent, label="LEARNED_WEB_DB_PATH parent")

        agent_root_default = data_dir / "agent"
        agent_root = _resolve_path(os.getenv("AGENT_DATA_DIR"), agent_root_default)
        agent_root = _guard_directory(agent_root, label="AGENT_DATA_DIR")
        agent_plans_dir = _guard_directory(agent_root / "plans", label="AGENT_PLANS_DIR")
        agent_sessions_dir = _guard_directory(agent_root / "sessions", label="AGENT_SESSIONS_DIR")
        frontier_db_path = _resolve_path(
            os.getenv("FRONTIER_DB_PATH"), agent_root / "frontier.sqlite3"
        )
        _guard_directory(frontier_db_path.parent, label="FRONTIER_DB_PATH parent")
        telemetry_dir_default = data_dir / "telemetry"
        telemetry_dir = _guard_directory(
            _resolve_path(os.getenv("TELEMETRY_DIR"), telemetry_dir_default),
            label="TELEMETRY_DIR",
        )
        agent_max_fetch_per_turn = max(1, int(os.getenv("AGENT_MAX_FETCH_PER_TURN", "3")))
        agent_coverage_threshold = float(os.getenv("AGENT_COVERAGE_THRESHOLD", "0.6"))

        focused_enabled = os.getenv("FOCUSED_CRAWL_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
        focused_budget = max(1, int(os.getenv("FOCUSED_CRAWL_BUDGET", "10")))
        smart_min_results = max(0, int(os.getenv("SMART_MIN_RESULTS", "1")))
        smart_trigger_cooldown = max(0, int(os.getenv("SMART_TRIGGER_COOLDOWN", "900")))
        smart_confidence_threshold = float(os.getenv("SMART_CONFIDENCE_THRESHOLD", "0.35"))
        smart_seed_min_similarity = float(os.getenv("SMART_SEED_MIN_SIMILARITY", "0.35"))
        smart_seed_limit = max(0, int(os.getenv("SMART_SEED_LIMIT", "12")))
        search_default_limit = max(1, int(os.getenv("SEARCH_DEFAULT_LIMIT", "20")))
        search_max_limit = max(search_default_limit, int(os.getenv("SEARCH_MAX_LIMIT", "50")))
        max_query_length = max(32, int(os.getenv("SEARCH_MAX_QUERY_LENGTH", "256")))
        ollama_url = os.getenv("OLLAMA_URL", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        crawl_use_playwright = os.getenv("CRAWL_USE_PLAYWRIGHT", "auto").lower()
        use_llm_rerank = os.getenv("USE_LLM_RERANK", "false").lower() in {"1", "true", "yes", "on"}
        chat_log_level_name = os.getenv("CHAT_LOG_LEVEL", "INFO").upper()
        chat_log_level = getattr(logging, chat_log_level_name, logging.INFO)

        return cls(
            index_dir=index_dir,
            crawl_raw_dir=crawl_raw_dir,
            normalized_path=normalized_path,
            ledger_path=ledger_path,
            simhash_path=simhash_path,
            last_index_time_path=last_index_time_path,
            logs_dir=logs_dir,
            learned_web_db_path=learned_web_db_path,
            frontier_db_path=frontier_db_path,
            agent_data_dir=agent_root,
            agent_plans_dir=agent_plans_dir,
            agent_sessions_dir=agent_sessions_dir,
            telemetry_dir=telemetry_dir,
            agent_max_fetch_per_turn=agent_max_fetch_per_turn,
            agent_coverage_threshold=agent_coverage_threshold,
            focused_enabled=focused_enabled,
            focused_budget=focused_budget,
            smart_min_results=smart_min_results,
            smart_trigger_cooldown=smart_trigger_cooldown,
            smart_confidence_threshold=smart_confidence_threshold,
            smart_seed_min_similarity=smart_seed_min_similarity,
            smart_seed_limit=smart_seed_limit,
            search_default_limit=search_default_limit,
            search_max_limit=search_max_limit,
            max_query_length=max_query_length,
            ollama_url=ollama_url,
            crawl_use_playwright=crawl_use_playwright,
            use_llm_rerank=use_llm_rerank,
            chat_log_level=chat_log_level,
        )

    def ensure_dirs(self) -> None:
        """Ensure all required directories exist."""

        for directory in (
            self.index_dir,
            self.crawl_raw_dir,
            self.logs_dir,
            self.normalized_path.parent,
            self.ledger_path.parent,
            self.simhash_path.parent,
            self.last_index_time_path.parent,
            self.learned_web_db_path.parent,
            self.frontier_db_path.parent,
            self.agent_data_dir,
            self.agent_plans_dir,
            self.agent_sessions_dir,
            self.telemetry_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def log_summary(self) -> None:
        """Log environment-derived flags for observability."""

        payload: Dict[str, Any] = {
            "focused_enabled": self.focused_enabled,
            "focused_budget": self.focused_budget,
            "smart_min_results": self.smart_min_results,
            "smart_trigger_cooldown": self.smart_trigger_cooldown,
            "smart_confidence_threshold": self.smart_confidence_threshold,
            "smart_seed_min_similarity": self.smart_seed_min_similarity,
            "smart_seed_limit": self.smart_seed_limit,
            "search_default_limit": self.search_default_limit,
            "search_max_limit": self.search_max_limit,
            "max_query_length": self.max_query_length,
            "ollama_url": self.ollama_url,
            "crawl_use_playwright": self.crawl_use_playwright,
            "use_llm_rerank": self.use_llm_rerank,
            "learned_web_db_path": str(self.learned_web_db_path),
            "frontier_db_path": str(self.frontier_db_path),
            "agent_data_dir": str(self.agent_data_dir),
            "agent_max_fetch_per_turn": self.agent_max_fetch_per_turn,
            "agent_coverage_threshold": self.agent_coverage_threshold,
            "chat_log_level": logging.getLevelName(self.chat_log_level),
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
