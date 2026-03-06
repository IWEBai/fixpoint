from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from rq import Connection, Worker

from main import process_repo_scan  # type: ignore
from railo_cloud import crud
from railo_cloud.artifacts import canonical_artifact_path
from railo_cloud.config import get_settings
from railo_cloud.db.base import get_session
from railo_cloud.models import RunStatus
from railo_cloud.queue import get_redis_connection
from core.status_checks import create_check_run_with_annotations
from core.pr_comments import create_warn_comment, create_fix_comment
from core.git_ops import commit_and_push_to_existing_branch

logger = logging.getLogger(__name__)


def _clone_repo(owner: str, repo: str, ref: str | None, dest: Path, git_timeout: int, token: str | None = None) -> None:
    if token:
        repo_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    else:
        repo_url = f"https://github.com/{owner}/{repo}.git"
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd.extend(["--branch", ref])
    cmd.extend([repo_url, str(dest)])

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    subprocess.run(cmd, check=True, timeout=git_timeout, env=env, capture_output=True)
    # Ensure target ref is checked out
    if ref:
        subprocess.run(["git", "checkout", ref], cwd=dest, check=True, timeout=git_timeout, env=env)


def _prepare_repo(job: dict[str, Any], git_timeout: int, token: str | None = None) -> tuple[Path, bool]:
    local_repo = job.get("local_repo_path")
    if local_repo:
        return Path(local_repo), False

    owner = job["repo_owner"]
    repo = job["repo_name"]
    head_ref = job.get("head_ref")
    tmpdir = Path(tempfile.mkdtemp(prefix="fixpoint-"))
    _clone_repo(owner, repo, head_ref, tmpdir, git_timeout, token=token)
    base_ref = job.get("base_ref")
    if base_ref:
        try:
            subprocess.run(
                ["git", "fetch", "origin", f"+refs/heads/{base_ref}:refs/remotes/origin/{base_ref}"],
                cwd=tmpdir,
                check=True,
                timeout=git_timeout,
                capture_output=True,
            )
        except Exception:
            pass
    return tmpdir, True


