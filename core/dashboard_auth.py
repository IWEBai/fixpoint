"""
GitHub OAuth for Fixpoint dashboard.
Enables users to log in and view installations/runs.
"""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlencode

import requests


def get_oauth_authorize_url(state: str) -> str:
    """Build GitHub OAuth authorization URL."""
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
    base_url = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
    redirect_uri = f"{base_url}/dashboard/callback"
    scope = "read:user"
    return (
        "https://github.com/login/oauth/authorize?"
        + urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        })
    )


def exchange_code_for_token(code: str, state: str) -> Optional[dict]:
    """
    Exchange OAuth code for access token.
    Returns dict with access_token, scope, token_type.
    """
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    base_url = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
    redirect_uri = f"{base_url}/dashboard/callback"

    resp = requests.post(
        "https://github.com/login/oauth/access_token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "state": state,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("error"):
        return None
    return data


def get_user_info(access_token: str) -> Optional[dict]:
    """Get current user from GitHub API."""
    resp = requests.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def get_user_installations(access_token: str) -> list[dict]:
    """
    Get installations the user has access to (GitHub API).
    Returns list of {id, account: {login, type}, ...}.
    Note: Requires user-to-server token; for OAuth App tokens this may return [].
    """
    try:
        resp = requests.get(
            "https://api.github.com/user/installations",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("installations", [])
    except Exception:
        return []


def is_oauth_configured() -> bool:
    """Check if OAuth is configured."""
    return bool(
        os.getenv("GITHUB_OAUTH_CLIENT_ID")
        and os.getenv("GITHUB_OAUTH_CLIENT_SECRET")
        and os.getenv("DASHBOARD_SESSION_SECRET")
    )
