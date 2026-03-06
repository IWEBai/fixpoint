"""
GitHub PR creation utilities for Railo.
Opens a fix PR (or returns the existing open PR for the same head branch).
"""
from __future__ import annotations

import os
from github import Github, Auth  # type: ignore[import-not-found]
from dotenv import load_dotenv

load_dotenv()


def open_or_get_pr(
    owner: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
    labels: list[str] | None = None,
    assignee: str | None = None,
    request_reviewers: list[str] | None = None,
) -> dict:
    """
    Open a new PR or return metadata for an existing PR with the same head/base.

    Returns a dict containing: number, url, html_url, state, created_at, author
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is required")

    try:
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")

        # Check for existing PR with same head branch
        existing_prs = r.get_pulls(state="open", head=f"{owner}:{head}", base=base)
        pr = None
        for existing in existing_prs:
            pr = existing
            break

        if pr is None:
            pr = r.create_pull(
                title=title,
                body=body,
                head=head,
                base=base,
            )

        # Apply labels if provided
        if labels:
            try:
                issue = r.get_issue(number=pr.number)
                issue.add_to_labels(*labels)
            except Exception:
                pass

        # Assign if provided
        if assignee:
            try:
                pr.add_to_assignees(assignee)
            except Exception:
                pass

        # Request reviewers if provided
        if request_reviewers:
            try:
                pr.create_review_request(reviewers=request_reviewers)
            except Exception:
                pass

        return {
            "number": pr.number,
            "url": pr.url,
            "html_url": pr.html_url,
            "state": pr.state,
            "created_at": getattr(pr, "created_at", None),
            "author": getattr(getattr(pr, "user", None), "login", None),
        }

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


def comment_on_pr(owner: str, repo: str, pr_number: int, body: str) -> bool:
    """Add a comment to an existing PR."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return False

    try:
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        pr.create_issue_comment(body)
        return True
    except Exception as e:  # pragma: no cover - defensive
        print(f"Warning: Failed to comment on PR: {e}")
        return False


def add_pr_labels(owner: str, repo: str, pr_number: int, labels: list[str]) -> bool:
    """Add labels to a PR (issues API)."""
    if not labels:
        return True
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return False

    try:
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        issue = r.get_issue(number=pr_number)
        issue.add_to_labels(*labels)
        return True
    except Exception as e:  # pragma: no cover - defensive
        print(f"Warning: Failed to add labels: {e}")
        return False


def request_review_from_users(owner: str, repo: str, pr_number: int, usernames: list[str]) -> bool:
    """Request reviews from specific users."""
    if not usernames:
        return True
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return False
    try:
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        pr.create_review_request(reviewers=usernames)
        return True
    except Exception as e:  # pragma: no cover - defensive
        print(f"Warning: Failed to request reviewers: {e}")
        return False
