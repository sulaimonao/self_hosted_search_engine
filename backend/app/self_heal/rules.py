from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

from backend.app.ai.self_heal_prompt import ALLOWED_VERBS

RULEPACK_PATH = Path(os.getenv("SELF_HEAL_RULEPACK", "data/self_heal/rulepack.yml"))
MAX_RULES = int(os.getenv("SELF_HEAL_MAX_RULES", "100"))
PLAN_MAX_STEPS = int(os.getenv("SELF_HEAL_PLAN_MAX_STEPS", "8"))


def _safe_load(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        if yaml:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[:MAX_RULES]
    except Exception:
        pass
    return []


def _safe_dump(path: Path, rules: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if yaml:
            path.write_text(
                yaml.safe_dump(list(rules), sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        else:
            path.write_text(json.dumps(list(rules), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_rulepack(path: Path = RULEPACK_PATH) -> List[Dict[str, Any]]:
    return _safe_load(path)


def save_rulepack(rules: Sequence[Dict[str, Any]], path: Path = RULEPACK_PATH) -> None:
    _safe_dump(path, rules)


def _match_banner(signature: Dict[str, Any], symptoms: Dict[str, Any]) -> bool:
    pattern = signature.get("banner_regex")
    if not pattern:
        return True
    try:
        return re.search(pattern, str(symptoms.get("bannerText") or "")) is not None
    except re.error:
        return False


def _match_network(signature: Dict[str, Any], symptoms: Dict[str, Any]) -> bool:
    rules = signature.get("network_any") or []
    if not rules:
        return True
    errors = symptoms.get("networkErrors") or []
    for rule in rules:
        url_rx = rule.get("url_regex")
        status = rule.get("status")
        for entry in errors:
            url_ok = True
            if url_rx:
                try:
                    url_ok = re.search(url_rx, str(entry.get("url") or "")) is not None
                except re.error:
                    url_ok = False
            status_ok = True if status is None else int(entry.get("status") or -1) == int(status)
            if url_ok and status_ok:
                return True
    return False


def _match_console(signature: Dict[str, Any], symptoms: Dict[str, Any]) -> bool:
    needles = signature.get("console_any") or []
    if not needles:
        return True
    logs = symptoms.get("consoleErrors") or []
    for needle in needles:
        if any(str(needle) in str(line or "") for line in logs):
            return True
    return False


def _match_dom(signature: Dict[str, Any], dom_snippet: str) -> bool:
    pattern = signature.get("dom_regex")
    if not pattern:
        return True
    try:
        return re.search(pattern, dom_snippet or "") is not None
    except re.error:
        return False


def _sanitize_steps(raw_steps: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_steps, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for raw in raw_steps[:PLAN_MAX_STEPS]:
        if not isinstance(raw, dict):
            continue
        step_type = str(raw.get("type") or raw.get("verb") or "").strip()
        if step_type not in ALLOWED_VERBS:
            continue
        payload: Dict[str, Any] = {"type": step_type}
        if raw.get("headless") is True:
            payload["headless"] = True
        args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
        if step_type == "navigate":
            url = str(args.get("url") or raw.get("url") or "").strip()
            if not url:
                continue
            payload["url"] = url
        elif step_type == "click":
            selector = str(args.get("selector") or raw.get("selector") or "").strip()
            text = str(args.get("text") or raw.get("text") or "").strip()
            if not selector and not text:
                continue
            if selector:
                payload["selector"] = selector
            if text:
                payload["text"] = text
        elif step_type == "type":
            selector = str(args.get("selector") or raw.get("selector") or "").strip()
            text_value = args.get("text") or raw.get("text")
            text = str(text_value) if text_value is not None else ""
            if not selector or not text:
                continue
            payload["selector"] = selector
            payload["text"] = text
        elif step_type == "waitForStable":
            ms_value = args.get("ms") or raw.get("ms")
            try:
                ms = int(ms_value)
            except (TypeError, ValueError):
                ms = None
            if ms and ms > 0:
                payload["ms"] = ms
        cleaned.append(payload)
    return cleaned


def try_rules_first(
    incident: Dict[str, Any],
    *,
    rules: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    rules_seq = list(rules) if rules is not None else load_rulepack()
    if not rules_seq:
        return None
    symptoms = dict(incident.get("symptoms") or {})
    dom_snippet = str(incident.get("domSnippet") or "")
    for rule in rules_seq:
        if not rule.get("enabled"):
            continue
        signature = dict(rule.get("signature") or {})
        if not (
            _match_banner(signature, symptoms)
            and _match_network(signature, symptoms)
            and _match_console(signature, symptoms)
            and _match_dom(signature, dom_snippet)
        ):
            continue
        directive_payload = dict(rule.get("directive") or {})
        steps = _sanitize_steps(directive_payload.get("steps"))
        if not steps:
            continue
        reason = str(directive_payload.get("reason") or f"Rule {rule.get('id') or 'matched'} applied").strip()
        payload = {"reason": reason, "steps": steps}
        return str(rule.get("id") or "unknown"), payload
    return None


def _escape_regex_literal(value: str) -> str:
    return re.escape(value or "")


def propose_rule_from_episode(ep: Dict[str, Any], *, default_enabled: bool = False) -> Dict[str, Any]:
    symptoms = dict(ep.get("symptoms") or {})
    directive = dict(ep.get("directive") or {})
    banner = str(symptoms.get("bannerText") or "")
    network_errors = list(symptoms.get("networkErrors") or [])
    meta = dict(ep.get("meta") or {})
    dom_snippet = str(ep.get("domSnippet") or symptoms.get("domSnippet") or meta.get("domSnippet") or "")

    signature: Dict[str, Any] = {}
    if banner:
        signature["banner_regex"] = _escape_regex_literal(banner[:200])
    if network_errors:
        entries: List[Dict[str, Any]] = []
        for entry in network_errors[:2]:
            url = str(entry.get("url") or "").split("?")[0]
            if not url:
                continue
            entries.append({
                "url_regex": _escape_regex_literal(url),
                "status": entry.get("status"),
            })
        if entries:
            signature["network_any"] = entries
    if "role=\"alert\"" in dom_snippet:
        signature["dom_regex"] = r'role="alert"'

    steps = _sanitize_steps(directive.get("steps"))
    reason = str(directive.get("reason") or "Deterministic replay of a successful fix").strip()

    rule_id = f"rule_{str(ep.get('id') or '')[:8]}" if ep.get("id") else None
    return {
        "id": rule_id,
        "enabled": bool(default_enabled),
        "signature": signature,
        "directive": {
            "reason": reason,
            "steps": steps,
        },
    }


def add_rule(rule: Dict[str, Any], *, path: Path = RULEPACK_PATH) -> Tuple[str, List[Dict[str, Any]]]:
    rules = load_rulepack(path)
    rule_id = str(rule.get("id") or f"rule_{len(rules) + 1}")
    rule["id"] = rule_id
    filtered = [existing for existing in rules if existing.get("id") != rule_id]
    if len(filtered) == len(rules) and len(rules) >= MAX_RULES:
        raise ValueError("rulepack limit reached")
    filtered.append(rule)
    save_rulepack(filtered, path)
    return rule_id, filtered


def enable_rule(rule_id: str, enabled: bool, *, path: Path = RULEPACK_PATH) -> List[Dict[str, Any]]:
    rules = load_rulepack(path)
    changed = False
    for rule in rules:
        if rule.get("id") == rule_id:
            rule["enabled"] = bool(enabled)
            changed = True
            break
    if changed:
        save_rulepack(rules, path)
    return rules


def reorder_rule(rule_id: str, new_index: int, *, path: Path = RULEPACK_PATH) -> List[Dict[str, Any]]:
    rules = load_rulepack(path)
    current_index = next((idx for idx, item in enumerate(rules) if item.get("id") == rule_id), None)
    if current_index is None:
        return rules
    rule = rules.pop(current_index)
    new_index = max(0, min(new_index, len(rules)))
    rules.insert(new_index, rule)
    save_rulepack(rules, path)
    return rules


def apply_order(order: Sequence[str], *, path: Path = RULEPACK_PATH) -> List[Dict[str, Any]]:
    rules = load_rulepack(path)
    lookup = {rule.get("id"): rule for rule in rules}
    ordered: List[Dict[str, Any]] = []
    for rid in order:
        rule = lookup.pop(rid, None)
        if rule:
            ordered.append(rule)
    ordered.extend(lookup.values())
    save_rulepack(ordered, path)
    return ordered


def read_rulepack_text(path: Path = RULEPACK_PATH) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


__all__ = [
    "RULEPACK_PATH",
    "MAX_RULES",
    "PLAN_MAX_STEPS",
    "load_rulepack",
    "save_rulepack",
    "try_rules_first",
    "propose_rule_from_episode",
    "add_rule",
    "enable_rule",
    "reorder_rule",
    "apply_order",
    "read_rulepack_text",
]
