"""
GitHub webhook server for Railo Phase 2.
Listens for PR events and triggers automatic fixes with full safety and security.
"""
from __future__ import annotations

import os
import json
import tempfile
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, redirect, session
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scanner import semgrep_scan, get_pr_diff_files
from core.fixer import process_findings
from core.git_ops import setup_git_identity
from core.safety import (
    compute_fix_idempotency_key,
    check_loop_prevention,
    check_confidence_gating,
    check_max_diff_lines,
    validate_patch_plan,
    analyze_diff_quality,
)
from core.config import load_config, ConfigError
from core.patch_plan import generate_patch_plan
from core.security import (
    validate_webhook_request,
    is_allowed_pr_action,
    is_repo_allowed,
    sanitize_repo_owner,
    sanitize_repo_name,
    validate_installation_id,
)
from core.github_app_auth import get_installation_access_token, is_github_app_configured
from core.pr_comments import (
    create_error_comment,
    create_warn_comment,
    generate_fix_pr_notification,
    generate_welcome_comment,
)
from core.fix_pr_service import create_fix_pr
from github_bot.open_pr import add_pr_labels, comment_on_pr
from core.status_checks import create_check_run_with_annotations
from core.observability import (
    log_webhook_event,
    log_processing_result,
    log_fix_applied,
    CorrelationContext,
)
from core.dashboard_queries import (
    get_vulnerability_breakdown,
    get_fix_merge_rate,
    get_ci_success_rate,
    get_run_timeseries,
    get_dry_run_stats,
    get_runs_per_hour,
    get_failed_runs_total,
    get_reverts_total,
    get_queue_depths,
    get_fix_prs_created,
    get_fix_prs_merged,
)


def process_pr_webhook(payload: dict, correlation_id: str) -> dict:
    """Public entrypoint: optionally enqueue, else process synchronously."""
    # Kill-switch: stop processing before anything else
    if os.getenv("RAILO_KILL_SWITCH", "").lower() in {"1", "true", "yes"}:
        return {"status": "kill_switch", "message": "Railo kill-switch active"}

    enable_queue = os.getenv("RAILO_ENABLE_QUEUE", "").lower() in {"1", "true", "yes"}
    if not enable_queue:
        return _process_pr_webhook_direct(payload, correlation_id)

    try:
        from core.job_dedup import get_dedup_key, is_already_processing, mark_processing
        import workers.config as _wconfig
        from workers.scan_worker import scan_and_fix_pr
    except Exception:
        # If queue infrastructure not available, fall back to sync path
        return _process_pr_webhook_direct(payload, correlation_id)

    pr = payload.get("pull_request") or {}
    installation = payload.get("installation") or {}
    installation_id = installation.get("id") if installation else None
    owner = payload.get("repository", {}).get("owner", {}).get("login")
    repo_name = payload.get("repository", {}).get("name")
    head_sha = pr.get("head", {}).get("sha") or ""
    pr_number = pr.get("number")

    if not all([owner, repo_name, pr_number, head_sha]):
        return _process_pr_webhook_direct(payload, correlation_id)

    dedup_key = get_dedup_key(owner, repo_name, pr_number, head_sha)
    if is_already_processing(dedup_key):
        return {"status": "skipped_duplicate", "message": "Job already processing"}

    if not mark_processing(dedup_key):
        return {"status": "queued_failed", "message": "Could not mark job"}

    from workers.config import get_retry_strategy as _get_retry  # noqa: PLC0415
    _retry = _get_retry()
    _enqueue_kwargs = {}
    if _retry is not None:
        _enqueue_kwargs["retry"] = _retry

    job = _wconfig.QUEUES["default"].enqueue(
        scan_and_fix_pr,
        payload,
        correlation_id,
        dedup_key=dedup_key,
        job_id=dedup_key,
        **_enqueue_kwargs,
    )

    from core.db import insert_run
    try:
        insert_run(
            installation_id=installation_id or 0,
            repo=f"{owner}/{repo_name}",
            pr_number=pr_number,
            status="queued",
            violations_found=0,
            violations_fixed=0,
            correlation_id=correlation_id,
            job_id=job.id,
            job_status="queued",
        )
    except Exception:
        pass

    return {
        "status": "queued",
        "job_id": job.id,
        "message": "Processing in background queue",
    }
from core.rate_limit import check_rate_limit, get_rate_limit_key, check_dashboard_rate_limit
from core.metrics import record_metric
from core.admin_controls import (
    is_repo_disabled,
    is_force_warn_org,
    get_disabled_rules,
    filter_findings_by_rules,
)
from core.db import (
    init_db,
    upsert_installation,
    remove_installation,
    register_repos,
    deregister_repos,
    get_registered_repos,
    get_all_installations,
    get_runs,
    get_run_by_id,
    get_prior_run_count,
    get_repo_settings,
    upsert_repo_settings,
    get_org_policy,
    upsert_org_policy,
    get_effective_repo_settings,
    get_notification_settings,
    upsert_notification_settings,
    is_delivery_seen,
    mark_delivery_seen,
    get_pending_digest_events,
    get_audit_log,
)
from core.dashboard_auth import (
    get_oauth_authorize_url,
    exchange_code_for_token,
    get_user_info,
    is_oauth_configured,
)
from core.baseline import audit_baseline, BaselineError
from core.sarif_upload import upload_sarif_to_github
from core.trust_contract import (
    DecisionReport,
    filter_supported_files,
    write_safety_report,
)
from core.cache import get_redis_client

load_dotenv()

# Initialize DB on first import
init_db()

app = Flask(__name__, static_folder=Path(__file__).parent / "static")
_session_secret = os.getenv("DASHBOARD_SESSION_SECRET")
if is_oauth_configured() and not _session_secret:
    raise RuntimeError(
        "DASHBOARD_SESSION_SECRET must be set when OAuth is configured. "
        "Generate a strong random value: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = _session_secret or "dev-secret-change-in-production"

# Request size limit (1MB max payload)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024


@app.before_request
def _api_require_auth():
    """Guard all /api/* routes behind GitHub OAuth session.

    Falls through (allows all) when OAuth is not configured so that
    self-hosted operators without OAuth are never locked out.
    Admin routes (/api/admin/*) use X-Admin-Token and are excluded here.
    """
    if not request.path.startswith("/api/"):
        return None
    if request.path.startswith("/api/admin/"):
        return None  # X-Admin-Token handles these
    if not is_oauth_configured():
        return None  # dev / self-hosted without OAuth — open
    if "github_user" not in session:
        return jsonify({"error": "Unauthorized", "login_url": "/dashboard"}), 401
    # Per-user rate limiting on all authenticated dashboard API calls
    user_login = session["github_user"].get("login", "unknown")
    allowed, remaining = check_dashboard_rate_limit(user_login)
    if not allowed:
        return jsonify({"error": "Too Many Requests", "retry_after": 60}), 429
    return None


# Webhook secrets (GitHub App uses app secret, self-hosted uses WEBHOOK_SECRET)
# NOTE: Values are read from the environment at request time via
# `_get_webhook_secrets()` so that tests and runtime secret rotation work
# consistently. These module-level constants are kept only for backwards
# compatibility and should not be relied on for current behaviour.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "") or os.getenv(
    "GITHUB_APP_WEBHOOK_SECRET", ""
)

# Mode: "warn" (comment only) or "enforce" (apply fixes).
# RAILO_MODE is checked first; FIXPOINT_MODE is accepted for backward compatibility.
RAILO_MODE = (os.getenv("RAILO_MODE") or os.getenv("FIXPOINT_MODE", "warn")).lower()
FIXPOINT_MODE = RAILO_MODE  # backward-compat alias — internal code uses RAILO_MODE

# Subprocess timeout (seconds)
GIT_TIMEOUT = int(os.getenv("GIT_TIMEOUT", "120"))

# In-memory idempotency store (Redis preferred when configured)
_processed_fixes: dict[str, bool] = {}
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60


def _idempotency_seen(idempotency_key: str) -> bool:
    redis_client = get_redis_client()
    if redis_client:
        redis_key = f"railo:idempotency:{idempotency_key}"
        try:
            if redis_client.exists(redis_key):
                return True
            redis_client.setex(redis_key, IDEMPOTENCY_TTL_SECONDS, "1")
            return False
        except Exception:
            # Fall back to in-memory idempotency on Redis errors
            pass

    if idempotency_key in _processed_fixes:
        return True
    _processed_fixes[idempotency_key] = True
    return False


def _collect_patch_hunks(repo_path: Path, max_hunks: int = 5, max_lines: int = 60) -> list[str]:
    """Collect top N diff hunks from staged changes for PR comment preview."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "-U3", "--no-color"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return []

    if not result.stdout.strip():
        return []

    hunks: list[str] = []
    file_header: list[str] = []
    current: list[str] = []

    for line in result.stdout.splitlines():
        if line.startswith("diff --git "):
            file_header = [line]
            current = []
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            file_header.append(line)
            continue
        if line.startswith("@@"):
            if current:
                hunks.append("\n".join(current[:max_lines]))
                if len(hunks) >= max_hunks:
                    return hunks
            current = list(file_header) + [line]
            continue
        if current:
            current.append(line)

    if current and len(hunks) < max_hunks:
        hunks.append("\n".join(current[:max_lines]))

    return hunks


def _setup_git_credentials(repo_path: Path) -> None:
    """
    Configure git credential helper to use GITHUB_TOKEN.
    This avoids embedding tokens in URLs (which can leak in logs).
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return
    
    # Use credential helper to provide token
    # This is more secure than embedding in URL
    subprocess.run(
        ["git", "config", "credential.helper", "store"],
        cwd=repo_path,
        check=False,
        timeout=GIT_TIMEOUT,
        capture_output=True,
    )
    
    # Configure the token via environment for this operation
    # Git will use GIT_ASKPASS or credential helper


