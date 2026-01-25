"""
Rate limiting utilities for Fixpoint webhook server.
Prevents DDoS on synchronize storms.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, Tuple
from datetime import datetime, timedelta, timezone


# In-memory rate limit store (in production, use Redis)
_rate_limit_store: Dict[str, list[float]] = defaultdict(list)

# Rate limit configuration
RATE_LIMIT_WINDOW = 60  # 1 minute window
RATE_LIMIT_MAX_REQUESTS = 10  # Max 10 requests per window per key


def check_rate_limit(key: str, max_requests: int = RATE_LIMIT_MAX_REQUESTS, window_seconds: int = RATE_LIMIT_WINDOW) -> Tuple[bool, int]:
    """
    Check if request should be rate limited.
    
    Args:
        key: Rate limit key (e.g., "pr:owner/repo:123")
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds
    
    Returns:
        Tuple of (is_allowed, remaining_requests)
    """
    now = time.time()
    cutoff = now - window_seconds
    
    # Get requests in current window
    requests = _rate_limit_store[key]
    
    # Remove old requests outside window
    requests[:] = [req_time for req_time in requests if req_time > cutoff]
    
    # Check if limit exceeded
    if len(requests) >= max_requests:
        return False, 0
    
    # Add current request
    requests.append(now)
    
    remaining = max_requests - len(requests)
    return True, remaining


def get_rate_limit_key(owner: str, repo: str, pr_number: int) -> str:
    """Generate rate limit key for a PR."""
    return f"pr:{owner}/{repo}:{pr_number}"


def reset_rate_limit(key: str):
    """Reset rate limit for a key (for testing)."""
    if key in _rate_limit_store:
        del _rate_limit_store[key]
