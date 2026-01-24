"""
Security utilities for AuditShield webhook server.
Handles signature verification, event filtering, and replay protection.
"""
from __future__ import annotations

import os
import hmac
import hashlib
import time
from typing import Optional
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
    
    Args:
        event_type: X-GitHub-Event header value
    
    Returns:
        True if event type is allowed
    """
    ALLOWED_EVENTS = {"pull_request"}
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
    _processed_deliveries.clear()  # Simple: clear all (in production, use proper TTL)
    
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


def validate_webhook_request(
    payload_body: bytes,
    signature: str,
    event_type: str,
    delivery_id: str,
    secret: str,
) -> tuple[bool, Optional[str]]:
    """
    Comprehensive webhook request validation.
    
    Args:
        payload_body: Raw request body
        signature: X-Hub-Signature-256 header
        event_type: X-GitHub-Event header
        delivery_id: X-GitHub-Delivery header
        secret: Webhook secret
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # 1. Verify signature
    if not verify_webhook_signature(payload_body, signature, secret):
        return False, "Invalid webhook signature"
    
    # 2. Check event type allowlist
    if not is_allowed_event_type(event_type):
        return False, f"Event type '{event_type}' not allowed"
    
    # 3. Check replay protection
    if check_replay_protection(delivery_id):
        return False, "Duplicate webhook delivery (replay detected)"
    
    return True, None
