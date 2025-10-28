"""Persistence helpers for domain clearance profiles."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from flask import current_app


DB_NAME = "domain_clearance.sqlite3"
_DB_PATH: Path | None = None


def configure(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _database_path() -> Path:
    if _DB_PATH is not None:
        return _DB_PATH
    config = current_app.config.get("APP_CONFIG")
    if config is None:
        raise RuntimeError("APP_CONFIG not initialized")
    data_dir = Path(config.agent_data_dir).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / DB_NAME


def _connect() -> sqlite3.Connection:
    path = _database_path()
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS domain_profiles (
            domain TEXT PRIMARY KEY,
            requires_login INTEGER DEFAULT 0,
            paywall_vendor TEXT,
            paywall_pattern TEXT,
            anti_bot INTEGER DEFAULT 0,
            last_seen REAL,
            notes TEXT
        )
        """
    )
    return conn


def upsert(profile: dict[str, Any]) -> None:
    domain = str(profile.get("domain") or "").strip().lower()
    if not domain:
        return
    requires_login = 1 if profile.get("requires_login") else 0
    anti_bot = 1 if profile.get("anti_bot") else 0
    vendor = profile.get("paywall_vendor")
    pattern = profile.get("paywall_pattern")
    notes = profile.get("notes")
    last_seen = float(profile.get("last_seen") or time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO domain_profiles(domain, requires_login, paywall_vendor, paywall_pattern, anti_bot, last_seen, notes)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(domain) DO UPDATE SET
                requires_login=excluded.requires_login,
                paywall_vendor=excluded.paywall_vendor,
                paywall_pattern=excluded.paywall_pattern,
                anti_bot=excluded.anti_bot,
                last_seen=excluded.last_seen,
                notes=excluded.notes
            """,
            (domain, requires_login, vendor, pattern, anti_bot, last_seen, notes),
        )


def get(domain: str) -> dict[str, Any] | None:
    normalized = (domain or "").strip().lower()
    if not normalized:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT domain, requires_login, paywall_vendor, paywall_pattern, anti_bot, last_seen, notes FROM domain_profiles WHERE domain=?",
            (normalized,),
        ).fetchone()
    if not row:
        return None
    return {
        "domain": row[0],
        "requires_login": bool(row[1]),
        "paywall_vendor": row[2],
        "paywall_pattern": row[3],
        "anti_bot": bool(row[4]),
        "last_seen": row[5],
        "notes": row[6],
    }


def list_profiles(limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT domain, requires_login, paywall_vendor, paywall_pattern, anti_bot, last_seen FROM domain_profiles ORDER BY last_seen DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "domain": row[0],
                "requires_login": bool(row[1]),
                "paywall_vendor": row[2],
                "paywall_pattern": row[3],
                "anti_bot": bool(row[4]),
                "last_seen": row[5],
            }
        )
    return results


__all__ = ["configure", "upsert", "get", "list_profiles"]
