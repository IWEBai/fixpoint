"""
Git operations for Fixpoint.
Supports both creating new branches and pushing to existing PR branches.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a command and raise a readable error if it fails."""
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


def setup_git_identity(repo_path: Path) -> None:
    """Ensure git identity exists (required on GitHub Actions runners)."""
    run(
        ["git", "config", "user.email", "fixpoint-bot@users.noreply.github.com"],
        cwd=repo_path,
    )
    run(
        ["git", "config", "user.name", "fixpoint-bot"],
        cwd=repo_path,
    )


def commit_and_push_new_branch(
    repo_path: Path,
    branch_name: str,
    commit_message: str,
) -> bool:
    """
    Create a new branch, commit changes, and push.
    
    Returns:
        True if changes were committed and pushed, False if no changes
    """
    setup_git_identity(repo_path)
    
    # Create branch
    run(["git", "checkout", "-B", branch_name], cwd=repo_path)
    
    # Stage changes
    run(["git", "add", "."], cwd=repo_path)
    
    # Check if there are changes
    status = run(["git", "status", "--porcelain"], cwd=repo_path)
    if not status.stdout.strip():
        return False
    
    # Commit and push
    run(
        ["git", "commit", "-m", commit_message],
        cwd=repo_path,
    )
    run(["git", "push", "-u", "origin", branch_name], cwd=repo_path)
    return True


def commit_and_push_to_existing_branch(
    repo_path: Path,
    branch_name: str,
    commit_message: str,
) -> bool:
    """
    Commit changes to existing branch and push (for PR updates).
    
    Returns:
        True if changes were committed and pushed, False if no changes
    
    Raises:
        subprocess.CalledProcessError: If git operations fail (e.g., branch protection)
    """
    setup_git_identity(repo_path)
    
    # Checkout the branch (fetch first to ensure we have latest)
    run(["git", "fetch", "origin", branch_name], cwd=repo_path)
    run(["git", "checkout", branch_name], cwd=repo_path)
    run(["git", "pull", "origin", branch_name], cwd=repo_path)
    
    # Stage changes
    run(["git", "add", "."], cwd=repo_path)
    
    # Check if there are changes
    status = run(["git", "status", "--porcelain"], cwd=repo_path)
    if not status.stdout.strip():
        return False
    
    # Commit and push (may raise CalledProcessError on branch protection)
    run(
        ["git", "commit", "-m", commit_message],
        cwd=repo_path,
    )
    run(["git", "push", "origin", branch_name], cwd=repo_path)
    return True


def generate_branch_name(prefix: str = "autopatcher/fix") -> str:
    """Generate a unique branch name with timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}"
