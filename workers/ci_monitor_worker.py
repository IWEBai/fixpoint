"""Background worker to monitor CI for fix PRs and revert on failure."""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict

from github import Github, Auth  # type: ignore

from core.db import (
    update_run_job_status,
    get_effective_permission_tier,
)
from core.rate_limit import call_github_api

# Allowlisted fixer labels that are considered safe to auto-merge
# (must appear in the PR title, case-insensitive)
_SAFE_PATCH_KEYWORDS = {
    "sqli",
    "sql-injection",
    "xss",
    "cross-site",
    "secrets",
    "hardcoded",
    "path-traversal",
    "ssrf",
    "command-injection",
}

# GitHub user-login that Railo uses when creating PRs
_RAILO_BOT_LOGINS = {"railo-bot", "railo[bot]", "fixpoint-bot"}


def _get_current_job():
    try:
        from rq import get_current_job  # noqa: PLC0415
        return get_current_job()
    except Exception:
        return None


def _kill_switch_active() -> bool:
    """Return True when the global kill-switch is set."""
    return os.getenv("RAILO_KILL_SWITCH", "").lower() in {"1", "true", "yes"}


def wait_for_ci_and_revert(
    owner: str,
    repo: str,
    fix_pr_number: int,
    tracked_job_id: str,
    head_sha: Optional[str] = None,
    max_wait_seconds: int = 300,
    poll_interval: int = 15,
    auto_merge: bool = False,
    installation_id: Optional[int] = None,
) -> Dict[str, object]:
    from core.observability import log_audit_event  # noqa: PLC0415

    # Kill-switch: abort immediately
    if _kill_switch_active():
        try:
            log_audit_event(
                "kill_switch_activated",
                "skipped",
                repo=f"{owner}/{repo}",
                pr_number=fix_pr_number,
                metadata={"worker": "ci_monitor", "job_id": tracked_job_id or ""},
            )
        except Exception:
            pass
        return _mark_ci(tracked_job_id or "", None, "skipped", "Kill-switch active — worker aborted")

    job = _get_current_job()
    monitor_id = job.id if job else None
    job_id_for_run = tracked_job_id or monitor_id or ""
    repo_full = f"{owner}/{repo}"

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return _mark_ci(job_id_for_run, None, "skipped", "Missing GITHUB_TOKEN for CI monitor")

    gh = Github(auth=Auth.Token(token))
    repo_obj = call_github_api(gh.get_repo, repo_full)
    pr = call_github_api(repo_obj.get_pull, fix_pr_number)
    sha = head_sha or pr.head.sha
    pr_url = pr.html_url or ""

    # Permission tier: revert push requires Tier B
    tier = get_effective_permission_tier(repo_full)

    elapsed = 0
    while elapsed <= max_wait_seconds:
        commit = call_github_api(repo_obj.get_commit, sha)
        status = call_github_api(commit.get_combined_status).state  # pending, success, failure, error
        if status == "success":
            _fire_notification("ci_success", repo_full, pr_url, installation_id)
            if auto_merge and tier == "B":
                eligible, reason = is_auto_merge_eligible(pr)
                if eligible:
                    merged = _attempt_auto_merge(pr)
                    msg = "CI passed; PR auto-merged" if merged else "CI passed; auto-merge attempted but skipped by GitHub"
                    try:
                        log_audit_event(
                            "ci_check_passed", "auto_merged" if merged else "merge_skipped",
                            repo=repo_full, pr_number=fix_pr_number,
                            metadata={"sha": sha, "pr_url": pr_url},
                        )
                    except Exception:
                        pass
                    return _mark_ci(job_id_for_run, True, "success", msg)
                else:
                    # Dry-run: record "would-have-merged" and continue without merging
                    _record_would_have_merged(job_id_for_run, reason)
                    try:
                        log_audit_event(
                            "ci_check_passed", "dry_run_merge_skipped",
                            repo=repo_full, pr_number=fix_pr_number,
                            metadata={"reason": reason, "sha": sha},
                        )
                    except Exception:
                        pass
                    return _mark_ci(job_id_for_run, True, "success", f"CI passed; dry-run auto-merge skipped ({reason})")
            elif auto_merge:
                # auto_merge requested but Tier A — record dry-run metric only
                _record_would_have_merged(job_id_for_run, "Tier A — auto-merge requires Tier B opt-in")
                try:
                    log_audit_event(
                        "ci_check_passed", "auto_merge_skipped_tier_a",
                        repo=repo_full, pr_number=fix_pr_number,
                        metadata={"sha": sha},
                    )
                except Exception:
                    pass
                return _mark_ci(job_id_for_run, True, "success", "CI passed; auto-merge skipped (Tier A)")
            try:
                log_audit_event(
                    "ci_check_passed", "success",
                    repo=repo_full, pr_number=fix_pr_number,
                    metadata={"sha": sha, "pr_url": pr_url},
                )
            except Exception:
                pass
            return _mark_ci(job_id_for_run, True, "success", "CI checks passed")
        if status in {"failure", "error"}:
            if tier == "B":
                reverted = revert_commit(repo_obj, pr, sha)
                message = "CI failed; revert pushed" if reverted else "CI failed; revert not applied (git error)"
            else:
                # Tier A: comment only, no push
                _post_revert_comment(pr, sha, reason="Tier A mode — manual revert required")
                message = "CI failed; comment posted (Tier A)"
            try:
                log_audit_event(
                    "ci_check_failed", "reverted" if (tier == "B") else "comment_posted",
                    repo=repo_full, pr_number=fix_pr_number,
                    metadata={"sha": sha, "pr_url": pr_url, "tier": tier, "message": message},
                )
            except Exception:
                pass
            _fire_notification("ci_failure", repo_full, pr_url, installation_id, extra=message)
            return _mark_ci(job_id_for_run, False, "failed", message)
        time.sleep(poll_interval)
        elapsed += poll_interval

    try:
        log_audit_event(
            "ci_check_timeout", "timeout",
            repo=repo_full, pr_number=fix_pr_number,
            metadata={"sha": sha, "max_wait_seconds": max_wait_seconds},
        )
    except Exception:
        pass
    _fire_notification("ci_timeout", repo_full, pr_url, installation_id)
    return _mark_ci(job_id_for_run, True, "timeout", "CI timeout; assuming success")



