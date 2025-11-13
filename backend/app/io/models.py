"""Pydantic models shared across FE/BE/LLM/Agent boundaries."""

from __future__ import annotations

import json
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VERB_MAP: dict[str, str] = {
    "navigate": "navigate",
    "goto": "navigate",
    "go": "navigate",
    "open": "navigate",
    "reload": "reload",
    "refresh": "reload",
    "click": "click",
    "press": "click",
    "tap": "click",
    "type": "type",
    "input": "type",
    "enter": "type",
    "wait": "waitForStable",
    "waitforstable": "waitForStable",
    "waitfor": "waitForStable",
    "pause": "waitForStable",
}
"""Mapping of loosely specified verbs to canonical executor verbs."""

ALLOWED_VERBS: set[str] = {"navigate", "reload", "click", "type", "waitForStable"}
"""Supported verbs for the executor boundary."""

VERB_EXECUTION_METADATA: dict[str, dict[str, bool]] = {
    "navigate": {"headless": True, "inTab": True},
    "reload": {"headless": True, "inTab": True},
    "click": {"headless": True, "inTab": True},
    "type": {"headless": True, "inTab": True},
    "waitForStable": {"headless": True, "inTab": True},
}
"""Executor verb capabilities exposed through shared schemas."""

_ALLOWED_CONFIDENCE = {"low", "medium", "high"}
_DEFAULT_REASON = "Planned fix"
_MAX_DOM = 4_096


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _coerce_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value).strip()
    return ""


def _normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


class Step(BaseModel):
    """Normalized executor step."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str | None = None
    type: str = Field(default="reload")
    args: dict[str, Any] = Field(default_factory=dict)
    headless: bool = False
    selector: str | None = None
    text: str | None = None
    url: str | None = None
    ms: int | None = None
    verify: dict[str, Any] | None = None
    on_fail_next: str | None = Field(default=None, alias="onFailNext")

    @model_validator(mode="before")
    @classmethod
    def _from_any(cls, value: Any) -> Mapping[str, Any]:
        if isinstance(value, Step):
            return value.model_dump(mode="json")
        if isinstance(value, Mapping):
            payload = dict(value)
            if "type" not in payload:
                for key in ("verb", "action"):
                    if key in payload and isinstance(payload[key], str):
                        payload["type"] = payload[key]
                        break
            return payload
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"type": value}
            if isinstance(parsed, Mapping):
                payload = dict(parsed)
                if "type" not in payload:
                    for key in ("verb", "action"):
                        if key in payload and isinstance(payload[key], str):
                            payload["type"] = payload[key]
                            break
                return payload
        return {}

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: Any) -> str:
        if isinstance(value, str):
            token = value.strip().lower().replace(" ", "")
        else:
            token = ""
        if not token:
            return ""
        canonical = VERB_MAP.get(token, token)
        if canonical not in ALLOWED_VERBS:
            return ""
        return canonical

    @field_validator("args", mode="before")
    @classmethod
    def _normalize_args(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    @field_validator("headless", mode="before")
    @classmethod
    def _coerce_headless(cls, value: Any) -> bool:
        normalized = _normalize_bool(value)
        return bool(normalized)

    @model_validator(mode="after")
    def _promote_fields(self) -> "Step":
        args = {k: v for k, v in (self.args or {}).items() if v is not None}
        for key in ("selector", "text", "url", "ms"):
            attr = getattr(self, key)
            if attr is None and key in args:
                setattr(self, key, args[key])
            elif attr is not None:
                args.setdefault(key, attr)
        if self.ms is not None:
            try:
                ms_int = int(float(self.ms))
            except (TypeError, ValueError):
                ms_int = None
            if ms_int is not None and ms_int >= 0:
                self.ms = ms_int
                args["ms"] = ms_int
            else:
                self.ms = None
                args.pop("ms", None)
        self.args = args
        if self.verify is not None and not isinstance(self.verify, Mapping):
            self.verify = None
        if self.on_fail_next:
            self.on_fail_next = str(self.on_fail_next).strip() or None
        if self.id:
            self.id = str(self.id).strip() or None
        return self

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type if self.type in ALLOWED_VERBS else "reload"
        }
        if self.selector:
            payload["selector"] = self.selector
        if self.text:
            payload["text"] = self.text
        if self.url:
            payload["url"] = self.url
        if self.ms is not None:
            payload["ms"] = self.ms
        if self.headless:
            payload["headless"] = True
        if self.verify:
            payload["verify"] = self.verify
        if self.on_fail_next:
            payload["onFailNext"] = self.on_fail_next
        return payload


class Directive(BaseModel):
    """Structured planner directive consumed by executors."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    reason: str = _DEFAULT_REASON
    steps: list[Step] = Field(default_factory=list)
    plan_confidence: str | None = Field(default=None, alias="planConfidence")
    needs_user_permission: bool | None = Field(
        default=None, alias="needsUserPermission"
    )
    ask_user: list[str] = Field(default_factory=list, alias="askUser")
    fallback: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Mapping[str, Any]:
        if isinstance(value, Directive):
            return value.model_dump(mode="json", by_alias=True)
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"reason": value}
            if isinstance(parsed, Mapping):
                return dict(parsed)
        return {}

    @field_validator("reason", mode="before")
    @classmethod
    def _normalize_reason(cls, value: Any) -> str:
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
        return _DEFAULT_REASON

    @field_validator("plan_confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: Any) -> str | None:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _ALLOWED_CONFIDENCE:
                return lowered
        return None

    @field_validator("needs_user_permission", mode="before")
    @classmethod
    def _normalize_permission(cls, value: Any) -> bool | None:
        return _normalize_bool(value)

    @field_validator("ask_user", mode="before")
    @classmethod
    def _normalize_questions(cls, value: Any) -> list[str]:
        items: list[str] = []
        if isinstance(value, str):
            value = [value]
        if isinstance(value, Mapping):
            value = list(value.values())
        if isinstance(value, (list, tuple, set)):
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        items.append(text)
        return items

    @field_validator("fallback", mode="before")
    @classmethod
    def _normalize_fallback(cls, value: Any) -> dict[str, Any] | None:
        payload = _to_dict(value)
        if not payload:
            return None
        enabled = _normalize_bool(payload.get("enabled"))
        if enabled is not None:
            payload["enabled"] = enabled
        hints = payload.get("headless_hint")
        if isinstance(hints, (list, tuple)):
            payload["headless_hint"] = [
                str(item).strip() for item in hints if str(item).strip()
            ]
        return payload or None

    @model_validator(mode="after")
    def _ensure_steps(self) -> "Directive":
        filtered: list[Step] = []
        for raw in self.steps or []:
            if isinstance(raw, Step):
                step = raw
            else:
                try:
                    step = Step.model_validate(raw)
                except Exception:
                    continue
            if step.type not in ALLOWED_VERBS:
                continue
            filtered.append(step)
        if not filtered:
            filtered = [Step(type="reload")]
        self.steps = filtered
        if not self.ask_user:
            self.ask_user = []
        return self

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reason": self.reason,
            "steps": [step.as_payload() for step in self.steps]
            or [Step(type="reload").as_payload()],
        }
        if self.plan_confidence in _ALLOWED_CONFIDENCE:
            payload["plan_confidence"] = self.plan_confidence
        if self.needs_user_permission is not None:
            payload["needs_user_permission"] = self.needs_user_permission
        if self.ask_user:
            payload["ask_user"] = self.ask_user
        if self.fallback:
            fallback_clean = {
                k: v for k, v in self.fallback.items() if v not in (None, [], {})
            }
            if fallback_clean:
                payload["fallback"] = fallback_clean
        return payload


