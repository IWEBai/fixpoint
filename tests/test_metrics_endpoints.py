"""Tests for the /metrics (Prometheus) and /api/metrics/health (JSON) endpoints."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from core.db import set_db_path, init_db, get_connection
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ts(hours_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


def _insert_run(conn, status: str, hours_ago: int = 0, job_status: str = "completed"):
    conn.execute(
        """INSERT INTO runs
           (installation_id, repo, pr_number, status, violations_found,
            violations_fixed, timestamp, job_status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (1, "owner/repo", 1, status, 0, 0, _ts(hours_ago), job_status),
    )


def _insert_audit(conn, action: str, result: str, hours_ago: int = 0):
    conn.execute(
        "INSERT INTO audit_log (action, result, timestamp) VALUES (?,?,?)",
        (action, result, _ts(hours_ago)),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    set_db_path(tmp_path / "test_metrics.db")
    init_db()
    os.environ.pop("RAILO_KILL_SWITCH", None)
    from webhook.server import app as flask_app
    flask_app.config["TESTING"] = True
    yield flask_app.test_client()
    set_db_path(None)


# ---------------------------------------------------------------------------
# /metrics  (Prometheus text)
# ---------------------------------------------------------------------------

class TestPrometheusMetricsEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_content_type_prometheus(self, client):
        resp = client.get("/metrics")
        assert "text/plain" in resp.content_type
        assert "0.0.4" in resp.content_type

    def test_contains_runs_per_hour_metric(self, client):
        conn = get_connection()
        _insert_run(conn, "success", hours_ago=0)
        conn.commit()
        conn.close()

        resp = client.get("/metrics")
        body = resp.data.decode()
        assert "railo_runs_per_hour" in body
        # Value should be at least 1
        for line in body.splitlines():
            if line.startswith("railo_runs_per_hour "):
                assert int(line.split()[-1]) >= 1
                break

    def test_contains_failed_runs_metric(self, client):
        conn = get_connection()
        _insert_run(conn, "error", hours_ago=1)
        _insert_run(conn, "error", hours_ago=1)
        conn.commit()
        conn.close()

        resp = client.get("/metrics")
        body = resp.data.decode()
        assert "railo_failed_runs_total" in body
        for line in body.splitlines():
            if line.startswith("railo_failed_runs_total "):
                assert int(line.split()[-1]) >= 2
                break

    def test_contains_reverts_metric(self, client):
        conn = get_connection()
        _insert_audit(conn, "ci_check_failed", "reverted", hours_ago=2)
        conn.commit()
        conn.close()

        resp = client.get("/metrics")
        body = resp.data.decode()
        assert "railo_reverts_total" in body
        for line in body.splitlines():
            if line.startswith("railo_reverts_total "):
                assert int(line.split()[-1]) >= 1
                break

    def test_zero_values_when_empty(self, client):
        resp = client.get("/metrics")
        body = resp.data.decode()
        for metric in ("railo_runs_per_hour", "railo_failed_runs_total", "railo_reverts_total"):
            for line in body.splitlines():
                if line.startswith(f"{metric} "):
                    assert int(line.split()[-1]) == 0
                    break

    def test_queue_depth_included_when_redis_available(self, client):
        """If get_queue_depths returns data, labels appear in the output."""
        fake_depths = {"high": 0, "default": 3, "low": 1}
        with patch("webhook.server.get_queue_depths", return_value=fake_depths):
            resp = client.get("/metrics")
        body = resp.data.decode()
        assert "railo_worker_queue_depth" in body
        assert 'queue="default"' in body
        assert "3" in body

    def test_queue_depth_omitted_when_redis_down(self, client):
        """When Redis is offline get_queue_depths returns {} and the block is skipped."""
        with patch("webhook.server.get_queue_depths", return_value={}):
            resp = client.get("/metrics")
        body = resp.data.decode()
        assert "railo_worker_queue_depth" not in body


# ---------------------------------------------------------------------------
# /api/metrics/health  (JSON)
# ---------------------------------------------------------------------------

class TestMetricsHealthEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/api/metrics/health")
        assert resp.status_code == 200

    def test_returns_json(self, client):
        resp = client.get("/api/metrics/health")
        data = resp.get_json()
        assert isinstance(data, dict)

    def test_has_required_keys(self, client):
        resp = client.get("/api/metrics/health")
        data = resp.get_json()
        assert "runs_per_hour" in data
        assert "failed_runs_24h" in data
        assert "reverts_24h" in data
        assert "worker_queue_depth" in data

    def test_values_are_numeric(self, client):
        resp = client.get("/api/metrics/health")
        data = resp.get_json()
        assert isinstance(data["runs_per_hour"], int)
        assert isinstance(data["failed_runs_24h"], int)
        assert isinstance(data["reverts_24h"], int)
        assert isinstance(data["worker_queue_depth"], dict)

    def test_counts_reflect_db_state(self, client):
        conn = get_connection()
        _insert_run(conn, "success", hours_ago=0)
        _insert_run(conn, "error", hours_ago=1)
        _insert_audit(conn, "ci_check_failed", "reverted", hours_ago=3)
        conn.commit()
        conn.close()

        resp = client.get("/api/metrics/health")
        data = resp.get_json()
        assert data["runs_per_hour"] >= 1
        assert data["failed_runs_24h"] >= 1
        assert data["reverts_24h"] >= 1
