"""
GitHub App authentication for Fixpoint.
Creates JWT and exchanges for installation access tokens.
Used when Fixpoint runs as a GitHub App (SaaS) instead of self-hosted webhook.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Lazy import to avoid requiring PyJWT when not using GitHub App mode
_JWT_MODULE = None
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Azure Key Vault helpers
# ---------------------------------------------------------------------------

_KV_URL = os.getenv("AZURE_KEY_VAULT_URL", "").rstrip("/")
_KV_SECRET_PRIVATE_KEY = os.getenv("AZURE_KV_SECRET_PRIVATE_KEY", "github-app-private-key")
_KV_SECRET_WEBHOOK = os.getenv("AZURE_KV_SECRET_WEBHOOK", "github-webhook-secret")


@lru_cache(maxsize=16)
def _load_from_key_vault(secret_name: str) -> Optional[str]:
    """
    Retrieve *secret_name* from Azure Key Vault.

    Uses ``azure-identity`` DefaultAzureCredential (supports Managed Identity,
    environment credentials, VS Code / CLI credentials in dev).

    Returns:
        Secret value string, or None on any error.

    Results are cached in-process to avoid repeated network calls.
    In production the worker is restarted regularly so stale caching is not
    a concern; for key rotation bump the pod.
    """
    if not _KV_URL:
        return None
    try:
        from azure.identity import DefaultAzureCredential  # type: ignore
        from azure.keyvault.secrets import SecretClient  # type: ignore

        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=_KV_URL, credential=credential)
        secret = client.get_secret(secret_name)
        value = secret.value
        if value:
            _log.info("Loaded secret '%s' from Azure Key Vault", secret_name)
        return value or None
    except ImportError:
        _log.debug(
            "azure-identity / azure-keyvault-secrets not installed; "
            "skipping Key Vault lookup for '%s'",
            secret_name,
        )
        return None
    except Exception as exc:
        _log.warning("Key Vault lookup failed for '%s': %s", secret_name, exc)
        return None


def get_secret_from_key_vault(secret_name: str) -> Optional[str]:
    """Public wrapper for Key Vault lookup (used by webhook server)."""
    return _load_from_key_vault(secret_name)


def get_webhook_secret_from_kv() -> Optional[str]:
    """
    Load the GitHub webhook secret from Azure Key Vault.

    Returns None when Key Vault is not configured or the secret is absent.
    """
    if not _KV_URL:
        return None
    return _load_from_key_vault(_KV_SECRET_WEBHOOK)


def _load_private_key() -> Optional[str]:
    """
    Load the GitHub App private key from the highest-priority source available.

    Priority (first non-empty value wins):
    1. Azure Key Vault (secret name from ``AZURE_KV_SECRET_PRIVATE_KEY``,
       requires ``AZURE_KEY_VAULT_URL`` to be set).
    2. Raw PEM string in ``GITHUB_APP_PRIVATE_KEY`` env var.
    3. File path — ``GITHUB_APP_PRIVATE_KEY_PATH``, then Docker secret paths
       (``/run/secrets/...`` and ``/var/run/secrets/...``).
    4. Base64-encoded PEM in ``GITHUB_APP_PRIVATE_KEY_PEM_BASE64``.
    """
    # 1) Azure Key Vault (production — most secure)
    if _KV_URL:
        kv_key = _load_from_key_vault(_KV_SECRET_PRIVATE_KEY)
        if kv_key:
            return kv_key

    # 2) Raw PEM string in env
    raw_key = os.getenv("GITHUB_APP_PRIVATE_KEY")
    if raw_key:
        return raw_key

    # 3) File path (supports Docker secret mounts)
    path_env = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
    secret_paths = [p for p in [path_env, "/run/secrets/github_app_private_key", "/var/run/secrets/github_app_private_key"] if p]
    for candidate in secret_paths:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            try:
                return candidate_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                _log.warning("Failed to read private key from %s: %s", candidate, e)

    # 4) Base64-encoded PEM
    b64_key = os.getenv("GITHUB_APP_PRIVATE_KEY_PEM_BASE64")
    if b64_key:
        try:
            # Strip whitespace/newlines before decode
            cleaned = "".join(b64_key.split())
            decoded = base64.b64decode(cleaned)
            return decoded.decode("utf-8", errors="replace")
        except Exception as e:
            _log.warning("Failed to decode base64 private key: %s", e)

    return None



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

    private_key = _load_private_key()
    if not private_key or not private_key.strip():
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
        _log.warning("Failed to create GitHub App JWT: %s", e)
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
        _log.warning("Failed to get installation token: %s", e)
        return None


def is_github_app_configured() -> bool:
    """Check if GitHub App auth is configured (APP_ID + private key)."""
    app_id = os.getenv("GITHUB_APP_ID")
    if not app_id:
        return False
    return _load_private_key() is not None
