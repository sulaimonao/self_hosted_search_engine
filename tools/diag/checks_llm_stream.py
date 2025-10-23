"""Diagnostics to ensure Electron LLM streaming infrastructure is robust."""

from __future__ import annotations

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
