"""Background worker for scanning PRs and creating fix PRs."""
from __future__ import annotations

from typing import Any, Dict
import os
import time

from webhook.server import _process_pr_webhook_direct
from core.job_dedup import unmark_processing
from core.db import update_run_job_status, get_effective_repo_settings


def _get_current_job():
    try:
        from rq import get_current_job  # noqa: PLC0415
        return get_current_job()
    except Exception:
        return None


def scan_and_fix_pr(payload: dict, correlation_id: str, dedup_key: str | None = None) -> Dict[str, Any]:
    from core.rate_limit import acquire_worker_slot, release_worker_slot  # noqa: PLC0415

    job = _get_current_job()
    job_id = (job.id if job else dedup_key) or ""
    started_at = time.monotonic()

    # Global worker concurrency throttle — prevent overloading downstream APIs
    slot_acquired = acquire_worker_slot(timeout_seconds=60)
    if not slot_acquired:
        if job_id:
            try:
                update_run_job_status(job_id=job_id, job_status="deferred", status="deferred")
            except Exception:
                pass
        return {"status": "deferred", "message": "Worker concurrency limit reached; try again later"}

    if job_id:
        try:
            update_run_job_status(job_id=job_id, job_status="processing", status="processing")
        except Exception:
            pass

    try:
        result = _process_pr_webhook_direct(payload, correlation_id)
        runtime_seconds = time.monotonic() - started_at

        if job_id:
            try:
                update_run_job_status(
                    job_id=job_id,
                    status=result.get("status"),
                    job_status="completed",
                    fix_pr_number=result.get("fix_pr_number"),
                    fix_pr_url=result.get("fix_pr_url"),
                    runtime_seconds=runtime_seconds,
                )
            except Exception:
                pass

        if (
            os.getenv("RAILO_ENABLE_CI_MONITOR", "").lower() in {"1", "true", "yes"}
            and job_id
            and result.get("fix_pr_number")
        ):
            try:
                from workers.config import QUEUES, get_retry_strategy  # noqa: PLC0415
                from workers.ci_monitor_worker import wait_for_ci_and_revert

                _retry = get_retry_strategy()
                _ci_enqueue_kwargs: dict = {}
                if _retry is not None:
                    _ci_enqueue_kwargs["retry"] = _retry

                pr = payload.get("pull_request") or {}
                owner = payload.get("repository", {}).get("owner", {}).get("login")
                repo_name = payload.get("repository", {}).get("name")
                head_sha = pr.get("head", {}).get("sha") or ""

                if owner and repo_name:
                    full_repo = f"{owner}/{repo_name}"
                    effective = get_effective_repo_settings(full_repo)
                    # Auto-merge: requires BOTH mode=fix AND explicit auto_merge_enabled opt-in
                    auto_merge = (
                        effective.get("mode") == "fix"
                        and bool(effective.get("auto_merge_enabled", 0))
                    )
                    install_id = (
                        result.get("installation_id")
                        or payload.get("installation", {}).get("id")
                    )
                    QUEUES.get("low", QUEUES.get("default")).enqueue(
                        wait_for_ci_and_revert,
                        owner,
                        repo_name,
                        int(result.get("fix_pr_number")),
                        job_id,
                        head_sha=head_sha,
                        auto_merge=auto_merge,
                        installation_id=install_id,
                        job_id=f"ci_monitor:{owner}:{repo_name}:{result.get('fix_pr_number')}",
                        **_ci_enqueue_kwargs,
                    )
            except Exception:
                pass

        return result
    except Exception:
        runtime_seconds = time.monotonic() - started_at
        if job_id:
            try:
                update_run_job_status(
                    job_id=job_id,
                    status="error",
                    job_status="failed",
                    runtime_seconds=runtime_seconds,
                )
            except Exception:
                pass
        raise
    finally:
        release_worker_slot()
        if dedup_key:
            unmark_processing(dedup_key)
