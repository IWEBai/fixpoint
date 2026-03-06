"""
Rate limiting utilities for Fixpoint webhook server.
Prevents DDoS on synchronize storms.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Dict, Tuple

from core.cache import get_redis_client


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
    redis_client = get_redis_client()
    if redis_client:
        redis_key = f"railo:rate:{key}"
        try:
            current = int(redis_client.incr(redis_key))
            if current == 1:
                redis_client.expire(redis_key, window_seconds)
            remaining = max(0, max_requests - current)
            return current <= max_requests, remaining
        except Exception:
            # Fall back to in-memory rate limiting on Redis errors
            pass

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
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.delete(f"railo:rate:{key}")
        except Exception:
            pass
    if key in _rate_limit_store:
        del _rate_limit_store[key]


# ---------------------------------------------------------------------------
# Per-user dashboard API rate limiting
# ---------------------------------------------------------------------------

# 120 requests per minute per authenticated user (generous for a dashboard)
_DASHBOARD_MAX_REQUESTS = int(os.getenv("DASHBOARD_API_RATE_LIMIT", "120"))
_DASHBOARD_WINDOW = 60  # seconds


def check_dashboard_rate_limit(user_login: str) -> tuple[bool, int]:
    """Rate-limit dashboard /api/* requests per GitHub user login.

    Returns:
        (is_allowed, remaining) — same semantics as :func:`check_rate_limit`.
    """
    key = f"dashboard:{user_login}"
    return check_rate_limit(key, max_requests=_DASHBOARD_MAX_REQUESTS, window_seconds=_DASHBOARD_WINDOW)


# ---------------------------------------------------------------------------
# GitHub API retry wrapper
# ---------------------------------------------------------------------------

import logging as _logging

_gh_logger = _logging.getLogger(__name__)

# GitHub caps check-run annotations at 50 per request.
GITHUB_MAX_ANNOTATIONS = 50

def _parse_wait_seconds(headers: dict | None, attempt: int) -> int:
    """
    Derive the sleep duration from GitHub response headers.

    Priority:
    1. ``Retry-After`` — returned by secondary / abuse-detection rate limits.
    2. ``X-RateLimit-Reset`` — Unix timestamp of primary rate-limit reset.
    3. Exponential back-off as fallback.

    The result is clamped to [1, 300] seconds.
    """
    h = headers or {}

    # Retry-After (integer seconds or HTTP-date; GitHub always sends integer)
    retry_after = h.get("Retry-After") or h.get("retry-after")
    if retry_after:
        try:
            secs = int(retry_after)
            return max(1, min(secs + 2, 300))  # +2 s buffer, capped at 5 min
        except (ValueError, TypeError):
            pass

    # X-RateLimit-Reset (Unix epoch when the primary window resets)
    reset_ts = h.get("X-RateLimit-Reset") or h.get("x-ratelimit-reset")
    if reset_ts:
        try:
            wait = max(1, int(reset_ts) - int(time.time())) + 5  # +5 s buffer
            return min(wait, 300)
        except (ValueError, TypeError):
            pass

    # Exponential back-off: 10, 20, 40, 80, 160 s
    return min(10 * (2 ** attempt), 300)


def call_github_api(fn, *args, max_attempts: int = 5, **kwargs):
    """
    Call a PyGithub API callable with exponential back-off on rate-limit or
    transient server errors.

    Respects both the *primary* rate-limit (``X-RateLimit-Reset``) and
    GitHub's *secondary* / abuse-detection rate-limit (``Retry-After``).

    Usage::

        from core.rate_limit import call_github_api
        repo = call_github_api(g.get_repo, "owner/repo")

    Args:
        fn:            Any callable (typically a PyGithub method).
        *args:         Positional arguments forwarded to *fn*.
        max_attempts:  Maximum total attempts before re-raising (default 5).
        **kwargs:      Keyword arguments forwarded to *fn*.

    Returns:
        The return value of *fn*.

    Raises:
        The last exception raised by *fn* after all retry attempts are
        exhausted.
    """
    try:
        from github import RateLimitExceededException, GithubException  # type: ignore
    except ImportError:
        # PyGithub not installed — fall through without retry logic.
        return fn(*args, **kwargs)

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except RateLimitExceededException as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                raise
            wait = _parse_wait_seconds(getattr(exc, "headers", None), attempt)
            _gh_logger.warning(
                "GitHub primary rate limit hit; waiting %ds before retry %d/%d",
                wait,
                attempt + 1,
                max_attempts,
            )
            time.sleep(wait)
        except GithubException as exc:
            last_exc = exc
            headers = getattr(exc, "headers", None)
            # Secondary/abuse rate limit: 403 with Retry-After header.
            is_secondary = exc.status == 403 and (
                (headers or {}).get("Retry-After") or (headers or {}).get("retry-after")
            )
            # Also retry on transient 5xx errors.
            retryable = is_secondary or (exc.status in (500, 502, 503, 504))
            if retryable and attempt < max_attempts - 1:
                wait = _parse_wait_seconds(headers, attempt)
                _gh_logger.warning(
                    "GitHub %s (status %d); waiting %ds (attempt %d/%d)",
                    "secondary rate limit" if is_secondary else "transient error",
                    exc.status,
                    wait,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(wait)
            else:
                raise

    # Should be unreachable, but satisfy type-checkers.
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Global worker concurrency throttle
# ---------------------------------------------------------------------------

# Maximum simultaneous scan jobs across all worker processes.
# Override with RAILO_WORKER_MAX_CONCURRENT env var (0 = unlimited).
_WORKER_MAX_CONCURRENT = int(os.getenv("RAILO_WORKER_MAX_CONCURRENT", "10"))
_WORKER_SLOT_KEY = "railo:worker:active"
_WORKER_SLOT_TTL = 900  # 15 min — safety expiry so crashed workers release slots


def acquire_worker_slot(timeout_seconds: int = 30) -> bool:
    """
    Acquire a global worker concurrency slot before starting a scan job.

    Uses a Redis atomic counter so the limit is enforced across all worker
    processes.  Falls back gracefully (returns True) when Redis is unavailable
    or the limit is 0 (unlimited).

    Args:
        timeout_seconds: How long to wait for a free slot before giving up.

    Returns:
        True  — slot acquired, caller may proceed.
        False — concurrency limit reached; caller should defer or fail fast.
    """
    if _WORKER_MAX_CONCURRENT <= 0:
        return True  # unlimited

    redis_client = get_redis_client()
    if not redis_client:
        return True  # no Redis — allow through

    deadline = time.time() + timeout_seconds
    poll = 1
    while time.time() < deadline:
        try:
            # Atomic increment
            current = int(redis_client.incr(_WORKER_SLOT_KEY))
            if current == 1:
                redis_client.expire(_WORKER_SLOT_KEY, _WORKER_SLOT_TTL)
            if current <= _WORKER_MAX_CONCURRENT:
                # Slot acquired — refresh TTL so long-running jobs don't expire
                redis_client.expire(_WORKER_SLOT_KEY, _WORKER_SLOT_TTL)
                return True
            # Over limit — release the increment we just added
            redis_client.decr(_WORKER_SLOT_KEY)
        except Exception as e:
            _gh_logger.debug("Worker slot check failed (Redis error): %s", e)
            return True  # Redis down — allow through
        time.sleep(poll)
        poll = min(poll * 2, 10)

    _gh_logger.warning(
        "Worker concurrency limit %d reached; job deferred after %ds wait",
        _WORKER_MAX_CONCURRENT,
        timeout_seconds,
    )
    return False


def release_worker_slot() -> None:
    """
    Release a previously acquired global worker concurrency slot.

    Safe to call even when Redis is unavailable (no-op).
    """
    if _WORKER_MAX_CONCURRENT <= 0:
        return

    redis_client = get_redis_client()
    if not redis_client:
        return
    try:
        new_val = redis_client.decr(_WORKER_SLOT_KEY)
        if new_val < 0:
            redis_client.set(_WORKER_SLOT_KEY, 0)
    except Exception:
        pass
