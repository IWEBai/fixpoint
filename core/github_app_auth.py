"""
GitHub App authentication for Fixpoint.
Creates JWT and exchanges for installation access tokens.
Used when Fixpoint runs as a GitHub App (SaaS) instead of self-hosted webhook.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

# Lazy import to avoid requiring PyJWT when not using GitHub App mode
_JWT_MODULE = None


def _get_jwt_module():
    """Lazy load PyJWT to avoid import errors when not in app mode."""
    global _JWT_MODULE
    if _JWT_MODULE is None:
        try:
            import jwt as _jwt
            _JWT_MODULE = _jwt
        except ImportError:
            raise ImportError(
                "PyJWT is required for GitHub App mode. Install with: pip install PyJWT[crypto]"
            )
    return _JWT_MODULE


def get_installation_access_token(installation_id: int) -> Optional[str]:
    """
    Generate a JWT and exchange it for an installation access token.

    Requires GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY (or GITHUB_APP_PRIVATE_KEY_PATH)
    environment variables.

    Args:
        installation_id: GitHub App installation ID from webhook payload

    Returns:
        Installation access token string, or None if auth fails
    """
    app_id = os.getenv("GITHUB_APP_ID")
    if not app_id:
        return None

    private_key = os.getenv("GITHUB_APP_PRIVATE_KEY")
    if not private_key:
        key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
        if key_path and Path(key_path).exists():
            private_key = Path(key_path).read_text(encoding="utf-8", errors="replace")
        else:
            return None

    if not private_key.strip():
        return None

    try:
        jwt_module = _get_jwt_module()
        now = int(time.time())
        payload = {
            "iat": now - 60,  # 60 seconds in past (clock drift)
            "exp": now + 600,  # 10 minutes max
            "iss": app_id.strip(),
        }
        encoded_jwt = jwt_module.encode(
            payload,
            private_key,
            algorithm="RS256",
        )
        if hasattr(encoded_jwt, "decode"):
            encoded_jwt = encoded_jwt.decode("utf-8")
    except Exception as e:
        print(f"Warning: Failed to create GitHub App JWT: {e}")
        return None

    # Exchange JWT for installation token
    try:
        import urllib.request
        import json as _json

        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        req = urllib.request.Request(
            url,
            data=b"",
            headers={
                "Authorization": f"Bearer {encoded_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
            return data.get("token")
    except Exception as e:
        print(f"Warning: Failed to get installation token: {e}")
        return None


def is_github_app_configured() -> bool:
    """Check if GitHub App auth is configured (APP_ID + private key)."""
    app_id = os.getenv("GITHUB_APP_ID")
    if not app_id:
        return False
    if os.getenv("GITHUB_APP_PRIVATE_KEY"):
        return True
    key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
    return bool(key_path and Path(key_path).exists())
