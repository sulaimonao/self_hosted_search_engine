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
) -> dict[str, Any]:
    """Return a context payload combining chat history, summary and scoped memories."""

    messages = state_db.recent_messages(thread_id, limit=20)
    summary = state_db.get_summary(thread_id)
    thread_mems = state_db.list_memories(scope="thread", scope_ref=thread_id, limit=20)
    user_mems = state_db.list_memories(scope="user", scope_ref=user_id, limit=20)
    global_mems = state_db.list_memories(scope="global", scope_ref=None, limit=20)

    combined = thread_mems + user_mems + global_mems
    payload = {
        "messages": messages,
        "summary": summary.get("summary") if summary else None,
        "memories": combined,
    }
    if query:
        payload["query"] = query
    return payload


__all__ = ["assemble_context"]
