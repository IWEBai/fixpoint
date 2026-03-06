"""Tests for CI monitor worker."""
from __future__ import annotations

import pytest
from pathlib import Path

from core.db import set_db_path, init_db, insert_run, get_connection


@pytest.fixture(autouse=True)
def _temp_db(tmp_path):
    set_db_path(tmp_path / "test_ci.db")
    init_db()
    yield
    set_db_path(None)


def test_mark_ci_no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    from workers.ci_monitor_worker import wait_for_ci_and_revert
    result = wait_for_ci_and_revert(
        owner="octo", repo="testrepo",
        fix_pr_number=7, tracked_job_id="job-test",
    )
    assert result["status"] == "skipped"
    assert result["ci_passed"] is None


def test_ci_updates_db(monkeypatch, tmp_path):
    # Insert a run to update
    insert_run(installation_id=1, repo="octo/testrepo", status="queued", job_id="job-ci")

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    from workers.ci_monitor_worker import wait_for_ci_and_revert
    wait_for_ci_and_revert(
        owner="octo", repo="testrepo",
        fix_pr_number=7, tracked_job_id="job-ci",
    )

    conn = get_connection()
    row = conn.execute("SELECT job_status FROM runs WHERE job_id = 'job-ci'").fetchone()
    conn.close()
    assert row is not None
    # skipped because no token but DB should have been attempted
    assert row["job_status"] == "skipped"