def handle_job(job_payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    run_id = uuid.UUID(str(job_payload["run_id"]))
    summary: dict[str, Any] = {}
    with contextlib.closing(get_session()) as session:
        try:
            crud.update_run_status(session, run_id, RunStatus.running, job_id=str(run_id))
            engine_mode = job_payload.get("engine_mode") or settings.engine_mode
            # Legacy enable_engine flag
            if job_payload.get("enable_engine") and engine_mode == "stub":
                engine_mode = "local"

            if engine_mode not in {"stub", "local", "live"}:
                crud.update_run_status(
                    session,
                    run_id,
                    RunStatus.failed,
                    error="Unsupported engine_mode",
                    error_code="ENGINE_MODE_INVALID",
                    error_summary=f"engine_mode={engine_mode}",
                )
                return {"message": "invalid engine mode", "engine_mode": engine_mode}

            artifact_root = Path(settings.artifact_root).resolve()
            run_artifact_dir = artifact_root / str(run_id)
            run_artifact_dir.mkdir(parents=True, exist_ok=True)

            if engine_mode == "stub":
                summary = {"message": "engine disabled (stub)", "mode": job_payload.get("mode")}
                crud.update_run_status(
                    session,
                    run_id,
                    RunStatus.succeeded,
                    summary=summary,
                    artifact_paths={},
                )
                return summary

            if engine_mode == "local":
                repo_path_str = (
                    job_payload.get("engine_repo_path")
                    or job_payload.get("local_repo_path")
                    or settings.engine_repo_path
                )
                base_ref = job_payload.get("base_ref") or settings.engine_base_ref
                head_ref = job_payload.get("head_ref") or settings.engine_head_ref

                if not repo_path_str:
                    crud.update_run_status(
                        session,
                        run_id,
                        RunStatus.failed,
                        error="ENGINE_REPO_PATH missing",
                        error_code="ENGINE_CONFIG",
                        error_summary="No engine repo path configured",
                    )
                    return {"message": "missing engine repo path"}
                if not head_ref or not base_ref:
                    crud.update_run_status(
                        session,
                        run_id,
                        RunStatus.failed,
                        error="HEAD/BASE ref missing",
                        error_code="ENGINE_CONFIG",
                        error_summary="Missing base/head refs",
                    )
                    return {"message": "missing refs"}

                repo_path = Path(repo_path_str)
                if not repo_path.exists():
                    crud.update_run_status(
                        session,
                        run_id,
                        RunStatus.failed,
                        error=f"Repo path does not exist: {repo_path}",
                        error_code="ENGINE_CONFIG",
                        error_summary="Repo path missing",
                    )
                    return {"message": "repo path missing"}

                # No clone in local mode; use provided repo path
                results_path = run_artifact_dir / "semgrep_results.json"
                any_changes, processed = process_repo_scan(
                    repo_path,
                    settings.rules_path,
                    results_path,
                    pr_mode=True,
                    base_ref=base_ref,
                    head_ref=head_ref,
                )

                patch_plan_path = run_artifact_dir / "patch_plan.json"
                with patch_plan_path.open("w", encoding="utf-8") as fp:
                    json.dump({"processed": processed}, fp, ensure_ascii=False, indent=2)

                artifact_paths = {
                    "semgrep": canonical_artifact_path(results_path, artifact_root),
                    "patch_plan": canonical_artifact_path(patch_plan_path, artifact_root),
                }

                summary = {
                    "any_changes": any_changes,
                    "findings": len(processed),
                }
                crud.update_run_status(
                    session,
                    run_id,
                    RunStatus.succeeded,
                    summary=summary,
                    artifact_paths=artifact_paths,
                )
                return summary

            # engine_mode == live
            owner = job_payload["repo_owner"]
            repo = job_payload["repo_name"]
            pr_number = job_payload.get("pr_number")
            base_ref = job_payload.get("base_ref")
            head_ref = job_payload.get("head_ref")
            head_sha = job_payload.get("head_sha")
            installation_token = job_payload.get("installation_token")

            if not installation_token:
                crud.update_run_status(
                    session,
                    run_id,
                    RunStatus.failed,
                    error="Missing installation token",
                    error_code="AUTH",
                    error_summary="No installation token provided",
                )
                return {"message": "missing installation token"}

            if not head_ref or not base_ref:
                crud.update_run_status(
                    session,
                    run_id,
                    RunStatus.failed,
                    error="HEAD/BASE ref missing",
                    error_code="ENGINE_CONFIG",
                    error_summary="Missing base/head refs",
                )
                return {"message": "missing refs"}

            tmpdir = Path(tempfile.mkdtemp(prefix="fixpoint-live-"))
            should_cleanup = True
            try:
                _clone_repo(owner, repo, head_ref, tmpdir, settings.git_timeout, token=installation_token)
                if base_ref:
                    try:
                        env = os.environ.copy()
                        env["GIT_TERMINAL_PROMPT"] = "0"
                        subprocess.run(
                            ["git", "fetch", "--depth=1", "origin",
                             f"+refs/heads/{base_ref}:refs/remotes/origin/{base_ref}"],
                            cwd=tmpdir,
                            check=True,
                            timeout=settings.git_timeout,
                            env=env,
                            capture_output=True,
                            text=True,
                        )
                        # Use origin/<base_ref> for diff since we only fetched, not checked out
                        base_ref = f"origin/{base_ref}"
                    except subprocess.CalledProcessError as fetch_err:
                        print(f"Warning: git fetch origin {base_ref} failed: {fetch_err.stderr}")
                    except Exception as e:
                        print(f"Warning: fetch base_ref failed: {e}")

                results_path = run_artifact_dir / "semgrep_results.json"
                any_changes, processed = process_repo_scan(
                    tmpdir,
                    settings.rules_path,
                    results_path,
                    pr_mode=True,
                    base_ref=base_ref,
                    head_ref=head_ref,
                )

                patch_plan_path = run_artifact_dir / "patch_plan.json"
                with patch_plan_path.open("w", encoding="utf-8") as fp:
                    json.dump({"processed": processed}, fp, ensure_ascii=False, indent=2)

                artifact_paths = {
                    "semgrep": canonical_artifact_path(results_path, artifact_root),
                    "patch_plan": canonical_artifact_path(patch_plan_path, artifact_root),
                }

                mode = (job_payload.get("mode") or "warn").lower()
                if mode == "enforce" and any_changes:
                    commit_message = "[fixpoint] apply security fixes"
                    try:
                        pushed = commit_and_push_to_existing_branch(tmpdir, head_ref, commit_message)
                    except Exception as e:
                        crud.update_run_status(
                            session,
                            run_id,
                            RunStatus.failed,
                            error=str(e),
                            error_code="PUSH_FAILED",
                            error_summary=str(e)[:500],
                        )
                        raise

                    files_fixed = [p.get("file") for p in processed if p.get("fixed")]
                    conclusion = "success" if pushed else "neutral"
                    create_check_run_with_annotations(
                        owner,
                        repo,
                        head_sha or head_ref or "",
                        processed,
                        conclusion=conclusion,
                        pr_url=None,
                        token=installation_token,
                    )
                    if pr_number:
                        create_fix_comment(
                            owner,
                            repo,
                            pr_number,
                            files_fixed=files_fixed,
                            findings=processed,
                            patch_hunks=None,
                            token=installation_token,
                        )
                else:
                    # Warn-only path
                    conclusion = "neutral" if processed else "success"
                    create_check_run_with_annotations(
                        owner,
                        repo,
                        head_sha or head_ref or "",
                        processed,
                        conclusion=conclusion,
                        pr_url=None,
                        token=installation_token,
                    )
                    if pr_number:
                        create_warn_comment(
                            owner,
                            repo,
                            pr_number,
                            findings=processed,
                            proposed_fixes=[],
                            head_sha=head_sha,
                            token=installation_token,
                        )
                summary = {
                    "any_changes": any_changes,
                    "findings": len(processed),
                    "mode": job_payload.get("mode"),
                }
                crud.update_run_status(
                    session,
                    run_id,
                    RunStatus.succeeded,
                    summary=summary,
                    artifact_paths=artifact_paths,
                )
                return summary
            finally:
                if should_cleanup:
                    shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception as exc:  # pragma: no cover - defensive
            crud.update_run_status(
                session,
                run_id,
                RunStatus.failed,
                error=str(exc),
                error_code="ENGINE_ERROR",
                error_summary=str(exc),
            )
            raise
    # contextlib.closing ensures session.close() is always called


def _on_job_failure(job, connection, type, value, traceback_obj):
    """RQ failure callback — logs a structured alert for any permanently failed job.

    This fires after all retries are exhausted, giving operators visibility
    into dead-lettered jobs via Azure Monitor / log tailing.
    """
    run_id = (job.args[0] or {}).get("run_id") if job.args else None
    logger.error(
        "Job permanently failed after all retries: job_id=%s run_id=%s error=%s: %s",
        job.id,
        run_id,
        type.__name__ if type else "unknown",
        value,
        exc_info=(type, value, traceback_obj),
    )


def main() -> None:
    settings = get_settings()
    redis_conn = get_redis_connection()
    with Connection(redis_conn):
        worker = Worker(
            [settings.rq_queue],
            exception_handlers=[_on_job_failure],
        )
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