def clone_or_update_repo(owner: str, repo: str, branch: str, repo_path: Path) -> None:
    """
    Clone repository or update if it exists.
    
    Uses GITHUB_TOKEN via environment variable for authentication,
    NOT embedded in the URL (to prevent token leakage in logs).
    """
    # SECURITY: Use HTTPS URL without embedded token
    repo_url = f"https://github.com/{owner}/{repo}.git"
    
    # Set up environment with token for git operations
    env = os.environ.copy()
    token = os.getenv("GITHUB_TOKEN")
    if token:
        # Use GIT_ASKPASS with a simple script approach or header-based auth
        # For GitHub, we can use the token as password with any username
        env["GIT_TERMINAL_PROMPT"] = "0"
        # Create auth header for HTTPS
        auth_header = f"Authorization: Bearer {token}"
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = auth_header
    
    try:
        if repo_path.exists() and (repo_path / ".git").exists():
            subprocess.run(
                ["git", "fetch", "origin", branch],
                cwd=repo_path,
                check=False,
                timeout=GIT_TIMEOUT,
                capture_output=True,
                env=env,
            )
            subprocess.run(
                ["git", "checkout", branch],
                cwd=repo_path,
                check=False,
                timeout=GIT_TIMEOUT,
                capture_output=True,
                env=env,
            )
            subprocess.run(
                ["git", "pull", "origin", branch],
                cwd=repo_path,
                check=False,
                timeout=GIT_TIMEOUT,
                capture_output=True,
                env=env,
            )
        else:
            subprocess.run(
                ["git", "clone", "--branch", branch, repo_url, str(repo_path)],
                check=True,
                timeout=GIT_TIMEOUT,
                capture_output=True,
                env=env,
            )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Git operation timed out after {GIT_TIMEOUT}s")


