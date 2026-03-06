"""Worker queue configuration — lazy-init so this module is safe to import on Windows."""
from __future__ import annotations

import os


# Default job timeout per queue tier (seconds).
# Override with RAILO_JOB_TIMEOUT_* env vars.
# 0 = RQ default (180 s); -1 = unlimited (not recommended for production).
_JOB_TIMEOUT_HIGH    = int(os.getenv("RAILO_JOB_TIMEOUT_HIGH",    "300"))   # 5 min
_JOB_TIMEOUT_DEFAULT = int(os.getenv("RAILO_JOB_TIMEOUT_DEFAULT", "600"))   # 10 min
_JOB_TIMEOUT_LOW     = int(os.getenv("RAILO_JOB_TIMEOUT_LOW",     "900"))   # 15 min (CI monitor)

# Worker heartbeat interval (seconds).  RQ uses this to detect stalled jobs.
WORKER_HEARTBEAT_INTERVAL = int(os.getenv("RAILO_WORKER_HEARTBEAT", "60"))


def get_retry_strategy():
    """
    Return an RQ ``Retry`` instance for scan / CI-monitor jobs.

    Retries 3 times with exponentially increasing backoff (30 s → 60 s → 120 s).
    Returns None when RQ < 1.5 (``Retry`` class unavailable) so callers can
    enqueue without the argument.
    """
    try:
        from rq.job import Retry  # noqa: PLC0415
        return Retry(max=3, interval=[30, 60, 120])
    except ImportError:
        return None


def _build_queues() -> dict:
    from rq import Queue  # noqa: PLC0415
    from redis import Redis  # noqa: PLC0415
    redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return {
        "high":    Queue("high",    connection=redis_conn, default_timeout=_JOB_TIMEOUT_HIGH),
        "default": Queue("default", connection=redis_conn, default_timeout=_JOB_TIMEOUT_DEFAULT),
        "low":     Queue("low",     connection=redis_conn, default_timeout=_JOB_TIMEOUT_LOW),
    }


def _ensure_queues() -> None:
    global QUEUES  # noqa: PLW0603
    if not QUEUES:
        QUEUES = _build_queues()


QUEUES: dict = {}
