"""
SQLite persistence for Fixpoint dashboard.
Tables: installations, runs, oauth_sessions, audit_log (optional).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Default DB path (override with FIXPOINT_DB_PATH)
_DB_PATH: Optional[Path] = None


def get_db_path() -> Path:
    """Get SQLite database path."""
    global _DB_PATH
    if _DB_PATH is not None:
        return _DB_PATH
    env_path = os.getenv("FIXPOINT_DB_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent / "fixpoint.db"


def set_db_path(path: Path) -> None:
    """Set database path (for tests)."""
    global _DB_PATH
    _DB_PATH = path


def get_connection() -> sqlite3.Connection:
    """Get a connection to the database."""
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS installations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                installation_id INTEGER UNIQUE NOT NULL,
                account_login TEXT NOT NULL,
                account_type TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_installations_account ON installations(account_login);

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                installation_id INTEGER NOT NULL,
                repo TEXT NOT NULL,
                pr_number INTEGER,
                status TEXT NOT NULL,
                violations_found INTEGER DEFAULT 0,
                violations_fixed INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                correlation_id TEXT,
                FOREIGN KEY (installation_id) REFERENCES installations(installation_id)
            );
            CREATE INDEX IF NOT EXISTS idx_runs_installation ON runs(installation_id);
            CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp DESC);

            CREATE TABLE IF NOT EXISTS oauth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                github_login TEXT,
                access_token TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT
            );

            -- Optional audit log table (best-effort persistence for security/audit trails)
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correlation_id TEXT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                repo TEXT,
                pr_number INTEGER,
                result TEXT,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_log_correlation ON audit_log(correlation_id);
        """)
        conn.commit()
    finally:
        conn.close()


def upsert_installation(
    installation_id: int,
    account_login: str,
    account_type: str = "User",
) -> None:
    """Insert or update installation from webhook."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO installations (installation_id, account_login, account_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(installation_id) DO UPDATE SET
                account_login = excluded.account_login,
                account_type = excluded.account_type,
                updated_at = excluded.updated_at
            """,
            (installation_id, account_login, account_type, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def insert_run(
    installation_id: int,
    repo: str,
    status: str,
    pr_number: Optional[int] = None,
    violations_found: int = 0,
    violations_fixed: int = 0,
    correlation_id: Optional[str] = None,
) -> None:
    """Insert a run record."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO runs (installation_id, repo, pr_number, status, violations_found, violations_fixed, timestamp, correlation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (installation_id, repo, pr_number, status, violations_found, violations_fixed, now, correlation_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_audit_log(
    action: str,
    timestamp: str,
    correlation_id: Optional[str] = None,
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    result: Optional[str] = None,
    metadata_json: Optional[str] = None,
) -> None:
    """
    Insert an audit log record (best-effort).

    This is intentionally non-throwing at call sites; callers should wrap
    in try/except or call through observability helpers.
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO audit_log (correlation_id, timestamp, action, repo, pr_number, result, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (correlation_id, timestamp, action, repo, pr_number, result, metadata_json),
        )
        conn.commit()
    finally:
        conn.close()


def get_runs(installation_ids: list[int], limit: int = 50) -> list[dict]:
    """Get recent runs for given installation IDs."""
    if not installation_ids:
        return []
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT installation_id, repo, pr_number, status, violations_found, violations_fixed, timestamp, correlation_id
            FROM runs
            WHERE installation_id IN ({placeholders})
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (*installation_ids, limit),
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_installations_by_ids(installation_ids: list[int]) -> list[dict]:
    """Get installation records by ID."""
    if not installation_ids:
        return []
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT installation_id, account_login, account_type, created_at
            FROM installations
            WHERE installation_id IN ({placeholders})
            """,
            installation_ids,
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_all_installations() -> list[dict]:
    """Get all installations (for admin view)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT installation_id, account_login, account_type, created_at FROM installations ORDER BY created_at DESC"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