def _process_pr_webhook_direct(payload: dict, correlation_id: str) -> dict:
    """Internal synchronous PR processing (used by async worker and fallback)."""
    installation = payload.get("installation", {})
    installation_id = installation.get("id") if installation else None
    import time as _time
    
    action = payload.get("action")
    pr = payload.get("pull_request", {})
    
    # Strict action allowlist
    if action not in ["opened", "synchronize"]:
        log_processing_result(correlation_id, "ignored", f"Action '{action}' not handled")
        return {"status": "ignored", "message": f"Action '{action}' not handled"}
    
    owner = payload.get("repository", {}).get("owner", {}).get("login")
    repo_name = payload.get("repository", {}).get("name")
    full_repo_name = f"{owner}/{repo_name}" if owner and repo_name else ""
    
    # SECURITY: Repository allowlist/denylist check
    is_allowed, reason = is_repo_allowed(full_repo_name)
    if not is_allowed:
        log_processing_result(correlation_id, "denied", reason)
        return {"status": "denied", "message": reason}

    # ADMIN CONTROL: Repository disabled (kill switch)
    is_disabled, disable_reason = is_repo_disabled(full_repo_name)
    if is_disabled:
        log_processing_result(correlation_id, "disabled", disable_reason or "Repo disabled")
        return {"status": "disabled", "message": disable_reason or "Repo disabled"}
    
    base_branch = pr.get("base", {}).get("ref", "main")
    head_branch = pr.get("head", {}).get("ref")
    head_sha = pr.get("head", {}).get("sha")
    pr_number = pr.get("number")
    pr_url = pr.get("html_url")
    pr_author = pr.get("user", {}).get("login", "")
    
    if not all([owner, repo_name, head_branch, pr_number]):
        log_processing_result(correlation_id, "error", "Missing required PR fields")
        return {"status": "error", "message": "Missing required PR fields"}
    
    # FORK PR DETECTION: Auto-downgrade enforce to warn for forks
    head_repo_full_name = pr.get("head", {}).get("repo", {}).get("full_name")
    base_repo_full_name = pr.get("base", {}).get("repo", {}).get("full_name")
    is_fork = head_repo_full_name != base_repo_full_name
    
    # Determine effective mode (downgrade enforce to warn for forks)
    effective_mode = FIXPOINT_MODE
    degraded_reasons: list[str] = []
    if is_fork and FIXPOINT_MODE == "enforce":
        effective_mode = "warn"
        degraded_reasons.append("fork_pr")
        log_processing_result(
            correlation_id,
            "fork_detected",
            "Fork PR detected - downgrading enforce to warn mode (no write access to fork)",
            {"head_repo": head_repo_full_name, "base_repo": base_repo_full_name},
        )

    # ADMIN CONTROL: Force warn-only for org during incidents
    if is_force_warn_org(owner) and effective_mode == "enforce":
        effective_mode = "warn"
        degraded_reasons.append("force_warn_org")
        log_processing_result(
            correlation_id,
            "force_warn_org",
            "Admin control: forcing warn mode for org",
            {"owner": owner},
        )

    # Initialise trust-contract decision report for this run
    decision = DecisionReport(mode_requested=FIXPOINT_MODE, mode_effective=effective_mode)

    # Best-effort permission preflight: can this token comment / create check-runs / push?
    can_comment = None
    can_check_runs = None
    can_push = None
    perm_note = ""
    token = os.getenv("GITHUB_TOKEN") or ""
    if token:
        try:
            from github import Github, Auth  # type: ignore

            gh = Github(auth=Auth.Token(token))
            repo_obj = gh.get_repo(f"{owner}/{repo_name}")
            perms = getattr(repo_obj, "permissions", None)
            if perms is not None:
                can_push = bool(getattr(perms, "push", False) or getattr(perms, "admin", False))
            can_comment = True
            can_check_runs = True
        except Exception as e:  # pragma: no cover - defensive path
            perm_note = f"Permission preflight failed: {e}"
    else:
        perm_note = "No GITHUB_TOKEN available for permission preflight."

    decision.mark_permissions(
        can_comment=can_comment,
        can_check_runs=can_check_runs,
        can_push=can_push,
        note=perm_note,
    )

    # If we definitively know we cannot push, never attempt enforce.
    if can_push is False and effective_mode == "enforce":
        effective_mode = "warn"
        decision.mode_effective = "warn"
        degraded_reasons.append("no_push_permission")
        log_processing_result(
            correlation_id,
            "permissions_downgrade",
            "Token cannot push to this repository; downgrading enforce to warn mode.",
        )
    
    run_start = _time.time()
    fixes_attempted = 0
    fixes_applied = 0
    failure_reason: str | None = None

    def _record_run_metric(status: str, message: str) -> None:
        runtime_seconds = _time.time() - run_start
        record_metric(
            event_type="run_completed",
            repo=full_repo_name,
            pr_number=pr_number,
            violations_found=0,
            violations_fixed=0,
            mode=effective_mode,
            status=status,
            metadata={
                "message": message,
                "runtime_seconds": runtime_seconds,
                "fixes_attempted": fixes_attempted,
                "fixes_applied": fixes_applied,
                "degraded_reasons": list(dict.fromkeys(degraded_reasons)),
                "failure_reason": failure_reason,
            },
            installation_id=installation_id,
            correlation_id=correlation_id,
        )

    # RATE LIMITING: Prevent DDoS on synchronize storms
    rate_limit_key = get_rate_limit_key(owner, repo_name, pr_number)
    is_allowed, remaining = check_rate_limit(rate_limit_key)
    
    if not is_allowed:
        log_processing_result(
            correlation_id,
            "rate_limited",
            f"Rate limit exceeded for PR #{pr_number}",
            {"rate_limit_key": rate_limit_key}
        )
        failure_reason = "rate_limited"
        _record_run_metric("rate_limited", "Rate limit exceeded")
        return {
            "status": "rate_limited",
            "message": "Rate limit exceeded. Please wait before retrying.",
        }
    
    log_processing_result(
        correlation_id,
        "processing",
        f"Processing PR #{pr_number}",
        {"owner": owner, "repo": repo_name, "pr_number": pr_number, "head_sha": head_sha, "rate_limit_remaining": remaining}
    )

    # FIRST-TIME ONBOARDING: Post a welcome comment on the repo's very first scan
    # so developers immediately understand what Railo is doing.
    try:
        if get_prior_run_count(full_repo_name) == 0:
            welcome = generate_welcome_comment(owner, repo_name)
            comment_on_pr(owner, repo_name, pr_number, welcome)
    except Exception:  # best-effort; never block the scan
        pass

    # Create temp directory for repo
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / repo_name
        
        try:
            # Clone/update repo
            clone_or_update_repo(owner, repo_name, head_branch, repo_path)
            
            # SAFETY CHECK 1: Loop prevention - don't process if latest commit is from bot
            if check_loop_prevention(repo_path, head_sha):
                log_processing_result(
                    correlation_id,
                    "skipped",
                    "Latest commit is from Railo bot - skipping to prevent loop"
                )
                failure_reason = "loop_prevention"
                _record_run_metric("skipped", "Loop prevention")
                return {
                    "status": "skipped",
                    "message": "Latest commit is from Railo bot - skipping to prevent loop"
                }
            
            # Load configuration (safety rails, baseline, time budget)
            try:
                config = load_config(repo_path)
            except ConfigError as e:
                msg = f"Invalid Railo config in {e.path.name}:\n- " + "\n- ".join(e.errors)
                create_error_comment(
                    owner,
                    repo_name,
                    pr_number,
                    "invalid_config",
                    msg,
                )
                log_processing_result(
                    correlation_id,
                    "invalid_config",
                    msg,
                )
                failure_reason = "invalid_config"
                _record_run_metric("invalid_config", msg)
                return {"status": "invalid_config", "message": "Invalid .fixpoint.yml"}
            
            # Get changed files in PR with early exit for out-of-scope files
            changed_files = get_pr_diff_files(repo_path, base_branch, head_branch)
            if not changed_files:
                log_processing_result(correlation_id, "no_changes", "No files changed in PR")
                _record_run_metric("no_changes", "No files changed")
                return {"status": "no_changes", "message": "No files changed in PR"}
            
            # Early exit: Filter to supported files - skip unsupported files quickly
            initial_count = len(changed_files)
            target_files = filter_supported_files(changed_files, decision)
            if initial_count > len(target_files):
                log_processing_result(
                    correlation_id,
                    "files_filtered",
                    f"Filtered out {initial_count - len(target_files)} unsupported file(s) (early exit)",
                )
            if not target_files:
                log_processing_result(correlation_id, "no_supported_files", "No supported files changed")
                _record_run_metric("no_supported_files", "No supported files")
                return {"status": "no_supported_files", "message": "No supported files changed"}
            
            # Apply .fixpointignore
            from core.ignore import filter_ignored_files
            target_files = filter_ignored_files(target_files, repo_path)
            if not target_files:
                log_processing_result(correlation_id, "all_ignored", "All files ignored by .fixpointignore")
                _record_run_metric("all_ignored", "All files ignored")
                return {"status": "all_ignored", "message": "All files ignored by .fixpointignore"}
            
            # Scan changed files (rules directory = all Semgrep rules)
            rules_path = Path(__file__).parent.parent / "rules"
            results_path = Path(temp_dir) / "semgrep_results.json"
            
            # Respect overall time budget for webhook processing; if we exceed
            # it, we'll degrade to warn/report-only mode even if enforce was
            # requested.
            import time as _time

            start_time = _time.time()
            max_runtime = float(config.get("max_runtime_seconds", 90) or 90)
            
            # Calculate remaining time budget for Semgrep (leave buffer for post-processing)
            elapsed_so_far = _time.time() - start_time
            remaining_budget = max(1, max_runtime - elapsed_so_far - 10)  # 10s buffer
            
            data = semgrep_scan(
                repo_path,
                rules_path,
                results_path,
                target_files,
                apply_ignore=False,  # Already filtered above
                max_runtime_seconds=int(remaining_budget) if remaining_budget > 0 else None,
            )
            elapsed = _time.time() - start_time
            timed_out = max_runtime > 0 and elapsed > max_runtime
            decision.mark_time_budget(elapsed=elapsed, max_runtime_seconds=max_runtime, timed_out=timed_out)
            if timed_out and effective_mode == "enforce":
                effective_mode = "warn"
                decision.mode_effective = "warn"
                degraded_reasons.append("time_budget")
                log_processing_result(
                    correlation_id,
                    "time_budget_exceeded",
                    f"Time budget exceeded ({elapsed:.1f}s > {max_runtime}s); degrading to warn/report-only mode",
                )

            findings = data.get("results", [])

            # Generate SARIF output for webhook/SaaS deployments as well.
            # The file lives in the temporary workspace for this run; operators
            # can choose to export/archive it if desired.
            try:
                from core.sarif import generate_sarif as _generate_sarif

                sarif = _generate_sarif(findings, repo_path)
                sarif_path = Path(temp_dir) / "fixpoint-results.sarif.json"
                sarif_path.write_text(
                    __import__("json").dumps(sarif, indent=2),
                    encoding="utf-8",
                )
                log_processing_result(
                    correlation_id,
                    "sarif_generated",
                    f"Wrote SARIF results to {sarif_path}",
                )

                # Best-effort upload to GitHub Code Scanning for installation
                # and self-hosted modes.
                if head_sha:
                    try:
                        ref = f"refs/heads/{head_branch}"
                        upload_sarif_to_github(
                            owner,
                            repo_name,
                            sarif_path,
                            head_sha,
                            ref,
                            github_token=os.getenv("GITHUB_TOKEN"),
                        )
                    except Exception as upload_err:
                        log_processing_result(
                            correlation_id,
                            "sarif_upload_error",
                            f"Failed to upload SARIF: {upload_err}",
                        )
            except Exception as sarif_err:
                log_processing_result(
                    correlation_id,
                    "sarif_error",
                    f"Failed to generate SARIF: {sarif_err}",
                )
            
            # Optional baseline filtering: drop findings that already existed
            # at the configured baseline SHA.
            if config.get("baseline_mode"):
                try:
                    findings, audit = audit_baseline(
                        repo_path,
                        findings,
                        config.get("baseline_sha"),
                        config.get("baseline_max_age_days", 0),
                    )
                    decision.mark_baseline(audit)
                    log_processing_result(
                        correlation_id,
                        "baseline_audit",
                        "Baseline audit: "
                        f"baseline_sha={audit.get('baseline_sha')}, "
                        f"filtered_count={audit.get('filtered_count')}, "
                        f"remaining_count={audit.get('remaining_count')}",
                    )
                except BaselineError as baseline_err:
                    msg = f"Baseline mode misconfigured: {baseline_err}"
                    create_error_comment(
                        owner,
                        repo_name,
                        pr_number,
                        "baseline_error",
                        msg,
                    )
                    log_processing_result(
                        correlation_id,
                        "baseline_error",
                        msg,
                    )
                    decision.status = "refused"
                    decision.reasons.append(msg)
                    write_safety_report(repo_path, decision)
                    failure_reason = "baseline_error"
                    _record_run_metric("baseline_error", msg)
                    return {"status": "baseline_error", "message": msg}

            disabled_rules = get_disabled_rules()
            if disabled_rules:
                findings, disabled_count = filter_findings_by_rules(findings, disabled_rules)
                if disabled_count:
                    log_processing_result(
                        correlation_id,
                        "rules_disabled",
                        f"Filtered {disabled_count} finding(s) due to disabled rules",
                        {"disabled_rules": disabled_rules},
                    )
            
            if not findings:
                if head_sha:
                    create_check_run_with_annotations(
                        owner,
                        repo_name,
                        head_sha,
                        [],
                        conclusion="success",
                        pr_url=pr_url,
                    )
                
                decision.status = "no_findings"
                decision.set_summary(
                    violations_found=0,
                    violations_fixed=0,
                    files_touched=0,
                    check_ids=[],
                )
                write_safety_report(repo_path, decision)

                # Record metric
                record_metric(
                    event_type="pr_processed",
                    repo=f"{owner}/{repo_name}",
                    pr_number=pr_number,
                    violations_found=0,
                    violations_fixed=0,
                    mode=FIXPOINT_MODE,
                    status="success",
                    metadata={"message": "No violations found"},
                    installation_id=installation_id,
                    correlation_id=correlation_id,
                )
                _record_run_metric("success", "No violations found")
                
                log_processing_result(correlation_id, "no_findings", "No violations found")
                return {"status": "no_findings", "message": "No violations found"}
            
            # SAFETY CHECK 2: Confidence gating - only fix high-confidence findings
            high_confidence_findings = [f for f in findings if check_confidence_gating(f)]
            if not high_confidence_findings:
                log_processing_result(
                    correlation_id,
                    "low_confidence",
                    "Findings found but confidence too low to auto-fix"
                )
                failure_reason = "low_confidence"
                _record_run_metric("low_confidence", "Confidence too low")
                return {
                    "status": "low_confidence",
                    "message": "Findings found but confidence too low to auto-fix"
                }
            
            # SAFETY CHECK 3: Idempotency - check if we've already fixed this exact issue
            findings_to_process = []
            for finding in high_confidence_findings:
                idempotency_key = compute_fix_idempotency_key(pr_number, head_sha, finding)
                if not _idempotency_seen(idempotency_key):
                    findings_to_process.append(finding)
                else:
                    log_processing_result(
                        correlation_id,
                        "idempotent_skip",
                        f"Already fixed this issue (key: {idempotency_key[:8]}...)",
                        {"file": finding.get("path"), "line": finding.get("start", {}).get("line")}
                    )
            
            if not findings_to_process:
                log_processing_result(correlation_id, "already_fixed", "All findings already fixed")
                _record_run_metric("already_fixed", "All findings already fixed")
                return {"status": "already_fixed", "message": "All findings already fixed"}

            fixes_attempted = len(findings_to_process)
            
            # WARN MODE: Propose fixes without applying (includes fork PRs downgraded from enforce)
            if effective_mode == "warn":
                from patcher.fix_sqli import propose_fix_sqli
                from patcher.fix_secrets import propose_fix_secrets
                from patcher.fix_xss import propose_fix_xss
                from patcher.fix_command_injection import propose_fix_command_injection
                from patcher.fix_path_traversal import propose_fix_path_traversal
                from patcher.fix_javascript import propose_fix_js_eval, propose_fix_js_secrets, propose_fix_js_dom_xss
                
                proposed_fixes = []
                for finding in findings_to_process:
                    file_path = finding.get("path", "")
                    file_path_obj = Path(file_path)
                    if file_path_obj.is_absolute():
                        try:
                            target_relpath = file_path_obj.relative_to(repo_path)
                        except ValueError:
                            target_relpath = file_path_obj.name
                    else:
                        target_relpath = file_path
                    
                    check_id = finding.get("check_id", "").lower()
                    proposal = None
                    
                    # Route by check_id
                    if "sql" in check_id or "sqli" in check_id:
                        proposal = propose_fix_sqli(repo_path, str(target_relpath))
                    elif (
                        "hardcoded" in check_id
                        or "secret" in check_id
                        or "token" in check_id
                        or "key" in check_id
                        or "password" in check_id
                    ):
                        if "javascript" in check_id or "typescript" in check_id:
                            proposals = propose_fix_js_secrets(
                                repo_path, str(target_relpath)
                            )
                            if proposals:
                                proposal = proposals[0]
                        else:
                            proposal = propose_fix_secrets(
                                repo_path, str(target_relpath)
                            )
                    elif (
                        "xss" in check_id
                        or "mark-safe" in check_id
                        or "safe-filter" in check_id
                    ):
                        if "dom-xss" in check_id:
                            proposals = propose_fix_js_dom_xss(
                                repo_path, str(target_relpath)
                            )
                            if proposals:
                                proposal = proposals[0]
                        else:
                            proposal = propose_fix_xss(
                                repo_path, str(target_relpath)
                            )
                    elif (
                        "command-injection" in check_id
                        or "os-system" in check_id
                        or "subprocess" in check_id
                    ):
                        proposals = propose_fix_command_injection(
                            repo_path, str(target_relpath)
                        )
                        if proposals:
                            proposal = proposals[0]
                    elif "path-traversal" in check_id:
                        proposals = propose_fix_path_traversal(
                            repo_path, str(target_relpath)
                        )
                        if proposals:
                            proposal = proposals[0]
                    elif "eval" in check_id:
                        proposals = propose_fix_js_eval(
                            repo_path, str(target_relpath)
                        )
                        if proposals:
                            proposal = proposals[0]
                    
                    if proposal:
                        proposed_fixes.append(proposal)
                
                if proposed_fixes:
                    # Post warn comment with proposals
                    # Add fork notice if this was downgraded from enforce
                    fork_notice = ""
                    if is_fork and FIXPOINT_MODE == "enforce":
                        fork_notice = "\n\n> **Note:** Fork PR detected. Enforce mode is disabled for fork PRs (no write access). Using warn mode instead."

                    decision.status = "report_only"
                    decision.set_summary(
                        violations_found=len(findings_to_process),
                        violations_fixed=0,
                        files_touched=len({f.get("path") for f in findings_to_process}),
                        check_ids=[str(f.get("check_id", "")) for f in findings_to_process],
                    )
                    safety_snippet = decision.to_comment_snippet()

                    comment_url = create_warn_comment(
                        owner,
                        repo_name,
                        pr_number,
                        findings_to_process,
                        proposed_fixes,
                        fork_notice=fork_notice,
                        head_sha=head_sha,
                        safety_snippet=safety_snippet,
                    )
                    write_safety_report(repo_path, decision)
                    
                    if head_sha:
                        create_check_run_with_annotations(
                            owner,
                            repo_name,
                            head_sha,
                            findings_to_process,
                            conclusion="failure",
                            pr_url=pr_url,
                        )
                    
                    # Record metric
                    record_metric(
                        event_type="pr_processed",
                        repo=f"{owner}/{repo_name}",
                        pr_number=pr_number,
                        violations_found=len(findings_to_process),
                        violations_fixed=0,
                        mode="warn",
                        status="warn_mode",
                        metadata={"comment_url": comment_url, "proposed_fixes": len(proposed_fixes)},
                        installation_id=installation_id,
                        correlation_id=correlation_id,
                    )
                    
                    log_processing_result(
                        correlation_id,
                        "warn_mode",
                        f"Proposed fixes for {len(findings_to_process)} violations (warn mode)",
                        {"comment_url": comment_url, "proposed_fixes": len(proposed_fixes)}
                    )
                    _record_run_metric("warn_mode", "Proposed fixes (warn mode)")
                    
                    return {
                        "status": "warn_mode",
                        "message": f"Proposed fixes for {len(findings_to_process)} violations (warn mode - no changes applied)",
                        "findings_count": len(findings_to_process),
                        "comment_url": comment_url,
                    }
                else:
                    log_processing_result(correlation_id, "no_fixes", "No fixes to propose")
                    failure_reason = "no_fixes"
                    _record_run_metric("no_fixes", "No fixes to propose")
                    return {"status": "no_fixes", "message": "No fixes to propose"}
            
            # ENFORCE MODE: Two-phase apply (plan -> validate -> apply)
            # Phase 1: plan and validate fixes using guardrails
            plan = generate_patch_plan(repo_path, findings_to_process, rules_path)
            ok_plan, reasons = validate_patch_plan(plan, config)
            if not ok_plan:
                # Guardrails blocked auto-fix; fall back to warn-like behaviour
                msg = "Enforce mode guardrails blocked auto-fix. Reasons:\\n- " + "\\n- ".join(reasons)
                create_error_comment(
                    owner,
                    repo_name,
                    pr_number,
                    "enforce_guardrails_blocked",
                    msg,
                )
                if head_sha:
                    create_check_run_with_annotations(
                        owner,
                        repo_name,
                        head_sha,
                        findings_to_process,
                        conclusion="failure",
                        pr_url=pr_url,
                    )
                decision.mark_policy(ok=False, reasons=reasons)
                decision.status = "refused"
                write_safety_report(repo_path, decision)
                log_processing_result(
                    correlation_id,
                    "enforce_guardrails_blocked",
                    msg,
                    {"reasons": reasons},
                )
                failure_reason = "guardrails_blocked"
                _record_run_metric("enforce_guardrails_blocked", "Guardrails blocked auto-fix")
                return {
                    "status": "enforce_guardrails_blocked",
                    "message": "Enforce mode guardrails blocked auto-fix",
                }

            # Phase 2: Apply fixes
            any_changes, processed = process_findings(
                repo_path, findings_to_process, rules_path, config, decision_report=decision
            )
            
            if not any_changes:
                log_processing_result(correlation_id, "no_fixes", "No fixes applied")
                decision.status = "report_only"
                decision.set_summary(
                    violations_found=len(findings_to_process),
                    violations_fixed=0,
                    files_touched=0,
                    check_ids=[str(f.get("check_id", "")) for f in findings_to_process],
                )
                write_safety_report(repo_path, decision)
                if head_sha:
                    create_check_run_with_annotations(
                        owner,
                        repo_name,
                        head_sha,
                        findings_to_process,
                        conclusion="failure",
                        pr_url=pr_url,
                    )
                failure_reason = "no_fixes"
                _record_run_metric("no_fixes", "No fixes applied")
                return {"status": "no_fixes", "message": "No fixes applied"}
            
            # Setup git identity before committing
            setup_git_identity(repo_path)
            
            # Stage changes for safety checks
            subprocess.run(
                ["git", "add", "."],
                cwd=repo_path,
                check=False,
                timeout=GIT_TIMEOUT,
                capture_output=True,
            )
            
            # SAFETY RAIL: Max-diff threshold (line-based)
            ok, added, removed = check_max_diff_lines(repo_path, config["max_diff_lines"])
            if not ok:
                total = added + removed
                create_error_comment(
                    owner,
                    repo_name,
                    pr_number,
                    "max_diff_exceeded",
                    f"Diff too large ({total} lines, max {config['max_diff_lines']}). "
                    "Railo will not auto-commit. Apply fixes manually or increase max_diff_lines.",
                )
                if head_sha:
                    create_check_run_with_annotations(
                        owner,
                        repo_name,
                        head_sha,
                        findings_to_process,
                        conclusion="failure",
                        pr_url=pr_url,
                    )
                log_processing_result(
                    correlation_id,
                    "max_diff_exceeded",
                    f"Diff {total} lines exceeds max {config['max_diff_lines']}",
                )
                failure_reason = "max_diff_exceeded"
                _record_run_metric("max_diff_exceeded", "Diff too large")
                return {
                    "status": "max_diff_exceeded",
                    "message": f"Diff too large ({total} lines)",
                }
            
            # SAFETY RAIL: Diff quality check - ensure minimal, focused patches
            quality_result = analyze_diff_quality(repo_path)
            if not quality_result.get("is_minimal", False):
                score = quality_result.get("quality_score", 0.0)
                issues = quality_result.get("issues", [])
                issues_text = "\n- ".join(issues) if issues else "Unknown quality issues"
                create_error_comment(
                    owner,
                    repo_name,
                    pr_number,
                    "diff_quality_failed",
                    f"Diff quality check failed (score: {score:.2f}). "
                    f"Patch quality issues:\n- {issues_text}\n\n"
                    "Patches must be minimal and focused on security fixes only.",
                )
                if head_sha:
                    create_check_run_with_annotations(
                        owner,
                        repo_name,
                        head_sha,
                        findings_to_process,
                        conclusion="failure",
                        pr_url=pr_url,
                    )
                log_processing_result(
                    correlation_id,
                    "diff_quality_failed",
                    f"Diff quality score {score:.2f} below threshold",
                    {"issues": issues},
                )
                failure_reason = "diff_quality_failed"
                _record_run_metric("diff_quality_failed", "Diff quality failed")
                return {
                    "status": "diff_quality_failed",
                    "message": f"Diff quality check failed (score: {score:.2f})",
                }
            
            # Create separate fix PR instead of pushing to the contributor branch
            try:
                fixes_applied = len([p for p in processed if p.get("fixed")])
                success, fix_info = create_fix_pr(
                    findings=findings_to_process,
                    owner=owner,
                    repo_name=repo_name,
                    original_pr_number=pr_number,
                    original_pr_author=pr_author,
                    original_pr_url=pr_url or "",
                    base_branch=base_branch,
                    repo_path=repo_path,
                )

                if not success:
                    create_error_comment(
                        owner,
                        repo_name,
                        pr_number,
                        "fix_pr_failed",
                        f"Railo could not create a fix PR: {fix_info.get('error', 'unknown error')}",
                    )
                    if head_sha:
                        create_check_run_with_annotations(
                            owner,
                            repo_name,
                            head_sha,
                            findings_to_process,
                            conclusion="failure",
                            pr_url=pr_url,
                        )
                    log_processing_result(
                        correlation_id,
                        "fix_pr_failed",
                        "Fix PR creation failed",
                        {"error": (fix_info.get("error", "") or "")[:200]},
                    )
                    failure_reason = "fix_pr_failed"
                    _record_run_metric("fix_pr_failed", "Fix PR creation failed")
                    return {
                        "status": "fix_pr_failed",
                        "message": "Fix PR creation failed",
                    }

                decision.status = "fixed"
                decision.set_summary(
                    violations_found=len(findings_to_process),
                    violations_fixed=fixes_applied,
                    files_touched=len(set([p.get("file") for p in processed if p.get("fixed")])),
                    check_ids=[str(f.get("check_id", "")) for f in findings_to_process],
                )
                write_safety_report(repo_path, decision)

                from core.vuln_classify import classify_findings  # noqa: PLC0415
                vuln_types: list[str] = classify_findings(findings_to_process)

                notification = generate_fix_pr_notification(
                    fix_pr_number=int(fix_info.get("fix_pr_number", 0) or 0),
                    fix_pr_url=str(fix_info.get("fix_pr_url", "")),
                    safety_score=float(fix_info.get("safety_score", 0.0) or 0.0),
                    vuln_count=len(findings_to_process),
                    vuln_types=vuln_types,
                    findings=findings_to_process,
                )

                comment_on_pr(owner, repo_name, pr_number, notification)

                add_pr_labels(
                    owner,
                    repo_name,
                    pr_number,
                    ["railo-needs-fix", "security"] + sorted(set(vuln_types)),
                )

                if head_sha:
                    create_check_run_with_annotations(
                        owner,
                        repo_name,
                        head_sha,
                        findings_to_process,
                        conclusion="neutral",
                        pr_url=pr_url,
                    )

                record_metric(
                    event_type="fix_applied",
                    repo=f"{owner}/{repo_name}",
                    pr_number=pr_number,
                    violations_found=len(findings_to_process),
                    violations_fixed=fixes_applied,
                    mode="enforce",
                    status="success",
                    metadata={
                        "fix_pr_url": fix_info.get("fix_pr_url"),
                        "fix_pr_number": fix_info.get("fix_pr_number"),
                        "branch_name": fix_info.get("branch_name"),
                    },
                    installation_id=installation_id,
                    correlation_id=correlation_id,
                    vuln_types=vuln_types,
                )

                log_fix_applied(
                    correlation_id,
                    pr_number,
                    [p.get("file") for p in processed if p.get("fixed")],
                    len(findings_to_process),
                )
                log_processing_result(
                    correlation_id,
                    "success",
                    "Created fix PR instead of patching contributor branch",
                    fix_info,
                )
                _record_run_metric("success", "Created fix PR")

                return {
                    "status": "success",
                    "message": "Created fix PR",
                    "fix_pr_url": fix_info.get("fix_pr_url"),
                    "fix_pr_number": fix_info.get("fix_pr_number"),
                }
            except subprocess.CalledProcessError as e:
                # Handle branch protection or permission errors gracefully
                error_msg = str(e)
                create_error_comment(
                    owner,
                    repo_name,
                    pr_number,
                    "branch_protection",
                    "Cannot push to protected branch. Please apply fix manually or adjust branch protection.",
                )
                log_processing_result(
                    correlation_id,
                    "error",
                    "Branch protection or permission error",
                    {"error": error_msg}
                )
                failure_reason = "branch_protection"
                _record_run_metric("error", "Branch protection or permission error")
                return {
                    "status": "error",
                    "message": "Branch protection or permission error - comment posted to PR",
                }
        
        except Exception as e:
            log_processing_result(correlation_id, "error", str(e), {"exception_type": type(e).__name__})
            failure_reason = "exception"
            _record_run_metric("error", str(e))
            return {"status": "error", "message": str(e)}


