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
from typing import Optional

from flask import Flask, request, jsonify
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scanner import semgrep_scan, get_pr_diff_files
from core.fixer import process_findings
from core.git_ops import commit_and_push_to_existing_branch, setup_git_identity
from core.safety import (
    compute_fix_idempotency_key,
    check_loop_prevention,
    check_confidence_gating,
)
from core.security import validate_webhook_request, is_allowed_pr_action, is_repo_allowed
from core.pr_comments import create_fix_comment, create_error_comment, create_warn_comment
from core.status_checks import set_compliance_status
from core.observability import (
    log_webhook_event,
    log_processing_result,
    log_fix_applied,
    CorrelationContext,
)
from core.rate_limit import check_rate_limit, get_rate_limit_key
from core.metrics import record_metric

load_dotenv()

app = Flask(__name__)

# Request size limit (1MB max payload)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

# Webhook secret for verifying GitHub payloads
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# Mode: "warn" (comment only) or "enforce" (apply fixes)
FIXPOINT_MODE = os.getenv("FIXPOINT_MODE", "warn").lower()

# Subprocess timeout (seconds)
GIT_TIMEOUT = int(os.getenv("GIT_TIMEOUT", "120"))

# In-memory idempotency store (in production, use Redis)
_processed_fixes: dict[str, bool] = {}


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
    if is_fork and FIXPOINT_MODE == "enforce":
        effective_mode = "warn"
        log_processing_result(
            correlation_id,
            "fork_detected",
            f"Fork PR detected - downgrading enforce to warn mode (no write access to fork)",
            {"head_repo": head_repo_full_name, "base_repo": base_repo_full_name}
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
        return {
            "status": "rate_limited",
            "message": f"Rate limit exceeded. Please wait before retrying.",
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
                return {
                    "status": "skipped",
                    "message": "Latest commit is from Fixpoint bot - skipping to prevent loop"
                }
            
            # Get changed files in PR
            changed_files = get_pr_diff_files(repo_path, base_branch, head_branch)
            if not changed_files:
                log_processing_result(correlation_id, "no_changes", "No files changed in PR")
                return {"status": "no_changes", "message": "No files changed in PR"}
            
            # Filter to Python files only (Phase 1 limitation)
            python_files = [f for f in changed_files if f.endswith(".py")]
            if not python_files:
                log_processing_result(correlation_id, "no_python", "No Python files changed")
                return {"status": "no_python", "message": "No Python files changed"}
            
            # Apply .fixpointignore
            from core.ignore import filter_ignored_files
            python_files = filter_ignored_files(python_files, repo_path)
            if not python_files:
                log_processing_result(correlation_id, "all_ignored", "All files ignored by .fixpointignore")
                return {"status": "all_ignored", "message": "All files ignored by .fixpointignore"}
            
            # Scan changed files
            rules_path = Path(__file__).parent.parent / "rules" / "sql_injection.yaml"
            results_path = Path(temp_dir) / "semgrep_results.json"
            
            data = semgrep_scan(repo_path, rules_path, results_path, python_files, apply_ignore=False)  # Already filtered above
            findings = data.get("results", [])
            
            if not findings:
                # Set status check: PASS (no violations found)
                set_compliance_status(
                    owner,
                    repo_name,
                    head_sha,
                    0,  # No violations
                    0,
                    pr_url,
                )
                
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
                )
                
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
                return {"status": "already_fixed", "message": "All findings already fixed"}
            
            # WARN MODE: Propose fixes without applying (includes fork PRs downgraded from enforce)
            if effective_mode == "warn":
                from patcher.fix_sqli import propose_fix_sqli
                
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
                    
                    proposal = propose_fix_sqli(repo_path, str(target_relpath))
                    if proposal:
                        proposed_fixes.append(proposal)
                
                if proposed_fixes:
                    # Post warn comment with proposals
                    # Add fork notice if this was downgraded from enforce
                    fork_notice = ""
                    if is_fork and FIXPOINT_MODE == "enforce":
                        fork_notice = "\n\n> **Note:** Fork PR detected. Enforce mode is disabled for fork PRs (no write access). Using warn mode instead."
                    
                    comment_url = create_warn_comment(
                        owner,
                        repo_name,
                        pr_number,
                        findings_to_process,
                        proposed_fixes,
                        fork_notice=fork_notice,
                        head_sha=head_sha,
                    )
                    
                    # Set status check: FAIL (violations found, not fixed)
                    set_compliance_status(
                        owner,
                        repo_name,
                        head_sha,
                        len(findings_to_process),
                        0,  # None fixed in warn mode
                        pr_url,
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
                    )
                    
                    log_processing_result(
                        correlation_id,
                        "warn_mode",
                        f"Proposed fixes for {len(findings_to_process)} violations (warn mode)",
                        {"comment_url": comment_url, "proposed_fixes": len(proposed_fixes)}
                    )
                    
                    return {
                        "status": "warn_mode",
                        "message": f"Proposed fixes for {len(findings_to_process)} violations (warn mode - no changes applied)",
                        "findings_count": len(findings_to_process),
                        "comment_url": comment_url,
                    }
                else:
                    log_processing_result(correlation_id, "no_fixes", "No fixes to propose")
                    return {"status": "no_fixes", "message": "No fixes to propose"}
            
            # ENFORCE MODE: Apply fixes
            # Apply fixes
            any_changes, processed = process_findings(repo_path, findings_to_process, rules_path)
            
            if not any_changes:
                log_processing_result(correlation_id, "no_fixes", "No fixes applied")
                # Set status: violations found but couldn't fix
                set_compliance_status(
                    owner,
                    repo_name,
                    head_sha,
                    len(findings_to_process),
                    0,
                    pr_url,
                )
                return {"status": "no_fixes", "message": "No fixes applied"}
            
            # Setup git identity before committing
            setup_git_identity(repo_path)
            
            # Commit and push to existing PR branch
            # Use canonical marker [fixpoint] for loop prevention
            violations_fixed = len([p for p in processed if p["fixed"]])
            commit_message = f"[fixpoint] fix: Apply compliance fixes ({violations_fixed} violation(s))"
            
            try:
                pushed = commit_and_push_to_existing_branch(
                    repo_path,
                    head_branch,
                    commit_message,
                )
                
                if pushed:
                    files_fixed = [p["file"] for p in processed if p["fixed"]]
                    violations_fixed = len([p for p in processed if p["fixed"]])
                    
                    # Post PR comment explaining the fix
                    comment_url = create_fix_comment(
                        owner,
                        repo_name,
                        pr_number,
                        files_fixed,
                        findings_to_process,
                    )
                    
                    # Set status check: PASS (violations found and fixed)
                    set_compliance_status(
                        owner,
                        repo_name,
                        head_sha,
                        len(findings_to_process),
                        violations_fixed,
                        pr_url,
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
                    )
                    
                    log_fix_applied(correlation_id, pr_number, files_fixed, len(findings_to_process))
                    log_processing_result(
                        correlation_id,
                        "success",
                        f"Applied fixes to {len(files_fixed)} files",
                        {"files_fixed": files_fixed, "comment_url": comment_url}
                    )
                    
                    return {
                        "status": "success",
                        "message": f"Applied fixes to {len(files_fixed)} files",
                        "files_fixed": files_fixed,
                        "comment_url": comment_url,
                    }
                else:
                    log_processing_result(correlation_id, "no_changes", "No changes to commit")
                    # Set status: violations found but no changes
                    set_compliance_status(
                        owner,
                        repo_name,
                        head_sha,
                        len(findings_to_process),
                        0,
                        pr_url,
                    )
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
                    return {
                        "status": "error",
                        "message": "Branch protection or permission error - comment posted to PR",
                    }
                else:
                    raise
        
        except Exception as e:
            log_processing_result(correlation_id, "error", str(e), {"exception_type": type(e).__name__})
            return {"status": "error", "message": str(e)}


@app.route("/webhook", methods=["POST"])
def webhook_handler():
    """Handle GitHub webhook POST requests with full security validation."""
    # Get headers
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    
    payload_body = request.data
    
    # SECURITY: Comprehensive validation
    is_valid, error_msg = validate_webhook_request(
        payload_body,
        signature,
        event_type,
        delivery_id,
        WEBHOOK_SECRET,
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
    owner = payload.get("repository", {}).get("owner", {}).get("login", "")
    repo = payload.get("repository", {}).get("name", "")
    pr_number = payload.get("pull_request", {}).get("number")
    
    log_webhook_event(event_type, action, owner, repo, pr_number, correlation_id)
    
    # Process based on event type
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("DEBUG", "false").lower() == "true")
