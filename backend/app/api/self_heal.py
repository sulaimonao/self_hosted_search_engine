"""Self-heal orchestrator: accepts BrowserIncident and returns an AutopilotDirective."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from flask import Blueprint, current_app, jsonify, request

from backend.app.ai.self_heal_prompt import ALLOWED_VERBS, build_prompts
from backend.app.api.reasoning import route_to_browser  # noqa: F401 - imported for future integration
from backend.app.llm.ollama_client import (
    DEFAULT_MODEL as DEFAULT_SELF_HEAL_MODEL,
    OllamaClient,
)
from backend.app.self_heal.episodes import append_episode
from backend.app.self_heal.metrics import record_event
from backend.app.self_heal.rules import try_rules_first
from backend.app.services.progress_bus import ProgressBus

bp = Blueprint("self_heal_api", __name__, url_prefix="/api")

LOGGER = logging.getLogger(__name__)
DEFAULT_VARIANT = "lite"
_VALID_VARIANTS = {"lite", "deep", "headless", "repair"}
_DIAGNOSTIC_JOB_ID = "__diagnostics__"


@dataclass(slots=True)
class SelfHealDirective:
    """Structured directive consumed by the in-tab executor."""

    reason: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    plan_confidence: Optional[str] = None
    needs_user_permission: Optional[bool] = None
    ask_user: Optional[List[str]] = None
    fallback: Optional[Dict[str, Any]] = None

    def model_dump(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"reason": self.reason, "steps": self.steps}
        if self.plan_confidence:
            payload["plan_confidence"] = self.plan_confidence
        if self.needs_user_permission is not None:
            payload["needs_user_permission"] = self.needs_user_permission
        if self.ask_user:
            payload["ask_user"] = self.ask_user
        if self.fallback:
            payload["fallback"] = self.fallback
        return payload


_OLLAMA_CLIENT = OllamaClient()


def _coerce_incident(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "url": str(payload.get("url") or ""),
        "symptoms": dict(payload.get("symptoms") or {}),
        "domSnippet": (payload.get("domSnippet") or "")[:4000],
    }


def _publish_diagnostic(stage: str, message: str, **extra: Any) -> None:
    event: Dict[str, Any] = {"stage": stage, "message": message}
    for key, value in extra.items():
        if value is None:
            continue
        event[key] = value
    try:
        bus: ProgressBus | None = current_app.config.get("PROGRESS_BUS")
    except RuntimeError:
        bus = None
    if isinstance(bus, ProgressBus):
        bus.publish(_DIAGNOSTIC_JOB_ID, event)


def _coerce_variant(raw: str | None) -> str:
    if not isinstance(raw, str):
        return DEFAULT_VARIANT
    variant = raw.strip().lower()
    if variant in _VALID_VARIANTS:
        return variant
    return DEFAULT_VARIANT


def _coerce_str(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return ""


def _parse_plan(response: Any) -> Dict[str, Any]:
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, str):
        try:
            return json.loads(response)
        except json.JSONDecodeError as exc:
            raise ValueError(f"planner returned invalid JSON: {exc}") from exc
    raise TypeError("planner response must be a string or mapping")


def _fallback_directive(reason: str) -> SelfHealDirective:
    return SelfHealDirective(reason=reason, steps=[{"type": "reload"}], plan_confidence="low")


def _validate_and_coerce(plan: Mapping[str, Any]) -> Tuple[SelfHealDirective, List[str], bool]:
    notes: List[str] = []
    steps_payload: List[Dict[str, Any]] = []
    steps_in = plan.get("steps")
    if not isinstance(steps_in, list):
        notes.append("Planner payload missing steps array; will fallback to reload().")
        reason = _coerce_str(plan.get("reason")) or "Fallback: invalid plan"
        return _fallback_directive(reason), notes, True

    for idx, raw_step in enumerate(steps_in, start=1):
        if not isinstance(raw_step, Mapping):
            notes.append(f"Step {idx} ignored: not a mapping.")
            continue
        type_raw = raw_step.get("type") or raw_step.get("verb") or raw_step.get("action")
        step_type = _coerce_str(type_raw).replace(" ", "")
        if step_type not in ALLOWED_VERBS:
            notes.append(f"Step {idx} skipped: unsupported verb '{step_type}'.")
            continue
        is_headless = bool(raw_step.get("headless"))
        args_raw = raw_step.get("args")
        args = dict(args_raw) if isinstance(args_raw, Mapping) else {}
        for alias in ("selector", "text", "url", "ms"):
            if alias not in args and alias in raw_step:
                args[alias] = raw_step[alias]

        if step_type == "navigate":
            url = _coerce_str(args.get("url"))
            if not url:
                notes.append(f"Step {idx} skipped: navigate requires a URL.")
                continue
            payload: Dict[str, Any] = {"type": "navigate", "url": url}
            if is_headless:
                payload["headless"] = True
            steps_payload.append(payload)
            continue
        if step_type == "reload":
            payload = {"type": "reload"}
            if is_headless:
                payload["headless"] = True
            steps_payload.append(payload)
            continue
        if step_type == "click":
            selector = _coerce_str(args.get("selector"))
            text = _coerce_str(args.get("text"))
            if not selector and not text:
                notes.append(f"Step {idx} skipped: click requires selector or text.")
                continue
            payload: Dict[str, Any] = {"type": "click"}
            if selector:
                payload["selector"] = selector
            if text:
                payload["text"] = text
            if is_headless:
                payload["headless"] = True
            steps_payload.append(payload)
            continue
        if step_type == "type":
            selector = _coerce_str(args.get("selector"))
            text_value = args.get("text")
            text = str(text_value) if text_value is not None else ""
            if not selector or not text:
                notes.append(f"Step {idx} skipped: type requires selector and text.")
                continue
            payload = {"type": "type", "selector": selector, "text": text}
            if is_headless:
                payload["headless"] = True
            steps_payload.append(payload)
            continue
        if step_type == "waitForStable":
            ms_value = args.get("ms") or args.get("timeout") or args.get("delay")
            delay_ms: int | None = None
            if ms_value is not None:
                try:
                    delay_ms = max(0, int(float(ms_value)))
                except (TypeError, ValueError):
                    notes.append(f"Step {idx}: waitForStable ms invalid; defaulting to 600ms.")
            payload = {"type": "waitForStable"}
            if delay_ms:
                payload["ms"] = delay_ms
            if is_headless:
                payload["headless"] = True
            steps_payload.append(payload)
            continue

    reason = _coerce_str(plan.get("reason")) or "Planned fix"
    directive_payload: Dict[str, Any] = {"reason": reason, "steps": steps_payload}

    confidence = _coerce_str(plan.get("plan_confidence")).lower()
    if confidence in {"low", "medium", "high"}:
        directive_payload["plan_confidence"] = confidence

    needs_permission = plan.get("needs_user_permission")
    if isinstance(needs_permission, bool):
        directive_payload["needs_user_permission"] = needs_permission

    ask_user = plan.get("ask_user")
    if isinstance(ask_user, (list, tuple)):
        questions = [question for question in (_coerce_str(item) for item in ask_user) if question]
        if questions:
            directive_payload["ask_user"] = questions

    fallback_info = plan.get("fallback")
    if isinstance(fallback_info, Mapping):
        headless_hint_raw = fallback_info.get("headless_hint")
        hints: List[str] = []
        if isinstance(headless_hint_raw, (list, tuple)):
            hints = [hint for hint in (_coerce_str(item) for item in headless_hint_raw) if hint]
        enabled_flag = fallback_info.get("enabled")
        directive_payload["fallback"] = {
            "enabled": bool(enabled_flag) if enabled_flag is not None else True,
            "headless_hint": hints,
        }

    if not steps_payload:
        notes.append("Planner produced no executable steps; fallback reload() will be used.")
        return _fallback_directive(reason), notes, True

    directive = SelfHealDirective(
        reason=directive_payload["reason"],
        steps=directive_payload["steps"],
        plan_confidence=directive_payload.get("plan_confidence"),
        needs_user_permission=directive_payload.get("needs_user_permission"),
        ask_user=directive_payload.get("ask_user"),
        fallback=directive_payload.get("fallback"),
    )
    return directive, notes, False


@bp.post("/self_heal")
def self_heal():
    """Plan or apply a safe, permissioned fix."""

    apply = request.args.get("apply", "false").lower() in {"1", "true", "yes", "on"}
    variant = _coerce_variant(request.args.get("variant"))
    incident = _coerce_incident(request.get_json(silent=True) or {})

    _publish_diagnostic(
        "planner.start",
        f"Self-heal planner invoked (apply={apply})",
        variant=variant,
        incident_id=incident.get("id"),
    )

    bus: ProgressBus | None
    try:
        bus = current_app.config.get("PROGRESS_BUS")
    except RuntimeError:
        bus = None

    maybe_rule = try_rules_first(incident)
    if maybe_rule:
        rule_id, directive_payload = maybe_rule
        _publish_diagnostic(
            "planner.rulepack",
            f"rule_hit:{rule_id}",
            rule_id=rule_id,
        )
        if isinstance(bus, ProgressBus):
            record_event("rule_hits_count", bus=bus)
        directive = SelfHealDirective(
            reason=directive_payload.get("reason", "Rule applied"),
            steps=list(directive_payload.get("steps") or []),
        )
        meta = {
            "variant": variant,
            "rule_id": rule_id,
            "source": "rulepack",
            "domSnippet": incident.get("domSnippet"),
        }
        episode_id, _ = append_episode(
            url=incident.get("url", ""),
            symptoms=incident.get("symptoms", {}),
            directive=directive.model_dump(),
            mode="apply" if apply else "plan",
            outcome="unknown",
            meta=meta,
        )
        response = {
            "mode": "apply" if apply else "plan",
            "directive": directive.model_dump(),
            "meta": {**meta, "episode_id": episode_id},
        }
        return jsonify(response), 200

    system_prompt, user_prompt = build_prompts(incident, variant)
    _publish_diagnostic(
        "planner.prompt",
        "Planner prompts prepared.",
        system_chars=len(system_prompt),
        user_chars=len(user_prompt),
    )

    try:
        plan_payload_raw = _OLLAMA_CLIENT.chat_json(
            system=system_prompt,
            user=user_prompt,
            model=DEFAULT_SELF_HEAL_MODEL,
        )
        if isinstance(bus, ProgressBus):
            record_event("planner_calls_total", bus=bus)
        plan_payload = _parse_plan(plan_payload_raw)
        serialized = json.dumps(plan_payload, ensure_ascii=False)
        preview = serialized[:500]
        _publish_diagnostic(
            "planner.response",
            f"Planner response received ({len(serialized)} chars).",
            preview=preview,
            model=DEFAULT_SELF_HEAL_MODEL,
        )
        directive, notes, used_fallback = _validate_and_coerce(plan_payload)
        for note in notes:
            _publish_diagnostic("planner.validation", note)
        if used_fallback:
            _publish_diagnostic("planner.fallback", "Planner fallback triggered; reload() selected.")
            if isinstance(bus, ProgressBus):
                record_event("planner_fallback_count", bus=bus)
    except Exception as exc:  # pragma: no cover - defensive guard for runtime issues
        LOGGER.exception("Self-heal planner failed: %s", exc)
        reason = f"Fallback reload (planner error: {exc})"
        _publish_diagnostic("planner.error", reason)
        directive = _fallback_directive(reason)
        if isinstance(bus, ProgressBus):
            record_event("planner_fallback_count", bus=bus)

    mode = "apply" if apply else "plan"
    _publish_diagnostic("planner.complete", f"Planner returning directive (mode={mode}).")

    meta = {
        "variant": variant,
        "source": "planner",
        "domSnippet": incident.get("domSnippet"),
    }
    try:
        episode_id, _ = append_episode(
            url=incident.get("url", ""),
            symptoms=incident.get("symptoms", {}),
            directive=directive.model_dump(),
            mode=mode,
            outcome="unknown",
            meta=meta,
        )
    except Exception:  # pragma: no cover - diagnostics best-effort
        episode_id = None
    response = {
        "mode": mode,
        "directive": directive.model_dump(),
        "meta": {**meta, "episode_id": episode_id},
    }
    return jsonify(response), 200