def _get_webhook_secrets() -> list[str]:
    """Build list of secrets to try: app secret first, then repo secret (dual mode).

    Secrets are read from environment on each call so that tests can override
    them and production can rotate them without restarting the process.

    Secret resolution order (highest priority first):
    1. Azure Key Vault (when AZURE_KEY_VAULT_URL is configured in env).
    2. GITHUB_WEBHOOK_SECRET / GITHUB_APP_WEBHOOK_SECRET env vars.
    3. WEBHOOK_SECRET env var (legacy self-hosted path).
    """
    secrets: list[str] = []

    # 1) Azure Key Vault (production — most secure; cached in-process)
    try:
        from core.github_app_auth import get_webhook_secret_from_kv  # noqa: PLC0415
        kv_secret = get_webhook_secret_from_kv()
        if kv_secret:
            secrets.append(kv_secret)
    except Exception:
        pass

    app_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "") or os.getenv(
        "GITHUB_APP_WEBHOOK_SECRET", ""
    )
    repo_secret = os.getenv("WEBHOOK_SECRET", "")
    if app_secret:
        secrets.append(app_secret)
    if repo_secret:
        secrets.append(repo_secret)
    return secrets


def _inject_installation_token_if_app(payload: dict) -> None:
    """
    For GitHub App webhooks: get installation token and set GITHUB_TOKEN.
    Enables existing pipeline (clone, comment, status) to work without changes.
    """
    installation = payload.get("installation")
    if not installation or not is_github_app_configured():
        return
    ok_inst, inst_id, _ = validate_installation_id(installation)
    if not ok_inst or not inst_id:
        return
    token = get_installation_access_token(inst_id)
    if token:
        os.environ["GITHUB_TOKEN"] = token


