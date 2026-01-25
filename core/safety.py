"""
Safety and trust mechanisms for Fixpoint.
Handles idempotency, loop prevention, and confidence gating.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional


def compute_fix_idempotency_key(
    pr_number: int,
    head_sha: str,
    finding: dict,
) -> str:
    """
    Compute idempotency key for a fix to prevent re-applying same fix.
    
    Args:
        pr_number: PR number
        head_sha: Current HEAD commit SHA
        finding: Semgrep finding dict
    
    Returns:
        Unique idempotency key
    """
    # Combine PR number, commit SHA, file path, and line number
    file_path = finding.get("path", "")
    start_line = finding.get("start", {}).get("line", 0)
    check_id = finding.get("check_id", "")
    
    key_data = {
        "pr": pr_number,
        "sha": head_sha,
        "file": file_path,
        "line": start_line,
        "check": check_id,
    }
    
    key_str = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(key_str.encode()).hexdigest()


def is_bot_commit(commit_message: str, commit_author: str) -> bool:
    """
    Check if a commit was made by Fixpoint bot.
    
    Uses canonical marker "[fixpoint]" in commit message and bot author.
    This prevents false positives from normal commits containing words like "autopatch".
    
    Args:
        commit_message: Git commit message
        commit_author: Git commit author email/name
    
    Returns:
        True if this is a bot commit
    """
    # Canonical marker: all bot commits must start with "[fixpoint]"
    if commit_message.strip().startswith("[fixpoint]"):
        return True
    
    # Also check author (canonical bot identity)
    author_lower = commit_author.lower()
    if "fixpoint-bot" in author_lower:
        return True
    
    return False


def check_loop_prevention(repo_path: Path, head_sha: str) -> bool:
    """
    Check if the latest commit is from Fixpoint bot.
    If so, skip processing to prevent infinite loops.
    
    Args:
        repo_path: Path to repository
        head_sha: Current HEAD commit SHA
    
    Returns:
        True if we should skip (bot commit detected), False to proceed
    """
    import subprocess
    
    try:
        # Get latest commit info
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%s%n%ae", head_sha],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            commit_message = lines[0]
            commit_author = lines[1]
            
            if is_bot_commit(commit_message, commit_author):
                return True  # Skip - this is a bot commit
    except Exception:
        # If we can't check, err on the side of caution and proceed
        pass
    
    return False  # Proceed with processing


def has_recent_bot_commit(repo_path: Path, max_commits: int = 5) -> bool:
    """
    Check if any of the recent commits are from Fixpoint bot.
    
    Args:
        repo_path: Path to repository
        max_commits: Number of recent commits to check
    
    Returns:
        True if recent bot commit found
    """
    import subprocess
    
    try:
        # Get recent commits
        result = subprocess.run(
            ["git", "log", f"-{max_commits}", "--pretty=format:%s%n%ae"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        lines = result.stdout.strip().split("\n")
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                commit_message = lines[i]
                commit_author = lines[i + 1]
                
                if is_bot_commit(commit_message, commit_author):
                    return True
    except Exception:
        pass
    
    return False


def check_confidence_gating(finding: dict) -> bool:
    """
    Gate fixes based on confidence level.
    Only apply fixes when confidence is high.
    
    Args:
        finding: Semgrep finding dict
    
    Returns:
        True if confidence is high enough to apply fix
    """
    # Check metadata confidence
    metadata = finding.get("extra", {}).get("metadata", {})
    confidence = metadata.get("confidence", "medium")
    
    # Only proceed if confidence is "high"
    if confidence == "high":
        return True
    
    # Also check severity - only fix ERROR level issues
    severity = finding.get("extra", {}).get("severity", "INFO")
    if severity == "ERROR":
        # Even if confidence isn't explicitly "high", ERROR severity is high confidence
        return True
    
    return False
