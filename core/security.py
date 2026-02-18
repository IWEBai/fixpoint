"""
Security utilities for Fixpoint webhook server.
Handles signature verification, event filtering, and replay protection.
"""
from __future__ import annotations

import os
import re
import hmac
import hashlib
from typing import Optional, Tuple
from datetime import datetime, timedelta, timezone


# In-memory store for processed delivery IDs (in production, use Redis)
_processed_deliveries: dict[str, datetime] = {}
DELIVERY_ID_TTL = timedelta(hours=24)  # Remember deliveries for 24 hours


def verify_webhook_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """
    Verify GitHub webhook signature using HMAC-SHA256.
    
    Args:
        payload_body: Raw request body bytes
        signature: X-Hub-Signature-256 header value
        secret: Webhook secret from environment
    
    Returns:
        True if signature is valid, False otherwise
    """
    if not secret:
        # SECURITY: Always require webhook secret in all environments
        # For local testing only, explicitly set SKIP_WEBHOOK_VERIFICATION=true
        if os.getenv("SKIP_WEBHOOK_VERIFICATION", "").lower() == "true":
            print("WARNING: SKIP_WEBHOOK_VERIFICATION=true - skipping signature verification (NEVER use in production!)")
            return True
        print("ERROR: WEBHOOK_SECRET not set - rejecting request")
        return False
    
    if not signature:
        return False
    
    # GitHub sends signature as "sha256=<hexdigest>"
    if not signature.startswith("sha256="):
        return False
    
    expected_signature = hmac.new(
        secret.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    expected_signature = f"sha256={expected_signature}"
    
    return hmac.compare_digest(signature, expected_signature)


def is_allowed_event_type(event_type: str) -> bool:
    """
    Strict allowlist of allowed GitHub event types.

    Includes installation events for GitHub App lifecycle.
    """
    ALLOWED_EVENTS = {
        "pull_request",
        "installation",
        "installation_repositories",
    }
    return event_type in ALLOWED_EVENTS


def is_allowed_pr_action(action: str) -> bool:
    """
    Strict allowlist of allowed PR actions.
    
    Args:
        action: PR action from webhook payload
    
    Returns:
        True if action is allowed
    """
    ALLOWED_ACTIONS = {"opened", "synchronize"}
    return action in ALLOWED_ACTIONS


def check_replay_protection(delivery_id: str) -> bool:
    """
    Check if this webhook delivery has already been processed (replay protection).
    
    Args:
        delivery_id: X-GitHub-Delivery header value
    
    Returns:
        True if this is a replay (should be rejected), False if new
    """
    if not delivery_id:
        # If no delivery ID, can't protect against replays
        return False
    
    now = datetime.now(timezone.utc)
    
    # Check if we've seen this delivery ID recently
    if delivery_id in _processed_deliveries:
        last_seen = _processed_deliveries[delivery_id]
        if now - last_seen < DELIVERY_ID_TTL:
            return True  # This is a replay
    
    # Record this delivery
    _processed_deliveries[delivery_id] = now
    
    # Clean up old entries (simple cleanup - in production use TTL-based store)
    cutoff = now - DELIVERY_ID_TTL
    expired_keys = [k for k, v in _processed_deliveries.items() if v < cutoff]
    for k in expired_keys:
        del _processed_deliveries[k]

    return False  # New delivery, proceed


def is_repo_allowed(full_repo_name: str) -> tuple[bool, Optional[str]]:
    """
    Check if a repository is allowed to be processed.
    
    Uses ALLOWED_REPOS and DENIED_REPOS environment variables.
    - If ALLOWED_REPOS is set, only those repos are allowed (allowlist mode)
    - If DENIED_REPOS is set, those repos are blocked (denylist mode)
    - If neither is set, all repos are allowed
    
    Args:
        full_repo_name: Repository in "owner/repo" format
    
    Returns:
        Tuple of (is_allowed, reason)
    """
    if not full_repo_name:
        return False, "Repository name is empty"
    
    # Normalize to lowercase for comparison
    full_repo_name = full_repo_name.lower().strip()
    
    # Check denylist first (always takes precedence)
    denied_repos = os.getenv("DENIED_REPOS", "").strip()
    if denied_repos:
        denied_list = [r.lower().strip() for r in denied_repos.split(",") if r.strip()]
        if full_repo_name in denied_list:
            return False, f"Repository '{full_repo_name}' is in the deny list"
    
    # Check allowlist (if configured, only allow listed repos)
    allowed_repos = os.getenv("ALLOWED_REPOS", "").strip()
    if allowed_repos:
        allowed_list = [r.lower().strip() for r in allowed_repos.split(",") if r.strip()]
        if full_repo_name not in allowed_list:
            return False, f"Repository '{full_repo_name}' is not in the allow list"
    
    return True, None


# --- Request sanitization helpers ------------------------------------------------

_SAFE_REPO_OWNER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_SAFE_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def sanitize_repo_owner(owner: str) -> tuple[bool, Optional[str]]:
    """
    Sanitize and validate a GitHub repository owner name.

    Rejects values with path traversal, whitespace, or unexpected characters.

    Returns:
        (is_valid, normalized_owner_or_error)
    """
    if not owner:
        return False, "Repository owner is empty"

    owner = str(owner).strip()

    # Disallow obvious path traversal / control chars
    if ".." in owner or "/" in owner or "\\" in owner or "\n" in owner or "\r" in owner:
        return False, "Repository owner contains invalid characters"

    if not _SAFE_REPO_OWNER_RE.match(owner):
        return False, "Repository owner contains unsupported characters"

    # Normalize to lowercase for consistency
    return True, owner.lower()


def sanitize_repo_name(name: str) -> tuple[bool, Optional[str]]:
    """
    Sanitize and validate a GitHub repository name.

    Rejects values with path traversal, whitespace, or unexpected characters.

    Returns:
        (is_valid, normalized_name_or_error)
    """
    if not name:
        return False, "Repository name is empty"

    name = str(name).strip()

    if ".." in name or "/" in name or "\\" in name or "\n" in name or "\r" in name:
        return False, "Repository name contains invalid characters"

    if not _SAFE_REPO_NAME_RE.match(name):
        return False, "Repository name contains unsupported characters"

    # GitHub repo names are case-sensitive, but we still normalize for logging
    return True, name


def validate_installation_id(installation: dict) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Validate the installation block from a webhook payload.

    Ensures the installation ID is present and well-formed before we call
    GitHub APIs or persist anything.

    Returns:
        (is_valid, installation_id_or_none, error_message)
    """
    if not isinstance(installation, dict):
        return False, None, "Missing or invalid installation payload"

    raw_id = installation.get("id")
    if raw_id is None:
        return False, None, "Missing installation ID"

    try:
        inst_id = int(raw_id)
    except (TypeError, ValueError):
        return False, None, "Installation ID is not a valid integer"

    if inst_id <= 0:
        return False, None, "Installation ID must be a positive integer"

    return True, inst_id, None


def validate_webhook_request(
    payload_body: bytes,
    signature: str,
    event_type: str,
    delivery_id: str,
    secret: str | list[str],
) -> tuple[bool, Optional[str]]:
    """
    Comprehensive webhook request validation.

    Supports both single secret (self-hosted) and multiple secrets
    (GitHub App + self-hosted dual mode).

    Args:
        payload_body: Raw request body
        signature: X-Hub-Signature-256 header
        event_type: X-GitHub-Event header
        delivery_id: X-GitHub-Delivery header
        secret: Webhook secret, or list of secrets to try (app + repo)

    Returns:
        Tuple of (is_valid, error_message)
    """
    # 1. Verify signature (try each secret if list)
    secrets = [secret] if isinstance(secret, str) else (secret or [])
    secrets = [s for s in secrets if s]
    secret_valid = False
    if not secrets:
        # Empty list: fall back to SKIP_WEBHOOK_VERIFICATION (dev only)
        secret_valid = verify_webhook_signature(payload_body, signature, "")
    else:
        for s in secrets:
            if verify_webhook_signature(payload_body, signature, s):
                secret_valid = True
                break
    if not secret_valid:
        return False, "Invalid webhook signature"
    
    # 2. Check event type allowlist
    if not is_allowed_event_type(event_type):
        return False, f"Event type '{event_type}' not allowed"
    
    # 3. Check replay protection
    if check_replay_protection(delivery_id):
        return False, "Duplicate webhook delivery (replay detected)"
    
    return True, None
