"""
Core scanning engine for AuditShield.
Supports both full repository scanning and PR diff scanning.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from core.ignore import filter_ignored_files, read_ignore_file


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """
    Run a command and raise a readable error if it fails.
    Windows-safe: force UTF-8 decoding (and ignore undecodable chars).
    """
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n\nSTDOUT:\n{p.stdout}\n\nSTDERR:\n{p.stderr}"
        )
    return p


def semgrep_scan(
    repo_path: Path,
    rules_path: Path,
    out_json: Path,
    target_files: Optional[list[str]] = None,
    apply_ignore: bool = True,
) -> dict:
    """
    Run semgrep and write JSON to out_json.
    
    Args:
        repo_path: Path to repository root
        rules_path: Path to Semgrep rules file
        out_json: Path to write JSON results
        target_files: Optional list of specific files to scan (for PR diff mode)
        apply_ignore: If True, filter files using .auditshieldignore
    
    Returns:
        Parsed Semgrep results as dict
    """
    # Apply .auditshieldignore filtering
    if apply_ignore and target_files:
        ignore_patterns = read_ignore_file(repo_path)
        target_files = filter_ignored_files(target_files, repo_path, ignore_patterns)
        if not target_files:
            # All files ignored, return empty results
            return {"results": []}
    
    cmd = [
        "semgrep",
        "--config",
        str(rules_path),
        "--json",
        "--output",
        str(out_json),
    ]
    
    # If target_files provided, scan only those files (PR diff mode)
    if target_files:
        # Semgrep can take multiple file paths
        for file_path in target_files:
            full_path = repo_path / file_path if not Path(file_path).is_absolute() else Path(file_path)
            if full_path.exists():
                cmd.append(str(full_path))
    else:
        # Full repo scan
        cmd.append(str(repo_path))
    
    run(cmd, cwd=repo_path)
    raw = out_json.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    return json.loads(text)


def get_pr_diff_files(repo_path: Path, base_branch: str, head_branch: str) -> list[str]:
    """
    Get list of changed files in PR diff.
    
    Args:
        repo_path: Path to repository root
        base_branch: Base branch (e.g., 'main')
        head_branch: Head branch (PR branch)
    
    Returns:
        List of relative file paths that changed
    """
    # Fetch latest changes
    run(["git", "fetch", "origin", base_branch, head_branch], cwd=repo_path)
    
    # Get diff between base and head
    result = run(
        ["git", "diff", "--name-only", f"origin/{base_branch}...origin/{head_branch}"],
        cwd=repo_path,
    )
    
    changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return changed_files


def get_pr_diff_files_local(repo_path: Path, base_ref: str, head_ref: str) -> list[str]:
    """
    Get list of changed files between two git refs (local).
    
    Args:
        repo_path: Path to repository root
        base_ref: Base git ref (commit, branch, etc.)
        head_ref: Head git ref
    
    Returns:
        List of relative file paths that changed
    """
    result = run(
        ["git", "diff", "--name-only", base_ref, head_ref],
        cwd=repo_path,
    )
    
    changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return changed_files
