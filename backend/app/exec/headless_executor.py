"""Headless execution of planner directives via the agent browser API."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

import requests

_STAGE = "headless"


@dataclass(slots=True)
class StepRecord:
    """Outcome for an individual directive step."""

    index: int
    type: str
    args: Dict[str, Any]
    status: str
    detail: Optional[str] = None
    response: Optional[Dict[str, Any]] = None
    elapsed_ms: Optional[int] = None


@dataclass(slots=True)
class HeadlessResult:
    """Aggregate results for a headless directive run."""

    ok: bool = True
    steps: List[StepRecord] = field(default_factory=list)
    failed_step: Optional[int] = None
    session_id: Optional[str] = None
    last_state: Optional[Dict[str, Any]] = None
    transcript: List[Dict[str, Any]] = field(default_factory=list)


class HeadlessExecutionError(RuntimeError):
    """Raised when setup for the headless executor fails."""


_PREFIX_TYPES = {"navigate", "waitForStable", "reload"}


def _coerce_steps(raw: Any) -> List[Mapping[str, Any]]:
    if not isinstance(raw, Iterable):
        return []

    candidates: List[Mapping[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            candidates.append(item)

    selected_indices: set[int] = set()
    for idx, item in enumerate(candidates):
        if bool(item.get("headless")):
            selected_indices.add(idx)
            prefix_idx = idx - 1
            while prefix_idx >= 0:
                prev = candidates[prefix_idx]
                step_type = str(prev.get("type") or prev.get("verb") or prev.get("action") or "").strip()
                if step_type not in _PREFIX_TYPES:
                    break
                selected_indices.add(prefix_idx)
                prefix_idx -= 1

    return [candidates[i] for i in sorted(selected_indices)]


def _post(session: requests.Session, url: str, payload: Dict[str, Any], *, timeout: float) -> Dict[str, Any]:
    response = session.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:  # pragma: no cover - defensive
        raise HeadlessExecutionError(f"{url} returned non-JSON response") from exc


def run(
    directive: Mapping[str, Any],
    *,
    base_url: str,
    sse_publish: Optional[Callable[[Dict[str, Any]], None]] = None,
    session_id: Optional[str] = None,
    max_steps: int = 12,
    max_runtime_s: float = 90.0,
    wait_ms_default: int = 600,
    request_timeout: float = 20.0,
) -> HeadlessResult:
    """Execute headless-only directive steps via the Agent-Browser HTTP API."""

    result = HeadlessResult()
    steps = _coerce_steps(directive.get("steps"))[: max(0, int(max_steps))]
    if not steps:
        return result

    base = (base_url or "").rstrip("/")
    if not base:
        raise HeadlessExecutionError("base_url is required")

    http = requests.Session()
    own_session = False
    sid = (session_id or "").strip()

    def _emit(event: Dict[str, Any]) -> None:
        payload = {"stage": _STAGE}
        payload.update(event)
        result.transcript.append(payload)
        if sse_publish is not None:
            try:
                sse_publish(payload)
            except Exception:  # pragma: no cover - defensive
                pass

    def _record_step(
        *,
        index: int,
        step_type: str,
        args: Dict[str, Any],
        status: str,
        detail: Optional[str],
        response: Optional[Dict[str, Any]],
        elapsed: float,
    ) -> None:
        result.steps.append(
            StepRecord(
                index=index,
                type=step_type,
                args=dict(args),
                status=status,
                detail=detail,
                response=response,
                elapsed_ms=int(elapsed * 1000),
            )
        )

    try:
        if not sid:
            _emit({"status": "start", "message": "Starting agent browser session."})
            payload = _post(http, f"{base}/api/agent/session/start", {}, timeout=request_timeout)
            sid = str(payload.get("sid") or payload.get("session_id") or "").strip()
            if not sid:
                raise HeadlessExecutionError("agent browser did not return a session identifier")
            own_session = True
            result.session_id = sid
            _emit({"status": "info", "message": f"Session started", "sid": sid})
        else:
            result.session_id = sid

        started_at = time.monotonic()
        last_url: Optional[str] = None

        for idx, raw_step in enumerate(steps, start=1):
            if max_runtime_s > 0 and (time.monotonic() - started_at) > max_runtime_s:
                result.ok = False
                result.failed_step = idx
                _emit({"status": "timeout", "message": f"Timeout before step {idx}"})
                break

            step_type = str(raw_step.get("type") or raw_step.get("verb") or "").strip()
            args_raw = raw_step.get("args")
            args = dict(args_raw) if isinstance(args_raw, Mapping) else {}
            for alias in ("url", "selector", "text", "ms"):
                if alias not in args and alias in raw_step:
                    args[alias] = raw_step[alias]

            effective_args = {key: value for key, value in args.items() if value is not None}
            _emit(
                {
                    "status": "start",
                    "message": f"Executing step {idx}",
                    "step": idx,
                    "type": step_type,
                    "args": effective_args,
                }
            )

            step_started = time.monotonic()
            response_payload: Optional[Dict[str, Any]] = None
            status = "ok"
            detail: Optional[str] = None

            try:
                if step_type == "navigate":
                    url = str(effective_args.get("url") or "").strip()
                    if not url:
                        raise ValueError("navigate requires url")
                    response_payload = _post(
                        http,
                        f"{base}/api/agent/navigate",
                        {"sid": sid, "url": url},
                        timeout=request_timeout,
                    )
                    last_url = str(response_payload.get("url") or url)
                    result.last_state = {"url": last_url, "action": "navigate"}
                elif step_type == "reload":
                    response_payload = None
                    try:
                        response_payload = _post(
                            http,
                            f"{base}/api/agent/reload",
                            {"sid": sid},
                            timeout=request_timeout,
                        )
                    except Exception:
                        # Reload failures should not block the planner; treat as best-effort.
                        response_payload = None
                    if isinstance(response_payload, dict):
                        last_url = str(response_payload.get("url") or last_url or "") or None
                    result.last_state = {"url": last_url, "action": "reload"}
                elif step_type == "click":
                    selector = str(effective_args.get("selector") or "").strip()
                    text = str(effective_args.get("text") or "").strip()
                    if not selector and not text:
                        raise ValueError("click requires selector or text")

                    def _click_payload(*, selector_value: Optional[str], text_value: Optional[str]) -> Dict[str, Any]:
                        payload: Dict[str, Any] = {"sid": sid}
                        if selector_value:
                            payload["selector"] = selector_value
                        if text_value and selector_value:
                            payload["text"] = text_value
                        elif text_value and not selector_value:
                            payload["text"] = text_value
                        return payload

                    used_selector: Optional[str] = selector or None
                    response_payload = None
                    click_error: Optional[BaseException] = None

                    if selector:
                        payload = _click_payload(selector_value=selector, text_value=text or None)
                        response_payload = _post(
                            http,
                            f"{base}/api/agent/click",
                            payload,
                            timeout=request_timeout,
                        )
                    else:
                        # Text-only clicks attempt robust selectors before falling back
                        fallback_selectors = []
                        if text:
                            safe_text = text.replace("\"", "\\\"")
                            fallback_selectors = [
                                f'button[aria-label*="{safe_text}"]',
                                f'[role="button"]:has-text("{safe_text}")',
                            ]
                        for candidate in fallback_selectors:
                            try:
                                payload = _click_payload(selector_value=candidate, text_value=text or None)
                                response_payload = _post(
                                    http,
                                    f"{base}/api/agent/click",
                                    payload,
                                    timeout=request_timeout,
                                )
                            except Exception as exc:  # pragma: no cover - fallback progression
                                click_error = exc
                                _emit(
                                    {
                                        "status": "info",
                                        "message": f"Fallback selector failed: {candidate}",
                                        "step": idx,
                                    }
                                )
                                continue
                            else:
                                used_selector = candidate
                                click_error = None
                                break

                        if response_payload is None:
                            payload = _click_payload(selector_value=None, text_value=text or None)
                            response_payload = _post(
                                http,
                                f"{base}/api/agent/click",
                                payload,
                                timeout=request_timeout,
                            )
                            used_selector = None
                            click_error = None

                        if click_error is not None:
                            raise click_error

                    last_url = str(response_payload.get("url") or last_url or "") or None
                    result.last_state = {
                        "url": last_url,
                        "action": "click",
                        "selector": used_selector,
                        "text": text or None,
                    }
                elif step_type == "type":
                    selector = str(effective_args.get("selector") or "").strip()
                    text = effective_args.get("text")
                    body = str(text) if text is not None else ""
                    if not selector:
                        raise ValueError("type requires selector")
                    payload = {"sid": sid, "selector": selector, "text": body}
                    response_payload = _post(
                        http,
                        f"{base}/api/agent/type",
                        payload,
                        timeout=request_timeout,
                    )
                    last_url = str(response_payload.get("url") or last_url or "") or None
                    result.last_state = {
                        "url": last_url,
                        "action": "type",
                        "selector": selector,
                        "text": body,
                    }
                elif step_type == "waitForStable":
                    try:
                        ms_value = int(effective_args.get("ms", wait_ms_default))
                    except (TypeError, ValueError):
                        ms_value = wait_ms_default
                    time.sleep(max(0, ms_value) / 1000.0)
                    result.last_state = {"action": "waitForStable", "ms": ms_value}
                else:
                    status = "skipped"
                    detail = f"Unsupported verb: {step_type}"
            except Exception as exc:
                status = "error"
                detail = str(exc)
                result.ok = False
                result.failed_step = idx
                _emit(
                    {
                        "status": "error",
                        "message": f"Step {idx} failed: {exc}",
                        "step": idx,
                        "type": step_type,
                    }
                )
                _record_step(
                    index=idx,
                    step_type=step_type,
                    args=effective_args,
                    status=status,
                    detail=detail,
                    response=response_payload,
                    elapsed=time.monotonic() - step_started,
                )
                break

            _record_step(
                index=idx,
                step_type=step_type,
                args=effective_args,
                status=status,
                detail=detail,
                response=response_payload,
                elapsed=time.monotonic() - step_started,
            )

            if status == "ok":
                _emit(
                    {
                        "status": "ok",
                        "message": f"Step {idx} completed",
                        "step": idx,
                        "type": step_type,
                    }
                )
            elif status == "skipped":
                _emit(
                    {
                        "status": "skipped",
                        "message": f"Step {idx} skipped: {detail}",
                        "step": idx,
                        "type": step_type,
                    }
                )

        if result.ok:
            try:
                response_payload = _post(
                    http,
                    f"{base}/api/agent/extract",
                    {"sid": sid},
                    timeout=request_timeout,
                )
                result.last_state = response_payload
                _emit(
                    {
                        "status": "info",
                        "message": "Final extract captured.",
                        "step": None,
                    }
                )
            except Exception:  # pragma: no cover - best effort
                pass

        if result.ok and result.failed_step is None:
            _emit({"status": "complete", "message": "Headless directive complete."})

        return result
    finally:
        if own_session and sid:
            try:
                _emit({"status": "info", "message": "Closing session.", "sid": sid})
                _post(http, f"{base}/api/agent/session/close", {"sid": sid}, timeout=request_timeout)
            except Exception:  # pragma: no cover - defensive cleanup
                pass
        http.close()


__all__ = ["HeadlessExecutionError", "HeadlessResult", "StepRecord", "run"]
