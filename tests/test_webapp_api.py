"""Tests for Railo web app API endpoints.

Covers the endpoints and query functions described in the Railo Web App spec:
  - /api/runs/<id>                     — Run History detail view
  - /api/analytics/summary             — Dashboard north-star metrics
  - /api/installations/<id>/notifications (GET + PUT)  — Notification settings
  - get_fix_prs_created / get_fix_prs_merged           — Dashboard query helpers
"""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone, timedelta

import pytest

from core.db import set_db_path, init_db, get_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(hours_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


def _insert_run(
    conn,
    installation_id: int = 1,
    repo: str = "owner/repo",
    pr_number: int = 1,
    status: str = "success",
    violations_found: int = 0,
    violations_fixed: int = 0,
    fix_pr_number: int | None = None,
    fix_pr_url: str | None = None,
    ci_passed: int | None = None,
    runtime_seconds: float | None = 1.5,
    vuln_types: list | None = None,
    hours_ago: int = 0,
    job_status: str = "completed",
) -> int:
    """Insert a run row and return its rowid."""
    vuln_json = json.dumps(vuln_types) if vuln_types is not None else None
    conn.execute(
        """
        INSERT INTO runs
          (installation_id, repo, pr_number, status, violations_found, violations_fixed,
           timestamp, job_status, fix_pr_number, fix_pr_url, ci_passed,
           runtime_seconds, vuln_types)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            installation_id, repo, pr_number, status, violations_found, violations_fixed,
            _ts(hours_ago), job_status, fix_pr_number, fix_pr_url, ci_passed,
            runtime_seconds, vuln_json,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_installation(conn, installation_id: int = 1, login: str = "myorg"):
    now = _ts()
    conn.execute(
        "INSERT OR IGNORE INTO installations (installation_id, account_login, account_type, created_at, updated_at) VALUES (?,?,?,?,?)",
        (installation_id, login, "Organization", now, now),
    )


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    """Fresh in-memory DB + Flask test client."""
    set_db_path(tmp_path / "test_webapp.db")
    init_db()
    os.environ.pop("RAILO_KILL_SWITCH", None)
    from webhook.server import app as flask_app
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
    set_db_path(None)


@pytest.fixture()
def db(tmp_path):
    """Direct DB connection for query-layer tests."""
    set_db_path(tmp_path / "test_query.db")
    init_db()
    conn = get_connection()
    yield conn
    conn.close()
    set_db_path(None)


# ===========================================================================
# GET /api/runs/<id>  — Run detail
# ===========================================================================

class TestRunDetailEndpoint:
    def test_returns_404_when_run_not_found(self, client):
        resp = client.get("/api/runs/99999")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_returns_run_for_valid_id(self, client, tmp_path):
        # We need the DB that the client fixture is using
        conn = get_connection()
        _insert_installation(conn)
        run_id = _insert_run(conn, violations_found=3, violations_fixed=2,
                              fix_pr_number=42, fix_pr_url="https://github.com/owner/repo/pull/42",
                              ci_passed=1, vuln_types=["SQLi", "XSS"])
        conn.commit()
        conn.close()

        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == run_id
        assert data["repo"] == "owner/repo"
        assert data["repo_owner"] == "owner"
        assert data["repo_name"] == "repo"
        assert data["violations_found"] == 3
        assert data["violations_fixed"] == 2
        assert data["fix_pr_number"] == 42
        assert data["fix_pr_url"] == "https://github.com/owner/repo/pull/42"
        assert data["ci_passed"] == 1
        assert data["vuln_types"] == ["SQLi", "XSS"]

    def test_vuln_types_null_returns_empty_list(self, client):
        conn = get_connection()
        _insert_installation(conn)
        run_id = _insert_run(conn, vuln_types=None)
        conn.commit()
        conn.close()

        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.get_json()["vuln_types"] == []

    def test_has_all_required_detail_fields(self, client):
        conn = get_connection()
        _insert_installation(conn)
        run_id = _insert_run(conn)
        conn.commit()
        conn.close()

        data = client.get(f"/api/runs/{run_id}").get_json()
        required = {
            "id", "repo", "repo_owner", "repo_name", "pr_number",
            "status", "job_status", "violations_found", "violations_fixed",
            "vuln_types", "fix_pr_number", "fix_pr_url", "ci_passed",
            "runtime_seconds", "timestamp", "correlation_id",
        }
        assert required.issubset(data.keys())

    def test_run_id_0_returns_404(self, client):
        resp = client.get("/api/runs/0")
        assert resp.status_code == 404

    def test_pr_number_present(self, client):
        conn = get_connection()
        _insert_installation(conn)
        run_id = _insert_run(conn, pr_number=77)
        conn.commit()
        conn.close()

        data = client.get(f"/api/runs/{run_id}").get_json()
        assert data["pr_number"] == 77

    def test_runtime_seconds_present(self, client):
        conn = get_connection()
        _insert_installation(conn)
        run_id = _insert_run(conn, runtime_seconds=42.5)
        conn.commit()
        conn.close()

        data = client.get(f"/api/runs/{run_id}").get_json()
        assert data["runtime_seconds"] == pytest.approx(42.5)


# ===========================================================================
# GET /api/analytics/summary  — North-star metrics
# ===========================================================================

class TestAnalyticsSummary:
    def _setup_runs(self, conn):
        _insert_installation(conn)
        # Run with fix PR, CI passed (counts as fix_prs_created AND fix_prs_merged)
        _insert_run(conn, fix_pr_number=10, fix_pr_url="https://github.com/o/r/pull/10", ci_passed=1)
        # Run with fix PR, CI failed (counts only as fix_prs_created)
        _insert_run(conn, fix_pr_number=11, fix_pr_url="https://github.com/o/r/pull/11", ci_passed=0)
        # Run without fix PR (counts for neither)
        _insert_run(conn, status="warn")
        conn.commit()

    def test_fix_prs_created_in_summary(self, client):
        conn = get_connection()
        self._setup_runs(conn)
        conn.close()

        data = client.get("/api/analytics/summary").get_json()
        assert "fix_prs_created" in data
        assert data["fix_prs_created"] == 2

    def test_fix_prs_merged_in_summary(self, client):
        conn = get_connection()
        self._setup_runs(conn)
        conn.close()

        data = client.get("/api/analytics/summary").get_json()
        assert "fix_prs_merged" in data
        assert data["fix_prs_merged"] == 1  # only the CI-passed one

    def test_summary_includes_legacy_fields(self, client):
        data = client.get("/api/analytics/summary").get_json()
        for key in ("total_runs", "succeeded_runs", "failed_runs",
                    "avg_duration_seconds", "fix_merge_rate", "ci_success_rate"):
            assert key in data, f"Missing legacy key: {key}"

    def test_fix_prs_created_zero_when_no_runs(self, client):
        data = client.get("/api/analytics/summary").get_json()
        assert data["fix_prs_created"] == 0
        assert data["fix_prs_merged"] == 0

    def test_fix_prs_merged_excludes_ci_failed(self, client):
        conn = get_connection()
        _insert_installation(conn)
        _insert_run(conn, fix_pr_number=5, ci_passed=0)
        conn.commit()
        conn.close()

        data = client.get("/api/analytics/summary").get_json()
        assert data["fix_prs_created"] == 1
        assert data["fix_prs_merged"] == 0


# ===========================================================================
# GET /api/installations/<id>/notifications  — notify_on_revert field
# ===========================================================================

class TestNotificationSettingsGet:
    def test_default_notify_on_revert_is_false(self, client):
        resp = client.get("/api/installations/1/notifications")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "notify_on_revert" in data
        assert data["notify_on_revert"] is False

    def test_stored_notify_on_revert_returned(self, client):
        from core.db import upsert_notification_settings
        upsert_notification_settings(installation_id=99, notify_on_revert=True)
        data = client.get("/api/installations/99/notifications").get_json()
        assert data["notify_on_revert"] is True

    def test_all_notify_fields_present(self, client):
        data = client.get("/api/installations/1/notifications").get_json()
        required = {
            "installation_id", "slack_webhook_url", "email",
            "notify_on_fix_applied", "notify_on_ci_failure",
            "notify_on_ci_success", "notify_on_revert", "digest_mode",
        }
        assert required.issubset(data.keys())


# ===========================================================================
# PUT /api/installations/<id>/notifications  — round-trip with notify_on_revert
# ===========================================================================

class TestNotificationSettingsPut:
    def test_put_sets_notify_on_revert(self, client):
        resp = client.put(
            "/api/installations/5/notifications",
            json={"notify_on_revert": True, "notify_on_fix_applied": True},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json().get("status") == "ok"

        data = client.get("/api/installations/5/notifications").get_json()
        assert data["notify_on_revert"] is True
        assert data["notify_on_fix_applied"] is True

    def test_put_updates_notify_on_revert_to_false(self, client):
        client.put("/api/installations/6/notifications",
                   json={"notify_on_revert": True}, content_type="application/json")
        client.put("/api/installations/6/notifications",
                   json={"notify_on_revert": False}, content_type="application/json")
        data = client.get("/api/installations/6/notifications").get_json()
        assert data["notify_on_revert"] is False

    def test_put_preserves_other_fields(self, client):
        client.put(
            "/api/installations/7/notifications",
            json={"slack_webhook_url": "https://hooks.slack.com/xyz",
                  "notify_on_revert": True, "digest_mode": True},
            content_type="application/json",
        )
        data = client.get("/api/installations/7/notifications").get_json()
        assert data["slack_webhook_url"] == "https://hooks.slack.com/xyz"
        assert data["digest_mode"] is True
        assert data["notify_on_revert"] is True


# ===========================================================================
# Query layer: get_fix_prs_created / get_fix_prs_merged
# ===========================================================================

class TestGetFixPrsCreated:
    def test_counts_runs_with_fix_pr_number(self, db):
        _insert_installation(db)
        _insert_run(db, fix_pr_number=10)
        _insert_run(db, fix_pr_number=11)
        _insert_run(db, fix_pr_number=None)
        db.commit()

        from core.dashboard_queries import get_fix_prs_created
        assert get_fix_prs_created([1]) == 2

    def test_returns_zero_for_no_fix_prs(self, db):
        _insert_installation(db)
        _insert_run(db)
        db.commit()

        from core.dashboard_queries import get_fix_prs_created
        assert get_fix_prs_created([1]) == 0

    def test_returns_zero_for_empty_installation_ids(self, db):
        from core.dashboard_queries import get_fix_prs_created
        assert get_fix_prs_created([]) == 0

    def test_filters_by_installation_id(self, db):
        now = _ts()
        db.execute(
            "INSERT OR IGNORE INTO installations (installation_id, account_login, account_type, created_at, updated_at) VALUES (?,?,?,?,?)",
            (2, "other", "Organization", now, now),
        )
        _insert_run(db, installation_id=1, fix_pr_number=10)
        _insert_run(db, installation_id=2, fix_pr_number=20)
        db.commit()

        from core.dashboard_queries import get_fix_prs_created
        assert get_fix_prs_created([1]) == 1
        assert get_fix_prs_created([2]) == 1
        assert get_fix_prs_created([1, 2]) == 2


class TestGetFixPrsMerged:
    def test_counts_ci_passed_runs_with_fix_pr(self, db):
        _insert_installation(db)
        _insert_run(db, fix_pr_number=10, ci_passed=1)
        _insert_run(db, fix_pr_number=11, ci_passed=1)
        _insert_run(db, fix_pr_number=12, ci_passed=0)  # failed — not merged
        _insert_run(db, fix_pr_number=None, ci_passed=1)  # no fix PR — not counted
        db.commit()

        from core.dashboard_queries import get_fix_prs_merged
        assert get_fix_prs_merged([1]) == 2

    def test_returns_zero_when_no_ci_passed(self, db):
        _insert_installation(db)
        _insert_run(db, fix_pr_number=10, ci_passed=0)
        db.commit()

        from core.dashboard_queries import get_fix_prs_merged
        assert get_fix_prs_merged([1]) == 0

    def test_returns_zero_for_empty_installation_ids(self, db):
        from core.dashboard_queries import get_fix_prs_merged
        assert get_fix_prs_merged([]) == 0

    def test_excludes_runs_without_fix_pr(self, db):
        _insert_installation(db)
        _insert_run(db, fix_pr_number=None, ci_passed=1)
        db.commit()

        from core.dashboard_queries import get_fix_prs_merged
        assert get_fix_prs_merged([1]) == 0

    def test_filters_by_installation_id(self, db):
        now = _ts()
        db.execute(
            "INSERT OR IGNORE INTO installations (installation_id, account_login, account_type, created_at, updated_at) VALUES (?,?,?,?,?)",
            (2, "other-org", "Organization", now, now),
        )
        _insert_run(db, installation_id=1, fix_pr_number=5, ci_passed=1)
        _insert_run(db, installation_id=2, fix_pr_number=6, ci_passed=1)
        db.commit()

        from core.dashboard_queries import get_fix_prs_merged
        assert get_fix_prs_merged([1]) == 1
        assert get_fix_prs_merged([1, 2]) == 2