@app.route("/webhook", methods=["POST"])
def webhook_handler():
    """Handle GitHub webhook POST requests with full security validation."""
    # Get headers
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    # Kill-switch: refuse all new work immediately
    if os.getenv("RAILO_KILL_SWITCH", "").lower() in {"1", "true", "yes"}:
        return jsonify({"status": "kill_switch", "message": "Railo kill-switch active — event not processed"}), 503

    # Delivery-ID idempotency: ignore exact retries from GitHub
    if delivery_id and is_delivery_seen(delivery_id):
        return jsonify({"status": "duplicate", "message": "Delivery already processed"}), 200
    if delivery_id:
        try:
            mark_delivery_seen(delivery_id)
        except Exception:
            pass

    payload_body = request.data

    # Build secrets: app secret + repo secret (try both for dual mode)
    secrets = _get_webhook_secrets()
    
    # SECURITY: Comprehensive validation
    is_valid, error_msg = validate_webhook_request(
        payload_body,
        signature,
        event_type,
        delivery_id,
        # Fallback for local/dev when no secrets are configured.
        secrets if secrets else os.getenv("WEBHOOK_SECRET", "") or "",
    )
    
    if not is_valid:
        return jsonify({"error": error_msg}), 401
    
    # Parse payload
    try:
        payload = json.loads(payload_body)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    # Get correlation ID from delivery ID
    correlation_id = delivery_id or f"webhook-{os.urandom(4).hex()}"
    
    # Log webhook event
    action = payload.get("action", "")
    owner_raw = payload.get("repository", {}).get("owner", {}).get("login", "")
    repo_raw = payload.get("repository", {}).get("name", "")
    pr_number = payload.get("pull_request", {}).get("number")

    # Installation events don't carry a repository field; skip sanitization.
    _installation_event = event_type in ("installation", "installation_repositories", "github_app_authorization")
    if _installation_event:
        owner = owner_raw or ""
        repo = repo_raw or ""
    else:
        # SECURITY: Sanitize repository owner/name from payload before use
        ok_owner, owner_or_error = sanitize_repo_owner(owner_raw)
        if not ok_owner:
            log_webhook_event(event_type, action, owner_raw or "", repo_raw or "", pr_number, correlation_id)
            return jsonify({"error": owner_or_error or "Invalid repository owner"}), 400

        ok_repo, repo_or_error = sanitize_repo_name(repo_raw)
        if not ok_repo:
            log_webhook_event(event_type, action, owner_raw or "", repo_raw or "", pr_number, correlation_id)
            return jsonify({"error": repo_or_error or "Invalid repository name"}), 400

        owner = owner_or_error
        repo = repo_or_error

    log_webhook_event(event_type, action, owner, repo, pr_number, correlation_id)
    
    # GitHub App: inject installation token before processing
    _inject_installation_token_if_app(payload)
    
    # Process based on event type
    if event_type == "installation":
        inst = payload.get("installation", {})
        ok_inst, inst_id, inst_error = validate_installation_id(inst)
        account = inst.get("account", {}) or {}
        if not ok_inst:
            log_processing_result(
                correlation_id,
                "invalid_installation",
                inst_error or "Invalid installation payload",
                {"raw_id": inst.get("id")},
            )
            return jsonify({"error": inst_error or "Invalid installation payload"}), 400
        if action == "deleted":
            # GitHub App was uninstalled — remove the installation record and
            # deactivate all repos (handled inside remove_installation).
            remove_installation(installation_id=inst_id)
            log_processing_result(
                correlation_id,
                "installation_deleted",
                f"Installation {inst_id} removed (uninstall)",
                {"installation_id": inst_id},
            )
            return jsonify({"status": "ok", "message": "Installation removed"}), 200
        if account:
            upsert_installation(
                installation_id=inst_id,
                account_login=account.get("login", "unknown"),
                account_type=account.get("type", "User"),
            )
        # GitHub sends a ``repositories`` array on the initial install event;
        # register those repos so they appear in the dashboard immediately.
        initial_repos = payload.get("repositories", [])
        if initial_repos:
            register_repos(inst_id, initial_repos)
        log_processing_result(
            correlation_id,
            "installation_event",
            f"Installation {action} ({len(initial_repos)} repo(s) registered)",
            {"installation_id": inst_id, "repos_registered": len(initial_repos)},
        )
        return jsonify({"status": "ok", "message": f"Installation {action}"}), 200
    
    if event_type == "installation_repositories":
        inst = payload.get("installation", {})
        ok_inst, inst_id, inst_error = validate_installation_id(inst)
        account = inst.get("account", {}) or {}
        if not ok_inst:
            log_processing_result(
                correlation_id,
                "invalid_installation",
                inst_error or "Invalid installation payload",
                {"raw_id": inst.get("id")},
            )
            return jsonify({"error": inst_error or "Invalid installation payload"}), 400
        if account:
            upsert_installation(
                installation_id=inst_id,
                account_login=account.get("login", "unknown"),
                account_type=account.get("type", "User"),
            )
        # Register/deregister individual repos
        repos_added = payload.get("repositories_added", [])
        repos_removed = payload.get("repositories_removed", [])
        if repos_added:
            register_repos(inst_id, repos_added)
        if repos_removed:
            deregister_repos(inst_id, repos_removed)
        log_processing_result(
            correlation_id,
            "installation_repositories_event",
            f"Repositories {action}: +{len(repos_added)} -{len(repos_removed)}",
            {
                "installation_id": inst_id,
                "added": len(repos_added),
                "removed": len(repos_removed),
            },
        )
        return jsonify({
            "status": "ok",
            "added": len(repos_added),
            "removed": len(repos_removed),
        }), 200
    
    if event_type == "pull_request":
        # Additional action validation
        if not is_allowed_pr_action(action):
            log_processing_result(
                correlation_id,
                "ignored",
                f"PR action '{action}' not allowed"
            )
            return jsonify({
                "status": "ignored",
                "message": f"PR action '{action}' not allowed"
            }), 200
        
        with CorrelationContext(correlation_id):
            result = process_pr_webhook(payload, correlation_id)

        status_code = 202 if result.get("status") == "queued" else 200
        return jsonify(result), status_code
    
    return jsonify({
        "status": "ignored",
        "message": f"Event type '{event_type}' not handled"
    }), 200


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint — verifies DB and Redis connectivity."""
    checks: dict = {}

    # Database check
    try:
        from core.db import get_connection  # noqa: PLC0415
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"

    # Redis check (optional — absence is not fatal for webhook-only deployments)
    try:
        redis = get_redis_client()
        if redis is not None:
            redis.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_configured"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    degraded = any(v.startswith("error") for v in checks.values())
    status_code = 503 if degraded else 200
    return jsonify({"status": "degraded" if degraded else "healthy", **checks}), status_code


@app.route("/metrics", methods=["GET"])
def prometheus_metrics():
    """Prometheus text-format scrape endpoint.

    Exposes four ops metrics:
      * ``railo_runs_per_hour``        — runs started in the last 60 min
      * ``railo_failed_runs_total``    — failed/errored runs in the last 24 h
      * ``railo_reverts_total``        — CI-failure reverts pushed in last 24 h
      * ``railo_worker_queue_depth``   — pending jobs per RQ queue
    """
    runs_per_hour = get_runs_per_hour()
    failed_runs = get_failed_runs_total(hours=24)
    reverts = get_reverts_total(hours=24)
    queue_depths = get_queue_depths()

    lines = [
        "# HELP railo_runs_per_hour Processing runs started in the last 60 minutes",
        "# TYPE railo_runs_per_hour gauge",
        f"railo_runs_per_hour {runs_per_hour}",
        "",
        "# HELP railo_failed_runs_total Runs that ended in error or failed state in the last 24 hours",
        "# TYPE railo_failed_runs_total gauge",
        f"railo_failed_runs_total {failed_runs}",
        "",
        "# HELP railo_reverts_total Revert commits pushed after CI failure in the last 24 hours",
        "# TYPE railo_reverts_total gauge",
        f"railo_reverts_total {reverts}",
    ]

    if queue_depths:
        lines += [
            "",
            "# HELP railo_worker_queue_depth Number of pending jobs waiting in the worker queue",
            "# TYPE railo_worker_queue_depth gauge",
        ]
        for queue_name, depth in sorted(queue_depths.items()):
            lines.append(f'railo_worker_queue_depth{{queue="{queue_name}"}} {depth}')

    lines.append("")  # trailing newline
    body = "\n".join(lines)
    return body, 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}


@app.route("/api/metrics/health", methods=["GET"])
def api_metrics_health():
    """JSON snapshot of the same ops metrics exposed at /metrics.

    Useful for simple health dashboards or alerting scripts that do not
    speak the Prometheus scrape protocol.
    """
    return jsonify({
        "runs_per_hour": get_runs_per_hour(),
        "failed_runs_24h": get_failed_runs_total(hours=24),
        "reverts_24h": get_reverts_total(hours=24),
        "worker_queue_depth": get_queue_depths(),
    })


# --- JSON API for frontend dashboard ---


@app.route("/api/analytics/summary", methods=["GET"])
def api_analytics_summary():
    installation_ids = _dashboard_installed_ids()
    runs = get_runs(installation_ids, limit=500)
    total_runs = len(runs)
    succeeded_runs = sum(1 for r in runs if r.get("status") == "success")
    failed_runs = sum(1 for r in runs if r.get("status") not in {"success", "warn", "ignored"})
    durations = [r.get("runtime_seconds") for r in runs if r.get("runtime_seconds") is not None]
    avg_duration_seconds = sum(durations) / len(durations) if durations else 0.0

    summary = {
        "total_runs": total_runs,
        "succeeded_runs": succeeded_runs,
        "failed_runs": failed_runs,
        "avg_duration_seconds": avg_duration_seconds,
        "fix_merge_rate": get_fix_merge_rate(installation_ids),
        "ci_success_rate": get_ci_success_rate(installation_ids),
        # North-star counts
        "fix_prs_created": get_fix_prs_created(installation_ids),
        "fix_prs_merged": get_fix_prs_merged(installation_ids),
    }
    return jsonify(summary)


@app.route("/api/analytics/timeseries", methods=["GET"])
def api_analytics_timeseries():
    installation_ids = _dashboard_installed_ids()
    days = int(request.args.get("days", 30))
    data = get_run_timeseries(installation_ids, days=days)
    return jsonify({"data": data})


@app.route("/api/analytics/vulnerabilities", methods=["GET"])
def api_analytics_vulnerabilities():
    installation_ids = _dashboard_installed_ids()
    data = get_vulnerability_breakdown(installation_ids)
    return jsonify({"data": data})


@app.route("/api/dashboard/dry-run-stats", methods=["GET"])
def api_dashboard_dry_run_stats():
    """Return would_have_auto_merged counts (Tier A dry-run auto-merge metric)."""
    installation_ids = _dashboard_installed_ids()
    return jsonify(get_dry_run_stats(installation_ids))


@app.route("/api/runs/<int:run_id>", methods=["GET"])
def api_run_detail(run_id: int):
    """Return detailed information for a single run by its database ID."""
    import json as _json
    row = get_run_by_id(run_id)
    if row is None:
        return jsonify({"error": "Run not found"}), 404
    # Deserialise vuln_types JSON string stored in the DB
    vuln_types_raw = row.get("vuln_types")
    if isinstance(vuln_types_raw, str):
        try:
            row["vuln_types"] = _json.loads(vuln_types_raw)
        except (ValueError, TypeError):
            row["vuln_types"] = []
    elif vuln_types_raw is None:
        row["vuln_types"] = []
    repo = row.get("repo") or ""
    repo_owner, repo_name = (repo.split("/", 1) + [""])[:2]
    return jsonify({
        "id": row.get("id"),
        "repo": repo,
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "pr_number": row.get("pr_number"),
        "status": row.get("status"),
        "job_status": row.get("job_status"),
        "violations_found": row.get("violations_found", 0),
        "violations_fixed": row.get("violations_fixed", 0),
        "vuln_types": row.get("vuln_types", []),
        "fix_pr_number": row.get("fix_pr_number"),
        "fix_pr_url": row.get("fix_pr_url"),
        "ci_passed": row.get("ci_passed"),
        "runtime_seconds": row.get("runtime_seconds"),
        "timestamp": row.get("timestamp"),
        "correlation_id": row.get("correlation_id"),
    })


@app.route("/api/runs", methods=["GET"])
def api_runs():
    installation_ids = _dashboard_installed_ids()
    limit = int(request.args.get("limit", 100))
    runs = get_runs(installation_ids, limit=limit)
    formatted = []
    for r in runs:
        repo = r.get("repo") or ""
        repo_owner, repo_name = (repo.split("/", 1) + [""])[:2]
        import json as _json
        vuln_types_raw = r.get("vuln_types")
        if isinstance(vuln_types_raw, str):
            try:
                vuln_types_parsed = _json.loads(vuln_types_raw)
            except (ValueError, TypeError):
                vuln_types_parsed = []
        else:
            vuln_types_parsed = vuln_types_raw or []
        formatted.append(
            {
                "id": r.get("id"),
                "repo": repo,
                "repo_owner": repo_owner,
                "repo_name": repo_name,
                "pr_number": r.get("pr_number"),
                "status": r.get("status"),
                "job_status": r.get("job_status"),
                "violations_found": r.get("violations_found", 0),
                "violations_fixed": r.get("violations_fixed", 0),
                "vuln_types": vuln_types_parsed,
                "fix_pr_number": r.get("fix_pr_number"),
                "fix_pr_url": r.get("fix_pr_url"),
                "ci_passed": r.get("ci_passed"),
                "runtime_seconds": r.get("runtime_seconds"),
                "timestamp": r.get("timestamp"),
            }
        )
    return jsonify({"runs": formatted})


@app.route("/api/audit-log", methods=["GET"])
def api_audit_log():
    """
    Return recent audit log entries, optionally filtered by repo, action, and time range.

    Query params:
      - repo:   Filter to a specific repo (``owner/repo`` format).
      - action: Filter to a specific action (e.g. ``fix_applied``).
      - since:  ISO-8601 lower-bound timestamp (inclusive).
      - limit:  Max rows (default 200, max 1000).
    """
    repo = request.args.get("repo") or None
    action = request.args.get("action") or None
    since = request.args.get("since") or None
    try:
        limit = min(int(request.args.get("limit", 200)), 1000)
    except (ValueError, TypeError):
        limit = 200

    rows = get_audit_log(repo=repo, action=action, limit=limit, since=since)
    return jsonify({"audit_log": rows, "count": len(rows)})


@app.route("/api/repos", methods=["GET"])
def api_repos():
    installations = get_all_installations()
    inst_ids = [i["installation_id"] for i in installations]
    reg_repos = get_registered_repos(installation_ids=inst_ids if inst_ids else None)
    repos = []
    for r in reg_repos:
        full_name = r["repo_full_name"]
        owner, _, name = full_name.partition("/")
        settings = get_repo_settings(full_name) or {}
        repos.append({
            "id": full_name,
            "repo": full_name,
            "repo_owner": owner,
            "repo_name": name or full_name,
            "installation_id": r["installation_id"],
            "account_login": r.get("account_login", owner),
            "active": bool(r["active"]),
            "added_at": r["added_at"],
            "mode": settings.get("mode", "warn"),
            "enabled": bool(settings.get("enabled", True)),
        })
    return jsonify({"repos": repos})


@app.route("/api/user/settings", methods=["GET"])
def api_user_settings():
    prefs = session.get("user_prefs", {})
    return jsonify({
        "theme": prefs.get("theme", "dark"),
        "notifications_enabled": prefs.get("notifications_enabled", True),
        "role": "admin",
    })


@app.route("/api/user/settings", methods=["PUT"])
def api_update_user_settings():
    data = request.get_json(silent=True) or {}
    prefs = session.get("user_prefs", {})
    if "notifications_enabled" in data:
        prefs["notifications_enabled"] = bool(data["notifications_enabled"])
    if "theme" in data:
        prefs["theme"] = str(data["theme"])
    session["user_prefs"] = prefs
    return jsonify({"status": "ok", **prefs})


@app.route("/api/repos/<path:repo_id>/settings", methods=["GET"])
def api_get_repo_settings(repo_id: str):
    row = get_repo_settings(repo_id)
    if row:
        return jsonify({
            "repo": row["repo"],
            "enabled": bool(row.get("enabled", 1)),
            "mode": row.get("mode", "warn"),
            "max_diff_lines": row.get("max_diff_lines", 500),
            "max_runtime_seconds": row.get("max_runtime_seconds", 120),
            "ignore_file": row.get("ignore_file", ""),
            "auto_merge_enabled": bool(row.get("auto_merge_enabled", 0)),
            "permission_tier": row.get("permission_tier", "A"),
        })
    return jsonify({
        "repo": repo_id,
        "enabled": True,
        "mode": "warn",
        "max_diff_lines": 500,
        "max_runtime_seconds": 120,
        "ignore_file": "",
        "auto_merge_enabled": False,
        "permission_tier": "A",
    })


@app.route("/api/repos/<path:repo_id>/settings", methods=["PUT"])
def api_put_repo_settings(repo_id: str):
    data = request.get_json(force=True, silent=True) or {}
    upsert_repo_settings(
        repo=repo_id,
        enabled=bool(data.get("enabled", True)),
        mode=str(data.get("mode", "warn")),
        max_diff_lines=int(data.get("max_diff_lines", 500)),
        max_runtime_seconds=int(data.get("max_runtime_seconds", 120)),
        ignore_file=str(data.get("ignore_file", "")),
        auto_merge_enabled=bool(data.get("auto_merge_enabled", False)),
        permission_tier=str(data.get("permission_tier", "A")),
    )
    return jsonify({"status": "ok"})


@app.route("/api/repos/<path:repo_id>/effective-settings", methods=["GET"])
def api_get_effective_repo_settings(repo_id: str):
    """Return the merged effective settings for a repo (org defaults + repo overrides)."""
    return jsonify(get_effective_repo_settings(repo_id))


# --- Org-level policy defaults ---

@app.route("/api/orgs/<string:login>/settings", methods=["GET"])
def api_get_org_settings(login: str):
    """Return the org-level policy for *login*, or application defaults if not set."""
    row = get_org_policy(login)
    if row:
        return jsonify({
            "account_login": row["account_login"],
            "enabled": bool(row.get("enabled", 1)),
            "mode": row.get("mode", "warn"),
            "max_diff_lines": row.get("max_diff_lines", 500),
            "max_runtime_seconds": row.get("max_runtime_seconds", 120),
            "ignore_file": row.get("ignore_file", ""),
            "auto_merge_enabled": bool(row.get("auto_merge_enabled", 0)),
            "permission_tier": row.get("permission_tier", "A"),
        })
    return jsonify({
        "account_login": login,
        "enabled": True,
        "mode": "warn",
        "max_diff_lines": 500,
        "max_runtime_seconds": 120,
        "ignore_file": "",
        "auto_merge_enabled": False,
        "permission_tier": "A",
    })


@app.route("/api/orgs/<string:login>/settings", methods=["PUT"])
def api_put_org_settings(login: str):
    """Create or update the org-level policy for *login*."""
    data = request.get_json(force=True, silent=True) or {}
    upsert_org_policy(
        account_login=login,
        enabled=bool(data.get("enabled", True)),
        mode=str(data.get("mode", "warn")),
        max_diff_lines=int(data.get("max_diff_lines", 500)),
        max_runtime_seconds=int(data.get("max_runtime_seconds", 120)),
        ignore_file=str(data.get("ignore_file", "")),
        auto_merge_enabled=bool(data.get("auto_merge_enabled", False)),
        permission_tier=str(data.get("permission_tier", "A")),
    )
    return jsonify({"status": "ok"})


# --- Notification settings ---

@app.route("/api/installations/<int:install_id>/notifications", methods=["GET"])
def api_get_notification_settings(install_id: int):
    """Return notification settings for an installation (all defaults OFF)."""
    row = get_notification_settings(install_id)
    if row:
        return jsonify({
            "installation_id": row["installation_id"],
            "slack_webhook_url": row.get("slack_webhook_url", ""),
            "email": row.get("email", ""),
            "notify_on_fix_applied": bool(row.get("notify_on_fix_applied", 0)),
            "notify_on_ci_failure": bool(row.get("notify_on_ci_failure", 0)),
            "notify_on_ci_success": bool(row.get("notify_on_ci_success", 0)),
            "notify_on_revert": bool(row.get("notify_on_revert", 0)),
            "digest_mode": bool(row.get("digest_mode", 0)),
        })
    return jsonify({
        "installation_id": install_id,
        "slack_webhook_url": "",
        "email": "",
        "notify_on_fix_applied": False,
        "notify_on_ci_failure": False,
        "notify_on_ci_success": False,
        "notify_on_revert": False,
        "digest_mode": False,
    })


@app.route("/api/installations/<int:install_id>/notifications", methods=["PUT"])
def api_put_notification_settings(install_id: int):
    """Create or update notification settings for an installation."""
    data = request.get_json(force=True, silent=True) or {}
    upsert_notification_settings(
        installation_id=install_id,
        slack_webhook_url=str(data.get("slack_webhook_url", "")),
        email=str(data.get("email", "")),
        notify_on_fix_applied=bool(data.get("notify_on_fix_applied", False)),
        notify_on_ci_failure=bool(data.get("notify_on_ci_failure", False)),
        notify_on_ci_success=bool(data.get("notify_on_ci_success", False)),
        notify_on_revert=bool(data.get("notify_on_revert", False)),
        digest_mode=bool(data.get("digest_mode", False)),
    )
    return jsonify({"status": "ok"})


@app.route("/api/installations/<int:install_id>/notifications/digest", methods=["POST"])
def api_flush_digest(install_id: int):
    """
    Flush the digest queue for an installation.

    Collects all pending notification_log entries from the last 24 hours,
    sends a single Slack/email summary, and returns the digest content.
    """
    admin_token = os.getenv("RAILO_ADMIN_TOKEN", "")
    if admin_token and request.headers.get("X-Admin-Token", "") != admin_token:
        return jsonify({"error": "Forbidden"}), 403

    row = get_notification_settings(install_id)
    if not row:
        return jsonify({"status": "no_settings", "events": []}), 200
    events = get_pending_digest_events(install_id)
    if not events:
        return jsonify({"status": "empty", "events": []}), 200
    try:
        from core.notifications import _send_slack, _send_email  # noqa: PLC0415
        lines = [f"*[Railo] Daily digest — {len(events)} event type(s)*"]
        for e in events:
            lines.append(f"• {e['repo']} — {e['event']} × {e['cnt']} (last: {e['last_at'][:10]})")
        body = "\n".join(lines)
        slack_url = row.get("slack_webhook_url", "")
        if slack_url:
            _send_slack(slack_url, body)
        email_to = row.get("email", "")
        if email_to:
            _send_email(email_to, "[Railo] Daily activity digest", body.replace("*", "").replace("`", ""))
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 500
    return jsonify({"status": "sent", "events": events})


# --- Kill-switch admin endpoint ---

@app.route("/api/admin/kill-switch", methods=["GET"])
def api_kill_switch_status():
    """Return current kill-switch state (read from env)."""
    active = os.getenv("RAILO_KILL_SWITCH", "").lower() in {"1", "true", "yes"}
    return jsonify({"active": active})


# --- Admin: enqueue maintenance job ---

@app.route("/api/admin/maintenance", methods=["POST"])
def api_enqueue_maintenance():
    """Enqueue a maintenance job on the *low* RQ queue.

    Requires ``ADMIN_TOKEN`` header to match the ``RAILO_ADMIN_TOKEN`` env var.
    If Redis / RQ is unavailable, falls back to running synchronously.
    """
    admin_token = os.getenv("RAILO_ADMIN_TOKEN", "")
    if admin_token and request.headers.get("X-Admin-Token", "") != admin_token:
        return jsonify({"error": "Forbidden"}), 403

    try:
        from workers.config import QUEUES, _ensure_queues  # noqa: PLC0415
        from workers.maintenance_worker import run_maintenance  # noqa: PLC0415
        _ensure_queues()
        job = QUEUES["low"].enqueue(run_maintenance)
        return jsonify({"status": "enqueued", "job_id": job.id})
    except Exception:
        # Redis unavailable — run synchronously so operators aren't left stranded
        from workers.maintenance_worker import run_maintenance  # noqa: PLC0415
        result = run_maintenance()
        return jsonify({"status": "ran_sync", **result})


# --- Flask CLI: maintenance (invoke from cron) ---
# Cron example (daily at 02:00 AM):
#   0 2 * * * cd /app && flask maintenance >> /var/log/railo/maintenance.log 2>&1

@app.cli.command("maintenance")
def cli_maintenance():
    """Run periodic maintenance tasks (prune old runs + delivery IDs)."""
    import json as _json  # noqa: PLC0415
    from workers.maintenance_worker import run_maintenance  # noqa: PLC0415
    result = run_maintenance()
    print(_json.dumps(result))


# --- Flask CLI: flush notification digest queues (invoke from cron) ---
# Cron example (daily at 07:00 AM UTC):
#   0 7 * * * cd /app && FLASK_APP=webhook.server flask flush-digests >> /var/log/railo/maintenance.log 2>&1

@app.cli.command("flush-digests")
def cli_flush_digests():
    """Flush pending notification digest events for all installations."""
    import json as _json  # noqa: PLC0415
    from workers.maintenance_worker import run_digest_flush  # noqa: PLC0415
    result = run_digest_flush()
    print(_json.dumps(result))


@app.route("/")
def landing():
    """Landing page with install CTA."""
    return send_from_directory(app.static_folder, "landing.html")


@app.route("/privacy")
def privacy():
    """Privacy policy page."""
    return send_from_directory(app.static_folder, "privacy.html")


# --- Dashboard (OAuth + installations + runs) ---

def _dashboard_installed_ids() -> list[int]:
    """Return installation IDs scoped to the current logged-in user.

    When OAuth is active the user's GitHub token is used to fetch the
    installations they actually have access to via the GitHub API
    (GET /user/installations).  The result is intersected with the IDs
    stored in our local database so that we never expose data for
    installations the user cannot reach.

    Without OAuth (self-hosted / dev) every installation is returned,
    preserving the original single-tenant behaviour.
    """
    all_local = {i["installation_id"] for i in get_all_installations()}
    if not is_oauth_configured():
        return list(all_local)

    access_token = session.get("github_token", "")
    if not access_token:
        return []

    from core.dashboard_auth import get_user_installations  # noqa: PLC0415
    gh_installs = get_user_installations(access_token)
    gh_ids = {i["id"] for i in gh_installs}

    # Intersection: only IDs the user can see AND that we have locally
    return list(all_local & gh_ids)


@app.route("/dashboard")
@app.route("/dashboard/")
def dashboard_index():
    """Dashboard: OAuth login or main view."""
    if not is_oauth_configured():
        return _render_dashboard_unconfigured()
    if "github_user" not in session:
        state = os.urandom(16).hex()
        session["oauth_state"] = state
        return redirect(get_oauth_authorize_url(state))
    return _render_dashboard(session.get("github_user", {}).get("login", "User"))


@app.route("/dashboard/callback")
def dashboard_callback():
    """OAuth callback."""
    if not is_oauth_configured():
        return redirect("/dashboard")
    state = request.args.get("state")
    code = request.args.get("code")
    if not code or state != session.get("oauth_state"):
        return redirect("/dashboard")
    session.pop("oauth_state", None)
    token_data = exchange_code_for_token(code, state)
    if not token_data:
        return redirect("/dashboard")
    access_token = token_data.get("access_token")
    user = get_user_info(access_token)
    if user:
        session["github_user"] = user
        session["github_token"] = access_token
    return redirect("/dashboard/")


@app.route("/dashboard/logout")
def dashboard_logout():
    """Clear session and redirect to landing."""
    session.clear()
    return redirect("/")


def _render_dashboard_unconfigured() -> str:
    """Dashboard when OAuth not configured."""
    html = """
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>Dashboard – Railo</title>
    <style>body{font-family:system-ui;background:#0d1117;color:#e6edf3;padding:2rem;}</style></head>
    <body>
    <h1>Dashboard</h1>
    <p>Dashboard requires OAuth configuration. Set GITHUB_OAUTH_CLIENT_ID, GITHUB_OAUTH_CLIENT_SECRET, and DASHBOARD_SESSION_SECRET.</p>
    <p><a href="/">← Back</a></p>
    </body></html>
    """
    return html


def _render_dashboard(username: str) -> str:
    """Render dashboard with installations and recent runs."""
    installation_ids = _dashboard_installed_ids()
    runs = get_runs(installation_ids, limit=50)
    installations = get_all_installations()

    rows = ""
    for r in runs:
        ts = r.get("timestamp", "")[:19].replace("T", " ") if r.get("timestamp") else "-"
        pr = r.get("pr_number") or "-"
        status = r.get("status", "")
        found = r.get("violations_found", 0)
        fixed = r.get("violations_fixed", 0)
        rows += f"<tr><td>{ts}</td><td>{r.get('repo', '-')}</td><td>{pr}</td><td>{status}</td><td>{found}</td><td>{fixed}</td></tr>"

    inst_rows = ""
    for i in installations:
        inst_rows += f"<tr><td>{i.get('installation_id')}</td><td>{i.get('account_login')}</td><td>{i.get('account_type')}</td></tr>"

    html = f"""
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>Dashboard – Railo</title>
    <style>
    :root{{--bg:#0d1117;--fg:#e6edf3;--muted:#8b949e;--accent:#58a6ff;}}
    body{{font-family:system-ui;background:var(--bg);color:var(--fg);padding:2rem;}}
    a{{color:var(--accent);}}
    table{{border-collapse:collapse;width:100%;margin-top:1rem;}}
    th,td{{border:1px solid rgba(255,255,255,0.1);padding:0.5rem 0.75rem;text-align:left;}}
    th{{background:rgba(255,255,255,0.05);}}
    </style></head>
    <body>
    <h1>Railo Dashboard</h1>
    <p>Logged in as <strong>{username}</strong> · <a href="/dashboard/logout">Logout</a> · <a href="/">Home</a></p>
    <h2>Installations</h2>
    <table><thead><tr><th>ID</th><th>Account</th><th>Type</th></tr></thead><tbody>{inst_rows or '<tr><td colspan="3">No installations yet</td></tr>'}</tbody></table>
    <h2>Recent Runs</h2>
    <table><thead><tr><th>Time</th><th>Repo</th><th>PR</th><th>Status</th><th>Found</th><th>Fixed</th></tr></thead><tbody>{rows or '<tr><td colspan="6">No runs yet</td></tr>'}</tbody></table>
    <p><a href="https://github.com/apps/railo-cloud/installations/new">Install Railo</a></p>
    </body></html>
    """
    return html


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("DEBUG", "false").lower() == "true")
