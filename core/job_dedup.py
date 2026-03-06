"""Simple Redis-based job deduplication for PR processing."""
from __future__ import annotations

import os
from typing import Optional

try:  # pragma: no cover - optional dependency surface
    from redis import Redis
except Exception:  # pragma: no cover
    Redis = None  # type: ignore


def _get_redis_client() -> Optional["Redis"]:
    if Redis is None:
        return None
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        return Redis.from_url(url)
    except Exception:
        return None


def get_dedup_key(owner: str, repo: str, pr_number: int, head_sha: str) -> str:
    return f"{owner}:{repo}:{pr_number}:{head_sha}"


def is_already_processing(dedup_key: str) -> bool:
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.exists(f"processing:{dedup_key}"))
    except Exception:
        return False


def mark_processing(dedup_key: str, ttl_seconds: int = 1800) -> bool:
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(
            client.set(
                f"processing:{dedup_key}",
                "1",
                nx=True,
                ex=ttl_seconds,
            )
        )
    except Exception:
        return False


def unmark_processing(dedup_key: str) -> bool:
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.delete(f"processing:{dedup_key}"))
    except Exception:
        return False
