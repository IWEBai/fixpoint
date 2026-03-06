"""Analytics queries for dashboard endpoints."""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict

from .db import get_connection


def _since_date(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def get_fixes_created_per_day(installation_ids: List[int], days: int = 30) -> List[Dict]:
    if not installation_ids:
        return []
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT substr(timestamp, 1, 10) as date, COUNT(*) as count
            FROM runs
            WHERE installation_id IN ({placeholders})
              AND timestamp >= ?
              AND status = 'success'
            GROUP BY substr(timestamp, 1, 10)
            ORDER BY date ASC
            """,
            (*installation_ids, _since_date(days)),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_fixes_merged_per_day(installation_ids: List[int], days: int = 30) -> List[Dict]:
    """Return count of fix PRs that were merged (ci_passed=1) per calendar day."""
    if not installation_ids:
        return []
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT substr(timestamp, 1, 10) AS date, COUNT(*) AS count
            FROM runs
            WHERE installation_id IN ({placeholders})
              AND fix_pr_number IS NOT NULL
              AND ci_passed = 1
              AND timestamp >= ?
            GROUP BY substr(timestamp, 1, 10)
            ORDER BY date ASC
            """,
            (*installation_ids, _since_date(days)),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_vulnerability_breakdown(installation_ids: List[int]) -> List[Dict]:
    """
    Return a breakdown of vulnerability types across all runs.

    Reads the ``vuln_types`` JSON column (e.g. ``["SQLi", "XSS"]``) and
    counts occurrences per category.  Runs that pre-date the column (NULL)
    are skipped.

    Returns:
        List of ``{"name": str, "count": int}`` sorted descending by count.
    """
    if not installation_ids:
        return []
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT vuln_types FROM runs
            WHERE installation_id IN ({placeholders})
              AND vuln_types IS NOT NULL
            """,
            tuple(installation_ids),
        )
        counter: Counter = Counter()
        for row in cur.fetchall():
            raw = row["vuln_types"] if isinstance(row, dict) else row[0]
            try:
                types = json.loads(raw or "[]")
                counter.update(types)
            except (json.JSONDecodeError, TypeError):
                pass
        return [
            {"name": name, "count": count}
            for name, count in counter.most_common()
        ]
    finally:
        conn.close()


def get_fix_merge_rate(installation_ids: List[int]) -> float:
    created = get_fixes_created_per_day(installation_ids, 90)
    merged = get_fixes_merged_per_day(installation_ids, 90)
    total_created = sum(item.get("count", 0) for item in created)
    total_merged = sum(item.get("count", 0) for item in merged)
    if total_created == 0:
        return 0.0
    return (total_merged / total_created) * 100.0


def get_ci_success_rate(installation_ids: List[int]) -> float:
    if not installation_ids:
        return 0.0
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT ci_passed FROM runs
            WHERE installation_id IN ({placeholders})
              AND ci_passed IS NOT NULL
            """,
            installation_ids,
        )
        rows = cur.fetchall()
        if not rows:
            return 0.0
        total = len(rows)
        passed = sum(1 for r in rows if r["ci_passed"])
        return (passed / total) * 100.0
    finally:
        conn.close()


