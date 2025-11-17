"""SQLite schema management for the application state database."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


LOGGER = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parent
_MIGRATIONS_DIR = _DB_DIR / "migrations"
_APP_CONFIG_SCHEMA = _MIGRATIONS_DIR / "008_app_config.sql"
_APP_CONFIG_DEFAULTS = _MIGRATIONS_DIR / "20251102_app_config.sql"
_APP_CONFIG_DESKTOP_DEFAULTS = _MIGRATIONS_DIR / "20251115_desktop_defaults.sql"

MigrationFn = Callable[[sqlite3.Connection], None]


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Return a SQLite connection with conservative defaults."""

    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.execute("PRAGMA synchronous=NORMAL;")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Apply all known migrations in a re-entrant, idempotent fashion."""

    LOGGER.debug("Ensuring migration ledger")
    _ensure_ledger(connection)
    _backfill_legacy_ledger(connection)

    for migration_id, migration_fn in _MIGRATIONS:
        if _already_applied(connection, migration_id):
            continue
        LOGGER.info("Applying migration %s", migration_id)
        try:
            migration_fn(connection)
            with connection:
                _mark_applied(connection, migration_id)
        except Exception:  # noqa: BLE001 - surface precise failure context to logs
            LOGGER.exception(
                "Migration %s failed. Inspect the _migrations ledger for partial state.",
                migration_id,
            )
            raise
        LOGGER.info("Applied migration %s", migration_id)


def _ensure_ledger(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )


def _backfill_legacy_ledger(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "schema_migrations"):
        return
    legacy = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT filename, COALESCE(applied_at, strftime('%s','now')) FROM schema_migrations"
        )
    }
    if not legacy:
        return
    inserts: list[tuple[str, str]] = []
    for filename, applied_at in legacy.items():
        migration_id = filename.rsplit(".", 1)[0]
        if migration_id not in MIGRATION_IDS or _already_applied(
            connection, migration_id
        ):
            continue
        LOGGER.debug("Backfilling legacy migration %s", migration_id)
        inserts.append((migration_id, _coerce_epoch_to_iso(applied_at)))

    if not inserts:
        return

    with connection:
        connection.executemany(
            "INSERT OR IGNORE INTO _migrations(id, applied_at) VALUES(?, ?)",
            inserts,
        )


def _already_applied(connection: sqlite3.Connection, migration_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM _migrations WHERE id=?",
        (migration_id,),
    ).fetchone()
    return row is not None


def _mark_applied(connection: sqlite3.Connection, migration_id: str) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO _migrations(id, applied_at) VALUES(?, ?)",
        (migration_id, datetime.now(tz=timezone.utc).isoformat(timespec="seconds")),
    )


def _coerce_epoch_to_iso(value: float | int | str) -> str:
    try:
        epoch = float(value)
    except (TypeError, ValueError):
        return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds")


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return any(
        row[1] == column for row in connection.execute(f"PRAGMA table_info({table})")
    )


def _column_type(connection: sqlite3.Connection, table: str, column: str) -> str | None:
    row = next(
        (
            info
            for info in connection.execute(f"PRAGMA table_info({table})")
            if info[1] == column
        ),
        None,
    )
    if row is None:
        return None
    declared = (row[2] or "").strip()
    return declared.upper() or None


def _index_exists(connection: sqlite3.Connection, table: str, name: str) -> bool:
    if not _table_exists(connection, table):
        return False
    return any(
        row[1] == name for row in connection.execute(f"PRAGMA index_list({table})")
    )


def _migration_001_init(connection: sqlite3.Connection) -> None:
    if _table_exists(connection, "crawl_jobs"):
        return
    connection.executescript(
        """
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS crawl_jobs (
          id TEXT PRIMARY KEY,
          started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          status TEXT CHECK(status IN ('queued','running','success','error')) NOT NULL,
          seed TEXT,
          query TEXT,
          stats TEXT,
          error TEXT,
          normalized_path TEXT,
          preview_json TEXT
        );

        CREATE TABLE IF NOT EXISTS crawl_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          stage TEXT NOT NULL,
          payload TEXT,
          FOREIGN KEY(job_id) REFERENCES crawl_jobs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_crawl_events_job ON crawl_events(job_id, id DESC);

        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY,
          url TEXT NOT NULL,
          canonical_url TEXT,
          site TEXT,
          title TEXT,
          description TEXT,
          authors TEXT,
          language TEXT,
          http_status INTEGER,
          mime_type TEXT,
          content_hash TEXT,
          fetched_at DATETIME,
          normalized_path TEXT,
          text_len INTEGER,
          tokens INTEGER,
          embeddings_ref TEXT,
          categories TEXT,
          labels TEXT,
          source TEXT,
          first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
          last_seen DATETIME,
          job_id TEXT,
          verification TEXT,
          FOREIGN KEY(job_id) REFERENCES crawl_jobs(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_documents_url ON documents(url);
        CREATE INDEX IF NOT EXISTS idx_documents_site ON documents(site);
        CREATE INDEX IF NOT EXISTS idx_documents_last_seen ON documents(last_seen DESC);

        CREATE TABLE IF NOT EXISTS page_visits (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          url TEXT NOT NULL,
          visited_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          referer TEXT,
          dur_ms INTEGER,
          source TEXT DEFAULT 'browser-mode'
        );
        CREATE INDEX IF NOT EXISTS idx_page_visits_url ON page_visits(url);

        CREATE TABLE IF NOT EXISTS chat_threads (
          id TEXT PRIMARY KEY,
          title TEXT,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          last_activity DATETIME
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
          id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL,
          role TEXT CHECK(role IN ('user','assistant','system')) NOT NULL,
          content TEXT NOT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          tokens INTEGER,
          FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS chat_summaries (
          thread_id TEXT PRIMARY KEY,
          summary TEXT,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          embedding_ref TEXT,
          FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memories (
          id TEXT PRIMARY KEY,
          scope TEXT CHECK(scope IN ('global','user','thread','doc')) NOT NULL,
          scope_ref TEXT,
          key TEXT,
          value TEXT,
          metadata TEXT,
          strength REAL DEFAULT 1.0,
          last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope, scope_ref);

        CREATE TABLE IF NOT EXISTS memory_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          memory_id TEXT,
          action TEXT,
          detail TEXT,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _migration_002_pending_vectors(connection: sqlite3.Connection) -> None:
    if _table_exists(connection, "pending_documents"):
        return
    sql_path = _MIGRATIONS_DIR / "002_pending_vectors.sql"
    connection.executescript(sql_path.read_text(encoding="utf-8"))


def _migration_003_job_status_settings(connection: sqlite3.Connection) -> None:
    needs_settings = not _table_exists(connection, "app_settings") or not _table_exists(
        connection, "job_status"
    )
    needs_columns = not _column_exists(
        connection, "pending_documents", "last_error"
    ) or not _column_exists(connection, "pending_documents", "retry_count")
    needs_indexes = not _index_exists(
        connection, "pending_chunks", "idx_pending_chunks_doc_seq"
    )
    if not (needs_settings or needs_columns or needs_indexes):
        return
    sql_path = _MIGRATIONS_DIR / "003_job_status_settings.sql"
    connection.executescript(sql_path.read_text(encoding="utf-8"))


def _migration_004_pending_vectors_text(connection: sqlite3.Connection) -> None:
    expected_types = {
        ("pending_documents", "sim_signature"): "TEXT",
        ("pending_documents", "created_at"): "INTEGER",
        ("pending_documents", "updated_at"): "INTEGER",
        ("pending_chunks", "created_at"): "INTEGER",
        ("pending_chunks", "updated_at"): "INTEGER",
        ("pending_vectors_queue", "next_attempt_at"): "INTEGER",
        ("pending_vectors_queue", "created_at"): "INTEGER",
        ("pending_vectors_queue", "updated_at"): "INTEGER",
    }
    if all(
        _column_type(connection, table, column) == expected
        for (table, column), expected in expected_types.items()
        if _table_exists(connection, table)
    ):
        return
    sql_path = _MIGRATIONS_DIR / "004_pending_vectors_text.sql"
    connection.executescript(sql_path.read_text(encoding="utf-8"))


def _migration_005_browser_features(connection: sqlite3.Connection) -> None:
    table = "crawl_jobs"
    with connection:
        if not _column_exists(connection, table, "priority"):
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN priority INTEGER NOT NULL DEFAULT 0"
            )
        if not _column_exists(connection, table, "reason"):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN reason TEXT")
        if not _column_exists(connection, table, "enqueued_at"):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN enqueued_at TEXT")
        if not _column_exists(connection, table, "finished_at"):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN finished_at TEXT")

    with connection:
        connection.execute(
            "UPDATE crawl_jobs SET enqueued_at = COALESCE(enqueued_at, started_at, datetime('now')) WHERE enqueued_at IS NULL"
        )

    connection.executescript(
        """
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS tabs (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            shadow_mode TEXT CHECK(shadow_mode IN ('off','visited_only','visited_outbound'))
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tab_id TEXT,
            url TEXT NOT NULL,
            title TEXT,
            visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            referrer TEXT,
            status_code INTEGER,
            content_type TEXT,
            shadow_enqueued BOOLEAN DEFAULT 0,
            FOREIGN KEY(tab_id) REFERENCES tabs(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_history_tab_time ON history(tab_id, visited_at DESC);
        CREATE INDEX IF NOT EXISTS idx_history_url ON history(url);

        CREATE TABLE IF NOT EXISTS bookmark_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(parent_id) REFERENCES bookmark_folders(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_bookmark_folders_parent ON bookmark_folders(parent_id);

        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER,
            url TEXT NOT NULL,
            title TEXT,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(folder_id) REFERENCES bookmark_folders(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bookmarks_folder ON bookmarks(folder_id);
        CREATE INDEX IF NOT EXISTS idx_bookmarks_url ON bookmarks(url);

        CREATE TABLE IF NOT EXISTS source_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL
        );

        INSERT OR IGNORE INTO source_categories(key, label) VALUES
            ('news', 'News & Current Affairs'),
            ('music', 'Music & Culture'),
            ('entertainment', 'Entertainment & Media'),
            ('art', 'Art & Design'),
            ('tech', 'Technology & Science');

        CREATE TABLE IF NOT EXISTS seed_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_key TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            added_by TEXT CHECK(added_by IN ('user','llm')) DEFAULT 'user',
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category_key, url),
            FOREIGN KEY(category_key) REFERENCES source_categories(key) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_seed_sources_category ON seed_sources(category_key, enabled);

        CREATE TABLE IF NOT EXISTS shadow_settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            enabled BOOLEAN NOT NULL DEFAULT 0,
            mode TEXT CHECK(mode IN ('off','visited_only','visited_outbound')) NOT NULL DEFAULT 'off',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            site TEXT,
            title TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP,
            topics TEXT,
            embedding BLOB
        );
        CREATE INDEX IF NOT EXISTS idx_pages_site ON pages(site);
        CREATE INDEX IF NOT EXISTS idx_pages_last_seen ON pages(last_seen DESC);

        CREATE TABLE IF NOT EXISTS link_edges (
            src_url TEXT,
            dst_url TEXT,
            relation TEXT DEFAULT 'link',
            PRIMARY KEY (src_url, dst_url)
        );
        CREATE INDEX IF NOT EXISTS idx_link_edges_src ON link_edges(src_url);
        CREATE INDEX IF NOT EXISTS idx_link_edges_dst ON link_edges(dst_url);
        """
    )


def _migration_006_sources(connection: sqlite3.Connection) -> None:
    table = "crawl_jobs"
    with connection:
        if not _column_exists(connection, table, "parent_url"):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN parent_url TEXT")
        if not _column_exists(connection, table, "is_source"):
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN is_source INTEGER NOT NULL DEFAULT 0"
            )

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_links (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          parent_url TEXT NOT NULL,
          source_url TEXT NOT NULL,
          kind TEXT,
          discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          enqueued INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_source_links_parent ON source_links(parent_url);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_links_unique ON source_links(parent_url, source_url);

        CREATE TABLE IF NOT EXISTS missing_sources (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          parent_url TEXT NOT NULL,
          source_url TEXT NOT NULL,
          reason TEXT,
          http_status INTEGER,
          last_attempt TIMESTAMP,
          retries INTEGER DEFAULT 0,
          next_action TEXT,
          notes TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_missing_sources_url ON missing_sources(source_url);
        CREATE INDEX IF NOT EXISTS idx_missing_sources_parent ON missing_sources(parent_url);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_missing_sources_unique ON missing_sources(parent_url, source_url);

        CREATE TABLE IF NOT EXISTS crawl_budgets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT,
          started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          max_pages INTEGER,
          max_minutes INTEGER,
          max_storage_mb INTEGER,
          pages_crawled INTEGER DEFAULT 0,
          bytes_stored INTEGER DEFAULT 0,
          UNIQUE(session_id)
        );
        """
    )


def _migration_007_domain_profiles(connection: sqlite3.Connection) -> None:
    schema_path = Path(__file__).resolve().parent / "domain_profiles.sql"
    try:
        sql = schema_path.read_text("utf-8")
    except OSError:
        LOGGER.warning("domain profile schema missing at %s", schema_path)
        return
    script = sql.strip()
    if not script:
        LOGGER.debug("domain profile schema file %s is empty", schema_path)
        return
    with connection:
        connection.executescript(script)


def _migration_009_domain_graph(connection: sqlite3.Connection) -> None:
    schema_path = _MIGRATIONS_DIR / "009_domain_graph.sql"
    try:
        sql = schema_path.read_text("utf-8")
    except OSError:
        LOGGER.warning("domain graph schema missing at %s", schema_path)
        return
    script = sql.strip()
    if not script:
        LOGGER.debug("domain graph schema file %s is empty", schema_path)
        return
    with connection:
        connection.executescript(script)


def _migration_010_hydraflow(connection: sqlite3.Connection) -> None:
    with connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS llm_threads (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                origin TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_user_message_at TEXT,
                last_assistant_message_at TEXT,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS llm_messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                parent_id TEXT,
                role TEXT CHECK(role IN ('user','assistant','system','tool')) NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                tokens INTEGER,
                metadata TEXT,
                FOREIGN KEY(thread_id) REFERENCES llm_threads(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_llm_messages_thread ON llm_messages(thread_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT CHECK(status IN ('pending','in_progress','blocked','completed','failed','cancelled')) NOT NULL DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                due_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                owner TEXT,
                metadata TEXT,
                result TEXT,
                FOREIGN KEY(thread_id) REFERENCES llm_threads(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tasks_thread ON tasks(thread_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS task_events (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, created_at ASC);

            CREATE TABLE IF NOT EXISTS memory_embeddings (
                memory_id TEXT PRIMARY KEY,
                embedding BLOB,
                dim INTEGER,
                vector_ref TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
            );
            """
        )

    for column, ddl in (
        ("thread_id", "ALTER TABLE memories ADD COLUMN thread_id TEXT"),
        ("task_id", "ALTER TABLE memories ADD COLUMN task_id TEXT"),
        ("source_message_id", "ALTER TABLE memories ADD COLUMN source_message_id TEXT"),
        ("embedding_ref", "ALTER TABLE memories ADD COLUMN embedding_ref TEXT"),
    ):
        if not _column_exists(connection, "memories", column):
            with connection:
                connection.execute(ddl)

    if _table_exists(connection, "chat_threads"):
        with connection:
            connection.execute(
                """
                INSERT INTO llm_threads(id, title, origin, created_at, updated_at)
                SELECT ct.id, ct.title, 'legacy', ct.created_at, COALESCE(ct.last_activity, ct.created_at)
                  FROM chat_threads AS ct
                 WHERE NOT EXISTS (SELECT 1 FROM llm_threads WHERE id = ct.id)
                """
            )

    if _table_exists(connection, "chat_messages"):
        with connection:
            connection.execute(
                """
                INSERT INTO llm_messages(id, thread_id, role, content, created_at, tokens)
                SELECT cm.id, cm.thread_id, cm.role, cm.content, cm.created_at, cm.tokens
                  FROM chat_messages AS cm
                 WHERE NOT EXISTS (SELECT 1 FROM llm_messages WHERE id = cm.id)
                """
            )

    with connection:
        connection.execute(
            """
            UPDATE llm_threads
               SET last_user_message_at = (
                       SELECT MAX(created_at)
                         FROM llm_messages
                        WHERE thread_id = llm_threads.id AND role = 'user'
                   ),
                   last_assistant_message_at = (
                       SELECT MAX(created_at)
                         FROM llm_messages
                        WHERE thread_id = llm_threads.id AND role = 'assistant'
                   ),
                   updated_at = COALESCE(
                       (SELECT MAX(created_at) FROM llm_messages WHERE thread_id = llm_threads.id),
                       updated_at,
                       created_at
                   )
            """
        )


def _migration_008_app_config(connection: sqlite3.Connection) -> None:
    schema_path = _APP_CONFIG_SCHEMA
    try:
        sql = schema_path.read_text("utf-8")
    except OSError:
        LOGGER.warning("app config schema missing at %s", schema_path)
        return
    script = sql.strip()
    if not script:
        LOGGER.debug("app config schema file %s is empty", schema_path)
        return
    with connection:
        connection.executescript(script)


def _migration_20251102_app_config(connection: sqlite3.Connection) -> None:
    schema_path = _APP_CONFIG_DEFAULTS
    try:
        sql = schema_path.read_text("utf-8")
    except OSError:
        LOGGER.warning("app config defaults missing at %s", schema_path)
        return
    script = sql.strip()
    if not script:
        LOGGER.debug("app config defaults file %s is empty", schema_path)
        return
    with connection:
        connection.executescript(script)


def _migration_20251115_desktop_defaults(connection: sqlite3.Connection) -> None:
    schema_path = _APP_CONFIG_DESKTOP_DEFAULTS
    try:
        sql = schema_path.read_text("utf-8")
    except OSError:
        LOGGER.warning("desktop defaults missing at %s", schema_path)
        return
    script = sql.strip()
    if not script:
        LOGGER.debug("desktop defaults file %s is empty", schema_path)
        return
    with connection:
        connection.executescript(script)


def _migration_011_tab_threads(connection: sqlite3.Connection) -> None:
    table = "tabs"
    if not _table_exists(connection, table):
        return
    with connection:
        if not _column_exists(connection, table, "thread_id"):
            connection.execute(
                "ALTER TABLE tabs ADD COLUMN thread_id TEXT REFERENCES llm_threads(id) ON DELETE SET NULL"
            )
        if not _column_exists(connection, table, "current_history_id"):
            connection.execute(
                "ALTER TABLE tabs ADD COLUMN current_history_id INTEGER REFERENCES history(id) ON DELETE SET NULL"
            )
        if not _column_exists(connection, table, "current_url"):
            connection.execute(
                "ALTER TABLE tabs ADD COLUMN current_url TEXT"
            )
        if not _column_exists(connection, table, "current_title"):
            connection.execute(
                "ALTER TABLE tabs ADD COLUMN current_title TEXT"
            )
        if not _column_exists(connection, table, "last_visited_at"):
            connection.execute(
                "ALTER TABLE tabs ADD COLUMN last_visited_at TIMESTAMP"
            )
        if not _column_exists(connection, table, "updated_at"):
            connection.execute(
                "ALTER TABLE tabs ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )

    with connection:
        if not _index_exists(connection, table, "idx_tabs_thread"):
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tabs_thread ON tabs(thread_id)")
        if not _index_exists(connection, table, "idx_tabs_history"):
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tabs_history ON tabs(current_history_id)"
            )


def _migration_012_repo_registry(connection: sqlite3.Connection) -> None:
    with connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS repos (
                id TEXT PRIMARY KEY,
                root_path TEXT NOT NULL,
                allowed_ops TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_repos_root ON repos(root_path);
            """
        )


def _migration_013_jobs_table(connection: sqlite3.Connection) -> None:
    with connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')) DEFAULT 'queued',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT,
                payload TEXT,
                result TEXT,
                error TEXT,
                task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
                thread_id TEXT REFERENCES llm_threads(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, updated_at DESC);
            """
        )


def _migration_014_repo_changes(connection: sqlite3.Connection) -> None:
    table = "repos"
    if _table_exists(connection, table):
        with connection:
            if not _column_exists(connection, table, "check_command"):
                connection.execute(
                    "ALTER TABLE repos ADD COLUMN check_command TEXT"
                )
    with connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS repo_changes (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
                job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
                summary TEXT,
                change_stats TEXT,
                result TEXT,
                error_message TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_repo_changes_repo ON repo_changes(repo_id, applied_at DESC);
            """
        )


_MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("001_init", _migration_001_init),
    ("002_pending_vectors", _migration_002_pending_vectors),
    ("003_job_status_settings", _migration_003_job_status_settings),
    ("004_pending_vectors_text", _migration_004_pending_vectors_text),
    ("005_browser_features", _migration_005_browser_features),
    ("006_sources", _migration_006_sources),
    ("007_domain_profiles", _migration_007_domain_profiles),
    ("008_app_config", _migration_008_app_config),
    ("009_domain_graph", _migration_009_domain_graph),
    ("010_hydraflow", _migration_010_hydraflow),
    ("011_tab_threads", _migration_011_tab_threads),
    ("012_repo_registry", _migration_012_repo_registry),
    ("013_jobs_table", _migration_013_jobs_table),
    ("014_repo_changes", _migration_014_repo_changes),
    ("20251102_app_config", _migration_20251102_app_config),
    ("20251115_desktop_defaults", _migration_20251115_desktop_defaults),
]

MIGRATION_IDS = tuple(migration_id for migration_id, _ in _MIGRATIONS)