def _mark_ci(job_id: str, ci_passed: Optional[bool], job_status: str, message: str) -> Dict[str, object]:
    if job_id:
        try:
            update_run_job_status(job_id=job_id, job_status=job_status, ci_passed=ci_passed)
        except Exception:
            pass
    return {"status": job_status, "ci_passed": ci_passed, "message": message}


def _record_would_have_merged(job_id: str, reason: str) -> None:
    """Increment the dry-run 'would_have_auto_merged' counter on the run row."""
    if not job_id:
        return
    try:
        from core.db import get_connection  # noqa: PLC0415
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE runs SET would_have_auto_merged = 1 WHERE job_id = ?",
                (job_id,),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _fire_notification(
    event: str,
    repo: str,
    pr_url: str,
    installation_id: Optional[int],
    extra: str = "",
    correlation_id: str = "",
) -> None:
    """Best-effort notification dispatch — never raises."""
    try:
        from core.notifications import send_notification  # noqa: PLC0415
        send_notification(
            event=event,
            data={
                "repo": repo,
                "pr_url": pr_url,
                "message": extra,
                "correlation_id": correlation_id,
            },
            installation_id=installation_id,
        )
    except Exception:
        pass


def is_auto_merge_eligible(pr) -> tuple[bool, str]:
    """
    Return (eligible, reason) for auto-merge with 5 hard gates.

    Gates (ALL must pass):
    1. ≤ 3 files changed
    2. ≤ 100 lines changed (additions + deletions)
    3. PR title contains an allowlisted fixer keyword
    4. PR was opened by the Railo bot (not a human)
    5. PR body contains the Railo-signed marker (``<!-- railo-fix -->``),
       proving the patch was created by Railo's own fixer pipeline.

    The 6th gate — "no new findings after fix" — is enforced at enqueue
    time via post-scan analysis; if unverified the ``auto_merge`` flag is
    not set at all (see scan_worker.py).
    """
    try:
        if pr.changed_files > 3:
            return False, f"too many files changed ({pr.changed_files} > 3)"
        total_lines = (pr.additions or 0) + (pr.deletions or 0)
        if total_lines > 100:
            return False, f"diff too large ({total_lines} lines > 100)"
        title_lower = (pr.title or "").lower()
        if not any(kw in title_lower for kw in _SAFE_PATCH_KEYWORDS):
            return False, "title does not match allowlisted fixer keywords"
        pr_author = (pr.user.login if pr.user else "").lower()
        if pr_author not in _RAILO_BOT_LOGINS and not pr_author.endswith("[bot]"):
            return False, f"PR author '{pr_author}' is not the Railo bot"
        body = pr.body or ""
        if "<!-- railo-fix -->" not in body:
            return False, "PR body missing Railo signature marker"
        return True, ""
    except Exception as exc:
        return False, f"eligibility check error: {exc}"


