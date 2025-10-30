"""Self-heal orchestrator: accepts BrowserIncident and returns an AutopilotDirective."""
from __future__ import annotations

import json
import logging
import os
import time
from time import perf_counter
from typing import Any, Dict, Mapping, Optional

from flask import Blueprint, current_app, jsonify, request

from backend.app.ai.self_heal_prompt import build_prompts
from backend.app.io import (
    DirectiveClampResult,
    clamp_directive,
    clamp_incident,
    normalize_model_alias,
    self_heal_schema,
)
from backend.app.io.models import Directive, Step
from backend.app.llm.ollama_client import OllamaClient
from backend.app.self_heal.episodes import append_episode
from backend.app.self_heal.metrics import record_event
from backend.app.self_heal.rules import try_rules_first
from backend.app.services.progress_bus import ProgressBus

bp = Blueprint("self_heal_api", __name__, url_prefix="/api")

LOGGER = logging.getLogger(__name__)
DEFAULT_VARIANT = "lite"
_VALID_VARIANTS = {"lite", "deep", "headless", "repair"}
_DIAGNOSTIC_JOB_ID = "__diagnostics__"
_PLAN_TIMEOUT_S = 8.0
_TRUE_FLAGS = {"1", "true", "yes", "on"}

_OLLAMA_CLIENT = OllamaClient()


@bp.get("/self_heal/schema")
def self_heal_schema_echo():
    """Expose JSON Schemas for self-heal payloads."""

    return jsonify(self_heal_schema())


def _progress_bus() -> ProgressBus | None:
    try:
        bus = current_app.config.get("PROGRESS_BUS")
    except RuntimeError:
        return None
    return bus if isinstance(bus, ProgressBus) else None


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


def _emit(stage: str, message: str, *, payload: Any | None = None, **extra: Any) -> None:
    bus = _progress_bus()
    if bus is None:
        return
    event: Dict[str, Any] = {"stage": stage, "message": message, "ts": time.time()}
    for key, value in extra.items():
        if value is None:
            continue
        event[key] = value
    if payload is not None:
        event["kind"] = "payload"
        event["payload"] = _shrink_payload(payload)
        event["preview"] = _payload_preview(payload)
    try:
        bus.publish(_DIAGNOSTIC_JOB_ID, event)
    except Exception:  # pragma: no cover - diagnostics best effort
        LOGGER.debug("diagnostics payload publish failed", exc_info=True)


def _coerce_variant(raw: str | None) -> str:
    if not isinstance(raw, str):
        return DEFAULT_VARIANT
    variant = raw.strip().lower()
    if variant in _VALID_VARIANTS:
        return variant
    return DEFAULT_VARIANT


def _flag(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in _TRUE_FLAGS


def _fallback_directive(reason: str = "timeout_or_invalid") -> DirectiveClampResult:
    directive = Directive(reason=reason, steps=[Step(type="reload")])
    return DirectiveClampResult(directive=directive, dropped_steps=[], fallback_applied=True)


def _plan_with_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    variant: str,
    timeout_s: float = _PLAN_TIMEOUT_S,
) -> tuple[DirectiveClampResult, dict[str, Any]]:
    start = perf_counter()
    meta: dict[str, Any] = {
        "status": "fallback",
        "model": None,
        "error": None,
        "called_llm": False,
    }

    if variant == "lite":
        meta["status"] = "variant_skip"
        meta["took_ms"] = int((perf_counter() - start) * 1000)
        return _fallback_directive(), meta

    preferred_env = os.getenv("SELF_HEAL_MODEL")
    try:
        preferred_model = normalize_model_alias(preferred_env) if preferred_env else normalize_model_alias(None)
    except ValueError:
        preferred_model = normalize_model_alias(None)

    try:
        resolved_model = _OLLAMA_CLIENT.resolve_model(preferred_model)
        meta["model"] = resolved_model
    except Exception as exc:
        LOGGER.warning("Self-heal planner could not resolve model: %s", exc)
        meta["status"] = "resolve_error"
        meta["error"] = str(exc)
        meta["took_ms"] = int((perf_counter() - start) * 1000)
        return _fallback_directive(), meta

    try:
        plan_payload_raw = _OLLAMA_CLIENT.chat_json(
            system=system_prompt,
            user=user_prompt,
            model=resolved_model,
            timeout=timeout_s,
        )
        meta["called_llm"] = True
    except Exception as exc:
        LOGGER.warning("Self-heal planner request failed: %s", exc)
        meta["status"] = "chat_error"
        meta["error"] = str(exc)
        meta["took_ms"] = int((perf_counter() - start) * 1000)
        return _fallback_directive(), meta

    result = clamp_directive(plan_payload_raw, fallback_reason="timeout_or_invalid")
    meta["status"] = "ok" if not result.fallback_applied else "invalid_plan"
    if result.fallback_applied:
        meta["error"] = "invalid_plan"
    meta["preview"] = _payload_preview(plan_payload_raw)
    meta["took_ms"] = int((perf_counter() - start) * 1000)
    meta["step_count"] = len(result.directive.steps)
    return result, meta


def _has_headless_step(directive: Directive) -> bool:
    for step in directive.steps or []:
        if bool(step.headless):
            return True
    return False


