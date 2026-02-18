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
from core.safety import check_max_diff_lines, validate_patch_plan, analyze_diff_quality
from core.config import load_config, ConfigError
from core.patch_plan import generate_patch_plan
from core.sarif import generate_sarif
from core.sarif_upload import upload_sarif_to_github
from core.status_checks import create_check_run_with_annotations
from core.ignore import filter_ignored_files
from core.baseline import audit_baseline, BaselineError
from core.trust_contract import (
    DecisionReport,
    filter_supported_files,
    write_safety_report,
)


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
        print("::notice::Fork PR detected - downgrading enforce to warn mode (no write access to fork)")
    
    # Initialise safety decision report for this run
    decision = DecisionReport(mode_requested=mode, mode_effective=effective_mode)

    # Best-effort permission preflight: can this token comment / create check-runs / push?
    can_comment = None
    can_check_runs = None
    can_push = None
    perm_note = ""
    try:
        from github import Github, Auth  # type: ignore

        gh = Github(auth=Auth.Token(github_token))
        repo_obj = gh.get_repo(f"{owner}/{repo_name}")
        perms = getattr(repo_obj, "permissions", None)
        # Repository permissions are coarse but give us a signal for push rights.
        if perms is not None:
            # PyGithub Permissions object exposes attributes; fall back to dict-style if present.
            can_push = bool(getattr(perms, "push", False) or getattr(perms, "admin", False))
        # If we can read the repo object, we can almost certainly comment and create check runs.
        can_comment = True
        can_check_runs = True
    except Exception as e:  # pragma: no cover - defensive path
        perm_note = f"Permission preflight failed: {e}"

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
        print("::notice::Token cannot push to this repository; downgrading enforce to warn mode.")
    
    warn_mode = effective_mode == "warn"
    
    print("::group::Fixpoint Scan")
    print(f"Repository: {owner}/{repo_name}")
    print(f"Base branch: {base_branch}")
    print(f"Head ref: {head_ref}")
    print(f"Mode: {effective_mode}" + (f" (downgraded from {mode} - fork PR)" if is_fork and mode == "enforce" else ""))
    print("::endgroup::")
    
    # Load configuration (safety rails, test settings, guardrails, time budget)
    try:
        config = load_config(workspace)
    except ConfigError as e:
        print(f"::error::Invalid Fixpoint config in {e.path.name}")
        for msg in e.errors:
            print(f"::error::{msg}")
        sys.exit(1)

    # Setup paths (rules directory = all Semgrep rules)
    rules_path = Path(__file__).parent / "rules"
    results_path = workspace / "semgrep_results.json"
    
    # Get changed files (PR diff mode) with early exit for out-of-scope files
    print("::group::Getting changed files")
    try:
        target_files = get_pr_diff_files_local(workspace, base_branch, head_ref)
        # Early exit: Filter to supported files - skip unsupported files quickly
        initial_count = len(target_files)
        target_files = filter_supported_files(target_files, decision)
        if initial_count > len(target_files):
            print(f"Filtered out {initial_count - len(target_files)} unsupported file(s) (early exit)")
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
    
    if target_files is not None and not target_files:
        print("::notice::No supported files changed or all files ignored")
        # Safety report: no work needed
        decision.status = "no_findings"
        decision.set_summary(
            violations_found=0,
            violations_fixed=0,
            files_touched=0,
            check_ids=[],
        )
        write_safety_report(workspace, decision)
        # Check-run: PASS (no violations to check)
        if head_sha:
            create_check_run_with_annotations(
                owner,
                repo_name,
                head_sha,
                [],
                conclusion="success",
            )
        sys.exit(0)
    
    # Run Semgrep scan with time budget enforcement
    print("::group::Running Semgrep scan")
    import time

    start_time = time.time()
    max_runtime = float(config.get("max_runtime_seconds", 90) or 90)

    try:
        # Calculate remaining time budget for Semgrep (leave some buffer for post-processing)
        elapsed_so_far = time.time() - start_time
        remaining_budget = max(1, max_runtime - elapsed_so_far - 10)  # 10s buffer for post-processing
        
        data = semgrep_scan(
            workspace,
            rules_path,
            results_path,
            target_files,
            apply_ignore=True,
            max_runtime_seconds=int(remaining_budget) if remaining_budget > 0 else None,
        )
        findings = data.get("results", [])
        print(f"Findings (raw): {len(findings)}")

        # Generate SARIF output for CI/Code Scanning consumers
        try:
            sarif = generate_sarif(findings, workspace)
            sarif_path = workspace / "fixpoint-results.sarif.json"
            sarif_path.write_text(
                __import__("json").dumps(sarif, indent=2),
                encoding="utf-8",
            )
            print(f"::notice::Wrote SARIF results to {sarif_path}")

            # Best-effort upload to GitHub Code Scanning
            if head_sha:
                try:
                    ref = f"refs/heads/{head_ref}"
                    upload_sarif_to_github(
                        owner,
                        repo_name,
                        sarif_path,
                        head_sha,
                        ref,
                        github_token=github_token,
                    )
                except Exception as upload_err:
                    print(f"::warning::Failed to upload SARIF: {upload_err}")
        except Exception as sarif_err:
            # Non-fatal: continue even if SARIF generation or upload fails
            print(f"::warning::Failed to generate SARIF: {sarif_err}")

        # Persist raw findings as an artifact for CI consumers
        try:
            findings_path = workspace / "findings.json"
            findings_path.write_text(
                json.dumps(findings, indent=2),
                encoding="utf-8",
            )
            print(f"::notice::Wrote findings to {findings_path}")
        except Exception as findings_err:
            print(f"::warning::Failed to write findings.json: {findings_err}")

        # Optional baseline filtering: drop findings that already existed
        # at the configured baseline SHA.
        if config.get("baseline_mode"):
            try:
                findings, audit = audit_baseline(
                    workspace,
                    findings,
                    config.get("baseline_sha"),
                    config.get("baseline_max_age_days", 0),
                )
                decision.mark_baseline(audit)
                print(
                    "Baseline audit: "
                    f"baseline_sha={audit.get('baseline_sha')}, "
                    f"filtered_count={audit.get('filtered_count')}, "
                    f"remaining_count={audit.get('remaining_count')}"
                )
            except BaselineError as baseline_err:
                msg = f"Baseline mode misconfigured: {baseline_err}"
                print(f"::error::{msg}")
                decision.status = "refused"
                decision.reasons.append(msg)
                write_safety_report(workspace, decision)
                sys.exit(1)
    except Exception as e:
        print(f"::error::Semgrep scan failed: {e}")
        decision.status = "refused"
        decision.reasons.append(f"Semgrep scan failed: {e}")
        decision.set_summary(
            violations_found=0,
            violations_fixed=0,
            files_touched=0,
            check_ids=[],
        )
        write_safety_report(workspace, decision)
        if head_sha:
            # Best-effort failure check-run so users see a conclusion in GitHub UI.
            try:
                create_check_run_with_annotations(
                    owner,
                    repo_name,
                    head_sha,
                    [],
                    conclusion="failure",
                )
            except Exception:
                # Already logged inside status_checks; nothing more to do.
                pass
        sys.exit(1)
    print("::endgroup::")
    
    elapsed = time.time() - start_time
    
    if not findings:
        print("::notice::No violations found")
        decision.status = "no_findings"
        decision.set_summary(
            violations_found=0,
            violations_fixed=0,
            files_touched=0,
            check_ids=[],
        )
        write_safety_report(workspace, decision)
        # Check-run: PASS
        if head_sha:
            create_check_run_with_annotations(
                owner,
                repo_name,
                head_sha,
                [],
                conclusion="success",
            )
        sys.exit(0)
    
    # If we exceeded time budget, degrade to "report only" mode even if
    # enforce was requested.
    timed_out = max_runtime > 0 and elapsed > max_runtime
    
    from core.trust_contract import DecisionReport as _DecisionReport  # local import to avoid cycles
    decision.mark_time_budget(elapsed=elapsed, max_runtime_seconds=max_runtime, timed_out=timed_out)
    if timed_out and isinstance(decision, _DecisionReport):
        decision.mode_effective = "report-only"
    
    if timed_out:
        print(f"::warning::Time budget exceeded ({elapsed:.1f}s > {max_runtime}s). Degrading to report-only mode.")

    # WARN MODE: Do not apply fixes, only report via status check
    if warn_mode or timed_out:
        print("::group::Processing findings (warn mode)")
        try:
            # We still call process_findings so that proposed fixes / metrics
            # keep their existing behaviour, but we do not commit any changes.
            any_changes, processed = process_findings(
                workspace, findings, rules_path, config, decision_report=decision
            )
        except Exception as e:
            print(f"::error::Failed to process findings: {e}")
            decision.status = "refused"
            write_safety_report(workspace, decision)
            sys.exit(1)
        print("::endgroup::")

        violations_found = len(findings)
        if timed_out:
            print("::notice::Time budget exceeded, degrading to report-only mode (no fixes applied)")
        else:
            print("::notice::Warn mode: Not applying fixes (set mode=enforce to auto-fix)")
        decision.status = "report_only"
        decision.set_summary(
            violations_found=violations_found,
            violations_fixed=0,
            files_touched=0,
            check_ids=[str(f.get("check_id", "")) for f in findings],
        )
        write_safety_report(workspace, decision)
        if head_sha:
            # Violations found but not fixed -> FAIL
            create_check_run_with_annotations(
                owner,
                repo_name,
                head_sha,
                findings,
                conclusion="failure",
            )
        print(f"::warning::Found {violations_found} violation(s) - fixes proposed but not applied")
        sys.exit(1)

    # ENFORCE MODE: Two-phase apply (plan -> validate -> apply)
    print("::group::Planning fixes (enforce mode)")
    try:
        plan = generate_patch_plan(workspace, findings, rules_path)
    except Exception as e:
        print(f"::error::Failed to generate patch plan: {e}")
        decision.status = "refused"
        decision.reasons.append(f"Failed to generate patch plan: {e}")
        write_safety_report(workspace, decision)
        sys.exit(1)

    # Save patch plan as CI artifact for debugging/review
    try:
        from dataclasses import asdict as _asdict

        patch_plan_path = workspace / "patch-plan.json"
        # PatchPlan is a dataclass; convert to a JSON-serializable dict
        serialisable_plan = _asdict(plan)
        # Normalise repo_path to string for portability
        if "repo_path" in serialisable_plan:
            serialisable_plan["repo_path"] = str(serialisable_plan["repo_path"])
        patch_plan_path.write_text(
            json.dumps(serialisable_plan, indent=2),
            encoding="utf-8",
        )
        print(f"::notice::Wrote patch plan to {patch_plan_path}")
    except Exception as plan_err:
        print(f"::warning::Failed to write patch-plan.json: {plan_err}")

    ok_plan, reasons = validate_patch_plan(plan, config)
    if not ok_plan:
        # Guardrails blocked auto-fix; fall back to "report only" behaviour
        print("::error::Enforce mode guardrails blocked auto-fix. Reasons:")
        for reason in reasons:
            print(f"::error::{reason}")
        decision.mark_policy(ok=False, reasons=reasons)
        decision.status = "refused"
        if head_sha:
            # We found violations but did not fix them due to safety rails
            create_check_run_with_annotations(
                owner,
                repo_name,
                head_sha,
                findings,
                conclusion="failure",
            )
        print("::notice::Falling back to report-only behaviour due to safety guardrails.")
        write_safety_report(workspace, decision)
        sys.exit(1)
    print("::endgroup::")

    # Phase 2: Apply fixes
    print("::group::Applying fixes")
    try:
        any_changes, processed = process_findings(
            workspace, findings, rules_path, config, decision_report=decision
        )
    except Exception as e:
        print(f"::error::Failed to process findings: {e}")
        decision.status = "refused"
        decision.reasons.append(f"Failed to process findings: {e}")
        write_safety_report(workspace, decision)
        sys.exit(1)
    print("::endgroup::")

    violations_found = len(findings)
    violations_fixed = len([p for p in processed if p.get("fixed")])

    if not any_changes:
        print("::notice::No fixes to apply (already safe or pattern mismatch)")
        decision.status = "report_only"
        decision.set_summary(
            violations_found=violations_found,
            violations_fixed=violations_fixed,
            files_touched=0,
            check_ids=[str(f.get("check_id", "")) for f in findings],
        )
        write_safety_report(workspace, decision)
        if head_sha:
            conclusion = "success" if violations_fixed >= violations_found else "failure"
            create_check_run_with_annotations(
                owner,
                repo_name,
                head_sha,
                findings,
                conclusion=conclusion,
            )
        sys.exit(0)

    # Safety rail: max-diff threshold before we consider committing
    import subprocess
    subprocess.run(["git", "add", "."], cwd=workspace, check=False, capture_output=True)
    ok, added, removed = check_max_diff_lines(workspace, config["max_diff_lines"])
    decision.mark_max_diff_lines(
        ok=ok,
        added=added,
        removed=removed,
        max_diff_lines=int(config["max_diff_lines"]),
    )
    if not ok:
        total = added + removed
        print(f"::error::Diff too large ({total} lines, max {config['max_diff_lines']}). Not committing.")
        decision.status = "refused"
        if head_sha:
            create_check_run_with_annotations(
                owner,
                repo_name,
                head_sha,
                findings,
                conclusion="failure",
            )
        write_safety_report(workspace, decision)
        sys.exit(1)
    
    # Safety rail: diff quality check - ensure minimal, focused patches
    quality_result = analyze_diff_quality(workspace)
    decision.mark_diff_quality(quality_result)
    if not quality_result.get("is_minimal", False):
        score = quality_result.get("quality_score", 0.0)
        issues = quality_result.get("issues", [])
        print(f"::error::Diff quality check failed (score: {score:.2f}). Patch quality issues:")
        for issue in issues:
            print(f"::error::{issue}")
        print("::error::Patches must be minimal and focused on security fixes only.")
        decision.status = "refused"
        if head_sha:
            create_check_run_with_annotations(
                owner,
                repo_name,
                head_sha,
                findings,
                conclusion="failure",
            )
        write_safety_report(workspace, decision)
        sys.exit(1)

    # Commit and push fixes using centralised helper (tests + rollback)
    from core.git_ops import commit_with_rollback

    print("::group::Committing fixes")
    commit_message = f"[fixpoint] fix: Apply compliance fixes ({violations_fixed} violation(s))"
    test_cmd = config["test_command"] if config["test_before_commit"] else None
    success, error_msg = commit_with_rollback(
        workspace,
        head_ref,
        commit_message,
        test_command=test_cmd,
    )
    if not success:
        print(f"::error::Failed to commit fixes safely: {error_msg or 'unknown error'}")
        decision.status = "refused"
        decision.reasons.append(f"Commit_with_rollback failed: {error_msg or 'unknown error'}")
        # Check-run: FAIL
        if head_sha:
            create_check_run_with_annotations(
                owner,
                repo_name,
                head_sha,
                findings,
                conclusion="failure",
            )
        write_safety_report(workspace, decision)
        sys.exit(1)
    print("::endgroup::")
    
    # Check-run: PASS (violations fixed)
    decision.status = "fixed"
    decision.set_summary(
        violations_found=violations_found,
        violations_fixed=violations_fixed,
        files_touched=len({p.get("file") for p in processed if p.get("fixed")}),
        check_ids=[str(f.get("check_id", "")) for f in findings],
    )
    write_safety_report(workspace, decision)
    if head_sha:
        conclusion = "success" if violations_fixed >= violations_found else "failure"
        create_check_run_with_annotations(
            owner,
            repo_name,
            head_sha,
            findings,
            conclusion=conclusion,
        )
    
    print(f"::notice::Applied fixes to {violations_fixed} violation(s)")
    sys.exit(0)


if __name__ == "__main__":
    main()