def get_run_timeseries(installation_ids: List[int], days: int = 30) -> List[Dict]:
    if not installation_ids:
        return []
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT substr(timestamp, 1, 10) as date,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as succeeded_runs,
                   SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as failed_runs
            FROM runs
            WHERE installation_id IN ({placeholders})
              AND timestamp >= ?
            GROUP BY substr(timestamp, 1, 10)
            ORDER BY date ASC
            """,
            (*installation_ids, _since_date(days)),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_dry_run_stats(installation_ids: List[int]) -> Dict:
    """Return counts of would-have-auto-merged runs (Tier A dry-run metric).

    These are runs where all 5 auto-merge gates passed but the installation is
    on Tier A, so the merge was recorded as a dry-run instead of actually
    being performed.

    Returns::

        {
            "would_have_auto_merged": int,          # total dry-run count
            "by_repo": [{"repo": str, "count": int}, ...]  # per-repo breakdown
        }
    """
    if not installation_ids:
        return {"would_have_auto_merged": 0, "by_repo": []}

    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT COALESCE(SUM(would_have_auto_merged), 0) AS total
            FROM runs
            WHERE installation_id IN ({placeholders})
            """,
            tuple(installation_ids),
        )
        row = cur.fetchone()
        total = int(row[0]) if row else 0

        cur2 = conn.execute(
            f"""
            SELECT repo, SUM(would_have_auto_merged) AS count
            FROM runs
            WHERE installation_id IN ({placeholders})
              AND would_have_auto_merged = 1
            GROUP BY repo
            ORDER BY count DESC
            """,
            tuple(installation_ids),
        )
        by_repo = [{"repo": r[0], "count": int(r[1])} for r in cur2.fetchall()]

        return {"would_have_auto_merged": total, "by_repo": by_repo}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# North-star counts (dashboard summary)
# ---------------------------------------------------------------------------

def get_fix_prs_created(installation_ids: List[int]) -> int:
    """Count runs that resulted in a fix PR being opened."""
    if not installation_ids:
        return 0
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT COUNT(*) FROM runs
            WHERE installation_id IN ({placeholders})
              AND fix_pr_number IS NOT NULL
            """,
            tuple(installation_ids),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def get_fix_prs_merged(installation_ids: List[int]) -> int:
    """Count fix PRs that passed CI (proxy for merged).

    We use ``ci_passed = 1`` as the proxy because the DB records the CI
    outcome when the CI monitor marks the fix PR as passed.  A value of
    ``True`` here means the fix PR's CI completed successfully, which for
    auto-merge configurations means the PR was merged by Railo.  For warn
    and fix modes it means CI passed but the merge was performed manually.
    """
    if not installation_ids:
        return 0
    placeholders = ",".join("?" * len(installation_ids))
    conn = get_connection()
    try:
        cur = conn.execute(
            f"""
            SELECT COUNT(*) FROM runs
            WHERE installation_id IN ({placeholders})
              AND fix_pr_number IS NOT NULL
              AND ci_passed = 1
            """,
            tuple(installation_ids),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Health / ops metrics
# ---------------------------------------------------------------------------

def get_runs_per_hour() -> int:
    """Count all runs whose timestamp falls within the last 60 minutes."""
    since = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE timestamp >= ?",
            (since,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def get_failed_runs_total(hours: int = 24) -> int:
    """Count runs that ended in a failed/error state in the last *hours* hours."""
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM runs
            WHERE timestamp >= ?
              AND (status IN ('error', 'failed') OR job_status = 'failed')
            """,
            (since,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def get_reverts_total(hours: int = 24) -> int:
    """Count revert pushes triggered by CI failures in the last *hours* hours.

    Reads the ``audit_log`` table for rows where ``action = 'ci_check_failed'``
    and ``result = 'reverted'``  (written by ``ci_monitor_worker``).
    """
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM audit_log
            WHERE action = 'ci_check_failed'
              AND result = 'reverted'
              AND timestamp >= ?
            """,
            (since,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def get_queue_depths() -> Dict[str, int]:
    """Return pending-job counts per RQ queue.

    Returns an empty dict when RQ / Redis is unavailable so callers can
    treat the absence of queue data as a graceful degradation rather than
    an error.  A value of ``-1`` for a queue means Redis replied but the
    specific queue count could not be determined.
    """
    try:
        from redis import Redis  # noqa: PLC0415
        from rq import Queue  # noqa: PLC0415

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_conn = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        depths: Dict[str, int] = {}
        for name in ("high", "default", "low"):
            try:
                q = Queue(name, connection=redis_conn)
                depths[name] = len(q)
            except Exception:
                depths[name] = -1
        return depths
    except Exception:
        return {}