# Keep old name as alias so existing callers don't break
def is_low_risk_pr(pr) -> bool:
    eligible, _ = is_auto_merge_eligible(pr)
    return eligible



def _attempt_auto_merge(pr) -> bool:
    """
    Attempt to merge *pr* via the squash strategy.

    Returns:
        True  – merge succeeded.
        False – merge skipped or failed (PR already closed, merge conflicts, etc.).
    """
    try:
        if pr.state != "open":
            return False
        if not pr.mergeable:
            return False
        call_github_api(
            pr.merge,
            commit_title=f"{pr.title} (auto-merged by Railo)",
            commit_message="Automatically merged low-risk security fix after CI passed.",
            merge_method="squash",
        )
        return True
    except Exception:
        return False


def revert_commit(repo_obj, pr, sha: str) -> bool:
    """
    Push a ``git revert`` commit on the PR branch for *sha*.

    Strategy:
    1. Clone the repo (shallow, single-branch of the PR head) into a temp dir.
    2. Run ``git revert --no-edit <sha>`` to create a revert commit locally.
    3. Push back to the PR branch.
    4. On any git failure, fall back to posting a comment so humans are notified.

    Returns:
        True  – revert commit successfully pushed.
        False – revert not applied (git error or missing token).
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        _post_revert_comment(pr, sha, reason="Missing GITHUB_TOKEN")
        return False

    clone_url = repo_obj.clone_url  # https://github.com/owner/repo.git
    auth_url = clone_url.replace("https://", f"https://x-access-token:{token}@", 1)
    branch = pr.head.ref

    try:
        with tempfile.TemporaryDirectory(prefix="railo-revert-") as tmpdir:
            repo_path = Path(tmpdir) / "repo"
            _git(
                ["git", "clone", "--depth=5", "--branch", branch, auth_url, str(repo_path)],
                cwd=Path(tmpdir),
            )
            _git(["git", "config", "user.email", "fixpoint-bot@users.noreply.github.com"], cwd=repo_path)
            _git(["git", "config", "user.name", "fixpoint-bot"], cwd=repo_path)
            _git(["git", "revert", "--no-edit", sha], cwd=repo_path)
            _git(["git", "push", "origin", branch], cwd=repo_path)
        try:
            call_github_api(
                pr.create_issue_comment,
                f"CI checks failed for commit {sha}. "
                f"A revert commit has been pushed to `{branch}` automatically.",
            )
        except Exception:
            pass
        return True
    except Exception as exc:
        _post_revert_comment(pr, sha, reason=str(exc)[:300])
        return False


def _git(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command, raising RuntimeError with stderr on failure."""
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git command failed: {' '.join(cmd)}\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result


def _post_revert_comment(pr, sha: str, reason: str = "") -> None:
    """Post a fallback comment when the automated revert could not be applied."""
    try:
        body = (
            f"CI checks failed for commit `{sha}`. "
            f"Automated revert was not applied"
            + (f" ({reason})" if reason else "")
            + ". Please revert manually or fix forward."
        )
        call_github_api(pr.create_issue_comment, body)
    except Exception:
        pass