class Incident(BaseModel):
    """Incident snapshot shared with planner."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    url: str = ""
    symptoms: dict[str, Any] = Field(default_factory=dict)
    dom_snippet: str = Field(default="", alias="domSnippet")

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Mapping[str, Any]:
        if isinstance(value, Incident):
            return value.model_dump(mode="json", by_alias=True)
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"url": value}
            if isinstance(parsed, Mapping):
                return dict(parsed)
        return {}

    @field_validator("id", "url", mode="before")
    @classmethod
    def _normalize_identity(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

    @field_validator("symptoms", mode="before")
    @classmethod
    def _normalize_symptoms(cls, value: Any) -> dict[str, Any]:
        data = _to_dict(value)
        console = data.get("consoleErrors")
        if isinstance(console, (list, tuple)):
            cleaned: list[str] = []
            for entry in console:
                text_value = ""
                if isinstance(entry, str):
                    text_value = entry.strip()
                elif isinstance(entry, Mapping):
                    candidate = (
                        entry.get("message") or entry.get("error") or entry.get("text")
                    )
                    if isinstance(candidate, str):
                        candidate_text = candidate.strip()
                        if candidate_text:
                            text_value = candidate_text
                elif entry is not None:
                    text_value = str(entry).strip()
                if text_value and any(
                    token in text_value.lower()
                    for token in ("error", "exception", "fail")
                ):
                    cleaned.append(text_value)
            if cleaned:
                data["consoleErrors"] = cleaned[-5:]
            else:
                data.pop("consoleErrors", None)
        network = data.get("networkErrors")
        if isinstance(network, (list, tuple)):
            normalized: list[dict[str, Any]] = []
            for entry in network:
                if isinstance(entry, Mapping):
                    payload: dict[str, Any] = {}
                    url = _coerce_str(entry.get("url"))
                    if url:
                        payload["url"] = url
                    status_value = entry.get("status")
                    if status_value is not None:
                        try:
                            payload["status"] = int(status_value)
                        except (TypeError, ValueError):
                            pass
                    if payload:
                        normalized.append(payload)
            if normalized:
                data["networkErrors"] = normalized[-5:]
            else:
                data.pop("networkErrors", None)
        banner = data.get("bannerText")
        if isinstance(banner, str):
            trimmed = banner.strip()
            if trimmed:
                data["bannerText"] = trimmed
            else:
                data.pop("bannerText", None)
        return data

    @field_validator("dom_snippet", mode="before")
    @classmethod
    def _normalize_dom(cls, value: Any) -> str:
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed[:_MAX_DOM]
        return ""

    def as_payload(self) -> dict[str, Any]:
        payload = self.model_dump(by_alias=True)
        payload["domSnippet"] = payload.get("domSnippet", "")[:_MAX_DOM]
        return payload


__all__ = [
    "ALLOWED_VERBS",
    "Directive",
    "Incident",
    "Step",
    "VERB_MAP",
]
