"""
Git operations for Fixpoint.
Supports both creating new branches and pushing to existing PR branches.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from datetime import datetime, timezone


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


def run_tests(repo_path: Path, command: str, timeout: int = 300) -> tuple[bool, str]:
    """
    Run test command before commit (safety rail).
    
    Args:
        repo_path: Path to repository
        command: Shell command to run (e.g. "pytest", "npm test")
        timeout: Max seconds to wait
    
    Returns:
        Tuple of (success, output_or_error_message)
    """
    import shlex
    import subprocess
    
    try:
        parts = shlex.split(command)
        result = subprocess.run(
            parts,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return True, result.stdout or ""
        return False, result.stderr or result.stdout or f"Exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"Test command timed out after {timeout}s"
    except FileNotFoundError:
        return False, f"Command not found: {command.split()[0] if command else command}"
    except Exception as e:
        return False, str(e)


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


def commit_with_rollback(
    repo_path: Path,
    branch_name: str,
    commit_message: str,
    test_command: str | None = None,
    test_timeout: int = 300,
) -> tuple[bool, str | None]:
    """
    Commit and push changes with an optional pre-commit test step.

    Semantics (two-phase with rollback):
    - Always commit and push first (using commit_and_push_to_existing_branch).
    - If test_command is provided, run tests *after* the commit.
      - If tests pass, keep the commit and return (True, None).
      - If tests fail, automatically create a rollback commit using
        `git revert` and push it, then return (False, error_message).
 
    This centralises the \"commit + tests + rollback\" safety rail so both
    the GitHub Action and webhook paths use the same behaviour.

    Returns:
        (success, error_message_or_None)
    """
    repo_path = Path(repo_path)

    try:
        # First phase: commit and push changes to the existing branch
        changed = commit_and_push_to_existing_branch(
            repo_path,
            branch_name,
            commit_message,
        )
        if not changed:
            return False, "No changes to commit"

        # Second phase: optionally run tests and rollback on failure
        if not test_command:
            return True, None

        ok, output = run_tests(repo_path, test_command, timeout=test_timeout)
        if ok:
            return True, None

        # Tests failed – attempt rollback by reverting the last commit
        try:
            last_commit = run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
            ).stdout.strip()
            if last_commit:
                # Create a revert commit and push it so remote state is clean
                run(
                    ["git", "revert", "--no-edit", last_commit],
                    cwd=repo_path,
                )
                run(
                    ["git", "push", "origin", branch_name],
                    cwd=repo_path,
                )
            msg = (output or "Tests failed after commit")[:500]
            return False, f"Tests failed after commit; rollback applied: {msg}"
        except Exception as revert_err:
            msg = (output or "Tests failed after commit")[:300]
            return False, (
                f"Tests failed after commit and rollback failed: {msg} "
                f"(rollback error: {revert_err})"
            )
    except Exception as e:
        return False, str(e)

