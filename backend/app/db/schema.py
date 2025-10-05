"""SQLite schema management for the application state database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Return a SQLite connection with conservative defaults."""

    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.execute("PRAGMA synchronous=NORMAL;")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Apply bootstrap migration(s) to *connection*."""

    migration_path = MIGRATIONS_DIR / "001_init.sql"
    sql = migration_path.read_text(encoding="utf-8")
    with connection:
        connection.executescript(sql)
