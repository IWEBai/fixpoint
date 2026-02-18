"""
GitHub Code Scanning SARIF upload utilities for Fixpoint.

Provides a thin wrapper around the
`POST /repos/{owner}/{repo}/code-scanning/sarifs` API.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def upload_sarif_to_github(
    owner: str,
    repo: str,
    sarif_path: Path,
    commit_sha: str,
    ref: str,
    github_token: Optional[str] = None,
) -> Optional[str]:
    """
    Upload a SARIF file to GitHub Code Scanning.

    GitHub expects the SARIF JSON to be gzipped and base64-encoded.

    Returns:
        The SARIF upload ID on success, or None on failure.
    """
    import base64
    import gzip
    import json
    import os

    try:
        import requests  # type: ignore[import-not-found]
    except Exception:
        # Soft-fail when requests is not available; callers should treat
        # this as "best-effort" rather than fatal.
        print("Warning: requests not installed, skipping SARIF upload")
        return None

    sarif_path = Path(sarif_path)
    if not sarif_path.exists():
        return None

    token = github_token or os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set, skipping SARIF upload")
        return None

    try:
        raw = sarif_path.read_bytes()
        gzipped = gzip.compress(raw)
        encoded = base64.b64encode(gzipped).decode("ascii")
    except Exception as e:
        print(f"Warning: failed to read/compress SARIF file: {e}")
        return None

    payload: Dict[str, Any] = {
        "commit_sha": commit_sha,
        "ref": ref,
        "sarif": encoded,
        "tool_name": "Fixpoint",
    }

    url = f"https://api.github.com/repos/{owner}/{repo}/code-scanning/sarifs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if 200 <= resp.status_code < 300:
            try:
                data = resp.json()
            except json.JSONDecodeError:
                data = {}
            upload_id = data.get("id") or data.get("sarif_id")
            if upload_id:
                print(f"Uploaded SARIF to GitHub Code Scanning (id={upload_id})")
            else:
                print("Uploaded SARIF to GitHub Code Scanning")
            return upload_id
        print(
            f"Warning: SARIF upload failed with status {resp.status_code}: "
            f"{resp.text[:500]}"
        )
        return None
    except Exception as e:
        print(f"Warning: SARIF upload request failed: {e}")
        return None

