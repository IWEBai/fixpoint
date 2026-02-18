"""
Baseline comparison utilities for Fixpoint.

Baseline mode allows teams to:
- Ignore pre-existing findings on legacy code.
- Only report / fix violations that are new since an agreed baseline.

This module expects a pre-generated baseline findings file in
`.fixpoint_baseline.json` (same schema as Semgrep results). Keeping
generation of that file out-of-band keeps the runtime path simple.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Set, Any
import datetime as _dt
import subprocess
import tempfile


def _fingerprint(finding: dict) -> str:
    """
    Generate a stable fingerprint for a finding.

    Uses (file_path, line, rule_id). This is intentionally simple and
    stable across runs so long as line numbers don't change.
    """
    path = str(finding.get("path", "") or "")
    start_line = int(finding.get("start", {}).get("line", 0) or 0)
    rule_id = str(finding.get("check_id", "") or "")
    return f"{path}:{start_line}:{rule_id}"


BASELINE_FILE_NAME = ".fixpoint_baseline.json"
BASELINE_CACHE_DIR = ".fixpoint_cache/baseline"


class BaselineError(Exception):
    """Raised when baseline mode is misconfigured or expired."""


def _baseline_cache_path(repo_path: Path, baseline_sha: str) -> Path:
    repo_path = Path(repo_path)
    cache_dir = repo_path / BASELINE_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{baseline_sha}.json"


def _load_baseline_data(repo_path: Path, baseline_sha: str) -> dict[str, Any] | None:
    repo_path = Path(repo_path)
    cache_path = _baseline_cache_path(repo_path, baseline_sha)
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass

    baseline_file = repo_path / BASELINE_FILE_NAME
    if not baseline_file.exists():
        return None

    try:
        return json.loads(baseline_file.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _parse_created_at(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(text)
    except Exception:
        return None


def get_baseline_findings(repo_path: Path, baseline_sha: str | None) -> Set[str]:
    """
    Load baseline findings from cache or `.fixpoint_baseline.json` in repo root.

    Returns:
        Set of finding fingerprints present in the baseline.
    """
    repo_path = Path(repo_path)
    if not baseline_sha:
        return set()

    data = _load_baseline_data(repo_path, baseline_sha)
    if not data:
        return set()

    results = data.get("results", [])
    return {_fingerprint(f) for f in results or []}


def create_baseline(
    repo_path: Path,
    baseline_sha: str,
    rules_path: Path,
    output_path: Path | None = None,
) -> Path:
    """
    Create a baseline by scanning the repository at the given SHA.

    Writes the baseline to `.fixpoint_baseline.json` and cache.
    """
    from core.scanner import semgrep_scan
    from core.cache import compute_rules_version

    repo_path = Path(repo_path)
    if not baseline_sha:
        raise BaselineError("baseline_sha is required")

    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{baseline_sha}^{{commit}}"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise BaselineError(f"Invalid baseline SHA: {baseline_sha}") from exc

    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir) / "baseline"
        try:
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), baseline_sha],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            results_path = Path(temp_dir) / "baseline-results.json"
            data = semgrep_scan(
                worktree_path,
                rules_path,
                results_path,
                target_files=None,
                apply_ignore=True,
            )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=repo_path,
                check=False,
                capture_output=True,
                text=True,
            )

    created_at = _dt.datetime.now(tz=_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    meta = {
        "baseline_sha": baseline_sha,
        "created_at": created_at,
        "rules_version": compute_rules_version(Path(rules_path)),
    }
    payload = dict(data or {})
    payload["meta"] = meta

    baseline_file = Path(output_path) if output_path else repo_path / BASELINE_FILE_NAME
    baseline_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    cache_path = _baseline_cache_path(repo_path, baseline_sha)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return baseline_file


def audit_baseline(
    repo_path: Path,
    findings: list[dict],
    baseline_sha: str | None,
    max_age_days: int | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """
    Apply baseline filtering and return audit metadata.

    Raises BaselineError when baseline is missing, mismatched, or expired.
    """
    if not baseline_sha:
        raise BaselineError("baseline_sha is required when baseline_mode is true")

    data = _load_baseline_data(repo_path, baseline_sha)
    if not data:
        raise BaselineError(
            f"Baseline not found. Run 'fixpoint baseline create --sha {baseline_sha}'"
        )

    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    meta_sha = str(meta.get("baseline_sha", "") or "")
    if meta_sha and meta_sha != baseline_sha:
        raise BaselineError(
            f"Baseline SHA mismatch (config {baseline_sha} != file {meta_sha})."
        )

    created_at = _parse_created_at(meta.get("created_at"))
    age_days: float | None = None
    expired = False
    if max_age_days is not None and max_age_days > 0:
        if not created_at:
            raise BaselineError(
                "Baseline missing created_at metadata. Recreate baseline to enable expiration."
            )
        age = _dt.datetime.now(tz=_dt.timezone.utc) - created_at
        age_days = age.total_seconds() / 86400.0
        expired = age_days > float(max_age_days)
        if expired:
            raise BaselineError(
                f"Baseline expired ({age_days:.1f} days > {max_age_days}). Rebaseline required."
            )

    baseline_fps = { _fingerprint(f) for f in data.get("results", []) }
    filtered = filter_new_findings(findings, baseline_fps)
    filtered_count = len(findings) - len(filtered)

    audit = {
        "baseline_sha": baseline_sha,
        "filtered_count": filtered_count,
        "remaining_count": len(filtered),
        "age_days": age_days,
        "expired": expired,
    }
    return filtered, audit


def filter_new_findings(
    findings: list[dict],
    baseline_fingerprints: Set[str],
) -> list[dict]:
    """
    Filter findings to only those not present in the baseline.

    Args:
        findings: Current Semgrep findings
        baseline_fingerprints: Set of fingerprint strings from baseline

    Returns:
        List of findings considered "new" relative to baseline.
    """
    if not baseline_fingerprints:
        return findings

    filtered: list[dict] = []
    for f in findings or []:
        fp = _fingerprint(f)
        if fp not in baseline_fingerprints:
            filtered.append(f)
    return filtered

