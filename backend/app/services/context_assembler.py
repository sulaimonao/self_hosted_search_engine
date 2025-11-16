"""Chat context assembly from persisted messages and memories."""

from __future__ import annotations

from typing import Any

from backend.app.db import AppStateDB


def assemble_context(
    state_db: AppStateDB,
    *,
    user_id: str,
    thread_id: str,
    query: str | None = None,
    url: str | None = None,
    include: set[str] | None = None,
    selection: str | None = None,
    metadata: dict[str, Any] | None = None,
    history_limit: int = 10,
) -> dict[str, Any]:
    """Return a context payload combining chat history, summary and scoped memories."""

    messages = state_db.recent_llm_messages(thread_id, limit=20)
    if not messages:
        messages = state_db.recent_messages(thread_id, limit=20)
    summary = state_db.get_summary(thread_id)
    thread_mems = state_db.list_memories(scope="thread", scope_ref=thread_id, limit=20)
    user_mems = state_db.list_memories(scope="user", scope_ref=user_id, limit=20)
    global_mems = state_db.list_memories(scope="global", scope_ref=None, limit=20)

    combined = thread_mems + user_mems + global_mems
    include_flags = {
        item.strip().lower() for item in include or set() if item and item.strip()
    }
    payload = {
        "messages": messages,
        "summary": summary.get("summary") if summary else None,
        "memories": combined,
    }
    if query:
        payload["query"] = query
    if url:
        payload["url"] = url

    if selection and "selection" in include_flags:
        trimmed = selection.strip()
        if trimmed:
            word_count = len([token for token in trimmed.split() if token])
            payload["selection"] = {
                "text": trimmed,
                "word_count": word_count,
            }

    if "history" in include_flags and url:
        history_entries = state_db.query_history(limit=max(1, history_limit), query=url)
        payload["history"] = history_entries

    if metadata and "metadata" in include_flags:
        payload["metadata"] = metadata

    return payload


__all__ = ["assemble_context"]
