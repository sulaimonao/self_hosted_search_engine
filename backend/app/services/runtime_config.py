"""Runtime configuration service backed by the application state DB."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from backend.app.db import AppStateDB


@dataclass(frozen=True, slots=True)
class ConfigField:
    key: str
    type: str
    label: str
    description: str
    default: Any
    options: tuple[str, ...] | None = None
    section: str = "general"
    group: str | None = None


_REQUIRED_MODEL_CHOICES = ("gemma-3", "gpt-oss")
_EMBED_MODEL_CHOICES = ("embeddinggemma",)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_choice(value: Any, *, choices: Iterable[str], default: str) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        lowered = candidate.lower()
        for choice in choices:
            if lowered == choice.lower():
                return choice
    return default


_FIELDS: tuple[ConfigField, ...] = (
    ConfigField(
        key="models.chat.primary",
        type="select",
        label="Primary chat model",
        description="Default chat model offered to the assistant UI.",
        default="gemma-3",
        options=_REQUIRED_MODEL_CHOICES,
        section="models",
    ),
    ConfigField(
        key="models.chat.fallback",
        type="select",
        label="Fallback chat model",
        description="Used when the primary model is unavailable or busy.",
        default="gpt-oss",
        options=_REQUIRED_MODEL_CHOICES,
        section="models",
    ),
    ConfigField(
        key="models.embedding.primary",
        type="select",
        label="Embedding model",
        description="Vector store embedding model used for hybrid search.",
        default="embeddinggemma",
        options=_EMBED_MODEL_CHOICES,
        section="models",
    ),
    ConfigField(
        key="features.shadow_mode",
        type="boolean",
        label="Shadow mode",
        description="Mirror your browsing session for offline replay.",
        default=False,
        section="chat_tools",
    ),
    ConfigField(
        key="features.agent_mode",
        type="boolean",
        label="Agent mode",
        description="Allow the assistant to stage multi-step browsing plans.",
        default=True,
        section="chat_tools",
    ),
    ConfigField(
        key="features.local_discovery",
        type="boolean",
        label="Local discovery",
        description="Stream link previews and domain annotations in real time.",
        default=True,
        section="chat_tools",
    ),
    ConfigField(
        key="features.browsing_fallbacks",
        type="boolean",
        label="Browser fallbacks",
        description="Auto-open the desktop browser when the embedded engine fails.",
        default=True,
        section="privacy",
    ),
    ConfigField(
        key="index.auto_rebuild",
        type="boolean",
        label="Auto rebuild index",
        description="Automatically rebuild keyword + vector indexes when corruption is detected.",
        default=True,
        section="index",
    ),
    ConfigField(
        key="index.auto_refresh",
        type="boolean",
        label="Auto refresh frontier",
        description="Refresh discovery queues when new favourite sources are added.",
        default=True,
        section="index",
    ),
    ConfigField(
        key="privacy.persist_history",
        type="boolean",
        label="Persist browsing history",
        description="Store visited URLs in the local history database.",
        default=True,
        section="privacy",
    ),
    ConfigField(
        key="privacy.persist_cookies",
        type="boolean",
        label="Persist cookies",
        description="Retain session cookies between application launches.",
        default=True,
        section="privacy",
    ),
    ConfigField(
        key="privacy.desktop_permissions",
        type="boolean",
        label="Sync site permissions",
        description="Share permission prompts between the desktop shell and the web UI.",
        default=True,
        section="privacy",
    ),
    ConfigField(
        key="developer.verbose_logging",
        type="boolean",
        label="Verbose logging",
        description="Emit detailed debug logs for troubleshooting.",
        default=False,
        section="developer",
    ),
    ConfigField(
        key="developer.experimental_features",
        type="boolean",
        label="Experimental surfaces",
        description="Expose in-development UI and crawler features.",
        default=False,
        section="developer",
    ),
    ConfigField(
        key="setup.completed",
        type="boolean",
        label="Setup completed",
        description="Tracks whether the first-run wizard has been acknowledged.",
        default=False,
        section="setup",
    ),
)


class RuntimeConfigService:
    """High-level configuration manager used by the Control Center UI."""

    schema_version = 1

    def __init__(self, state_db: AppStateDB) -> None:
        self._db = state_db
        self._defaults = {field.key: field.default for field in _FIELDS}
        self._field_index = {field.key: field for field in _FIELDS}

    # ------------------------------------------------------------------
    # Schema accessors
    def schema(self) -> dict[str, Any]:
        sections: dict[str, dict[str, Any]] = {}
        for field in _FIELDS:
            section = sections.setdefault(
                field.section,
                {
                    "id": field.section,
                    "label": _section_label(field.section),
                    "fields": [],
                },
            )
            section["fields"].append(
                {
                    "key": field.key,
                    "type": field.type,
                    "label": field.label,
                    "description": field.description,
                    "default": field.default,
                    "options": list(field.options) if field.options else None,
                }
            )
        ordered = [sections[key] for key in _section_order(sections.keys())]
        return {
            "version": self.schema_version,
            "sections": ordered,
        }

    # ------------------------------------------------------------------
    # CRUD helpers
    def snapshot(self) -> dict[str, Any]:
        stored = self._db.config_snapshot()
        merged = self._defaults.copy()
        for key, value in stored.items():
            if key not in self._field_index:
                merged[key] = value
            else:
                merged[key] = self._validate_value(key, value)
        return merged

    def get(self, key: str, default: Any | None = None) -> Any:
        if key not in self._field_index:
            return self._db.get_config(key, default)
        return self._validate_value(key, self._db.get_config(key, self._defaults.get(key)))

    def update(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        sanitized: dict[str, Any] = {}
        passthrough: dict[str, Any] = {}
        for key, value in payload.items():
            if key in self._field_index:
                sanitized[key] = self._validate_value(key, value)
            else:
                passthrough[str(key)] = value
        if sanitized:
            self._db.update_config(sanitized)
        if passthrough:
            self._db.update_config(passthrough)
        return self.snapshot()

    # ------------------------------------------------------------------
    # Internal helpers
    def _validate_value(self, key: str, value: Any) -> Any:
        field = self._field_index.get(key)
        if field is None:
            return value
        if field.type == "boolean":
            return _as_bool(value)
        if field.type == "select" and field.options:
            return _as_choice(value, choices=field.options, default=field.default)
        return value


def _section_label(section: str) -> str:
    mapping = {
        "models": "Models",
        "index": "Index & Crawler",
        "chat_tools": "Chat & Tools",
        "privacy": "Privacy & Session",
        "developer": "Developer",
        "setup": "Setup",
    }
    return mapping.get(section, section.replace("_", " ").title())


def _section_order(sections: Iterable[str]) -> list[str]:
    order = ["models", "index", "chat_tools", "privacy", "developer", "setup"]
    remaining = [section for section in sections if section not in order]
    return order + sorted(remaining)


__all__ = [
    "RuntimeConfigService",
]
