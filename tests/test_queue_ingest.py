import os
from pathlib import Path

import pytest

from core import job_dedup
from core.db import set_db_path, init_db
from webhook.server import process_pr_webhook

import workers.config as _workers_config


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def exists(self, key):
        return key in self.store

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def delete(self, key):
        return self.store.pop(key, None) is not None


class _DummyJob:
    def __init__(self, job_id: str):
        self.id = job_id


class _DummyQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, fn, *args, **kwargs):
        job_id = kwargs.get("job_id") or f"job-{len(self.enqueued)}"
        self.enqueued.append({"fn": fn, "args": args, "kwargs": kwargs})
        return _DummyJob(job_id)


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "queue_test.db"
    set_db_path(db_path)
    init_db()
    monkeypatch.setenv("FIXPOINT_DB_PATH", str(db_path))
    yield


def test_queue_ingests_and_dedupes(monkeypatch):
    monkeypatch.setenv("RAILO_ENABLE_QUEUE", "1")

    fake_redis = _FakeRedis()
    monkeypatch.setattr(job_dedup, "_get_redis_client", lambda: fake_redis)

    dummy_queue = _DummyQueue()
    monkeypatch.setattr(_workers_config, "QUEUES", {"default": dummy_queue}, raising=False)

    payload = {
        "installation": {"id": 1234},
        "repository": {"owner": {"login": "octo"}, "name": "repo"},
        "pull_request": {
            "number": 42,
            "head": {"sha": "abc123", "ref": "feature"},
            "base": {"ref": "main"},
        },
        "action": "opened",
    }

    first = process_pr_webhook(payload, correlation_id="test-1")
    assert first["status"] == "queued"
    assert first["job_id"] == "octo:repo:42:abc123"

    second = process_pr_webhook(payload, correlation_id="test-2")
    assert second["status"] == "skipped_duplicate"
