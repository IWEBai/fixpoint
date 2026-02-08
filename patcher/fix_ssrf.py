"""
SSRF fixer.
Adds URL validation for requests.get/post with user-controlled URLs.
"""
from __future__ import annotations

from pathlib import Path


def apply_fix_ssrf(repo_path: Path, target_relpath: str) -> bool:
    """
    Add SSRF validation for requests.get(url) patterns.
    
    For now, detection only - full fix requires allowlist configuration.
    """
    # SSRF fix requires domain allowlist/blocklist configuration.
    # Detection is implemented; deterministic fix deferred to config-driven approach.
    return False


def propose_fix_ssrf(repo_path: Path, target_relpath: str) -> list[dict] | None:
    """Propose SSRF fix (warn mode)."""
    return [{
        "file": target_relpath,
        "line": 0,
        "before": "requests.get(user_url)",
        "after": "# Validate URL allowlist before requests.get(user_url)",
    }]