@bp.post("/self_heal")
def self_heal():
    """Plan or apply a safe, permissioned fix."""

    request_start = perf_counter()
    apply_flag = _flag(request.args.get("apply"))
    variant = _coerce_variant(request.args.get("variant"))
    incident_model = clamp_incident(request.get_json(silent=True) or {})
    incident_payload = incident_model.as_payload()

    _emit("payload.pre", "incident captured", payload=incident_payload)
    _emit("planner.start", f"Planner invoked (variant={variant}, apply={apply_flag})", variant=variant, apply=apply_flag)

    bus = _progress_bus()

    rule_hit = try_rules_first(incident_payload)
    directive_result: DirectiveClampResult
    planner_meta: dict[str, Any]
    source = "planner"

    if rule_hit:
        source = "rulepack"
        rule_id, directive_payload = rule_hit
        raw_steps = list(directive_payload.get("steps") or [])
        directive_result = clamp_directive(
            {
                "reason": directive_payload.get("reason", "Rule applied"),
                "steps": raw_steps,
            }
        )
        planner_meta = {"status": "rule", "rule_id": rule_id, "model": None, "took_ms": 0}
        _emit("planner.ok", f"rule_hit:{rule_id}", rule_id=rule_id)
        if directive_result.fallback_applied:
            _emit("planner.fallback", "Rulepack produced fallback reload().", rule_id=rule_id)
            try:
                record_event("planner_fallback_count", bus=bus)
            except Exception:  # pragma: no cover - metrics best effort
                pass
        try:
            record_event("rule_hits_count", bus=bus)
        except Exception:  # pragma: no cover - defensive metrics guard
            pass
    else:
        system_prompt, user_prompt = build_prompts(incident_payload, variant)
        _emit(
            "planner.prompt",
            "Planner prompts prepared.",
            system_chars=len(system_prompt),
            user_chars=len(user_prompt),
            preview=_payload_preview({"system": system_prompt, "user": user_prompt}),
        )
        directive_result, planner_meta = _plan_with_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            variant=variant,
            timeout_s=_PLAN_TIMEOUT_S,
        )
        status = planner_meta.get("status")
        if status == "ok":
            _emit(
                "planner.ok",
                "Planner directive ready.",
                model=planner_meta.get("model"),
                took_ms=planner_meta.get("took_ms"),
                steps=len(directive_result.directive.steps),
            )
        elif status == "variant_skip":
            _emit(
                "planner.fallback",
                "Lite variant bypassed LLM; reload directive issued.",
                took_ms=planner_meta.get("took_ms"),
            )
        elif status == "invalid_plan":
            _emit(
                "planner.fallback",
                "Planner payload invalid; fallback reload() used.",
                model=planner_meta.get("model"),
                took_ms=planner_meta.get("took_ms"),
                preview=planner_meta.get("preview"),
            )
        else:
            _emit(
                "planner.error",
                f"Planner failure: {planner_meta.get('error')}",
                model=planner_meta.get("model"),
            )
            _emit(
                "planner.fallback",
                "Planner failure triggered fallback reload().",
                model=planner_meta.get("model"),
                took_ms=planner_meta.get("took_ms"),
            )
        if planner_meta.get("called_llm"):
            try:
                record_event("planner_calls_total", bus=bus)
            except Exception:  # pragma: no cover - metrics best effort
                pass
        if directive_result.fallback_applied or planner_meta.get("status") in {
            "resolve_error",
            "chat_error",
            "variant_skip",
            "invalid_plan",
        }:
            try:
                record_event("planner_fallback_count", bus=bus)
            except Exception:  # pragma: no cover - metrics best effort
                pass

    directive_payload = directive_result.directive.as_payload()
    total_ms = int((perf_counter() - request_start) * 1000)
    needs_headless = _has_headless_step(directive_result.directive)
    mode = "apply" if apply_flag else "plan"

    response_meta: Dict[str, Any] = {
        "variant": variant,
        "source": source,
        "domSnippet": incident_payload.get("domSnippet"),
        "planner_status": planner_meta.get("status"),
    }
    if planner_meta.get("model"):
        response_meta["planner_model"] = planner_meta["model"]
    if planner_meta.get("took_ms") is not None:
        response_meta["planner_took_ms"] = planner_meta.get("took_ms")
    if planner_meta.get("rule_id"):
        response_meta["rule_id"] = planner_meta.get("rule_id")

    response: Dict[str, Any] = {
        "mode": mode,
        "directive": directive_payload,
        "meta": response_meta,
        "took_ms": total_ms,
    }
    if apply_flag:
        response["needs_headless"] = bool(needs_headless)

    try:
        episode_id, _ = append_episode(
            url=incident_payload.get("url", ""),
            symptoms=incident_payload.get("symptoms", {}),
            directive=directive_payload,
            mode=mode,
            outcome="unknown",
            meta={**response_meta},
        )
    except Exception:  # pragma: no cover - diagnostics best effort
        episode_id = None
    if episode_id:
        response_meta["episode_id"] = episode_id

    _emit("payload.post", f"directive ready ({mode})", payload=response)
    return jsonify(response), 200


__all__ = ["bp"]
