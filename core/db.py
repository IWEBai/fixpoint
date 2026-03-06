"""
Persistence layer for Railo — supports SQLite (dev/test) and PostgreSQL (production).

Backend selection:
  • Set ``DATABASE_URL=postgresql://...`` (or ``postgres://...``) to use PostgreSQL.
  • Otherwise SQLite is used (path from ``FIXPOINT_DB_PATH`` env var or ``fixpoint.db``).
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Backend detection helpers
# ---------------------------------------------------------------------------

def _is_postgres() -> bool:
    """Return True when DATABASE_URL points at a PostgreSQL server."""
    url = os.getenv("DATABASE_URL", "")
    return url.startswith(("postgres://", "postgresql://", "postgresql+psycopg"))


def _adapt_ddl(sql: str) -> str:
    """Translate SQLite DDL keywords to their PostgreSQL equivalents."""
    if _is_postgres():
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return sql


# ---------------------------------------------------------------------------
# PostgreSQL connection wrapper
# ---------------------------------------------------------------------------

class _PgConn:
    """
    Thin adapter that makes a psycopg2 connection behave like the subset of
    ``sqlite3.Connection`` used by this module:

        conn.execute(sql, params)  → returns self (chainable)
        conn.fetchall()            → list[dict]
        conn.fetchone()            → Optional[dict]
        conn.executescript(ddl)    → executes multiple `;`-delimited statements
        conn.commit()
        conn.close()
    """

    def __init__(self, raw_conn: Any) -> None:
        self._conn = raw_conn
        import psycopg2.extras  # noqa: PLC0415
        self._cur = raw_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # --- DML / DQL ---

    def execute(self, sql: str, params: Any = ()) -> "_PgConn":
        """Execute a single statement, translating ``?`` placeholders to ``%s``."""
        pg_sql = sql.replace("?", "%s")
        self._cur.execute(pg_sql, params or None)
        return self

    def executemany(self, sql: str, params_seq: Any) -> None:
        pg_sql = sql.replace("?", "%s")
        self._cur.executemany(pg_sql, params_seq)

    def fetchall(self) -> list[dict]:
        return [dict(r) for r in (self._cur.fetchall() or [])]

    def fetchone(self) -> Optional[dict]:
        row = self._cur.fetchone()
        return dict(row) if row else None

    # --- DDL ---

    def executescript(self, sql: str) -> None:
        """Execute DDL containing multiple ``;``-delimited statements."""
        adapted = _adapt_ddl(sql)
        for stmt in adapted.split(";"):
            # Strip whitespace; skip segments that are empty or comment-only.
            clean = re.sub(r"--[^\n]*", "", stmt).strip()
            if clean:
                self._cur.execute(stmt.strip())

    # --- Transaction / lifecycle ---

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        try:
            self._cur.close()
        except Exception:
            pass
        self._conn.close()


# ---------------------------------------------------------------------------
# DB path (SQLite only)
# ---------------------------------------------------------------------------

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
    # Invalidate any cached connections when the DB path changes (e.g. in tests)
    _sqlite_local.__dict__.clear()


# ---------------------------------------------------------------------------
# Per-thread SQLite connection pool
# ---------------------------------------------------------------------------
# Each OS thread gets its own sqlite3.Connection reused across calls.
# WAL journal mode is enabled on first connect so concurrent readers don't
# block a writer and vice-versa.

_sqlite_local = threading.local()


def _new_sqlite_conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL mode: readers don't block writers; writers don't block readers.
    conn.execute("PRAGMA journal_mode=WAL")
    # Slightly relaxed fsync — safe after WAL checkpointing.
    conn.execute("PRAGMA synchronous=NORMAL")
    # Keep 64 MB of shared page cache per connection.
    conn.execute("PRAGMA cache_size=-65536")
    return conn


class _PooledSQLiteConn:
    """Thin proxy that delegates to a pooled sqlite3.Connection.

    ``.close()`` is intentionally a no-op — the underlying connection stays
    alive in the thread-local pool so the next call can reuse it without
    re-opening the file.  All other attribute accesses pass through directly.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection) -> None:
        object.__setattr__(self, "_conn", conn)

    def close(self) -> None:  # noqa: D401
        """No-op: connection is kept alive in the thread-local pool."""

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_conn"), name, value)


