"""
GitHub status check utilities for Fixpoint.
Sets status checks to make Fixpoint a true "gate" in GitHub.
"""
from __future__ import annotations

import os
from typing import Optional
from github import Github, Auth
from dotenv import load_dotenv

load_dotenv()


def set_status_check(
    owner: str,
    repo: str,
    sha: str,
    state: str,
    description: str,
    context: str = "fixpoint/compliance",
    target_url: Optional[str] = None,
) -> bool:
    """
    Set GitHub status check for a commit.
    
    Args:
        owner: Repository owner
        repo: Repository name
        sha: Commit SHA
        state: "success", "failure", "error", or "pending"
        description: Status description
        context: Status check context (default: "auditshield/compliance")
        target_url: Optional URL for more details
    
    Returns:
        True if successful, False otherwise
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not found, cannot set status check")
        return False
    
    try:
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        
        # Create status
        r.get_commit(sha).create_status(
            state=state,
            target_url=target_url,
            description=description,
            context=context,
        )
        
        return True
        
    except Exception as e:
        print(f"Warning: Failed to set status check: {e}")
        return False


def set_compliance_status(
    owner: str,
    repo: str,
    sha: str,
    violations_found: int,
    violations_fixed: int,
    pr_url: Optional[str] = None,
) -> bool:
    """
    Set compliance status check based on violations.
    
    Logic:
    - PASS if no violations found
    - FAIL if violations found and not fixed
    - PASS if violations found and fixed by bot
    
    Args:
        owner: Repository owner
        repo: Repository name
        sha: Commit SHA
        violations_found: Number of violations found
        violations_fixed: Number of violations fixed
        pr_url: Optional PR URL for context
    
    Returns:
        True if successful
    """
    if violations_found == 0:
        # No violations - PASS
        return set_status_check(
            owner=owner,
            repo=repo,
            sha=sha,
            state="success",
            description="No compliance violations found",
            target_url=pr_url,
        )
    elif violations_fixed >= violations_found:
        # All violations fixed - PASS
        return set_status_check(
            owner=owner,
            repo=repo,
            sha=sha,
            state="success",
            description=f"All {violations_found} violation(s) fixed",
            target_url=pr_url,
        )
    else:
        # Violations remain - FAIL
        remaining = violations_found - violations_fixed
        return set_status_check(
            owner=owner,
            repo=repo,
            sha=sha,
            state="failure",
            description=f"{remaining} compliance violation(s) remain",
            target_url=pr_url,
        )
