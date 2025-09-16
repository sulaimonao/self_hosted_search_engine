"""Configuration loader for the self-hosted search engine."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, MutableMapping

import yaml
from dotenv import load_dotenv

_CONFIG_CACHE: dict[str, Any] | None = None
CONFIG_ENV_VAR = "SELFSEARCH_CONFIG"


def _deep_update(base: MutableMapping[str, Any], overrides: MutableMapping[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, MutableMapping) and isinstance(base.get(key), MutableMapping):
            _deep_update(base[key], value)  # type: ignore[index]
        else:
            base[key] = value


def _apply_env_overrides(config: MutableMapping[str, Any]) -> None:
    def walker(prefix: str, node: MutableMapping[str, Any]) -> None:
        for key, value in node.items():
            env_key = f"{prefix}_{key}" if prefix else key
            if isinstance(value, MutableMapping):
                walker(env_key, value)
                continue
            env_value = os.getenv(env_key.upper())
            if env_value is None:
                continue
            if isinstance(value, bool):
                node[key] = env_value.lower() in {"1", "true", "yes", "on"}
            elif isinstance(value, int):
                node[key] = int(env_value)
            elif isinstance(value, float):
                node[key] = float(env_value)
            else:
                node[key] = env_value

    walker("", config)


def load_config(reload: bool = False) -> dict[str, Any]:
    """Load configuration from YAML and environment overrides."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not reload:
        return _CONFIG_CACHE

    load_dotenv()

    config_path = os.getenv(CONFIG_ENV_VAR)
    if config_path:
        path = Path(config_path).expanduser().resolve()
    else:
        path = Path(__file__).resolve().parent / "config.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found at {path}")

    with path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    if not isinstance(config, MutableMapping):
        raise ValueError("config.yaml must define a mapping")

    _apply_env_overrides(config)

    _CONFIG_CACHE = dict(config)
    return _CONFIG_CACHE


def project_root() -> Path:
    return Path(__file__).resolve().parent


def data_dir(config: dict[str, Any] | None = None) -> Path:
    cfg = config or load_config()
    frontier_path = Path(cfg["crawler"]["frontier_db"])
    return frontier_path.expanduser().resolve().parent


def index_dir(config: dict[str, Any] | None = None) -> Path:
    cfg = config or load_config()
    return Path(cfg["index"]["dir"]).expanduser().resolve()


def reset_config_cache() -> None:
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