def get_connection():
    """Return a database connection for the active backend.

    For SQLite a per-thread connection is returned and reused across calls
    (WAL mode is enabled on first connect).  PostgreSQL creates a new
    connection each call (use pgBouncer or a pool library for production PG).

    Both return objects expose the same ``.execute()`` / ``.commit()`` /
    ``.close()`` interface.  Callers should still call ``.close()`` — for
    SQLite the connection is *not* actually closed (it is kept alive in the
    thread-local); for PostgreSQL it is.
    """
    if _is_postgres():
        try:
            import psycopg2  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "psycopg2-binary is required for PostgreSQL mode. "
                "Run: pip install psycopg2-binary"
            ) from exc
        raw = psycopg2.connect(os.environ["DATABASE_URL"])
        return _PgConn(raw)

    # --- SQLite (default) — reuse per-thread connection ---
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = getattr(_sqlite_local, "conn", None)
    # Invalidate if DB path has changed (e.g. between tests)
    cached_path = getattr(_sqlite_local, "db_path", None)
    if conn is None or cached_path != path:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
        conn = _new_sqlite_conn(path)
        _sqlite_local.conn = conn
        _sqlite_local.db_path = path

    return _PooledSQLiteConn(conn)


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
                job_id TEXT,
                job_status TEXT,
                fix_pr_number INTEGER,
                fix_pr_url TEXT,
                ci_passed BOOLEAN,
                runtime_seconds REAL,
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

            CREATE TABLE IF NOT EXISTS repo_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo TEXT UNIQUE NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                mode TEXT NOT NULL DEFAULT 'warn',
                max_diff_lines INTEGER NOT NULL DEFAULT 500,
                max_runtime_seconds INTEGER NOT NULL DEFAULT 120,
                ignore_file TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_repo_settings_repo ON repo_settings(repo);

            CREATE TABLE IF NOT EXISTS registered_repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                installation_id INTEGER NOT NULL,
                repo_full_name TEXT NOT NULL,
                github_repo_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                added_at TEXT NOT NULL,
                removed_at TEXT,
                UNIQUE(installation_id, repo_full_name)
            );
            CREATE INDEX IF NOT EXISTS idx_registered_repos_installation ON registered_repos(installation_id);
            CREATE INDEX IF NOT EXISTS idx_registered_repos_repo ON registered_repos(repo_full_name);
        """)
        conn.commit()
    finally:
        conn.close()
    _migrate_db()


def _migrate_db() -> None:
    """
    Apply additive schema migrations to an existing database.

    Each ALTER TABLE statement is wrapped in its own try/except so a column
    that already exists simply causes a no-op (SQLite raises
    ``OperationalError: duplicate column name`` which we safely ignore).
    """
    migrations = [
        # 2026-03-04: add vuln_types JSON column to runs
        "ALTER TABLE runs ADD COLUMN vuln_types TEXT DEFAULT NULL",
        # 2026-03-05: org-level policy defaults
        """
        CREATE TABLE IF NOT EXISTS org_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_login TEXT UNIQUE NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            mode TEXT NOT NULL DEFAULT 'warn',
            max_diff_lines INTEGER NOT NULL DEFAULT 500,
            max_runtime_seconds INTEGER NOT NULL DEFAULT 120,
            ignore_file TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """,
        # 2026-03-05: per-installation notification settings (defaults OFF)
        """
        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            installation_id INTEGER UNIQUE NOT NULL,
            slack_webhook_url TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            notify_on_fix_applied INTEGER NOT NULL DEFAULT 0,
            notify_on_ci_failure INTEGER NOT NULL DEFAULT 0,
            notify_on_ci_success INTEGER NOT NULL DEFAULT 0,
            digest_mode INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """,
        # 2026-03-05: notification throttle / digest queue
        """
        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            installation_id INTEGER NOT NULL,
            repo TEXT NOT NULL DEFAULT '',
            event TEXT NOT NULL,
            sent_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_notif_log ON notification_log(installation_id, repo, event, sent_at)",
        # 2026-03-05: delivery-ID idempotency (prevent duplicate webhook processing)
        """
        CREATE TABLE IF NOT EXISTS delivery_ids (
            delivery_id TEXT PRIMARY KEY NOT NULL,
            received_at TEXT NOT NULL
        )
        """,
        # 2026-03-05: auto_merge opt-in + permission_tier on org_policies
        "ALTER TABLE org_policies ADD COLUMN auto_merge_enabled INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE org_policies ADD COLUMN permission_tier TEXT NOT NULL DEFAULT 'A'",
        # 2026-03-05: auto_merge opt-in + permission_tier on repo_settings
        "ALTER TABLE repo_settings ADD COLUMN auto_merge_enabled INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE repo_settings ADD COLUMN permission_tier TEXT NOT NULL DEFAULT 'A'",
        # 2026-03-05: dry-run counter on runs table
        "ALTER TABLE runs ADD COLUMN would_have_auto_merged INTEGER NOT NULL DEFAULT 0",
        # 2026-03-05: run retention TTL (seconds); 0 = use global default
        "ALTER TABLE runs ADD COLUMN retain_until TEXT DEFAULT NULL",
        # 2026-03-06: notify on revert event
        "ALTER TABLE notification_settings ADD COLUMN notify_on_revert INTEGER NOT NULL DEFAULT 0",
    ]
    conn = get_connection()
    try:
        for stmt in migrations:
            try:
                conn.execute(stmt)
            except Exception:
                pass  # column already exists or other harmless error
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


