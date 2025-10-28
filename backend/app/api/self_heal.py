"""Self-heal orchestrator: accepts BrowserIncident and returns an AutopilotDirective."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Mapping, Tuple

from flask import Blueprint, current_app, jsonify, request

from backend.app.ai.self_heal_prompt import ALLOWED_VERBS, build_prompts
from backend.app.api.reasoning import route_to_browser  # noqa: F401 - imported for future integration
from backend.app.services import ollama_client as ollama_services
from backend.app.services.progress_bus import ProgressBus
from engine.llm.ollama_client import ChatMessage, OllamaClient, OllamaClientError

bp = Blueprint("self_heal_api", __name__, url_prefix="/api")

LOGGER = logging.getLogger(__name__)
DEFAULT_VARIANT = "lite"
_VALID_VARIANTS = {"lite", "deep", "headless", "repair"}
_DIAGNOSTIC_JOB_ID = "__diagnostics__"
_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


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


def _extract_json_blob(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ValueError("planner returned empty response")
    match = _CODE_BLOCK_RE.search(stripped)
    if match:
        candidate = match.group(1).strip()
    else:
        candidate = stripped
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return candidate[start : end + 1].strip()
    return candidate


def _call_llm(system_prompt: str, user_prompt: str, *, max_tokens: int = 700) -> str:
    engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
    if engine_config is None:
        raise RuntimeError("RAG_ENGINE_CONFIG missing from app configuration")
    primary_model = getattr(engine_config.models, "llm_primary", None) or "gpt-oss"
    resolved_model = ollama_services.resolve_model_name(
        primary_model,
        base_url=engine_config.ollama.base_url,
        chat_only=True,
    )
    client = OllamaClient(engine_config.ollama.base_url, timeout=60.0)
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    options = {"temperature": 0.1, "num_predict": max_tokens, "format": "json"}
    try:
        return client.chat(resolved_model, messages, options=options)
    except OllamaClientError as exc:  # pragma: no cover - network errors are external
        raise RuntimeError(f"ollama chat failed: {exc}") from exc


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
        payload = _extract_json_blob(response)
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"planner returned invalid JSON: {exc}") from exc
    raise TypeError("planner response must be a string or mapping")


def _fallback_directive(reason: str) -> Dict[str, Any]:
    return {
        "reason": reason,
        "plan_confidence": "low",
        "steps": [{"type": "reload"}],
    }


def _validate_and_coerce(plan: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str], bool]:
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
        if bool(raw_step.get("headless")):
            notes.append(f"Step {idx} skipped: headless steps deferred to agent browser.")
            continue
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
            steps_payload.append({"type": "navigate", "url": url})
            continue
        if step_type == "reload":
            steps_payload.append({"type": "reload"})
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
            steps_payload.append(payload)
            continue
        if step_type == "type":
            selector = _coerce_str(args.get("selector"))
            text_value = args.get("text")
            text = str(text_value) if text_value is not None else ""
            if not selector or not text:
                notes.append(f"Step {idx} skipped: type requires selector and text.")
                continue
            steps_payload.append({"type": "type", "selector": selector, "text": text})
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
            steps_payload.append(payload)
            continue

    reason = _coerce_str(plan.get("reason")) or "Planned fix"
    directive: Dict[str, Any] = {"reason": reason, "steps": steps_payload}

    confidence = _coerce_str(plan.get("plan_confidence")).lower()
    if confidence in {"low", "medium", "high"}:
        directive["plan_confidence"] = confidence

    needs_permission = plan.get("needs_user_permission")
    if isinstance(needs_permission, bool):
        directive["needs_user_permission"] = needs_permission

    ask_user = plan.get("ask_user")
    if isinstance(ask_user, (list, tuple)):
        questions = [question for question in (_coerce_str(item) for item in ask_user) if question]
        if questions:
            directive["ask_user"] = questions

    fallback_info = plan.get("fallback")
    if isinstance(fallback_info, Mapping):
        headless_hint_raw = fallback_info.get("headless_hint")
        hints: List[str] = []
        if isinstance(headless_hint_raw, (list, tuple)):
            hints = [hint for hint in (_coerce_str(item) for item in headless_hint_raw) if hint]
        enabled_flag = fallback_info.get("enabled")
        directive["fallback"] = {
            "enabled": bool(enabled_flag) if enabled_flag is not None else True,
            "headless_hint": hints,
        }

    if not steps_payload:
        notes.append("Planner produced no executable steps; fallback reload() will be used.")
        return _fallback_directive(reason), notes, True

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

    system_prompt, user_prompt = build_prompts(incident, variant)
    _publish_diagnostic(
        "planner.prompt",
        "Planner prompts prepared.",
        system_chars=len(system_prompt),
        user_chars=len(user_prompt),
    )

    try:
        raw_response = _call_llm(system_prompt, user_prompt)
        preview = raw_response.strip()[:500]
        _publish_diagnostic(
            "planner.response",
            f"Planner response received ({len(raw_response)} chars).",
            preview=preview,
        )
        plan_payload = _parse_plan(raw_response)
        directive, notes, used_fallback = _validate_and_coerce(plan_payload)
        for note in notes:
            _publish_diagnostic("planner.validation", note)
        if used_fallback:
            _publish_diagnostic("planner.fallback", "Planner fallback triggered; reload() selected.")
    except Exception as exc:  # pragma: no cover - defensive guard for runtime issues
        LOGGER.exception("Self-heal planner failed: %%s", exc)
        reason = f"Fallback reload (planner error: {exc})"
        _publish_diagnostic("planner.error", reason)
        directive = _fallback_directive(reason)

    mode = "apply" if apply else "plan"
    _publish_diagnostic("planner.complete", f"Planner returning directive (mode={mode}).")
    return jsonify({"mode": mode, "directive": directive}), 200
