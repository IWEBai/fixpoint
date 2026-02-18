"""
GitHub webhook server for Fixpoint Phase 2.
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
from core.pr_comments import create_fix_comment, create_error_comment, create_warn_comment
from core.status_checks import create_check_run_with_annotations
from core.observability import (
    log_webhook_event,
    log_processing_result,
    log_fix_applied,
    CorrelationContext,
)
from core.rate_limit import check_rate_limit, get_rate_limit_key
from core.metrics import record_metric
from core.admin_controls import (
    is_repo_disabled,
    is_force_warn_org,
    get_disabled_rules,
    filter_findings_by_rules,
)
from core.db import init_db, upsert_installation, get_all_installations, get_runs
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

load_dotenv()

# Initialize DB on first import
init_db()

app = Flask(__name__, static_folder=Path(__file__).parent / "static")
app.secret_key = os.getenv("DASHBOARD_SESSION_SECRET") or "dev-secret-change-in-production"

# Request size limit (1MB max payload)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

# Webhook secrets (GitHub App uses app secret, self-hosted uses WEBHOOK_SECRET)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
GITHUB_APP_WEBHOOK_SECRET = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")

# Mode: "warn" (comment only) or "enforce" (apply fixes)
FIXPOINT_MODE = os.getenv("FIXPOINT_MODE", "warn").lower()

# Subprocess timeout (seconds)
GIT_TIMEOUT = int(os.getenv("GIT_TIMEOUT", "120"))

# In-memory idempotency store (in production, use Redis)
_processed_fixes: dict[str, bool] = {}


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


def process_pr_webhook(payload: dict, correlation_id: str) -> dict:
    """
    Process a PR webhook event with full safety checks.
    
    Returns:
        Dict with status and message
    """
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
                    "Latest commit is from Fixpoint bot - skipping to prevent loop"
                )
                failure_reason = "loop_prevention"
                _record_run_metric("skipped", "Loop prevention")
                return {
                    "status": "skipped",
                    "message": "Latest commit is from Fixpoint bot - skipping to prevent loop"
                }
            
            # Load configuration (safety rails, baseline, time budget)
            try:
                config = load_config(repo_path)
            except ConfigError as e:
                msg = f"Invalid Fixpoint config in {e.path.name}:\n- " + "\n- ".join(e.errors)
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
                if idempotency_key not in _processed_fixes:
                    findings_to_process.append(finding)
                    _processed_fixes[idempotency_key] = True
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
                    "Fixpoint will not auto-commit. Apply fixes manually or increase max_diff_lines.",
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
            
            # Commit and push to existing PR branch with centralised test/rollback logic
            from core.git_ops import commit_with_rollback

            violations_fixed = len([p for p in processed if p["fixed"]])
            commit_message = f"[fixpoint] fix: Apply compliance fixes ({violations_fixed} violation(s))"

            test_cmd = config["test_command"] if config["test_before_commit"] else None

            success, error_msg = commit_with_rollback(
                repo_path,
                head_branch,
                commit_message,
                test_command=test_cmd,
                test_timeout=GIT_TIMEOUT,
            )

            if not success:
                # Tests failed or commit/push failed – do not leave half-applied state.
                create_error_comment(
                    owner,
                    repo_name,
                    pr_number,
                    "commit_or_tests_failed",
                    f"Fixpoint could not push fixes safely: {error_msg or 'unknown error'}",
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
                    "commit_or_tests_failed",
                    "Commit or tests failed, no auto-fix applied",
                    {"error": (error_msg or "")[:200]},
                )
                failure_reason = "commit_or_tests_failed"
                _record_run_metric("commit_or_tests_failed", "Commit or tests failed")
                return {
                    "status": "commit_or_tests_failed",
                    "message": "Commit or tests failed; no auto-fix was pushed",
                }

            try:
                pushed = True  # commit_with_rollback already pushed on success
                if pushed:
                    files_fixed = [p["file"] for p in processed if p["fixed"]]
                    violations_fixed = len([p for p in processed if p["fixed"]])
                    fixes_applied = violations_fixed

                    decision.status = "fixed"
                    decision.set_summary(
                        violations_found=len(findings_to_process),
                        violations_fixed=violations_fixed,
                        files_touched=len(set(files_fixed)),
                        check_ids=[str(f.get("check_id", "")) for f in findings_to_process],
                    )
                    safety_snippet = decision.to_comment_snippet()

                    # Post PR comment explaining the fix
                    patch_hunks = _collect_patch_hunks(repo_path, max_hunks=5, max_lines=60)
                    comment_url = create_fix_comment(
                        owner,
                        repo_name,
                        pr_number,
                        files_fixed,
                        findings_to_process,
                        patch_hunks=patch_hunks,
                        safety_snippet=safety_snippet,
                    )
                    write_safety_report(repo_path, decision)
                    
                    if head_sha:
                        create_check_run_with_annotations(
                            owner,
                            repo_name,
                            head_sha,
                            findings_to_process,
                            conclusion="success" if violations_fixed >= len(findings_to_process) else "failure",
                            pr_url=pr_url,
                        )
                    
                    # Record metric
                    record_metric(
                        event_type="fix_applied",
                        repo=f"{owner}/{repo_name}",
                        pr_number=pr_number,
                        violations_found=len(findings_to_process),
                        violations_fixed=violations_fixed,
                        mode="enforce",
                        status="success",
                        metadata={"files_fixed": files_fixed, "comment_url": comment_url},
                        installation_id=installation_id,
                        correlation_id=correlation_id,
                    )
                    
                    log_fix_applied(correlation_id, pr_number, files_fixed, len(findings_to_process))
                    log_processing_result(
                        correlation_id,
                        "success",
                        f"Applied fixes to {len(files_fixed)} files",
                        {"files_fixed": files_fixed, "comment_url": comment_url}
                    )
                    _record_run_metric("success", f"Applied fixes to {len(files_fixed)} files")
                    
                    return {
                        "status": "success",
                        "message": f"Applied fixes to {len(files_fixed)} files",
                        "files_fixed": files_fixed,
                        "comment_url": comment_url,
                    }
                else:
                    log_processing_result(correlation_id, "no_changes", "No changes to commit")
                    if head_sha:
                        create_check_run_with_annotations(
                            owner,
                            repo_name,
                            head_sha,
                            findings_to_process,
                            conclusion="failure",
                            pr_url=pr_url,
                        )
                    failure_reason = "no_changes"
                    _record_run_metric("no_changes", "No changes to commit")
                    return {"status": "no_changes", "message": "No changes to commit"}
            
            except subprocess.CalledProcessError as e:
                # Handle branch protection or permission errors gracefully
                error_msg = str(e)
                if "permission" in error_msg.lower() or "protected" in error_msg.lower():
                    # Post helpful comment
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
                else:
                    raise
        
        except Exception as e:
            log_processing_result(correlation_id, "error", str(e), {"exception_type": type(e).__name__})
            failure_reason = "exception"
            _record_run_metric("error", str(e))
            return {"status": "error", "message": str(e)}


def _get_webhook_secrets() -> list[str]:
    """Build list of secrets to try: app secret first, then repo secret (dual mode)."""
    secrets = []
    if GITHUB_APP_WEBHOOK_SECRET:
        secrets.append(GITHUB_APP_WEBHOOK_SECRET)
    if WEBHOOK_SECRET:
        secrets.append(WEBHOOK_SECRET)
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
    
    payload_body = request.data
    
    # Build secrets: app secret + repo secret (try both for dual mode)
    secrets = _get_webhook_secrets()
    
    # SECURITY: Comprehensive validation
    is_valid, error_msg = validate_webhook_request(
        payload_body,
        signature,
        event_type,
        delivery_id,
        secrets if secrets else WEBHOOK_SECRET or "",  # fallback for dev
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
        if account:
            upsert_installation(
                installation_id=inst_id,
                account_login=account.get("login", "unknown"),
                account_type=account.get("type", "User"),
            )
        log_processing_result(
            correlation_id,
            "installation_event",
            f"Installation {action}",
            {"installation_id": inst_id},
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
        log_processing_result(
            correlation_id,
            "installation_repositories_event",
            f"Repositories {action}",
            {"installation_id": inst_id},
        )
        return jsonify({"status": "ok", "message": f"Repositories {action}"}), 200
    
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
        
        return jsonify(result), 200
    
    return jsonify({
        "status": "ignored",
        "message": f"Event type '{event_type}' not handled"
    }), 200


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


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
    """Get installation IDs from DB (for dashboard when no OAuth filtering)."""
    installations = get_all_installations()
    return [i["installation_id"] for i in installations]


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
    <html><head><meta charset="UTF-8"><title>Dashboard – Fixpoint</title>
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
    <html><head><meta charset="UTF-8"><title>Dashboard – Fixpoint</title>
    <style>
    :root{{--bg:#0d1117;--fg:#e6edf3;--muted:#8b949e;--accent:#58a6ff;}}
    body{{font-family:system-ui;background:var(--bg);color:var(--fg);padding:2rem;}}
    a{{color:var(--accent);}}
    table{{border-collapse:collapse;width:100%;margin-top:1rem;}}
    th,td{{border:1px solid rgba(255,255,255,0.1);padding:0.5rem 0.75rem;text-align:left;}}
    th{{background:rgba(255,255,255,0.05);}}
    </style></head>
    <body>
    <h1>Fixpoint Dashboard</h1>
    <p>Logged in as <strong>{username}</strong> · <a href="/dashboard/logout">Logout</a> · <a href="/">Home</a></p>
    <h2>Installations</h2>
    <table><thead><tr><th>ID</th><th>Account</th><th>Type</th></tr></thead><tbody>{inst_rows or '<tr><td colspan="3">No installations yet</td></tr>'}</tbody></table>
    <h2>Recent Runs</h2>
    <table><thead><tr><th>Time</th><th>Repo</th><th>PR</th><th>Status</th><th>Found</th><th>Fixed</th></tr></thead><tbody>{rows or '<tr><td colspan="6">No runs yet</td></tr>'}</tbody></table>
    <p><a href="https://github.com/apps/fixpoint-security/installations/new">Install Fixpoint</a></p>
    </body></html>
    """
    return html


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("DEBUG", "false").lower() == "true")
