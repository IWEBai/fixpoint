"""
GitHub Action entry point for Fixpoint.
Runs in GitHub Actions environment with GITHUB_TOKEN and repository context.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv

from core.scanner import semgrep_scan, get_pr_diff_files_local
from core.fixer import process_findings
from core.git_ops import commit_and_push_to_existing_branch, run_tests
from core.safety import check_max_diff_lines
from core.config import load_config
from core.status_checks import set_compliance_status
from core.ignore import filter_ignored_files


def main():
    """Main entry point for GitHub Action."""
    # Load environment variables (GitHub Actions provides these)
    load_dotenv()
    
    # Get inputs from GitHub Actions environment
    github_token = os.getenv("INPUT_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("::error::GITHUB_TOKEN not found")
        sys.exit(1)
    
    # Set GITHUB_TOKEN for other modules
    os.environ["GITHUB_TOKEN"] = github_token
    
    # Get repository info from GitHub Actions
    repo_full_name = os.getenv("GITHUB_REPOSITORY")  # e.g., "owner/repo"
    if not repo_full_name:
        print("::error::GITHUB_REPOSITORY not found")
        sys.exit(1)
    
    owner, repo_name = repo_full_name.split("/", 1)
    os.environ["GITHUB_OWNER"] = owner
    os.environ["GITHUB_REPO"] = repo_name
    
    # Get base branch (default: main)
    base_branch = os.getenv("INPUT_BASE_BRANCH") or os.getenv("GITHUB_BASE_REF") or "main"
    
    # Get current branch/ref
    head_ref = os.getenv("GITHUB_HEAD_REF") or os.getenv("GITHUB_REF_NAME") or "main"
    head_sha = os.getenv("GITHUB_SHA")
    
    # Get workspace path (GitHub Actions checkout location)
    workspace = Path(os.getenv("GITHUB_WORKSPACE", "."))
    if not workspace.exists():
        print(f"::error::Workspace not found: {workspace}")
        sys.exit(1)
    
    # Get PR number if available (from GITHUB_REF for pull_request events)
    pr_number = None
    github_ref = os.getenv("GITHUB_REF", "")
    if "/pull/" in github_ref:
        try:
            pr_number = int(github_ref.split("/")[-2])
        except (ValueError, IndexError):
            pass
    
    # Determine mode (warn or enforce)
    mode = os.getenv("INPUT_MODE", "warn").lower()
    
    # FORK PR DETECTION: Auto-downgrade enforce to warn for forks
    # Read PR event payload if available
    is_fork = False
    github_event_path = os.getenv("GITHUB_EVENT_PATH")
    if github_event_path and Path(github_event_path).exists():
        with open(github_event_path, "r") as f:
            event_data = json.load(f)
            pr = event_data.get("pull_request", {})
            head_repo_full_name = pr.get("head", {}).get("repo", {}).get("full_name")
            base_repo_full_name = pr.get("base", {}).get("repo", {}).get("full_name")
            is_fork = head_repo_full_name != base_repo_full_name
    
    # Downgrade enforce to warn for fork PRs
    effective_mode = mode
    if is_fork and mode == "enforce":
        effective_mode = "warn"
        print(f"::notice::Fork PR detected - downgrading enforce to warn mode (no write access to fork)")
    
    warn_mode = effective_mode == "warn"
    
    print(f"::group::Fixpoint Scan")
    print(f"Repository: {owner}/{repo_name}")
    print(f"Base branch: {base_branch}")
    print(f"Head ref: {head_ref}")
    print(f"Mode: {effective_mode}" + (f" (downgraded from {mode} - fork PR)" if is_fork and mode == "enforce" else ""))
    print(f"::endgroup::")
    
    # Setup paths (rules directory = all Semgrep rules)
    rules_path = Path(__file__).parent / "rules"
    results_path = workspace / "semgrep_results.json"
    
    # Get changed files (PR diff mode)
    print("::group::Getting changed files")
    try:
        target_files = get_pr_diff_files_local(workspace, base_branch, head_ref)
        # Filter to supported files (Python + JS/TS)
        ext_ok = (".py", ".js", ".ts", ".jsx", ".tsx")
        target_files = [f for f in target_files if f.endswith(ext_ok)]
        # Apply .fixpointignore
        target_files = filter_ignored_files(target_files, workspace)
        print(f"Changed files: {len(target_files)}")
        if target_files:
            print(f"Files: {', '.join(target_files[:5])}{'...' if len(target_files) > 5 else ''}")
    except Exception as e:
        print(f"::warning::Could not get PR diff: {e}")
        print("Falling back to full repo scan")
        target_files = None
    print("::endgroup::")
    
    if target_files and not target_files:
        print("::notice::No supported files changed or all files ignored")
        # Set status check: PASS (no violations to check)
        if head_sha:
            set_compliance_status(owner, repo_name, head_sha, 0, 0)
        sys.exit(0)
    
    # Run Semgrep scan
    print("::group::Running Semgrep scan")
    try:
        data = semgrep_scan(workspace, rules_path, results_path, target_files, apply_ignore=True)
        findings = data.get("results", [])
        print(f"Findings: {len(findings)}")
    except Exception as e:
        print(f"::error::Semgrep scan failed: {e}")
        sys.exit(1)
    print("::endgroup::")
    
    if not findings:
        print("::notice::No violations found")
        # Set status check: PASS
        if head_sha:
            set_compliance_status(owner, repo_name, head_sha, 0, 0)
        sys.exit(0)
    
    # Process findings
    print(f"::group::Processing {len(findings)} findings")
    try:
        any_changes, processed = process_findings(workspace, findings, rules_path)
    except Exception as e:
        print(f"::error::Failed to process findings: {e}")
        sys.exit(1)
    print("::endgroup::")
    
    violations_found = len(findings)
    violations_fixed = len([p for p in processed if p.get("fixed")])
    
    # WARN MODE: Just set status check, don't commit
    if warn_mode:
        print("::notice::Warn mode: Not applying fixes (set mode=enforce to auto-fix)")
        # Set status check: FAIL (violations found, not fixed)
        if head_sha:
            set_compliance_status(owner, repo_name, head_sha, violations_found, 0)
        print(f"::warning::Found {violations_found} violation(s) - fixes proposed but not applied")
        sys.exit(1)  # Exit with error to fail the check
    
    # ENFORCE MODE: Apply fixes
    if not any_changes:
        print("::notice::No fixes to apply (already safe or pattern mismatch)")
        if head_sha:
            set_compliance_status(owner, repo_name, head_sha, violations_found, violations_fixed)
        sys.exit(0)
    
    # Safety rails: max-diff and optional test run
    import subprocess
    subprocess.run(["git", "add", "."], cwd=workspace, check=False, capture_output=True)
    config = load_config(workspace)
    ok, added, removed = check_max_diff_lines(workspace, config["max_diff_lines"])
    if not ok:
        total = added + removed
        print(f"::error::Diff too large ({total} lines, max {config['max_diff_lines']}). Not committing.")
        if head_sha:
            set_compliance_status(owner, repo_name, head_sha, violations_found, 0)
        sys.exit(1)
    if config["test_before_commit"]:
        success, output = run_tests(workspace, config["test_command"])
        if not success:
            print(f"::error::Tests failed before commit: {output[:500]}")
            if head_sha:
                set_compliance_status(owner, repo_name, head_sha, violations_found, 0)
            sys.exit(1)

    # Commit and push fixes
    # Use canonical marker [fixpoint] for loop prevention
    print("::group::Committing fixes")
    try:
        commit_and_push_to_existing_branch(
            workspace,
            head_ref,
            f"[fixpoint] fix: Apply compliance fixes ({violations_fixed} violation(s))",
        )
        print("::endgroup::")
    except Exception as e:
        print(f"::error::Failed to commit fixes: {e}")
        # Set status check: FAIL
        if head_sha:
            set_compliance_status(owner, repo_name, head_sha, violations_found, 0)
        sys.exit(1)
    
    # Set status check: PASS (violations fixed)
    if head_sha:
        set_compliance_status(owner, repo_name, head_sha, violations_found, violations_fixed)
    
    print(f"::notice::Applied fixes to {violations_fixed} violation(s)")
    sys.exit(0)


if __name__ == "__main__":
    main()
