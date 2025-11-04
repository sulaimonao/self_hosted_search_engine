"""Shared helpers for React-oriented diagnostics."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set, Tuple


EFFECT_CALL_RE = re.compile(r"(?:React\.)?use(?:Layout)?Effect\s*\(")
STATE_DECL_RE = re.compile(
    r"const\s+\[\s*(?P<state>[A-Za-z_][A-Za-z0-9_]*)\s*,\s*(?P<setter>[A-Za-z_][A-Za-z0-9_]*)\s*\]"
    r"\s*=\s*(?:React\.)?useState\s*(?:<[^>]+>)?\s*\("
)


@dataclass(frozen=True)
class EffectBlock:
    """Descriptor for a React effect along with dependency metadata."""

    deps: Set[str]
    body: str
    body_start: int
    body_end: int
    line: int
    kind: str  # "effect" or "layout"


def _skip_string(text: str, index: int, quote: str, limit: int) -> int:
    escape = False
    i = index + 1
    while i < limit:
        char = text[i]
        if escape:
            escape = False
            i += 1
            continue
        if char == "\\":
            escape = True
            i += 1
            continue
        if char == quote:
            return i + 1
        i += 1
    return limit


def _skip_line_comment(text: str, index: int, limit: int) -> int:
    newline = text.find("\n", index + 2, limit)
    if newline == -1:
        return limit
    return newline + 1


def _skip_block_comment(text: str, index: int, limit: int) -> int:
    close = text.find("*/", index + 2, limit)
    if close == -1:
        return limit
    return close + 2


def _consume_balanced(text: str, start: int, open_char: str, close_char: str, limit: int | None = None) -> Tuple[str, int]:
    """Return the substring enclosed by matching delimiters starting at index."""

    limit = limit if limit is not None else len(text)
    depth = 0
    i = start
    if i >= limit or text[i] != open_char:
        return "", limit
    while i < limit:
        char = text[i]
        if char == open_char:
            depth += 1
            i += 1
            continue
        if char == close_char:
            depth -= 1
            i += 1
            if depth == 0:
                return text[start + 1 : i - 1], i
            continue
        if char in "\"'`":
            i = _skip_string(text, i, char, limit)
            continue
        if char == "/" and i + 1 < limit:
            nxt = text[i + 1]
            if nxt == "/":
                i = _skip_line_comment(text, i, limit)
                continue
            if nxt == "*":
                i = _skip_block_comment(text, i, limit)
                continue
        i += 1
    return "", limit


def _split_top_level(text: str, start: int, end: int) -> List[Tuple[str, int, int]]:
    """Split a slice of text by commas without descending into nested structures."""

    parts: List[Tuple[str, int, int]] = []
    paren = bracket = brace = 0
    current_start: int | None = None
    i = start
    while i < end:
        char = text[i]
        if char in "\"'`":
            if current_start is None:
                current_start = i
            i = _skip_string(text, i, char, end)
            continue
        if char == "/" and i + 1 < end:
            nxt = text[i + 1]
            if nxt == "/":
                if current_start is None:
                    current_start = i
                i = _skip_line_comment(text, i, end)
                continue
            if nxt == "*":
                if current_start is None:
                    current_start = i
                i = _skip_block_comment(text, i, end)
                continue
        if char == "(":
            paren += 1
        elif char == ")":
            paren = max(paren - 1, 0)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(bracket - 1, 0)
        elif char == "{":
            brace += 1
        elif char == "}":
            brace = max(brace - 1, 0)
        if char == "," and paren == 0 and bracket == 0 and brace == 0:
            if current_start is not None:
                raw_segment = text[current_start:i]
                stripped = raw_segment.strip()
                if stripped:
                    leading = len(raw_segment) - len(raw_segment.lstrip())
                    parts.append((stripped, current_start + leading, i))
            current_start = None
            i += 1
            continue
        if current_start is None and not char.isspace():
            current_start = i
        i += 1
    if current_start is not None:
        raw_segment = text[current_start:end]
        stripped = raw_segment.strip()
        if stripped:
            leading = len(raw_segment) - len(raw_segment.lstrip())
            parts.append((stripped, current_start + leading, end))
    return parts


def _parse_dependency_segment(text: str, start: int) -> Tuple[Set[str], int]:
    deps: Set[str] = set()
    content, end_index = _consume_balanced(text, start, "[", "]")
    if not content:
        return deps, end_index
    for raw in content.split(","):
        token = raw.split("//", 1)[0].split("#", 1)[0].strip()
        if not token:
            continue
        sanitized = re.sub(r"[^\w.]", "", token)
        if sanitized:
            deps.add(sanitized)
    return deps, end_index


def iter_effect_blocks(text: str) -> List[EffectBlock]:
    """Parse the file and return metadata about useEffect/useLayoutEffect blocks."""

    blocks: List[EffectBlock] = []
    for match in EFFECT_CALL_RE.finditer(text):
        call_start = match.start()
        paren_index = text.find("(", call_start)
        if paren_index == -1:
            continue
        args_parts, call_end = split_call_arguments(text, paren_index)
        if not args_parts:
            continue
        callback_src, callback_start, callback_end = args_parts[0]
        deps: Set[str] = set()
        for segment, segment_start, _segment_end in args_parts[1:]:
            if segment.startswith("["):
                deps, _ = _parse_dependency_segment(text, segment_start)
                break
        arrow_index = text.find("=>", callback_start, callback_end)
        body_start = body_end = None
        body_text = ""
        if arrow_index != -1:
            scan_start = arrow_index + 2
            while scan_start < callback_end and text[scan_start].isspace():
                scan_start += 1
            if scan_start < callback_end and text[scan_start] == "{":
                body_content, body_closure = _consume_balanced(text, scan_start, "{", "}")
                body_text = body_content
                body_start = scan_start + 1
                body_end = body_closure - 1
            else:
                body_start = scan_start
                body_end = callback_end
                body_text = text[body_start:body_end].strip()
        else:
            brace_index = text.find("{", callback_start, callback_end)
            if brace_index == -1:
                continue
            body_content, body_closure = _consume_balanced(text, brace_index, "{", "}")
            body_text = body_content
            body_start = brace_index + 1
            body_end = body_closure - 1
        if body_start is None or body_end is None:
            continue
        line = text.count("\n", 0, call_start) + 1
        kind = "layout" if "useLayoutEffect" in text[call_start:match.end()] else "effect"
        blocks.append(
            EffectBlock(
                deps=deps,
                body=body_text,
                body_start=body_start,
                body_end=body_end,
                line=line,
                kind=kind,
            )
        )
    return blocks


def split_call_arguments(text: str, paren_index: int) -> Tuple[List[Tuple[str, int, int]], int]:
    """Return top-level arguments for a call starting at the provided '('."""

    content, end_index = _consume_balanced(text, paren_index, "(", ")")
    if not content:
        return [], end_index
    parts = _split_top_level(text, paren_index + 1, end_index - 1)
    return parts, end_index


def collect_state_setters(text: str) -> dict[str, str]:
    """Return mapping of state variable name to its setter function."""

    mapping: dict[str, str] = {}
    for match in STATE_DECL_RE.finditer(text):
        state = match.group("state")
        setter = match.group("setter")
        if not state or not setter:
            continue
        mapping[state] = setter
    return mapping


def position_to_line(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def inside_effect(position: int, blocks: Sequence[EffectBlock]) -> bool:
    return any(block.body_start <= position <= block.body_end for block in blocks)


__all__ = [
    "EffectBlock",
    "collect_state_setters",
    "inside_effect",
    "iter_effect_blocks",
    "position_to_line",
    "split_call_arguments",
]