def remove_installation(installation_id: int) -> None:
    """
    Hard-delete an installation record when the GitHub App is uninstalled.

    The associated runs rows are kept for historical/audit purposes; since
    SQLite does not enforce foreign-key constraints by default those rows
    simply become orphaned (installation_id no longer references a live row).
    Also deactivates all registered repos for this installation.
    """
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM installations WHERE installation_id = ?",
            (installation_id,),
        )
        conn.commit()
    finally:
        conn.close()
    # Deactivate all repos (empty list = all)
    deregister_repos(installation_id, [])


# ---------------------------------------------------------------------------
# Registered repositories
# ---------------------------------------------------------------------------

def register_repos(installation_id: int, repos: list[dict]) -> None:
    """
    Insert or re-activate repositories for an installation.

    *repos* is a list of GitHub repository objects — each must contain at
    least a ``full_name`` key (e.g. ``"owner/repo"``) and optionally ``id``
    (GitHub's numeric repo ID).

    Also seeds default ``repo_settings`` rows (mode=warn, enabled=True) if
    no row exists yet — so every repo works immediately after install with
    zero configuration required.

    Called from:
      • ``installation`` created event (``repositories`` array)
      • ``installation_repositories`` added event
    """
    if not repos:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        for repo in repos:
            full_name = repo.get("full_name") or repo.get("name") or ""
            if not full_name:
                continue
            github_repo_id = repo.get("id")
            conn.execute(
                """
                INSERT INTO registered_repos
                    (installation_id, repo_full_name, github_repo_id, active, added_at, removed_at)
                VALUES (?, ?, ?, 1, ?, NULL)
                ON CONFLICT(installation_id, repo_full_name) DO UPDATE SET
                    active = 1,
                    github_repo_id = COALESCE(excluded.github_repo_id, registered_repos.github_repo_id),
                    removed_at = NULL
                """,
                (installation_id, full_name, github_repo_id, now),
            )
            # Seed default repo_settings so the repo is immediately operational
            # without any manual configuration.  INSERT OR IGNORE means we never
            # overwrite settings that the user has already customised.
            conn.execute(
                """
                INSERT OR IGNORE INTO repo_settings
                    (repo, enabled, mode, max_diff_lines, max_runtime_seconds,
                     ignore_file, auto_merge_enabled, permission_tier, updated_at)
                VALUES (?, 1, 'warn', 500, 120, '', 0, 'A', ?)
                """,
                (full_name, now),
            )
        conn.commit()
    finally:
        conn.close()


