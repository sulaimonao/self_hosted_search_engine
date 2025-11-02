"""Shared helpers for lightweight route modules."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager

_DB_PATH = os.environ.get("APP_STATE_DB", os.path.join("data", "app_state.sqlite3"))
_LOCK = threading.Lock()


def _ensure_dirs() -> None:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


def _bootstrap(conn: sqlite3.Connection) -> None:
    """Create the ``app_config`` table if it is missing."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_config (
          k TEXT PRIMARY KEY,
          v TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """
    )


@contextmanager
def get_db() -> sqlite3.Connection:
    """Yield a SQLite connection configured for WAL mode."""

    _ensure_dirs()
    with _LOCK:
        conn = sqlite3.connect(_DB_PATH, isolation_level=None, check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            _bootstrap(conn)
            yield conn
        finally:
            conn.close()
