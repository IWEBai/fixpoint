"""
GitHub PR creation utilities for Fixpoint CLI mode.
Creates or updates pull requests with auto-fix commits.
"""
from __future__ import annotations

import os
from typing import Optional
from github import Github, Auth
from dotenv import load_dotenv

load_dotenv()


def open_or_get_pr(
    owner: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
) -> str:
    """
    Open a new PR or return URL of existing PR for the same branch.
    
    Args:
        owner: Repository owner
        repo: Repository name
        head: Head branch name (the branch with changes)
        base: Base branch name (the branch to merge into)
        title: PR title
        body: PR description
    
    Returns:
        PR URL (either new or existing)
    
    Raises:
        ValueError: If GITHUB_TOKEN is not set
        RuntimeError: If PR creation fails
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is required")
    
    try:
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        
        # Check for existing PR with same head branch
        existing_prs = r.get_pulls(state="open", head=f"{owner}:{head}", base=base)
        
        for pr in existing_prs:
            # Found existing PR, return its URL
            print(f"Found existing PR: #{pr.number}")
            return pr.html_url
        
        # Create new PR
        pr = r.create_pull(
            title=title,
            body=body,
            head=head,
            base=base,
        )
        
        print(f"Created PR: #{pr.number}")
        return pr.html_url
        
    except Exception as e:
        raise RuntimeError(f"Failed to create/find PR: {e}")


def update_pr_body(
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
) -> bool:
    """
    Update PR description.
    
    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: PR number
        body: New PR description
    
    Returns:
        True if successful
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return False
    
    try:
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        
        pr.edit(body=body)
        return True
        
    except Exception as e:
        print(f"Warning: Failed to update PR body: {e}")
        return False
