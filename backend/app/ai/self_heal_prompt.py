"""Prompt builders for the self-heal planner."""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Tuple

# Contract for the in-tab executor
ALLOWED_VERBS = {"navigate", "reload", "click", "type", "waitForStable"}

# (Optional) Include this schema text verbatim inside the SYSTEM prompt to enforce JSON-only replies
OUTPUT_SCHEMA_JSON = r"""
{
  "reason": "string - concise why this plan should fix the incident",
  "plan_confidence": "high | medium | low",
  "needs_user_permission": true,
  "steps": [
    {
      "id": "s1",
      "type": "reload | navigate | click | type | waitForStable",
      "args": { "url?": "string", "selector?": "string", "text?": "string", "ms?": 600 },
      "headless": false,
      "verify": { "noBannerRegex?": "string", "elementExists?": "css", "httpOkProbe?": "url" },
      "on_fail_next": "s2"
    }
  ],
  "ask_user": ["zero-or-more short clarification questions when plan_confidence = low"],
  "fallback": {
    "enabled": true,
    "headless_hint": [
      "precise steps that require the Agent-Browser (multi-page flows, no credentials)"
    ]
  }
}
""".strip()

SYSTEM_PROMPT = f"""
You are a Playwright-savvy self-healing planner.
You receive a browser incident (UI banner, console/network failures, DOM snippet).
Return a minimal, permissioned plan that a SAFE in-tab executor can run.

STRICT REQUIREMENTS
- Output must be valid JSON matching this schema (no prose outside JSON):
{OUTPUT_SCHEMA_JSON}
- Allowed verbs only: navigate(url), reload(), click(selector?|text?), type(selector,text), waitForStable(ms?).
- Prefer least-invasive steps first (reload, targeted click like 'Retry').
- Provide a verification for each critical step (noBannerRegex, elementExists, httpOkProbe).
- If not confident, set plan_confidence = "low" and add 1–3 ask_user questions.
- If a fix requires multi-page scripted flows, tag those steps headless:true and also list them in fallback.headless_hint.
- Never include secrets, credentials, or destructive actions. Never clear storage/cookies unless explicitly requested.
- Do not include chain-of-thought; return only the final JSON.
""".strip()

USER_TEMPLATE = """
Incident:
- url: {url}
- bannerText: {banner}
- consoleErrors (last 5): {console}
- networkErrors (last 3): {network}
- domSnippet (trimmed): {dom}

Desired state:
- The page renders without the error banner and is usable for the next action.

Context:
- Allowed verbs: navigate, reload, click, type, waitForStable.
- Executor prefers selector-based clicks; text targeting is fallback only.
- Headless Agent-Browser is available when headless:true (no secrets).

Return:
- Valid JSON only (match the schema exactly). No prose.
""".strip()

BIAS = {
    "lite": (
        "Bias:\n"
        "- Produce at most 3 steps.\n"
        "- First step should be reload() or a single click('Retry') if present in domSnippet.\n"
        "- Provide one verification per critical step.\n"
        "- If confidence < high, add exactly one ask_user question.\n"
    ),
    "deep": (
        "Bias:\n"
        "- Up to 6 steps, still minimal and safe-first.\n"
        "- Prefer precise selectors derived from domSnippet (role, data-*), avoid brittle nth-child.\n"
        "- If networkErrors include 5xx on a key route, plan a recoverable UI flow (click 'Retry' / 'Refresh data').\n"
        "- Include waitForStable between async steps (400–800ms).\n"
        "- Provide verification after each 1–2 steps.\n"
        "- If uncertain between two plausible flows, include both as branches via on_fail_next.\n"
    ),
    "headless": (
        "Bias:\n"
        "- Steps that require multi-page flows must be tagged headless:true.\n"
        "- Still provide in-tab verifications (e.g., noBannerRegex after returning).\n"
        "- Keep 4–8 steps; include an httpOkProbe for the previously failing endpoint if known.\n"
    ),
    "repair": (
        "Bias:\n"
        "- Propose BOTH a UI quick-fix plan AND a minimal code patch hint (as a diff summary) in fallback.headless_hint.\n"
        "- No secrets; code hint is human-reviewed later.\n"
    ),
}

# Truncation & sanitization rules
_ATTR_RE = re.compile(r'\s+(onclick|style|srcset|on\w+|data:image/[^"]+)="[^"]*"')


def _strip_attributes(html: str) -> str:
    try:
        return _ATTR_RE.sub("", html)
    except Exception:
        return html


def _truncate_incident(payload: Mapping[str, Any]) -> Dict[str, Any]:
    sym = dict(payload.get("symptoms") or {})
    console = list(sym.get("consoleErrors") or [])[-5:]
    network = list(sym.get("networkErrors") or [])[-3:]
    dom = (payload.get("domSnippet") or "")[:4000]
    return {
        "url": str(payload.get("url") or ""),
        "banner": (sym.get("bannerText") or "")[:300],
        "console": console,
        "network": network,
        "dom": _strip_attributes(dom),
    }


def build_prompts(
    incident: Mapping[str, Any], variant: str = "lite"
) -> Tuple[str, str]:
    """Return the (system_prompt, user_message) pair for the planner."""

    ev = _truncate_incident(incident)
    sys_prompt = SYSTEM_PROMPT + "\n" + BIAS.get(variant, BIAS["lite"])
    user_prompt = USER_TEMPLATE.format(
        url=ev["url"],
        banner=ev["banner"],
        console=ev["console"],
        network=ev["network"],
        dom=ev["dom"],
    )
    return sys_prompt, user_prompt


__all__ = [
    "ALLOWED_VERBS",
    "BIAS",
    "OUTPUT_SCHEMA_JSON",
    "SYSTEM_PROMPT",
    "USER_TEMPLATE",
    "build_prompts",
]
