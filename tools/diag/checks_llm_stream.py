"""Diagnostics to ensure Electron LLM streaming infrastructure is robust."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable, List

from .engine import Finding, RuleContext, Severity, register


@register(
    "R20_stream_integrity",
    description="Electron desktop must frame chat streams and expose llm bridge",
    severity=Severity.HIGH,
)
def rule_stream_integrity(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    decoder_ok = False
    for relative in context.iter_patterns("desktop/**/main.ts", "desktop/**/main.js", "electron/main.js"):
        text = context.read_text(relative)
        if "TextDecoder" in text and "stream: true" in text:
            decoder_ok = True
            break
    if not decoder_ok:
        findings.append(
            Finding(
                id="llm-stream:decoder-missing",
                rule_id="R20_stream_integrity",
                severity=Severity.HIGH,
                summary="Electron main process is not using TextDecoder with streaming mode for LLM SSE.",
                suggestion="Use new TextDecoder('utf-8') with decode(..., { stream: true }) when splitting chat frames.",
            )
        )

    preload_ok = False
    for relative in context.iter_patterns("desktop/**/preload.ts", "desktop/**/preload.js", "electron/preload.js"):
        text = context.read_text(relative)
        if "exposeInMainWorld('llm'" in text and "onFrame" in text and "stream" in text:
            preload_ok = True
            break
    if not preload_ok:
        findings.append(
            Finding(
                id="llm-stream:preload-missing",
                rule_id="R20_stream_integrity",
                severity=Severity.HIGH,
                summary="Preload script does not expose window.llm stream/onFrame bridge.",
                suggestion="Expose window.llm.stream/onFrame/abort via contextBridge to forward desktop SSE frames.",
            )
        )

    hook_text = context.read_text("frontend/src/hooks/useLlmStream.ts")
    if hook_text:
        if "\\n\\n" not in hook_text or "useSyncExternalStore" not in hook_text:
            findings.append(
                Finding(
                    id="llm-stream:renderer-parsing",
                    rule_id="R20_stream_integrity",
                    severity=Severity.HIGH,
                    summary="Renderer LLM hook is not splitting SSE frames or using a single-writer store.",
                    suggestion="Parse frames on '\n\n' boundaries and store text via useSyncExternalStore to avoid token flicker.",
                    file="frontend/src/hooks/useLlmStream.ts",
                )
            )
    else:
        findings.append(
            Finding(
                id="llm-stream:hook-missing",
                rule_id="R20_stream_integrity",
                severity=Severity.HIGH,
                summary="Renderer streaming hook useLlmStream.ts is missing.",
                suggestion="Implement frontend/src/hooks/useLlmStream.ts with SSE parsing and external store.",
            )
        )

    if context.smoke and hook_text:
        if "frames" not in hook_text or (
            "frames" in hook_text and "frames + 1" not in hook_text and "frames++" not in hook_text
        ):
            findings.append(
                Finding(
                    id="llm-stream:frames-smoke",
                    rule_id="R20_stream_integrity",
                    severity=Severity.MEDIUM,
                    summary="Streaming hook does not appear to increment frame counters.",
                    suggestion="Increment a frames counter as frames arrive to monitor stream health.",
                    file="frontend/src/hooks/useLlmStream.ts",
                )
            )

    backend_chat = context.read_text("backend/app/api/chat.py")
    if backend_chat and "_StreamAccumulator" in backend_chat:
        if "previous +" not in backend_chat:
            findings.append(
                Finding(
                    id="llm-stream:accumulator-no-append",
                    rule_id="R20_stream_integrity",
                    severity=Severity.HIGH,
                    summary="Chat stream accumulator does not append incremental chunks to the existing answer.",
                    suggestion="Append new token text to the existing answer when upstream chunks are not cumulative.",
                    file="backend/app/api/chat.py",
                )
            )

    return findings


@register(
    "R21_chat_message_guard",
    description="Chat API must emit a contentful message field with punctuation guards",
    severity=Severity.MEDIUM,
)
def rule_chat_message_guard(_: RuleContext) -> Iterable[Finding]:
    try:
        from flask import Flask

        from backend.app.api import chat as chat_module
        from backend.app.api.chat import bp as chat_bp
    except Exception as exc:  # pragma: no cover - import guard
        return [
            Finding(
                id="llm-chat:import-error",
                rule_id="R21_chat_message_guard",
                severity=Severity.MEDIUM,
                summary="Unable to import chat API for diagnostics.",
                suggestion="Ensure backend dependencies are installed so diagnostics can instantiate the chat blueprint.",
                evidence=str(exc),
            )
        ]

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(chat_bp)
    app.config.update(APP_CONFIG=SimpleNamespace(ollama_url="http://ollama"))

    class _DummyResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200
            self.text = ""

        def json(self):
            return self._payload

        def close(self):
            return None

    def _fake_post(url, json, stream, timeout):  # noqa: ANN001 - requests compatibility
        return _DummyResponse(
            {
                "message": {
                    "role": "assistant",
                    "content": "**",
                }
            }
        )

    original_post = chat_module.requests.post
    chat_module.requests.post = _fake_post
    try:
        with app.test_client() as client:
            response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "stream": False})
    finally:
        chat_module.requests.post = original_post

    if response.status_code != 200:
        return [
            Finding(
                id="llm-chat:status",
                rule_id="R21_chat_message_guard",
                severity=Severity.MEDIUM,
                summary="Chat API returned non-200 status under diagnostic stub.",
                suggestion="Review chat API error handling for punctuation guard scenarios.",
                evidence=f"status={response.status_code}",
            )
        ]

    data = response.get_json() or {}
    message = str(data.get("message") or "").strip()
    has_alpha = any(ch.isalpha() for ch in message)
    if len(message) < 4 or not has_alpha:
        preview = message or "<empty>"
        return [
            Finding(
                id="llm-chat:message-guard",
                rule_id="R21_chat_message_guard",
                severity=Severity.MEDIUM,
                summary="Chat API did not coerce a contentful message field.",
                suggestion="Ensure punctuation-only responses fall back to a readable assistant reply.",
                evidence=preview,
            )
        ]
    return []


@register(
    "R22_llm_models_alias",
    description="LLM models alias endpoint should mirror the canonical route",
    severity=Severity.MEDIUM,
)
def rule_llm_models_alias(_: RuleContext) -> Iterable[Finding]:
    try:
        from flask import Flask

        from backend.app.api import llm as llm_module
        from backend.app.api.llm import bp as llm_bp
    except Exception as exc:  # pragma: no cover - import guard
        return [
            Finding(
                id="llm-models:import-error",
                rule_id="R22_llm_models_alias",
                severity=Severity.MEDIUM,
                summary="Unable to import LLM API for diagnostics.",
                suggestion="Ensure backend dependencies are installed so diagnostics can probe the models endpoint.",
                evidence=str(exc),
            )
        ]

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(llm_bp)

    engine_config = SimpleNamespace(
        ollama=SimpleNamespace(base_url="http://ollama"),
        models=SimpleNamespace(llm_primary="mock-primary", llm_fallback="mock-fallback", embed="mock-embed"),
    )
    app.config.update(
        RAG_ENGINE_CONFIG=engine_config,
        RAG_EMBED_MANAGER=None,
    )

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def _fake_get(url, timeout):  # noqa: ANN001 - requests compatibility
        return _FakeResponse({"models": [{"name": "mock-model"}]})

    original_get = llm_module.shared_requests.get
    llm_module.shared_requests.get = _fake_get
    try:
        with app.test_client() as client:
            canonical = client.get("/api/llm/models")
            alias = client.get("/api/llm/llm_models")
    finally:
        llm_module.shared_requests.get = original_get

    if canonical.status_code != 200 or alias.status_code != 200:
        return [
            Finding(
                id="llm-models:alias-status",
                rule_id="R22_llm_models_alias",
                severity=Severity.MEDIUM,
                summary="/api/llm/models and /api/llm/llm_models should both return 200.",
                suggestion="Ensure the alias route delegates to the canonical implementation.",
                evidence=f"models={canonical.status_code} alias={alias.status_code}",
            )
        ]
    return []
