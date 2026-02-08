"""
Fixpoint by IWEB - Compliance Auto-Patcher
Main entry point supporting both CLI mode (Phase 1) and PR diff mode (Phase 2).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from core.scanner import semgrep_scan, get_pr_diff_files_local
from core.fixer import process_findings
from core.git_ops import commit_and_push_new_branch, commit_and_push_to_existing_branch, generate_branch_name
from core.ignore import filter_ignored_files
from github_bot.open_pr import open_or_get_pr


def process_repo_scan(
    repo_path: Path,
    rules_path: Path,
    results_path: Path,
    pr_mode: bool = False,
    base_ref: str | None = None,
    head_ref: str | None = None,
) -> tuple[bool, list[dict]]:
    """
    Scan repository and process findings.
    
    Args:
        repo_path: Path to repository
        rules_path: Path to Semgrep rules
        results_path: Path to write results JSON
        pr_mode: If True, only scan changed files in PR diff
        base_ref: Base git ref for PR diff (required if pr_mode=True)
        head_ref: Head git ref for PR diff (required if pr_mode=True)
    
    Returns:
        Tuple of (any_changes, processed_findings)
    """
    target_files = None
    
    if pr_mode:
        if not base_ref or not head_ref:
            raise ValueError("base_ref and head_ref required for PR mode")
        print(f"[1/5] Scanning PR diff: {base_ref}..{head_ref}")
        target_files = get_pr_diff_files_local(repo_path, base_ref, head_ref)
        # Filter to supported files (Python + JS/TS)
        ext_ok = (".py", ".js", ".ts", ".jsx", ".tsx")
        target_files = [f for f in target_files if f.endswith(ext_ok)]
        if not target_files:
            print("No supported files changed in PR diff.")
            return False, []
        # Apply .fixpointignore
        target_files = filter_ignored_files(target_files, repo_path)
        if not target_files:
            print("All files ignored by .fixpointignore.")
            return False, []
        print(f"Changed files: {len(target_files)}")
    else:
        print(f"[1/5] Scanning repository for compliance violations: {repo_path}")
    
    # Run Semgrep scan
    data = semgrep_scan(repo_path, rules_path, results_path, target_files, apply_ignore=True)
    
    results = data.get("results", [])
    if not results:
        print("No findings. Exiting.")
        return False, []
    
    print(f"[2/5] Findings: {len(results)}")
    
    # Process findings and apply fixes
    print("[3/5] Applying fixes (deterministic)")
    any_changes, processed = process_findings(repo_path, results, rules_path)
    
    if not any_changes:
        print("No fixes applied (already safe or pattern mismatch).")
        return False, processed
    
    fixed_count = len([p for p in processed if p["fixed"]])
    print(f"Applied fixes to {fixed_count} file(s)")
    
    return any_changes, processed


def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="Fixpoint: Auto-fix security vulnerabilities in your PRs"
    )
    parser.add_argument("repo", type=str, help="Path to local git repo to patch")
    parser.add_argument(
        "--pr-mode",
        action="store_true",
        help="PR diff mode: only scan changed files between base and head refs",
    )
    parser.add_argument(
        "--base-ref",
        type=str,
        help="Base git ref for PR diff mode (e.g., 'main' or commit SHA)",
    )
    parser.add_argument(
        "--head-ref",
        type=str,
        help="Head git ref for PR diff mode (e.g., 'feature-branch' or commit SHA)",
    )
    parser.add_argument(
        "--push-to-existing",
        type=str,
        help="Push to existing branch instead of creating new one (branch name)",
    )
    parser.add_argument(
        "--no-pr",
        action="store_true",
        help="Don't create/open PR (just commit and push)",
    )
    parser.add_argument(
        "--warn-mode",
        action="store_true",
        help="Warn mode: propose fixes in comments, don't apply",
    )
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        raise FileNotFoundError(f"Repo path does not exist: {repo_path}")
    
    rules_path = Path(__file__).parent / "rules"
    results_path = Path("semgrep_results.json")
    
    # Process scan
    any_changes, processed = process_repo_scan(
        repo_path,
        rules_path,
        results_path,
        pr_mode=args.pr_mode,
        base_ref=args.base_ref,
        head_ref=args.head_ref,
    )
    
    if not any_changes:
        return
    
    # WARN MODE: Propose fixes without applying
    if args.warn_mode:
        print("[4/5] Warn mode: Proposing fixes (not applying)")
        from core.fixer import _propose_fixer
        
        proposed_fixes = []
        for p in processed:
            if p.get("finding") and p.get("fixer"):
                file_path = p["file"]
                fixer_name = p["fixer"]
                finding = p.get("finding", {})
                proposal = _propose_fixer(fixer_name, repo_path, file_path, finding)
                if proposal:
                    if proposal.get("line", 0) == 0 and finding:
                        proposal = {
                            **proposal,
                            "line": int(finding.get("start", {}).get("line", 0)),
                        }
                    proposal["finding"] = finding  # for print fallback
                    proposed_fixes.append(proposal)
        
        if proposed_fixes:
            # Get PR number if available (for CLI, we'll just print)
            print("\n=== Proposed Fixes (Warn Mode) ===\n")
            for fix in proposed_fixes:
                line = fix.get("line", 0)
                if line == 0 and fix.get("finding"):
                    line = fix.get("finding", {}).get("start", {}).get("line", 0)
                print(f"File: {fix['file']}:{line}")
                print(f"Before: {fix['before']}")
                print(f"After:  {fix['after']}")
                if "exec_before" in fix and "exec_after" in fix:
                    print(f"Execute before: {fix['exec_before']}")
                    print(f"Execute after:  {fix['exec_after']}")
                print()
            
            print("To apply these fixes automatically, run without --warn-mode")
            return
        else:
            print("No fixes to propose.")
            return
    
    # ENFORCE MODE: Apply fixes
    # Git operations
    print("[4/5] Committing fix and pushing")
    
    # Use canonical marker [fixpoint] for loop prevention
    fixed_count = len([p for p in processed if p["fixed"]])
    commit_message = f"[fixpoint] fix: Apply compliance fixes ({fixed_count} violation(s))"
    
    if args.push_to_existing:
        # Phase 2: Push to existing PR branch
        pushed = commit_and_push_to_existing_branch(
            repo_path,
            args.push_to_existing,
            commit_message,
        )
        if not pushed:
            print("No changes to commit.")
            return
        print(f"Pushed fix to existing branch: {args.push_to_existing}")
    else:
        # Phase 1: Create new branch
        branch_name = generate_branch_name("autopatcher/fix-sqli")
        pushed = commit_and_push_new_branch(repo_path, branch_name, commit_message)
        if not pushed:
            print("No changes to commit.")
            return
        
        if not args.no_pr:
            print("[5/5] Opening Pull Request (or reusing existing)")
            pr_url = open_or_get_pr(
                owner=os.getenv("GITHUB_OWNER"),
                repo=os.getenv("GITHUB_REPO"),
                head=branch_name,
                base="main",
                title="AutoPatch: Fix SQL injection (parameterized query)",
                body=(
                    "This PR was generated automatically.\n\n"
                    "## What was found\n"
                    "- Possible SQL injection via string formatting.\n\n"
                    "## What changed\n"
                    "- Replaced formatted SQL with a parameterized query.\n"
                    "- Updated execute call to pass parameters safely.\n\n"
                    "## Safety\n"
                    "- Minimal diff\n"
                    "- No refactors\n"
                ),
            )
            print("Done.")
            print("PR:", pr_url)
        else:
            print(f"Done. Branch: {branch_name}")


if __name__ == "__main__":
    main()
