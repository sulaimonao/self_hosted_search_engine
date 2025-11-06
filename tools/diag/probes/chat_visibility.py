"""Static probe to catch chat visibility regressions.

Ensures the useChat renderer concatenates UIMessage.parts[].text and that the
model picker onModelChange is wired through ChatPanel -> ChatPanelUseChat -> CopilotHeader.

This helps detect cases where assistant/user messages render as empty strings.
"""
from __future__ import annotations

import re
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe

PANEL_USECHAT = "frontend/src/components/panels/ChatPanelUseChat.tsx"
PANEL_PARENT = "frontend/src/components/panels/ChatPanel.tsx"


def _line(text: str, needle: str) -> int | None:
    i = text.find(needle)
    if i == -1:
        return None
    return text.count("\n", 0, i) + 1


@register_probe(
    "probe_chat_visibility",
    description="Chat UI should render UIMessage.parts and wire onModelChange",
    severity=Severity.HIGH,
)
def probe_chat_visibility(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    usechat_text = context.read_text(PANEL_USECHAT)
    if not usechat_text:
        return [
            Finding(
                id=f"{PANEL_USECHAT}:missing",
                rule_id="probe_chat_visibility",
                severity=Severity.HIGH,
                summary=f"{PANEL_USECHAT} missing; cannot verify chat visibility wiring.",
                suggestion="Restore ChatPanelUseChat.tsx and ensure UIMessage.parts[].text is rendered.",
                file=PANEL_USECHAT,
            )
        ]

    # Ensure parts[].text concatenation exists
    parts_concat_present = bool(
        re.search(r"parts\s*\?\s*parts\s*\.map\(.*text\s*\?\s*String\(p\.text", usechat_text, re.DOTALL)
    ) or "textFromParts" in usechat_text
    if not parts_concat_present:
        findings.append(
            Finding(
                id=f"{PANEL_USECHAT}:missing-parts-join",
                rule_id="probe_chat_visibility",
                severity=Severity.HIGH,
                summary="ChatPanelUseChat does not join UIMessage.parts[].text before rendering.",
                suggestion="Prefer parts.map(p => p.text).join("") and fallback to content/text.",
                file=PANEL_USECHAT,
                line_hint=_line(usechat_text, "parts"),
            )
        )

    # Ensure CopilotHeader receives onModelChange
    if "<CopilotHeader" in usechat_text and "onModelChange" not in usechat_text:
        findings.append(
            Finding(
                id=f"{PANEL_USECHAT}:missing-onModelChange",
                rule_id="probe_chat_visibility",
                severity=Severity.MEDIUM,
                summary="CopilotHeader in ChatPanelUseChat does not receive onModelChange.",
                suggestion="Pass onModelChange prop through to <CopilotHeader />.",
                file=PANEL_USECHAT,
                line_hint=_line(usechat_text, "CopilotHeader"),
            )
        )

    parent_text = context.read_text(PANEL_PARENT)
    if parent_text:
        # Ensure ChatPanel.tsx passes onModelChange to <ChatPanelUseChat />
        if "<ChatPanelUseChat" in parent_text and "onModelChange={handleModelChange}" not in parent_text:
            findings.append(
                Finding(
                    id=f"{PANEL_PARENT}:missing-onModelChange",
                    rule_id="probe_chat_visibility",
                    severity=Severity.MEDIUM,
                    summary="ChatPanel does not pass handleModelChange to ChatPanelUseChat.",
                    suggestion="Provide onModelChange={handleModelChange} when rendering ChatPanelUseChat.",
                    file=PANEL_PARENT,
                    line_hint=_line(parent_text, "ChatPanelUseChat"),
                )
            )

        # Ensure send fallback model logic exists in ChatPanelUseChat
    if usechat_text and not re.search(r"selectedModel\s*\|\|\s*inventory\?\.configured\?\.primary\s*\|\|\s*inventory\?\.configured\?\.fallback", usechat_text):
        findings.append(
            Finding(
                id=f"{PANEL_USECHAT}:missing-fallback-model",
                rule_id="probe_chat_visibility",
                severity=Severity.MEDIUM,
                summary="ChatPanelUseChat is not computing fallback model on send.",
                suggestion="Use selectedModel || inventory?.configured?.primary || inventory?.configured?.fallback.",
                file=PANEL_USECHAT,
            )
        )

    return findings
