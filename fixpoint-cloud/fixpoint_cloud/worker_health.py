from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from rq import Queue, Worker
from rq.registries import FailedJobRegistry

from fixpoint_cloud.config import get_settings
from fixpoint_cloud.queue import get_redis_connection

# A worker is considered stale if it hasn't finished a job in this many minutes.
_STALE_WORKER_MINUTES = 30


def main() -> None:
    exit_code = 0
    settings = get_settings()

    # 1. Redis reachability
    try:
        conn = get_redis_connection()
        conn.ping()
    except Exception as exc:  # pragma: no cover
        print(f"FAIL redis ping: {exc}")
        sys.exit(1)

    # 2. At least one worker is registered
    try:
        workers = Worker.all(connection=conn)
        if not workers:
            print("WARN no RQ workers registered with Redis")
            exit_code = 1
        else:
            print(f"OK   {len(workers)} worker(s) registered: {[w.name for w in workers]}")
    except Exception as exc:  # pragma: no cover
        print(f"WARN could not enumerate workers: {exc}")
        exit_code = 1

    # 3. Queue depth
    try:
        q = Queue(settings.rq_queue, connection=conn)
        failed_registry = FailedJobRegistry(queue=q)
        depth = len(q)
        failed = len(failed_registry)
        status = "OK  " if depth < 50 else "WARN"
        print(f"{status} queue depth={depth} failed={failed}")
        if depth >= 50:
            exit_code = 1
    except Exception as exc:  # pragma: no cover
        print(f"WARN could not check queue depth: {exc}")

    # 4. Last successful job freshness (only if workers are registered)
    try:
        workers = Worker.all(connection=conn)
        stale_cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=_STALE_WORKER_MINUTES)
        fresh = [
            w for w in workers
            if w.last_heartbeat and w.last_heartbeat >= stale_cutoff
        ]
        if workers and not fresh:
            print(f"WARN all workers last heartbeat > {_STALE_WORKER_MINUTES}m ago — possible stall")
            exit_code = 1
        elif fresh:
            print(f"OK   {len(fresh)}/{len(workers)} worker(s) heartbeat within {_STALE_WORKER_MINUTES}m")
    except Exception as exc:  # pragma: no cover
        print(f"WARN could not check worker heartbeats: {exc}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
