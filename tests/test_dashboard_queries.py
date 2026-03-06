"""Tests for dashboard analytics queries."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from core.db import set_db_path, init_db, get_connection
from core.dashboard_queries import (
    get_fixes_created_per_day,
    get_vulnerability_breakdown,
    get_fix_merge_rate,
    get_ci_success_rate,
    get_run_timeseries,
    get_runs_per_hour,
    get_failed_runs_total,
    get_reverts_total,
    get_queue_depths,
)


@pytest.fixture(autouse=True)
def _temp_db(tmp_path):
    set_db_path(tmp_path / "test_dash.db")
    init_db()
    yield
    set_db_path(None)


def _insert(installation_id: int, status: str, ci_passed=None, days_ago: int = 0):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT INTO runs (installation_id, repo, pr_number, status, violations_found, violations_fixed, timestamp, ci_passed) VALUES (?,?,?,?,?,?,?,?)",
        (installation_id, "owner/repo", 1, status, 2, 1, ts, ci_passed),
    )
    conn.commit()
    conn.close()


def test_fixes_created_per_day():
    _insert(1, "success", days_ago=0)
    _insert(1, "success", days_ago=0)
    _insert(1, "error", days_ago=1)
    result = get_fixes_created_per_day([1], days=30)
    counts = {r["date"]: r["count"] for r in result}
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert counts.get(today, 0) == 2


def test_ci_success_rate():
    _insert(1, "success", ci_passed=True)
    _insert(1, "success", ci_passed=True)
    _insert(1, "error", ci_passed=False)
    rate = get_ci_success_rate([1])
    assert abs(rate - 66.67) < 1.0


def test_ci_success_rate_empty():
    assert get_ci_success_rate([99]) == 0.0


def test_fix_merge_rate_no_data():
    assert get_fix_merge_rate([99]) == 0.0


def test_run_timeseries():
    _insert(1, "success", days_ago=0)
    _insert(1, "error", days_ago=0)
    rows = get_run_timeseries([1], days=30)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    day_row = next((r for r in rows if r["date"] == today), None)
    assert day_row is not None
    assert day_row["succeeded_runs"] == 1
    assert day_row["failed_runs"] == 1


def test_vulnerability_breakdown_empty():
    result = get_vulnerability_breakdown([1])
    assert result == []


# ---------------------------------------------------------------------------
# Ops / health metrics
# ---------------------------------------------------------------------------

def _ts(hours_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


def _insert_run(status: str, hours_ago: int = 0, job_status: str = "completed"):
    conn = get_connection()
    conn.execute(
        """INSERT INTO runs
           (installation_id, repo, pr_number, status, violations_found,
            violations_fixed, timestamp, job_status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (1, "owner/repo", 1, status, 0, 0, _ts(hours_ago), job_status),
    )
    conn.commit()
    conn.close()


def _insert_audit(action: str, result: str, hours_ago: int = 0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_log (action, result, timestamp) VALUES (?,?,?)",
        (action, result, _ts(hours_ago)),
    )
    conn.commit()
    conn.close()


class TestRunsPerHour:
    def test_counts_recent_runs(self):
        _insert_run("success", hours_ago=0)
        _insert_run("success", hours_ago=0)
        assert get_runs_per_hour() == 2

    def test_excludes_old_runs(self):
        _insert_run("success", hours_ago=2)  # 2 hours ago — outside window
        assert get_runs_per_hour() == 0

    def test_empty_is_zero(self):
        assert get_runs_per_hour() == 0


class TestFailedRunsTotal:
    def test_counts_error_status(self):
        _insert_run("error", hours_ago=1)
        _insert_run("error", hours_ago=1)
        assert get_failed_runs_total(hours=24) == 2

    def test_counts_failed_job_status(self):
        _insert_run("unknown", hours_ago=1, job_status="failed")
        assert get_failed_runs_total(hours=24) == 1

    def test_excludes_success(self):
        _insert_run("success", hours_ago=1)
        assert get_failed_runs_total(hours=24) == 0

    def test_excludes_outside_window(self):
        _insert_run("error", hours_ago=25)  # older than 24 h
        assert get_failed_runs_total(hours=24) == 0

    def test_empty_is_zero(self):
        assert get_failed_runs_total() == 0


class TestRevertsTotal:
    def test_counts_ci_failure_reverted(self):
        _insert_audit("ci_check_failed", "reverted", hours_ago=1)
        _insert_audit("ci_check_failed", "reverted", hours_ago=2)
        assert get_reverts_total(hours=24) == 2

    def test_ignores_comment_only(self):
        _insert_audit("ci_check_failed", "comment_posted", hours_ago=1)
        assert get_reverts_total(hours=24) == 0

    def test_ignores_success_events(self):
        _insert_audit("ci_check_passed", "success", hours_ago=1)
        assert get_reverts_total(hours=24) == 0

    def test_excludes_outside_window(self):
        _insert_audit("ci_check_failed", "reverted", hours_ago=25)
        assert get_reverts_total(hours=24) == 0

    def test_empty_is_zero(self):
        assert get_reverts_total() == 0


class TestQueueDepths:
    def test_returns_dict(self):
        # Redis is not available in test environment — should return empty dict
        result = get_queue_depths()
        assert isinstance(result, dict)

    def test_no_crash_without_redis(self):
        # Must never raise even when Redis is completely offline
        result = get_queue_depths()
        assert result == {} or all(isinstance(v, int) for v in result.values())
