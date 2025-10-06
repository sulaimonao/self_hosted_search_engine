"""SQLite schema management for the application state database."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

LOGGER = logging.getLogger(__name__)

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
    """Apply all SQL migrations located in :mod:`backend.app.db.migrations`."""

    _ensure_migration_table(connection)
    applied = _load_applied_migrations(connection)

    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        name = migration_path.name
        if name in applied:
            continue
        sql = migration_path.read_text(encoding="utf-8")
        if not sql.strip():
            _record_migration(connection, name)
            applied.add(name)
            continue
        try:
            with connection:
                connection.executescript(sql)
        except sqlite3.OperationalError as exc:
            if _migration_already_applied(connection, name, exc):
                LOGGER.debug("Skipping already-applied migration %s: %s", name, exc)
                _record_migration(connection, name)
                applied.add(name)
                continue
            raise
        _record_migration(connection, name)
        applied.add(name)


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at REAL DEFAULT (strftime('%s','now'))
            )
            """
        )


def _load_applied_migrations(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT filename FROM schema_migrations"
    ).fetchall()
    return {row[0] for row in rows}


def _record_migration(connection: sqlite3.Connection, name: str) -> None:
    with connection:
        connection.execute(
            "INSERT OR REPLACE INTO schema_migrations(filename) VALUES (?)",
            (name,),
        )


def _migration_already_applied(
    connection: sqlite3.Connection, name: str, error: sqlite3.OperationalError
) -> bool:
    message = str(error).lower()
    if "duplicate column name" in message:
        if name == "003_job_status_settings.sql":
            return _column_exists(connection, "pending_documents", "last_error") and _column_exists(
                connection, "pending_documents", "retry_count"
            )
    if "already exists" in message and name == "003_job_status_settings.sql":
        return _table_exists(connection, "job_status")
    return False


def _column_exists(
    connection: sqlite3.Connection, table: str, column: str
) -> bool:
    table_name = table.replace("'", "''")
    query = f"PRAGMA table_info('{table_name}')"
    rows = connection.execute(query).fetchall()
    return any(row[1] == column for row in rows)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None
