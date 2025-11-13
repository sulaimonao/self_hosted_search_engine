"""Lightweight helpers for running FTS5 queries safely."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

_WORD_RE = re.compile(r"\S+")


def _fts_safe(text: str) -> str:
    tokens = _WORD_RE.findall((text or "").strip())
    if not tokens:
        return ""
    quoted: list[str] = []
    for token in tokens:
        escaped = token.replace('"', '""')
        quoted.append(f'"{escaped}"')
    return " ".join(quoted)


def search_docs(
    db_path: str | Path, text: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    sanitized = _fts_safe(text)
    if not sanitized:
        return []
    path = Path(db_path)
    limit_value = max(1, min(int(limit or 1), 200))
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                url,
                title,
                highlight(docs_fts, 2, '[', ']') AS snippet,
                bm25(docs_fts) AS score
            FROM docs_fts
            WHERE docs_fts MATCH ?
            ORDER BY score ASC
            LIMIT ?
            """,
            (sanitized, limit_value),
        )
        rows = cursor.fetchall()
    finally:
        connection.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        url = row["url"] if isinstance(row, sqlite3.Row) else row[0]
        title = row["title"] if isinstance(row, sqlite3.Row) else row[1]
        snippet = row["snippet"] if isinstance(row, sqlite3.Row) else row[2]
        score_value = row["score"] if isinstance(row, sqlite3.Row) else row[3]
        try:
            score = float(score_value)
        except (TypeError, ValueError):
            score = 0.0
        results.append(
            {
                "url": url,
                "title": title,
                "snippet": snippet or "",
                "score": score,
            }
        )
    return results


__all__ = ["_fts_safe", "search_docs"]
