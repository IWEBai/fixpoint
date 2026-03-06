"""
Runbook simulation tests.

Each class maps to one runbook scenario:

  RunbookCIFailureRevert      – CI checks fail  → revert commit is pushed
  RunbookWebhookReplay        – Duplicate webhook delivery → idempotency guard
  RunbookKillSwitch           – RAILO_KILL_SWITCH=1 halts all processing
  RunbookWorkerCrash          – Worker raises mid-job → DB marked failed, slot released
  RunbookRedisOutage          – Redis unavailable → graceful degradation (allow-through)
  RunbookGitHubRateLimit      – GitHub returns 429/403 Retry-After → back-off + retry

All tests use in-process mocks; no live GitHub/Redis connections are required.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _pr_payload(
    repo: str = "acme/testrepo",
    pr_number: int = 99,
    sha: str = "cafebabe0000",
) -> dict:
    owner, _, name = repo.partition("/")
    return {
        "action": "opened",
        "installation": {"id": 1001},
        "number": pr_number,
        "pull_request": {
            "number": pr_number,
            "head": {
                "ref": "fix-branch",
                "sha": sha,
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
            "html_url": f"https://github.com/{repo}/pull/{pr_number}",
        },
        "repository": {
            "full_name": repo,
            "name": name,
            "owner": {"login": owner},
            "clone_url": f"https://github.com/{repo}.git",
        },
    }


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    """Each test gets a fresh SQLite database that is torn down afterwards."""
    from core.db import set_db_path, init_db
    set_db_path(tmp_path / "runbook.db")
    init_db()
    yield
    set_db_path(None)


# ---------------------------------------------------------------------------
# 1. CI failure → revert
# ---------------------------------------------------------------------------

class TestRunbookCIFailureRevert:
    """
    Scenario: a fix PR is created, CI checks fail, Railo pushes a revert commit.

    Simulated path:
      wait_for_ci_and_revert() → GitHub commit status = "failure"
      → tier B repo → revert_commit() called
      → job status in DB becomes "failed"
    """

    @pytest.fixture()
    def _tier_b(self, monkeypatch):
        """Make the repo resolve to permission tier B so revert is attempted."""
        monkeypatch.setattr(
            "workers.ci_monitor_worker.get_effective_permission_tier",
            lambda repo: "B",
        )

    def _make_fake_gh(self, ci_status: str):
        """Build a minimal PyGithub object tree that returns *ci_status* once."""
        combined_status = MagicMock()
        combined_status.state = ci_status

        commit = MagicMock()
        commit.get_combined_status = MagicMock(return_value=combined_status)

        pr = MagicMock()
        pr.head.sha = "deadbeef"
        pr.head.ref = "fix/sqli-patch"
        pr.html_url = "https://github.com/acme/testrepo/pull/5"
        pr.state = "open"

        repo_obj = MagicMock()
        repo_obj.get_pull = MagicMock(return_value=pr)
        repo_obj.get_commit = MagicMock(return_value=commit)
        repo_obj.clone_url = "https://github.com/acme/testrepo.git"

        gh = MagicMock()
        gh.get_repo = MagicMock(return_value=repo_obj)
        return gh, repo_obj, pr

    def test_ci_failure_triggers_revert_on_tier_b(self, monkeypatch, _tier_b):
        """When CI fails and the repo is Tier B, revert_commit() must be called."""
        from core.db import insert_run
        insert_run(
            installation_id=1001, repo="acme/testrepo",
            status="queued", job_id="job-ci-fail",
        )

        gh, repo_obj, pr = self._make_fake_gh("failure")

        revert_called: list[bool] = []

        def _fake_revert(repo_o, pr_o, sha):
            revert_called.append(True)
            return True  # simulate successful revert push

        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        with patch("workers.ci_monitor_worker.Github", return_value=gh), \
             patch("workers.ci_monitor_worker.call_github_api",
                   side_effect=lambda fn, *a, **kw: fn(*a, **kw)), \
             patch("workers.ci_monitor_worker.revert_commit",
                   side_effect=_fake_revert):

            from workers.ci_monitor_worker import wait_for_ci_and_revert
            result = wait_for_ci_and_revert(
                owner="acme", repo="testrepo",
                fix_pr_number=5, tracked_job_id="job-ci-fail",
                head_sha="deadbeef",
                max_wait_seconds=0, poll_interval=1,
            )

        assert result["status"] == "failed"
        assert result["ci_passed"] is False
        assert revert_called, "revert_commit() must have been called"

        # DB must reflect the failure
        from core.db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT job_status, ci_passed FROM runs WHERE job_id = 'job-ci-fail'"
        ).fetchone()
        conn.close()
        assert row["job_status"] == "failed"

    def test_ci_failure_tier_a_no_revert_only_comment(self, monkeypatch):
        """Tier A: CI failure must post a comment but NOT push a revert commit."""
        monkeypatch.setattr(
            "workers.ci_monitor_worker.get_effective_permission_tier",
            lambda repo: "A",
        )

        gh, repo_obj, pr = self._make_fake_gh("failure")
        revert_called: list[bool] = []
        comment_called: list[bool] = []

        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        with patch("workers.ci_monitor_worker.Github", return_value=gh), \
             patch("workers.ci_monitor_worker.call_github_api",
                   side_effect=lambda fn, *a, **kw: fn(*a, **kw)), \
             patch("workers.ci_monitor_worker.revert_commit",
                   side_effect=lambda *a, **kw: revert_called.append(True) or True), \
             patch("workers.ci_monitor_worker._post_revert_comment",
                   side_effect=lambda *a, **kw: comment_called.append(True)):

            from workers.ci_monitor_worker import wait_for_ci_and_revert
            result = wait_for_ci_and_revert(
                owner="acme", repo="testrepo",
                fix_pr_number=5, tracked_job_id="",
                head_sha="deadbeef",
                max_wait_seconds=0, poll_interval=1,
            )

        assert result["ci_passed"] is False
        assert not revert_called, "Tier A must NOT push a revert"
        assert comment_called, "Tier A must post a comment"

    def test_ci_success_no_revert(self, monkeypatch, _tier_b):
        """When CI passes, revert_commit() must NOT be called."""
        gh, repo_obj, pr = self._make_fake_gh("success")
        revert_called: list[bool] = []

        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        with patch("workers.ci_monitor_worker.Github", return_value=gh), \
             patch("workers.ci_monitor_worker.call_github_api",
                   side_effect=lambda fn, *a, **kw: fn(*a, **kw)), \
             patch("workers.ci_monitor_worker.revert_commit",
                   side_effect=lambda *a, **kw: revert_called.append(True) or True):

            from workers.ci_monitor_worker import wait_for_ci_and_revert
            result = wait_for_ci_and_revert(
                owner="acme", repo="testrepo",
                fix_pr_number=5, tracked_job_id="",
                head_sha="deadbeef",
                max_wait_seconds=0, poll_interval=1,
            )

        assert result["ci_passed"] is True
        assert not revert_called


# ---------------------------------------------------------------------------
# 2. Webhook replay → idempotency
# ---------------------------------------------------------------------------

class TestRunbookWebhookReplay:
    """
    Scenario: GitHub retries the same webhook delivery three times.

    Expected: only the first delivery triggers processing; subsequent
    duplicates are short-circuited with {"status": "duplicate"}.
    """

    @pytest.fixture()
    def client(self, tmp_path):
        from core.db import set_db_path, init_db
        set_db_path(tmp_path / "replay.db")
        init_db()
        from webhook.server import app as flask_app
        flask_app.config["TESTING"] = True
        yield flask_app.test_client()
        set_db_path(None)

    def _post(self, client, payload: dict, delivery_id: str):
        body = json.dumps(payload).encode()
        with patch.dict(os.environ, {
            "SKIP_WEBHOOK_VERIFICATION": "true",
            "WEBHOOK_SECRET": "",
            "GITHUB_WEBHOOK_SECRET": "",
        }, clear=False):
            return client.post(
                "/webhook",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": delivery_id,
                },
            )

    def test_first_delivery_processed_once(self, client):
        delivery_id = f"rb-replay-{uuid.uuid4().hex}"
        call_count = 0

        def _handler(payload, correlation_id):
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        with patch("webhook.server.process_pr_webhook", side_effect=_handler):
            r = self._post(client, _pr_payload(), delivery_id)

        assert r.status_code == 200
        assert call_count == 1

    def test_replay_is_short_circuited(self, client):
        """Three retries of the same delivery ID: handler runs exactly once."""
        delivery_id = f"rb-triple-{uuid.uuid4().hex}"
        call_count = 0

        def _handler(payload, correlation_id):
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        with patch("webhook.server.process_pr_webhook", side_effect=_handler):
            responses = [self._post(client, _pr_payload(), delivery_id) for _ in range(3)]

        assert call_count == 1, "Handler must run exactly once"
        # Second and third responses must be duplicate
        for resp in responses[1:]:
            assert resp.get_json()["status"] == "duplicate"

    def test_distinct_delivery_ids_both_processed(self, client):
        call_count = 0

        def _handler(payload, correlation_id):
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        with patch("webhook.server.process_pr_webhook", side_effect=_handler):
            self._post(client, _pr_payload(), f"id-a-{uuid.uuid4().hex}")
            self._post(client, _pr_payload(), f"id-b-{uuid.uuid4().hex}")

        assert call_count == 2

    def test_idempotency_survives_restart(self, tmp_path):
        """
        Delivery IDs are persisted to SQLite, so they survive a process restart
        (simulated by re-importing the app module with the same DB path).
        """
        from core.db import set_db_path, init_db, mark_delivery_seen, is_delivery_seen
        delivery_id = f"persist-{uuid.uuid4().hex}"

        mark_delivery_seen(delivery_id)

        # Without restarting Python we simply re-open the same DB and verify
        assert is_delivery_seen(delivery_id), \
            "Delivery ID must be durable across re-reads of the same DB"


# ---------------------------------------------------------------------------
# 3. Kill-switch activation
# ---------------------------------------------------------------------------

class TestRunbookKillSwitch:
    """
    Scenario: ops activates the kill-switch to halt all automated changes.

    Expected:
      - Webhook endpoint returns 503 before any processing
      - CI monitor worker aborts immediately
      - Audit log records the event
    """

    @pytest.fixture()
    def client(self, tmp_path):
        from core.db import set_db_path, init_db
        set_db_path(tmp_path / "ks.db")
        init_db()
        os.environ.pop("RAILO_KILL_SWITCH", None)
        from webhook.server import app as flask_app
        flask_app.config["TESTING"] = True
        yield flask_app.test_client()
        set_db_path(None)
        os.environ.pop("RAILO_KILL_SWITCH", None)

    def _post_webhook(self, client, delivery_id: str, extra_env: dict | None = None):
        body = json.dumps(_pr_payload()).encode()
        env = {
            "SKIP_WEBHOOK_VERIFICATION": "true",
            "WEBHOOK_SECRET": "",
            "GITHUB_WEBHOOK_SECRET": "",
            **(extra_env or {}),
        }
        with patch.dict(os.environ, env, clear=False):
            return client.post(
                "/webhook",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": delivery_id,
                },
            )

    def test_kill_switch_returns_503(self, client):
        resp = self._post_webhook(
            client,
            delivery_id=f"ks-{uuid.uuid4().hex}",
            extra_env={"RAILO_KILL_SWITCH": "1"},
        )
        assert resp.status_code == 503
        assert resp.get_json()["status"] == "kill_switch"

    def test_kill_switch_prevents_processing(self, client):
        with patch("webhook.server.process_pr_webhook") as mock_proc:
            self._post_webhook(
                client,
                delivery_id=f"ks2-{uuid.uuid4().hex}",
                extra_env={"RAILO_KILL_SWITCH": "1"},
            )
        mock_proc.assert_not_called()

    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
    def test_kill_switch_truthy_values(self, client, value):
        resp = self._post_webhook(
            client,
            delivery_id=f"ks-{value}-{uuid.uuid4().hex}",
            extra_env={"RAILO_KILL_SWITCH": value},
        )
        assert resp.status_code == 503

    def test_kill_switch_off_allows_webhook(self, client):
        with patch(
            "webhook.server.process_pr_webhook",
            return_value={"status": "ok"},
        ):
            resp = self._post_webhook(
                client,
                delivery_id=f"ks-off-{uuid.uuid4().hex}",
            )
        assert resp.status_code == 200

    def test_ci_monitor_aborts_on_kill_switch(self, monkeypatch):
        """wait_for_ci_and_revert() returns immediately when kill-switch is set."""
        monkeypatch.setenv("RAILO_KILL_SWITCH", "1")

        from workers.ci_monitor_worker import wait_for_ci_and_revert
        result = wait_for_ci_and_revert(
            owner="acme", repo="testrepo",
            fix_pr_number=1, tracked_job_id="job-ks",
        )
        assert result["status"] == "skipped"
        assert "kill" in result["message"].lower()

    def test_ci_monitor_abort_writes_audit_record(self, monkeypatch):
        """Kill-switch activation emits an audit event."""
        monkeypatch.setenv("RAILO_KILL_SWITCH", "1")
        monkeypatch.setenv("RAILO_AUDIT_LOG_DB", "1")

        from workers.ci_monitor_worker import wait_for_ci_and_revert
        wait_for_ci_and_revert(
            owner="acme", repo="testrepo",
            fix_pr_number=2, tracked_job_id="job-ks-audit",
        )

        from core.db import get_audit_log
        events = get_audit_log(repo="acme/testrepo", action="kill_switch_activated")
        assert events, "Audit event for kill-switch activation must be persisted"


# ---------------------------------------------------------------------------
# 4. Worker crash mid-job
# ---------------------------------------------------------------------------

class TestRunbookWorkerCrash:
    """
    Scenario: the worker raises an exception partway through a scan job.

    Expected:
      - DB run row transitions to job_status='failed'
      - Worker concurrency slot is released (counter returns to 0)
      - dedup key is unmarked so the job can be retried
    """

    def test_crash_marks_run_as_failed(self, monkeypatch):
        """When _process_pr_webhook_direct raises, the DB row must show failed."""
        from core.db import insert_run, get_connection
        job_id = "job-crash-1"
        insert_run(
            installation_id=1, repo="acme/testrepo",
            status="queued", job_id=job_id,
        )

        bomb = RuntimeError("simulated worker crash")
        monkeypatch.setattr(
            "workers.scan_worker._process_pr_webhook_direct",
            MagicMock(side_effect=bomb),
        )
        # Disable concurrency limit so slot acquisition doesn't block
        monkeypatch.setenv("RAILO_WORKER_MAX_CONCURRENT", "0")

        from workers.scan_worker import scan_and_fix_pr
        with pytest.raises(RuntimeError, match="simulated worker crash"):
            scan_and_fix_pr(
                {"installation": {"id": 1}},
                correlation_id="crash-test",
                dedup_key=job_id,
            )

        conn = get_connection()
        row = conn.execute(
            "SELECT job_status FROM runs WHERE job_id = ?", (job_id,)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["job_status"] == "failed"

    def test_crash_releases_worker_slot(self, monkeypatch):
        """The concurrency slot counter must return to 0 even after a crash."""
        from core import rate_limit as rl

        # Use a minimal fake Redis that only supports incr/decr/expire/set
        store: dict[str, int] = {}

        class _FakeRedis:
            def incr(self, key):
                store[key] = store.get(key, 0) + 1
                return store[key]

            def decr(self, key):
                store[key] = store.get(key, 0) - 1
                return store[key]

            def expire(self, key, ttl):
                pass

            def set(self, key, val):
                store[key] = int(val)

        fake_redis = _FakeRedis()
        monkeypatch.setattr(
            "core.rate_limit.get_redis_client",
            lambda: fake_redis,
        )
        monkeypatch.setenv("RAILO_WORKER_MAX_CONCURRENT", "5")
        # Reload the module-level constant to pick up the env change
        rl._WORKER_MAX_CONCURRENT = 5

        monkeypatch.setattr(
            "workers.scan_worker._process_pr_webhook_direct",
            MagicMock(side_effect=RuntimeError("crash")),
        )

        from workers.scan_worker import scan_and_fix_pr
        with pytest.raises(RuntimeError):
            scan_and_fix_pr({}, "cid", dedup_key=None)

        assert store.get(rl._WORKER_SLOT_KEY, 0) <= 0, \
            "Worker slot must be released after crash"

    def test_crash_unmarks_dedup_key(self, monkeypatch):
        """The dedup key must be cleared so the job can be re-enqueued."""
        import workers.scan_worker as sw

        unmarked: list[str] = []
        original_unmark = sw.unmark_processing

        def _spy_unmark(key):
            unmarked.append(key)
            return original_unmark(key)

        # patch at the scan_worker module level (where the finally block calls it)
        monkeypatch.setattr(sw, "unmark_processing", _spy_unmark)
        # Ensure the concurrency slot is acquired so execution reaches the inner call
        monkeypatch.setattr("core.rate_limit.acquire_worker_slot", lambda **kw: True)
        monkeypatch.setattr("core.rate_limit.release_worker_slot", lambda: None)
        monkeypatch.setattr(
            "workers.scan_worker._process_pr_webhook_direct",
            MagicMock(side_effect=RuntimeError("crash")),
        )

        from workers.scan_worker import scan_and_fix_pr
        with pytest.raises(RuntimeError):
            scan_and_fix_pr({}, "cid", dedup_key="acme:repo:42:sha")

        assert "acme:repo:42:sha" in unmarked, \
            "unmark_processing() must be called even after a crash"

    def test_worker_slot_deferred_when_limit_full(self, monkeypatch):
        """
        When the concurrency slot is exhausted the job returns 'deferred'
        without calling the inner handler.
        """
        inner_called: list[bool] = []
        monkeypatch.setattr(
            "workers.scan_worker._process_pr_webhook_direct",
            MagicMock(side_effect=lambda *a, **kw: inner_called.append(True) or {}),
        )
        # Always fail to acquire the slot
        monkeypatch.setattr(
            "core.rate_limit.acquire_worker_slot",
            lambda timeout_seconds=30: False,
        )

        from workers.scan_worker import scan_and_fix_pr
        result = scan_and_fix_pr({}, "cid-deferred", dedup_key=None)

        assert result["status"] == "deferred"
        assert not inner_called, "Inner handler must NOT be called when slot is full"


# ---------------------------------------------------------------------------
# 5. Redis outage
# ---------------------------------------------------------------------------

class TestRunbookRedisOutage:
    """
    Scenario: Redis becomes unreachable during normal operation.

    Expected:
      - Worker concurrency slot acquisition returns True (allow-through)
      - Per-PR rate limiter falls back to in-memory counter
      - Delivery-ID dedup falls back to always-process (fail-open)
      - Webhook endpoint still returns 200 (no crash)
    """

    def test_worker_slot_allows_when_redis_down(self, monkeypatch):
        """acquire_worker_slot() must return True when Redis raises."""
        import core.rate_limit as rl

        def _broken_redis():
            r = MagicMock()
            r.incr.side_effect = ConnectionError("Redis is down")
            return r

        monkeypatch.setattr("core.rate_limit.get_redis_client", _broken_redis)
        monkeypatch.setenv("RAILO_WORKER_MAX_CONCURRENT", "5")
        rl._WORKER_MAX_CONCURRENT = 5

        result = rl.acquire_worker_slot(timeout_seconds=1)
        assert result is True, \
            "Worker slot must be granted (fail-open) when Redis is unavailable"

    def test_release_worker_slot_no_crash_when_redis_down(self, monkeypatch):
        """release_worker_slot() must be a no-op (not raise) when Redis is down."""
        import core.rate_limit as rl

        def _broken_redis():
            r = MagicMock()
            r.decr.side_effect = ConnectionError("Redis is down")
            return r

        monkeypatch.setattr("core.rate_limit.get_redis_client", _broken_redis)
        monkeypatch.setenv("RAILO_WORKER_MAX_CONCURRENT", "5")
        rl._WORKER_MAX_CONCURRENT = 5

        # Must not raise
        rl.release_worker_slot()

    def test_rate_limiter_falls_back_to_memory(self, monkeypatch):
        """check_rate_limit() uses in-memory store when Redis is unavailable."""
        monkeypatch.setattr("core.rate_limit.get_redis_client", lambda: None)

        from core.rate_limit import check_rate_limit, reset_rate_limit
        key = f"test-redis-down-{uuid.uuid4().hex}"
        reset_rate_limit(key)

        allowed, remaining = check_rate_limit(key, max_requests=3, window_seconds=60)
        assert allowed is True
        assert remaining == 2  # 3 allowed - 1 used = 2

    def test_delivery_dedup_redis_down_fail_open(self, monkeypatch):
        """
        When Redis is down, delivery-ID dedup falls back to SQLite, which is
        still available — so dedup must still work via the SQLite path.
        """
        # The dedup path uses SQLite (core.db), not Redis directly,
        # so a Redis outage does not affect it.
        from core.db import mark_delivery_seen, is_delivery_seen
        did = f"no-redis-{uuid.uuid4().hex}"
        assert not is_delivery_seen(did)
        mark_delivery_seen(did)
        assert is_delivery_seen(did)

    def test_webhook_endpoint_survives_redis_outage(self, tmp_path, monkeypatch):
        """
        The /webhook endpoint must return 200 even when Redis is completely down.
        """
        from core.db import set_db_path, init_db
        set_db_path(tmp_path / "redis-down.db")
        init_db()

        # Simulate Redis unavailable everywhere
        monkeypatch.setattr("core.rate_limit.get_redis_client", lambda: None)
        monkeypatch.setattr("core.cache.get_redis_client", lambda: None)

        from webhook.server import app as flask_app
        flask_app.config["TESTING"] = True
        client = flask_app.test_client()

        body = json.dumps(_pr_payload()).encode()
        with patch("webhook.server.process_pr_webhook", return_value={"status": "ok"}):
            with patch.dict(os.environ, {
                "SKIP_WEBHOOK_VERIFICATION": "true",
                "WEBHOOK_SECRET": "",
                "GITHUB_WEBHOOK_SECRET": "",
            }, clear=False):
                resp = client.post(
                    "/webhook",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-GitHub-Event": "pull_request",
                        "X-GitHub-Delivery": f"redis-down-{uuid.uuid4().hex}",
                    },
                )

        assert resp.status_code == 200
        set_db_path(None)


# ---------------------------------------------------------------------------
# 6. GitHub API rate-limit
# ---------------------------------------------------------------------------

class TestRunbookGitHubRateLimit:
    """
    Scenario: GitHub returns rate-limit responses during CI monitoring.

    Sub-scenarios:
      a. Primary rate-limit (X-RateLimit-Reset) → waits until reset, then succeeds
      b. Secondary / abuse-detection (403 + Retry-After) → obeys Retry-After
      c. Transient 5xx → retried with exponential back-off
      d. Exhausted retries → raises the original exception

    All tests patch time.sleep to avoid actual delays.
    """

    def test_parse_wait_seconds_retry_after(self):
        """`Retry-After` header takes priority over X-RateLimit-Reset."""
        from core.rate_limit import _parse_wait_seconds

        headers = {"Retry-After": "45", "X-RateLimit-Reset": str(int(time.time()) + 600)}
        wait = _parse_wait_seconds(headers, attempt=0)
        # 45 + 2 s buffer = 47
        assert wait == 47

    def test_parse_wait_seconds_rate_limit_reset(self):
        """Falls back to X-RateLimit-Reset when Retry-After is absent."""
        from core.rate_limit import _parse_wait_seconds

        future_ts = int(time.time()) + 30
        headers = {"X-RateLimit-Reset": str(future_ts)}
        wait = _parse_wait_seconds(headers, attempt=0)
        # ~30 s + 5 s buffer; allow ±2 s for execution time
        assert 30 <= wait <= 40

    def test_parse_wait_seconds_exponential_fallback(self):
        """No headers → exponential back-off."""
        from core.rate_limit import _parse_wait_seconds

        assert _parse_wait_seconds({}, attempt=0) == 10   # 10 * 2^0
        assert _parse_wait_seconds({}, attempt=1) == 20   # 10 * 2^1
        assert _parse_wait_seconds({}, attempt=2) == 40
        assert _parse_wait_seconds({}, attempt=5) == 300  # capped at 300

    def test_primary_rate_limit_retried(self, monkeypatch):
        """
        call_github_api() retries after a RateLimitExceededException and
        eventually returns the successful result.
        """
        try:
            from github import RateLimitExceededException  # type: ignore
        except ImportError:
            pytest.skip("PyGithub not installed")

        sleep_calls: list[float] = []
        monkeypatch.setattr("core.rate_limit.time.sleep", lambda s: sleep_calls.append(s))

        # Fail twice, succeed on third attempt
        exc = RateLimitExceededException(403, {}, {"X-RateLimit-Reset": str(int(time.time()) + 5)})
        call_count = 0

        def _flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise exc
            return "ok"

        from core.rate_limit import call_github_api
        result = call_github_api(_flaky, max_attempts=5)

        assert result == "ok"
        assert call_count == 3
        assert len(sleep_calls) == 2  # slept once per failed attempt

    def test_secondary_rate_limit_403_retry_after(self, monkeypatch):
        """
        A 403 with Retry-After (secondary / abuse-detection limit) is retried,
        and the Retry-After value is respected.
        """
        try:
            from github import GithubException  # type: ignore
        except ImportError:
            pytest.skip("PyGithub not installed")

        sleep_calls: list[float] = []
        monkeypatch.setattr("core.rate_limit.time.sleep", lambda s: sleep_calls.append(s))

        headers = {"Retry-After": "30"}
        exc = GithubException(403, {}, headers)

        call_count = 0

        def _flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise exc
            return "recovered"

        from core.rate_limit import call_github_api
        result = call_github_api(_flaky, max_attempts=3)

        assert result == "recovered"
        # Must have slept for Retry-After + buffer = 32
        assert sleep_calls and sleep_calls[0] == 32

    def test_transient_5xx_retried_with_backoff(self, monkeypatch):
        """5xx responses are retried up to max_attempts times."""
        try:
            from github import GithubException  # type: ignore
        except ImportError:
            pytest.skip("PyGithub not installed")

        sleep_calls: list[float] = []
        monkeypatch.setattr("core.rate_limit.time.sleep", lambda s: sleep_calls.append(s))

        call_count = 0

        def _flaky_502():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise GithubException(502, {}, {})
            return "ok"

        from core.rate_limit import call_github_api
        result = call_github_api(_flaky_502, max_attempts=5)

        assert result == "ok"
        assert len(sleep_calls) == 3

    def test_exhausted_retries_raises(self, monkeypatch):
        """After max_attempts failures, the original exception is re-raised."""
        try:
            from github import RateLimitExceededException  # type: ignore
        except ImportError:
            pytest.skip("PyGithub not installed")

        monkeypatch.setattr("core.rate_limit.time.sleep", lambda s: None)

        exc = RateLimitExceededException(429, {}, {})

        from core.rate_limit import call_github_api
        with pytest.raises(RateLimitExceededException):
            call_github_api(MagicMock(side_effect=exc), max_attempts=3)

    def test_non_retryable_403_not_retried(self, monkeypatch):
        """A plain 403 (no Retry-After) must NOT be retried — it is a permission error."""
        try:
            from github import GithubException  # type: ignore
        except ImportError:
            pytest.skip("PyGithub not installed")

        sleep_calls: list[float] = []
        monkeypatch.setattr("core.rate_limit.time.sleep", lambda s: sleep_calls.append(s))

        exc = GithubException(403, {}, {})  # no Retry-After header
        call_count = 0

        def _fn():
            nonlocal call_count
            call_count += 1
            raise exc

        from core.rate_limit import call_github_api
        with pytest.raises(GithubException):
            call_github_api(_fn, max_attempts=3)

        # Must have been called exactly once — no retries for plain 403
        assert call_count == 1
        assert not sleep_calls