def deregister_repos(installation_id: int, repos: list[dict]) -> None:
    """
    Deactivate repositories for an installation.

    Pass an **empty** *repos* list to deactivate *all* repos for the
    installation — used when the app is uninstalled or revoked entirely.

    Also disables ``repo_settings`` rows for the same repos so they no
    longer appear as active in the dashboard.

    Called from:
      • ``installation`` deleted event (empty list → deactivate all)
      • ``installation_repositories`` removed event
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        if not repos:
            # Deactivate all repos for this installation
            conn.execute(
                "UPDATE registered_repos SET active = 0, removed_at = ? WHERE installation_id = ?",
                (now, installation_id),
            )
            # Disable all matching repo_settings rows (JOIN via registered_repos)
            conn.execute(
                """
                UPDATE repo_settings
                SET enabled = 0, updated_at = ?
                WHERE repo IN (
                    SELECT repo_full_name FROM registered_repos WHERE installation_id = ?
                )
                """,
                (now, installation_id),
            )
        else:
            for repo in repos:
                full_name = repo.get("full_name") or repo.get("name") or ""
                if not full_name:
                    continue
                conn.execute(
                    """
                    UPDATE registered_repos
                    SET active = 0, removed_at = ?
                    WHERE installation_id = ? AND repo_full_name = ?
                    """,
                    (now, installation_id, full_name),
                )
                conn.execute(
                    "UPDATE repo_settings SET enabled = 0, updated_at = ? WHERE repo = ?",
                    (now, full_name),
                )
        conn.commit()
    finally:
        conn.close()


def get_registered_repos(
    installation_ids: Optional[list[int]] = None,
    active_only: bool = True,
) -> list[dict]:
    """
    Return registered repositories, optionally filtered to specific installation IDs.

    Args:
        installation_ids: When provided, restrict results to these installations.
        active_only:       When True (default) return only repos with ``active=1``.
    """
    conn = get_connection()
    try:
        active_clause = "AND rr.active = 1" if active_only else ""
        if installation_ids:
            placeholders = ",".join("?" * len(installation_ids))
            cur = conn.execute(
                f"""
                SELECT rr.id, rr.installation_id, rr.repo_full_name, rr.github_repo_id,
                       rr.active, rr.added_at, rr.removed_at, i.account_login
                FROM registered_repos rr
                LEFT JOIN installations i ON rr.installation_id = i.installation_id
                WHERE rr.installation_id IN ({placeholders}) {active_clause}
                ORDER BY rr.added_at DESC
                """,
                tuple(installation_ids),
            )
        else:
            where_clause = "WHERE rr.active = 1" if active_only else ""
            cur = conn.execute(
                f"""
                SELECT rr.id, rr.installation_id, rr.repo_full_name, rr.github_repo_id,
                       rr.active, rr.added_at, rr.removed_at, i.account_login
                FROM registered_repos rr
                LEFT JOIN installations i ON rr.installation_id = i.installation_id
                {where_clause}
                ORDER BY rr.added_at DESC
                """
            )
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_prior_run_count(repo: str) -> int:
    """Return the number of completed runs recorded for *repo*.

    Used to detect the first-ever scan for a repo so we can post a
    welcome / orientation comment on that PR.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE repo = ?",
            (repo,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
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
    job_id: Optional[str] = None,
    job_status: Optional[str] = None,
    fix_pr_number: Optional[int] = None,
    fix_pr_url: Optional[str] = None,
    ci_passed: Optional[bool] = None,
    runtime_seconds: Optional[float] = None,
    vuln_types: Optional[list] = None,
) -> None:
    """Insert a run record."""
    import json as _json
    now = datetime.now(timezone.utc).isoformat()
    vuln_types_json = _json.dumps(vuln_types) if vuln_types is not None else None
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO runs (installation_id, repo, pr_number, status, violations_found, violations_fixed, timestamp, correlation_id, job_id, job_status, fix_pr_number, fix_pr_url, ci_passed, runtime_seconds, vuln_types)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                installation_id,
                repo,
                pr_number,
                status,
                violations_found,
                violations_fixed,
                now,
                correlation_id,
                job_id,
                job_status,
                fix_pr_number,
                fix_pr_url,
                ci_passed,
                runtime_seconds,
                vuln_types_json,
            ),
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


