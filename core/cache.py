"""
Result caching utilities for Fixpoint scans.

Supports two backends:
1. File-based cache (default): `.fixpoint_cache/` directory in repo
2. Redis cache (optional): If REDIS_URL env var is set, use Redis instead

Cache keys are derived from (repo_sha, rule_version_hash).
Values are full Semgrep JSON result dicts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any


CACHE_DIR_NAME = ".fixpoint_cache"

# Redis support (optional)
_redis_client: Optional[Any] = None
_redis_available = False


def _init_redis() -> bool:
    """Initialize Redis client if REDIS_URL is configured."""
    global _redis_client, _redis_available
    
    if _redis_available:
        return True
    
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return False
    
    try:
        import redis
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        # Test connection
        _redis_client.ping()
        _redis_available = True
        return True
    except ImportError:
        # redis package not installed
        return False
    except Exception:
        # Redis connection failed - fall back to file cache
        _redis_client = None
        _redis_available = False
        return False


def _get_cache_dir(repo_path: Path) -> Path:
    repo_path = Path(repo_path)
    cache_dir = repo_path / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def compute_rules_version(rules_path: Path) -> str:
    """
    Compute a content hash representing the current ruleset.

    For a single YAML file, we hash its contents. For a directory,
    we hash all *.yml / *.yaml files (path + contents).
    """
    rules_path = Path(rules_path)
    h = hashlib.sha256()

    if rules_path.is_file():
        try:
            data = rules_path.read_bytes()
            h.update(rules_path.name.encode("utf-8", errors="replace"))
            h.update(b"\0")
            h.update(data)
        except OSError:
            pass
    elif rules_path.is_dir():
        for p in sorted(rules_path.rglob("*.yml")) + sorted(rules_path.rglob("*.yaml")):
            try:
                h.update(str(p.relative_to(rules_path)).encode("utf-8", errors="replace"))
                h.update(b"\0")
                h.update(p.read_bytes())
            except OSError:
                continue
    else:
        h.update(str(rules_path).encode("utf-8", errors="replace"))

    return h.hexdigest()


def _make_key(repo_sha: str, rule_version: str) -> str:
    raw = f"{repo_sha}:{rule_version}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def get_cached_scan(
    repo_path: Path,
    repo_sha: str,
    rule_version: str,
) -> Optional[Dict[str, Any]]:
    """
    Return cached Semgrep scan results for (repo_sha, rule_version), if any.

    Only used for full-repo scans (not PR-diff mode) to keep semantics simple.
    
    Tries Redis first (if configured), then falls back to file-based cache.
    """
    cache_key = _make_key(repo_sha, rule_version)
    
    # Try Redis cache first
    if _init_redis() and _redis_client:
        try:
            cached_json = _redis_client.get(f"fixpoint:scan:{cache_key}")
            if cached_json:
                return json.loads(cached_json)
        except Exception:
            # Redis error - fall through to file cache
            pass
    
    # Fall back to file-based cache
    cache_dir = _get_cache_dir(repo_path)
    cache_file = cache_dir / f"{cache_key}.json"
    if not cache_file.exists():
        return None
    try:
        text = cache_file.read_text(encoding="utf-8", errors="replace")
        return json.loads(text)
    except Exception:
        return None


def cache_scan(
    repo_path: Path,
    repo_sha: str,
    rule_version: str,
    results: Dict[str, Any],
) -> None:
    """
    Persist Semgrep scan results into cache.
    
    Uses Redis if configured, otherwise falls back to file-based cache.
    Cache failures are non-fatal and silently ignored.
    """
    cache_key = _make_key(repo_sha, rule_version)
    results_json = json.dumps(results, indent=2)
    
    # Try Redis cache first
    if _init_redis() and _redis_client:
        try:
            # Set TTL to 7 days (604800 seconds) to prevent unbounded growth
            _redis_client.setex(
                f"fixpoint:scan:{cache_key}",
                604800,  # 7 days
                results_json,
            )
            return  # Successfully cached in Redis
        except Exception:
            # Redis error - fall through to file cache
            pass
    
    # Fall back to file-based cache
    cache_dir = _get_cache_dir(repo_path)
    cache_file = cache_dir / f"{cache_key}.json"
    try:
        cache_file.write_text(
            results_json,
            encoding="utf-8",
        )
    except Exception:
        # Cache failures are non-fatal
        return

