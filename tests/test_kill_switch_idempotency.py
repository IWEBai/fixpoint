"""E2E tests for the global kill-switch and delivery-ID idempotency guarantees.

Kill-switch tests confirm that RAILO_KILL_SWITCH=1 causes the webhook endpoint
to return 503 *before* any processing happens.

Idempotency tests confirm that repeating the same X-GitHub-Delivery header
causes the second (and subsequent) requests to be short-circuited with
{"status": "duplicate"} without re-running the handler logic.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pr_payload(repo: str = "acme/repo") -> dict:
    return {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "number": 42,
            "head": {
                "ref": "fix-branch",
                "sha": "deadbeef1234",
                "repo": {
                    "full_name": repo,
                    "clone_url": f"https://github.com/{repo}.git",
                    "fork": False,
                },
            },
            "base": {
                "ref": "main",
                "repo": {"full_name": repo},
            },
            "html_url": f"https://github.com/{repo}/pull/42",
        },
        "repository": {
            "full_name": repo,
            "name": repo.split("/")[-1],
            "owner": {"login": repo.split("/")[0]},
            "clone_url": f"https://github.com/{repo}.git",
        },
    }


def _post_webhook(client, payload: dict, delivery_id: str, extra_env: dict | None = None):
    """POST to /webhook with SKIP_WEBHOOK_VERIFICATION so no HMAC is required."""
    body = json.dumps(payload).encode()
    env_override = {
        "SKIP_WEBHOOK_VERIFICATION": "true",
        "WEBHOOK_SECRET": "",
        "GITHUB_WEBHOOK_SECRET": "",
        "GITHUB_APP_WEBHOOK_SECRET": "",
        **(extra_env or {}),
    }
    with patch.dict(os.environ, env_override, clear=False):
        return client.post(
            "/webhook",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": delivery_id,
            },
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    """Fresh Flask test client with an isolated SQLite database."""
    from core.db import set_db_path, init_db
    set_db_path(tmp_path / "test_ks.db")
    init_db()
    # Ensure kill-switch is OFF at fixture setup
    os.environ.pop("RAILO_KILL_SWITCH", None)
    from webhook.server import app as flask_app
    flask_app.config["TESTING"] = True
    yield flask_app.test_client()
    set_db_path(None)
    os.environ.pop("RAILO_KILL_SWITCH", None)


# ---------------------------------------------------------------------------
# Kill-switch tests
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_kill_switch_off_by_default(self, app):
        """When RAILO_KILL_SWITCH is unset the status endpoint reports active=False."""
        resp = app.get("/api/admin/kill-switch")
        assert resp.status_code == 200
        assert resp.get_json()["active"] is False

    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "YES"])
    def test_kill_switch_status_endpoint_on(self, app, value):
        """Any truthy value activates the kill-switch status endpoint."""
        with patch.dict(os.environ, {"RAILO_KILL_SWITCH": value}):
            resp = app.get("/api/admin/kill-switch")
        assert resp.status_code == 200
        assert resp.get_json()["active"] is True

    def test_kill_switch_blocks_webhook_with_503(self, app):
        """RAILO_KILL_SWITCH=1 must return 503 before any webhook processing."""
        with patch("webhook.server.process_pr_webhook") as mock_process:
            resp = _post_webhook(
                app,
                _pr_payload(),
                delivery_id=f"ks-{uuid.uuid4().hex}",
                extra_env={"RAILO_KILL_SWITCH": "1"},
            )
            # process_pr_webhook must NOT have been called
            mock_process.assert_not_called()

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "kill_switch"

    def test_kill_switch_off_allows_webhook(self, app):
        """Without RAILO_KILL_SWITCH the webhook is processed normally."""
        with patch(
            "webhook.server.process_pr_webhook",
            return_value={"status": "ok"},
        ):
            resp = _post_webhook(
                app,
                _pr_payload(),
                delivery_id=f"ok-{uuid.uuid4().hex}",
            )
        assert resp.status_code == 200

    def test_kill_switch_blocks_regardless_of_signature(self, app):
        """Kill-switch fires *before* HMAC validation — no signature needed."""
        body = json.dumps(_pr_payload()).encode()
        with patch.dict(os.environ, {"RAILO_KILL_SWITCH": "1"}):
            resp = app.post(
                "/webhook",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": f"sig-{uuid.uuid4().hex}",
                    # No X-Hub-Signature-256 header at all — still 503 not 401
                },
            )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Delivery-ID idempotency tests
# ---------------------------------------------------------------------------

class TestDeliveryIdempotency:
    def test_first_delivery_is_accepted(self, app):
        """A fresh delivery ID is accepted and the handler is invoked."""
        with patch(
            "webhook.server.process_pr_webhook",
            return_value={"status": "ok"},
        ) as mock:
            resp = _post_webhook(app, _pr_payload(), delivery_id=f"fresh-{uuid.uuid4().hex}")
        assert resp.status_code == 200
        mock.assert_called_once()

    def test_duplicate_delivery_id_is_short_circuited(self, app):
        """Replaying the same delivery ID must return 'duplicate' without calling the handler."""
        delivery_id = f"dup-{uuid.uuid4().hex}"

        # First delivery — processed normally
        with patch(
            "webhook.server.process_pr_webhook",
            return_value={"status": "ok"},
        ):
            r1 = _post_webhook(app, _pr_payload(), delivery_id)
        assert r1.status_code == 200

        # Second delivery with the same ID — must be short-circuited
        with patch(
            "webhook.server.process_pr_webhook",
            return_value={"status": "ok"},
        ) as mock_second:
            r2 = _post_webhook(app, _pr_payload(), delivery_id)
            mock_second.assert_not_called()

        assert r2.status_code == 200
        assert r2.get_json()["status"] == "duplicate"

    def test_different_delivery_ids_both_processed(self, app):
        """Two distinct delivery IDs are both handled independently."""
        id1 = f"a-{uuid.uuid4().hex}"
        id2 = f"b-{uuid.uuid4().hex}"

        with patch(
            "webhook.server.process_pr_webhook",
            return_value={"status": "ok"},
        ) as mock:
            _post_webhook(app, _pr_payload(), id1)
            _post_webhook(app, _pr_payload(), id2)

        assert mock.call_count == 2

    def test_missing_delivery_id_is_not_deduplicated(self, app):
        """A webhook with no X-GitHub-Delivery header bypasses dedup and is processed."""
        body = json.dumps(_pr_payload()).encode()
        env_override = {
            "SKIP_WEBHOOK_VERIFICATION": "true",
            "WEBHOOK_SECRET": "",
            "GITHUB_WEBHOOK_SECRET": "",
            "GITHUB_APP_WEBHOOK_SECRET": "",
        }
        with patch.dict(os.environ, env_override, clear=False):
            with patch(
                "webhook.server.process_pr_webhook",
                return_value={"status": "ok"},
            ) as mock:
                # Two requests, both without a delivery ID — both should be processed
                for _ in range(2):
                    app.post(
                        "/webhook",
                        data=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-GitHub-Event": "pull_request",
                            # No X-GitHub-Delivery
                        },
                    )
        assert mock.call_count == 2

    def test_triplicate_delivery_still_processed_once(self, app):
        """Even with three retries of the same ID, the handler runs exactly once."""
        delivery_id = f"triple-{uuid.uuid4().hex}"
        call_count = 0

        def _handler(_payload, _correlation_id):
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        with patch("webhook.server.process_pr_webhook", side_effect=_handler):
            for _ in range(3):
                _post_webhook(app, _pr_payload(), delivery_id)

        assert call_count == 1