def update_run_job_status(
    job_id: str,
    job_status: Optional[str] = None,
    status: Optional[str] = None,
    fix_pr_number: Optional[int] = None,
    fix_pr_url: Optional[str] = None,
    ci_passed: Optional[bool] = None,
    runtime_seconds: Optional[float] = None,
) -> None:
    """Update run job status and optional fix PR / CI info."""
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE runs
            SET job_status = COALESCE(?, job_status),
                status = COALESCE(?, status),
                fix_pr_number = COALESCE(?, fix_pr_number),
                fix_pr_url = COALESCE(?, fix_pr_url),
                ci_passed = COALESCE(?, ci_passed),
                runtime_seconds = COALESCE(?, runtime_seconds)
            WHERE job_id = ?
            """,
            (job_status, status, fix_pr_number, fix_pr_url, ci_passed, runtime_seconds, job_id),
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
            SELECT id, installation_id, repo, pr_number, status, violations_found, violations_fixed, timestamp, correlation_id, job_id, job_status, fix_pr_number, fix_pr_url, ci_passed, runtime_seconds, vuln_types
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


def get_repo_settings(repo: str) -> Optional[dict]:
    """Get settings for a repo, or None if not set."""
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM repo_settings WHERE repo = ?", (repo,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_repo_settings(
    repo: str,
    enabled: bool = True,
    mode: str = "warn",
    max_diff_lines: int = 500,
    max_runtime_seconds: int = 120,
    ignore_file: str = "",
    auto_merge_enabled: bool = False,
    permission_tier: str = "A",
) -> None:
    """Insert or update repo settings."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO repo_settings (repo, enabled, mode, max_diff_lines, max_runtime_seconds, ignore_file, auto_merge_enabled, permission_tier, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo) DO UPDATE SET
                enabled = excluded.enabled,
                mode = excluded.mode,
                max_diff_lines = excluded.max_diff_lines,
                max_runtime_seconds = excluded.max_runtime_seconds,
                ignore_file = excluded.ignore_file,
                auto_merge_enabled = excluded.auto_merge_enabled,
                permission_tier = excluded.permission_tier,
                updated_at = excluded.updated_at
            """,
            (repo, int(enabled), mode, max_diff_lines, max_runtime_seconds, ignore_file, int(auto_merge_enabled), permission_tier, now),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Org-level policy defaults
# ---------------------------------------------------------------------------

_ORG_POLICY_DEFAULTS: dict = {
    "enabled": True,
    "mode": "warn",
    "max_diff_lines": 500,
    "max_runtime_seconds": 120,
    "ignore_file": "",
    "auto_merge_enabled": False,
    "permission_tier": "A",
}


def get_org_policy(account_login: str) -> Optional[dict]:
    """Return the org-level policy for *account_login*, or None if not set."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM org_policies WHERE account_login = ?",
            (account_login,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_org_policy(
    account_login: str,
    enabled: bool = True,
    mode: str = "warn",
    max_diff_lines: int = 500,
    max_runtime_seconds: int = 120,
    ignore_file: str = "",
    auto_merge_enabled: bool = False,
    permission_tier: str = "A",
) -> None:
    """Insert or update the org-level policy for *account_login*."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO org_policies
                (account_login, enabled, mode, max_diff_lines, max_runtime_seconds,
                 ignore_file, auto_merge_enabled, permission_tier, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_login) DO UPDATE SET
                enabled = excluded.enabled,
                mode = excluded.mode,
                max_diff_lines = excluded.max_diff_lines,
                max_runtime_seconds = excluded.max_runtime_seconds,
                ignore_file = excluded.ignore_file,
                auto_merge_enabled = excluded.auto_merge_enabled,
                permission_tier = excluded.permission_tier,
                updated_at = excluded.updated_at
            """,
            (account_login, int(enabled), mode, max_diff_lines, max_runtime_seconds,
             ignore_file, int(auto_merge_enabled), permission_tier, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_effective_repo_settings(repo: str) -> dict:
    """
    Merge org policy + repo-level overrides into a single effective settings dict.

    Priority (highest → lowest):
    1. Repo-specific settings (``repo_settings`` row), if present.
    2. Org-level defaults (``org_policies`` row for the owner of the repo).
    3. Hard-coded application defaults.

    The repo is expected to be in ``owner/name`` format.
    """
    # Determine the owner of the repo (first path component)
    owner = repo.split("/", 1)[0] if "/" in repo else repo

    # Start from hard-coded defaults
    effective: dict = dict(_ORG_POLICY_DEFAULTS)

    # Layer org defaults on top
    org = get_org_policy(owner)
    if org:
        for key in _ORG_POLICY_DEFAULTS:
            if key in org:
                val = org[key]
                if key in {"enabled", "auto_merge_enabled"}:
                    val = bool(val)
                effective[key] = val

    # Layer repo-specific overrides on top
    repo_row = get_repo_settings(repo)
    if repo_row:
        for key in _ORG_POLICY_DEFAULTS:
            if key in repo_row:
                val = repo_row[key]
                if key in {"enabled", "auto_merge_enabled"}:
                    val = bool(val)
                effective[key] = val

    effective["repo"] = repo
    return effective


# ---------------------------------------------------------------------------
# Per-installation notification settings
# ---------------------------------------------------------------------------

def get_notification_settings(installation_id: int) -> Optional[dict]:
    """Return notification settings for *installation_id*, or None if not set."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM notification_settings WHERE installation_id = ?",
            (installation_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_notification_settings(
    installation_id: int,
    slack_webhook_url: str = "",
    email: str = "",
    notify_on_fix_applied: bool = False,
    notify_on_ci_failure: bool = False,
    notify_on_ci_success: bool = False,
    notify_on_revert: bool = False,
    digest_mode: bool = False,
) -> None:
    """Insert or update notification settings for *installation_id*.

    All event toggles default to OFF to prevent notification spam.
    Users must explicitly opt in.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO notification_settings
                (installation_id, slack_webhook_url, email,
                 notify_on_fix_applied, notify_on_ci_failure, notify_on_ci_success,
                 notify_on_revert, digest_mode, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(installation_id) DO UPDATE SET
                slack_webhook_url = excluded.slack_webhook_url,
                email = excluded.email,
                notify_on_fix_applied = excluded.notify_on_fix_applied,
                notify_on_ci_failure = excluded.notify_on_ci_failure,
                notify_on_ci_success = excluded.notify_on_ci_success,
                notify_on_revert = excluded.notify_on_revert,
                digest_mode = excluded.digest_mode,
                updated_at = excluded.updated_at
            """,
            (
                installation_id,
                slack_webhook_url,
                email,
                int(notify_on_fix_applied),
                int(notify_on_ci_failure),
                int(notify_on_ci_success),
                int(notify_on_revert),
                int(digest_mode),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_run_by_id(run_id: int) -> Optional[dict]:
    """Return a single run record by primary key, or None if not found."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT id, installation_id, repo, pr_number, status, violations_found, violations_fixed,
                   timestamp, correlation_id, job_id, job_status, fix_pr_number, fix_pr_url,
                   ci_passed, runtime_seconds, vuln_types
            FROM runs WHERE id = ?
            """,
            (run_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Delivery-ID idempotency
# ---------------------------------------------------------------------------

def is_delivery_seen(delivery_id: str) -> bool:
    """Return True if this GitHub delivery ID has already been processed."""
    if not delivery_id:
        return False
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT 1 FROM delivery_ids WHERE delivery_id = ?", (delivery_id,)
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def mark_delivery_seen(delivery_id: str) -> None:
    """Record a delivery ID as processed (idempotent INSERT OR IGNORE)."""
    if not delivery_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO delivery_ids (delivery_id, received_at) VALUES (?, ?)",
            (delivery_id, now),
        )
        conn.commit()
    finally:
        conn.close()


def prune_old_delivery_ids(older_than_days: int = 30) -> int:
    """Delete delivery_ids older than *older_than_days*. Returns deleted count."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM delivery_ids WHERE received_at < ?", (cutoff,)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Notification throttle helpers
# ---------------------------------------------------------------------------

_NOTIF_MAX_PER_REPO_PER_HOUR = int(os.getenv("RAILO_NOTIF_THROTTLE", "5"))


def is_notification_throttled(
    installation_id: int,
    repo: str,
    event: str,
    max_per_hour: int = _NOTIF_MAX_PER_REPO_PER_HOUR,
) -> bool:
    """Return True if the notification rate limit for this repo+event has been hit."""
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM notification_log
            WHERE installation_id = ? AND repo = ? AND event = ? AND sent_at > ?
            """,
            (installation_id, repo, event, since),
        )
        row = cur.fetchone()
        count = row[0] if row else 0
        return count >= max_per_hour
    finally:
        conn.close()


def log_notification_sent(installation_id: int, repo: str, event: str) -> None:
    """Record that a notification was dispatched (for throttle tracking)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO notification_log (installation_id, repo, event, sent_at) VALUES (?, ?, ?, ?)",
            (installation_id, repo, event, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_pending_digest_events(
    installation_id: int,
    since_hours: int = 24,
) -> list:
    """Return all un-digested notification_log rows for digest-mode delivery."""
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT repo, event, COUNT(*) as cnt, MAX(sent_at) as last_at
            FROM notification_log
            WHERE installation_id = ? AND sent_at > ?
            GROUP BY repo, event
            ORDER BY last_at DESC
            """,
            (installation_id, since),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Run retention
# ---------------------------------------------------------------------------

def prune_old_runs(retention_days: Optional[int] = None) -> int:
    """
    Delete run rows older than *retention_days* (default: ``RUN_RETENTION_DAYS``
    env var, fallback 90).

    Returns:
        Number of deleted rows.
    """
    if retention_days is None:
        retention_days = int(os.getenv("RUN_RETENTION_DAYS", "90"))
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Permission tier helpers
# ---------------------------------------------------------------------------

def get_effective_permission_tier(repo: str) -> str:
    """
    Return the effective permission tier for *repo*.

    Tier A (default, safe):  warn-only + fix PR creation; no direct pushes to
                              contributor branches; no auto-merge.
    Tier B (enterprise):     revert push + auto-merge; requires explicit opt-in
                             at org or repo level.

    Priority: repo_settings → org_policies → 'A'.
    """
    owner = repo.split("/", 1)[0] if "/" in repo else repo
    repo_row = get_repo_settings(repo)
    if repo_row and repo_row.get("permission_tier") == "B":
        return "B"
    org_row = get_org_policy(owner)
    if org_row and org_row.get("permission_tier") == "B":
        return "B"
    return "A"


# ---------------------------------------------------------------------------
# Audit log queries
# ---------------------------------------------------------------------------

def get_audit_log(
    repo: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 200,
    since: Optional[str] = None,
) -> list[dict]:
    """
    Return audit log rows, optionally filtered by repo, action, and time range.

    Args:
        repo:   Filter to a specific repo (``owner/repo`` format).
        action: Filter to a specific action string (exact match).
        limit:  Maximum rows to return (newest first, default 200).
        since:  ISO-8601 timestamp lower bound (inclusive).

    Returns:
        List of dicts with keys: id, correlation_id, timestamp, action,
        repo, pr_number, result, metadata.
    """
    conn = get_connection()
    try:
        conditions: list[str] = []
        params: list = []

        if repo:
            conditions.append("repo = ?")
            params.append(repo)
        if action:
            conditions.append("action = ?")
            params.append(action)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cur = conn.execute(
            f"SELECT id, correlation_id, timestamp, action, repo, pr_number, result, metadata "
            f"FROM audit_log {where} ORDER BY timestamp DESC LIMIT ?",
            (*params, limit),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
