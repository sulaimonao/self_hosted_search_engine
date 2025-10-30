"""Self-heal orchestrator: accepts BrowserIncident and returns an AutopilotDirective."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Mapping, Optional, Tuple

from flask import Blueprint, current_app, jsonify, request

from backend.app.ai.self_heal_prompt import ALLOWED_VERBS, build_prompts
from backend.app.api.reasoning import route_to_browser  # noqa: F401 - imported for future integration
from backend.app.io import coerce_directive, coerce_incident, self_heal_schema
from backend.app.io.models import Directive, Step, VERB_MAP
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


@bp.get("/self_heal/schema")
def self_heal_schema_echo():
    """Expose JSON Schemas for self-heal payloads."""

    return jsonify(self_heal_schema())


_OLLAMA_CLIENT = OllamaClient()


def _shrink_payload(value: Any, *, max_string: int = 512, max_items: int = 20) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _shrink_payload(v, max_string=max_string, max_items=max_items) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [
            _shrink_payload(item, max_string=max_string, max_items=max_items)
            for item in list(value)[:max_items]
        ]
    if isinstance(value, str):
        if len(value) > max_string:
            return value[: max_string - 3] + "..."
        return value
    return value


def _payload_preview(payload: Any, *, limit: int = 900) -> str:
    try:
        rendered = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(payload)
    if len(rendered) > limit:
        return rendered[: limit - 3] + "..."
    return rendered


def _publish_diagnostic(stage: str, message: str, *, payload: Any | None = None, **extra: Any) -> None:
    event: Dict[str, Any] = {"stage": stage, "message": message}
    if payload is not None:
        event["kind"] = "payload"
        event["payload"] = _shrink_payload(payload)
        event["preview"] = _payload_preview(payload)
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


def _coerce_bool(value: Any) -> bool | None:
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


def _parse_plan(response: Any) -> Dict[str, Any]:
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, str):
        try:
            return json.loads(response)
        except json.JSONDecodeError as exc:
            raise ValueError(f"planner returned invalid JSON: {exc}") from exc
    raise TypeError("planner response must be a string or mapping")


def _fallback_directive(reason: str) -> Directive:
    return Directive(reason=reason, steps=[Step(type="reload")], plan_confidence="low")


def _validate_and_coerce(plan: Mapping[str, Any]) -> Tuple[Directive, List[str], bool]:
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
        step_type = VERB_MAP.get(step_type.lower(), step_type)
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

    needs_permission = _coerce_bool(plan.get("needs_user_permission"))
    if needs_permission is not None:
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
        enabled_flag = _coerce_bool(fallback_info.get("enabled"))
        directive_payload["fallback"] = {
            "enabled": True if enabled_flag is None else enabled_flag,
            "headless_hint": hints,
        }

    if not steps_payload:
        notes.append("Planner produced no executable steps; fallback reload() will be used.")
        return _fallback_directive(reason), notes, True

    directive = coerce_directive(directive_payload)
    return directive, notes, False


@bp.post("/self_heal")
def self_heal():
    """Plan or apply a safe, permissioned fix."""

    apply = request.args.get("apply", "false").lower() in {"1", "true", "yes", "on"}
    variant = _coerce_variant(request.args.get("variant"))
    incident_model = coerce_incident(request.get_json(silent=True) or {})
    incident = incident_model.as_payload()

    _publish_diagnostic("io.self_heal.request", "incident captured", payload=incident)

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
        directive = coerce_directive(
            {
                "reason": directive_payload.get("reason", "Rule applied"),
                "steps": list(directive_payload.get("steps") or []),
            }
        )
        directive_payload_out = directive.as_payload()
        meta = {
            "variant": variant,
            "rule_id": rule_id,
            "source": "rulepack",
            "domSnippet": incident.get("domSnippet"),
        }
        episode_id, _ = append_episode(
            url=incident.get("url", ""),
            symptoms=incident.get("symptoms", {}),
            directive=directive_payload_out,
            mode="apply" if apply else "plan",
            outcome="unknown",
            meta=meta,
        )
        response = {
            "mode": "apply" if apply else "plan",
            "directive": directive_payload_out,
            "meta": {**meta, "episode_id": episode_id},
        }
        _publish_diagnostic("io.self_heal.response", "rule directive", payload=response)
        return jsonify(response), 200

    system_prompt, user_prompt = build_prompts(incident, variant)
    _publish_diagnostic(
        "planner.prompt",
        "Planner prompts prepared.",
        system_chars=len(system_prompt),
        user_chars=len(user_prompt),
    )

    directive: Optional[Directive] = None
    resolved_model: Optional[str] = None

    try:
        resolved_model = _OLLAMA_CLIENT.resolve_model(os.getenv("SELF_HEAL_MODEL"))
        _publish_diagnostic("planner.model", "Allowed Ollama model resolved.", model=resolved_model)
    except Exception as exc:
        reason = f"Ollama not ready or no allowed model: {exc}; safe fallback reload."
        LOGGER.warning("Self-heal planner skipping Ollama call: %s", reason)
        _publish_diagnostic("planner.error", reason)
        directive = _fallback_directive(reason)
        if isinstance(bus, ProgressBus):
            record_event("planner_fallback_count", bus=bus)

    if directive is None:
        chosen_model = resolved_model or DEFAULT_SELF_HEAL_MODEL
        try:
            plan_payload_raw = _OLLAMA_CLIENT.chat_json(
                system=system_prompt,
                user=user_prompt,
                model=chosen_model,
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
                model=chosen_model,
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
    directive_payload_out = directive.as_payload()
    try:
        episode_id, _ = append_episode(
            url=incident.get("url", ""),
            symptoms=incident.get("symptoms", {}),
            directive=directive_payload_out,
            mode=mode,
            outcome="unknown",
            meta=meta,
        )
    except Exception:  # pragma: no cover - diagnostics best-effort
        episode_id = None
    response = {
        "mode": mode,
        "directive": directive_payload_out,
        "meta": {**meta, "episode_id": episode_id},
    }
    _publish_diagnostic("io.self_heal.response", f"directive ready ({mode})", payload=response)
    return jsonify(response), 200
