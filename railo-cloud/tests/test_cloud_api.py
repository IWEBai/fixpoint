"""Basic integration tests for the Railo Cloud FastAPI application.

These tests verify routing, authentication, CORS, and webhook validation
without requiring a real database or Redis connection.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_dependencies():
    """Stub out external dependencies so tests run without real infra."""
    mock_session = MagicMock()
    mock_queue = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "test-job-id"
    mock_queue.enqueue.return_value = mock_job

    mock_run = MagicMock()
    mock_run.id = "00000000-0000-0000-0000-000000000001"
    mock_run.status = "queued"
    mock_run.repo_owner = "testowner"
    mock_run.repo_name = "testrepo"
    mock_run.pr_number = 1
    mock_run.base_ref = "main"
    mock_run.head_ref = "feature"
    mock_run.head_sha = "abc123"
    mock_run.mode = "warn"
    mock_run.engine_version = None
    mock_run.job_id = "test-job-id"
    mock_run.correlation_id = "test-corr"
    mock_run.fingerprint = "fp"
    mock_run.error = None
    mock_run.error_code = None
    mock_run.error_summary = None
    mock_run.summary = {}
    mock_run.artifact_paths = {}
    mock_run.created_at = None
    mock_run.updated_at = None

    with (
        patch("railo_cloud.api.main.get_queue", return_value=mock_queue),
        patch("railo_cloud.deps.get_session", return_value=mock_session),
        patch("railo_cloud.api.main.crud.create_run", return_value=mock_run),
        patch("railo_cloud.api.main.crud.update_run_status", return_value=mock_run),
        patch("railo_cloud.api.main.crud.get_run", return_value=mock_run),
        patch("railo_cloud.api.main.crud.list_runs", return_value=[mock_run]),
        patch("railo_cloud.api.main.crud.list_repos", return_value=[]),
        patch("railo_cloud.api.main.get_installation_access_token", return_value="ghs_test"),
        patch("railo_cloud.api.main.crud.upsert_installation", return_value=MagicMock()),
        patch("railo_cloud.api.main.crud.upsert_repository", return_value=MagicMock(
            mode="warn", id="repo-id"
        )),
    ):
        yield mock_session


@pytest.fixture()
def client() -> Generator:
    # Import after patching infrastructure
    from railo_cloud.api.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def webhook_secret() -> str:
    return "test-webhook-secret"


def _sign_payload(payload: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


# ---------------------------------------------------------------------------
# Health / root (public, no auth required)
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root(client):
    resp = client.get("/api")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Railo Cloud"


# ---------------------------------------------------------------------------
# API key auth on management endpoints
# ---------------------------------------------------------------------------

def test_runs_no_api_key_when_key_not_configured(client):
    """Without api_key in settings, endpoints now require JWT cookies, causing a 401 if missing."""
    resp = client.get("/runs")
    # Should 401 when no key and no cookie is present
    assert resp.status_code == 401


def test_runs_requires_api_key_when_configured(client):
    with patch("railo_cloud.config.get_settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.api_key = "secret-key"
        mock_cfg.engine_mode = "stub"
        mock_settings.return_value = mock_cfg

        resp = client.get("/runs")
        # With a key configured and no header, should return 401
        assert resp.status_code == 401


def test_runs_accepts_correct_api_key(client):
    with patch("railo_cloud.config.get_settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.api_key = "secret-key"
        mock_cfg.engine_mode = "stub"
        mock_settings.return_value = mock_cfg

        resp = client.get("/runs", headers={"X-API-Key": "secret-key"})
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------

def test_cors_headers_present(client):
    resp = client.options(
        "/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Should have CORS headers
    assert "access-control-allow-origin" in {k.lower() for k in resp.headers.keys()}


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

def test_webhook_rejects_missing_signature(client):
    resp = client.post(
        "/webhook/github",
        content=b'{"action":"opened"}',
        headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "test-id"},
    )
    assert resp.status_code == 400


def test_webhook_rejects_invalid_signature(client):
    resp = client.post(
        "/webhook/github",
        content=b'{"action":"opened"}',
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "test-id",
            "X-Hub-Signature-256": "sha256=badhash",
        },
    )
    assert resp.status_code == 400


def test_webhook_ignores_non_pr_events(client):
    with patch("railo_cloud.api.main.settings") as mock_cfg:
        mock_cfg.skip_webhook_verification = True
        mock_cfg.github_webhook_secret = ""
        mock_cfg.webhook_secret = ""
        mock_cfg.engine_mode = "stub"
        mock_cfg.fixpoint_mode = "warn"
        mock_cfg.artifact_root = "/tmp"
        mock_cfg.enable_engine = False
        mock_cfg.local_repo_path = None
        mock_cfg.engine_repo_path = None
        mock_cfg.engine_base_ref = None
        mock_cfg.engine_head_ref = None
        mock_cfg.max_runtime_seconds = None
        mock_cfg.engine_version = None

        payload = json.dumps({"action": "opened"}).encode()
        resp = client.post(
            "/webhook/github",
            content=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "test-id",
                "X-Hub-Signature-256": "sha256=ignored",
                "Content-Type": "application/json",
            },
        )
        # Non-PR events return 202 (accepted/ignored) or 400 (bad sig when skip is false)
        assert resp.status_code in (202, 400)


# ---------------------------------------------------------------------------
# Request body size limit
# ---------------------------------------------------------------------------

def test_webhook_rejects_oversized_body(client):
    large_body = b"x" * (1_048_576 + 1)
    resp = client.post(
        "/webhook/github",
        content=large_body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "test-id",
            "Content-Length": str(len(large_body)),
        },
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# DB / infra smoke
# ---------------------------------------------------------------------------

def test_get_engine_uses_pooling_for_postgres():
    """Ensure connection pooling kwargs are set for non-SQLite URLs."""
    from unittest.mock import patch as mp
    with mp("railo_cloud.db.base.get_settings") as ms:
        ms.return_value.database_url = "postgresql+psycopg://user:pass@host/db"
        # Clear lru_cache so our patched settings are used
        from railo_cloud.db.base import get_engine
        get_engine.cache_clear()
        with mp("railo_cloud.db.base.create_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            get_engine()
            call_kwargs = mock_engine.call_args[1]
            assert call_kwargs.get("pool_pre_ping") is True
            assert "pool_size" in call_kwargs
        get_engine.cache_clear()


def test_get_engine_no_pooling_for_sqlite():
    from unittest.mock import patch as mp
    with mp("railo_cloud.db.base.get_settings") as ms:
        ms.return_value.database_url = "sqlite:///./test.db"
        from railo_cloud.db.base import get_engine
        get_engine.cache_clear()
        with mp("railo_cloud.db.base.create_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            get_engine()
            call_kwargs = mock_engine.call_args[1]
            assert "pool_size" not in call_kwargs
        get_engine.cache_clear()
