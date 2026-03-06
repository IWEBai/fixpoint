"""
Core scanning engine for Fixpoint.
Supports both full repository scanning and PR diff scanning.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from core.ignore import filter_ignored_files, read_ignore_file
from core.cache import compute_rules_version, get_cached_scan, cache_scan

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Large-repository protection limits
# ---------------------------------------------------------------------------

# Maximum number of files in a PR diff that Railo will scan.
# PRs with more changed files than this are skipped to avoid runaway scans.
MAX_PR_DIFF_FILES: int = int(os.getenv("RAILO_MAX_PR_DIFF_FILES", "200"))

# Hard cap on files passed to semgrep (after extension + ignore filtering).
# When a PR diff exceeds this after filtering, only the first N files are
# scanned and the run is annotated as partial.
MAX_FILES_TO_SCAN: int = int(os.getenv("RAILO_MAX_FILES_TO_SCAN", "500"))

# Maximum on-disk repository size in MiB (0 = unlimited).
MAX_REPO_SIZE_MIB: int = int(os.getenv("RAILO_MAX_REPO_SIZE_MIB", "1024"))


class RepoTooLargeError(ValueError):
    """Raised when a repository or PR exceeds configured size limits."""


def check_repo_size(repo_path: Path) -> None:
    """
    Raise ``RepoTooLargeError`` when *repo_path* exceeds ``MAX_REPO_SIZE_MIB``.

    Skipped when ``MAX_REPO_SIZE_MIB`` is 0 (unlimited).
    Falls back silently on any OS error (e.g. permission denied).
    """
    if MAX_REPO_SIZE_MIB <= 0:
        return
    try:
        total_bytes = sum(
            f.stat().st_size
            for f in repo_path.rglob("*")
            if f.is_file()
        )
        total_mib = total_bytes / (1024 * 1024)
        if total_mib > MAX_REPO_SIZE_MIB:
            raise RepoTooLargeError(
                f"Repository is {total_mib:.1f} MiB which exceeds the "
                f"{MAX_REPO_SIZE_MIB} MiB limit (RAILO_MAX_REPO_SIZE_MIB). "
                "Scan skipped. Raise the limit or exclude large artefacts "
                "with a .fixpointignore file."
            )
    except RepoTooLargeError:
        raise
    except Exception as e:
        _log.debug("check_repo_size: ignored error: %s", e)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """
    Run a command and raise a readable error if it fails.
    Windows-safe: force UTF-8 decoding (and ignore undecodable chars).
    """
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n\nSTDOUT:\n{p.stdout}\n\nSTDERR:\n{p.stderr}"
        )
    return p


def semgrep_scan(
    repo_path: Path,
    rules_path: Path,
    out_json: Path,
    target_files: Optional[list[str]] = None,
    apply_ignore: bool = True,
    max_runtime_seconds: Optional[int] = None,
) -> dict:
    """
    Run semgrep and write JSON to out_json.
    
    Args:
        repo_path: Path to repository root
        rules_path: Path to Semgrep rules file
        out_json: Path to write JSON results
        target_files: Optional list of specific files to scan (for PR diff mode)
        apply_ignore: If True, filter files using .fixpointignore
    
    Returns:
        Parsed Semgrep results as dict

    Raises:
        RepoTooLargeError: When the PR diff exceeds MAX_PR_DIFF_FILES or the
            repository on disk exceeds MAX_REPO_SIZE_MIB.
    """
    # ------------------------------------------------------------------
    # Large-repository guard: PR diff file count
    # ------------------------------------------------------------------
    if target_files is not None and MAX_PR_DIFF_FILES > 0:
        if len(target_files) > MAX_PR_DIFF_FILES:
            raise RepoTooLargeError(
                f"PR diff contains {len(target_files)} changed files which exceeds "
                f"the {MAX_PR_DIFF_FILES}-file limit (RAILO_MAX_PR_DIFF_FILES). "
                "Scan skipped to protect API rate limits."
            )

    # Early exit: filter out-of-scope files quickly
    # Supported extensions: Python and JS/TS only
    SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}
    
    if target_files:
        # Fast path: filter to supported extensions only
        filtered = []
        for file_path in target_files:
            file_path_obj = Path(file_path)
            ext = file_path_obj.suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                filtered.append(file_path)
        
        if not filtered:
            # No supported files - early exit
            return {"results": []}
        
        target_files = filtered
    
    # Apply .fixpointignore filtering
    if apply_ignore and target_files:
        ignore_patterns = read_ignore_file(repo_path)
        target_files = filter_ignored_files(target_files, repo_path, ignore_patterns)
        if not target_files:
            # All files ignored, return empty results
            return {"results": []}
    
    # Handle empty target list explicitly
    if target_files is not None and len(target_files) == 0:
        # Empty list means no files to scan (e.g. no files changed or all filtered)
        return {"results": []}

    # ------------------------------------------------------------------
    # Large-repository guard: per-scan file count cap (truncate, partial scan)
    # ------------------------------------------------------------------
    truncated = False
    if target_files is not None and MAX_FILES_TO_SCAN > 0 and len(target_files) > MAX_FILES_TO_SCAN:
        _log.warning(
            "Scan capped at %d files (PR diff had %d after filtering); "
            "set RAILO_MAX_FILES_TO_SCAN to raise this limit.",
            MAX_FILES_TO_SCAN,
            len(target_files),
        )
        target_files = target_files[:MAX_FILES_TO_SCAN]
        truncated = True

    # ------------------------------------------------------------------
    # Large-repository guard: on-disk repo size
    # ------------------------------------------------------------------
    if target_files is None:
        # Full-repo mode only — PR diff mode checks happen above
        check_repo_size(repo_path)

    cmd = [
        "semgrep",
        "--config",
        str(rules_path),
        "--json",
        "--output",
        str(out_json),
    ]

    # Respect overall runtime budget by passing a timeout hint to Semgrep.
    # We keep this conservative – if Semgrep exceeds it, it will stop early.
    if max_runtime_seconds is not None and max_runtime_seconds > 0:
        cmd.extend(["--timeout", str(max_runtime_seconds)])
    
    # If target_files provided, scan only those files (PR diff mode)
    if target_files is not None:
        if not target_files:
            # Empty list means no files to scan
            return {"results": []}
            
        # Semgrep can take multiple file paths and handles them efficiently internally.
        # No need for parallelization here - Semgrep's internal engine is already optimized
        # for scanning multiple files in a single process.
        for file_path in target_files:
            full_path = repo_path / file_path if not Path(file_path).is_absolute() else Path(file_path)
            if full_path.exists():
                cmd.append(str(full_path))
    else:
        # Full repo scan – may use cached results when available
        # Compute cache key based on current repo HEAD + rules version.
        repo_path = Path(repo_path)
        try:
            # Resolve current HEAD SHA
            sha_result = run(["git", "rev-parse", "HEAD"], cwd=repo_path)
            repo_sha = sha_result.stdout.strip()
        except Exception:
            repo_sha = ""

        rule_version = compute_rules_version(Path(rules_path))

        # Only leverage cache when we have a repo SHA (inside a git repo)
        # and no explicit target_files (full-repo scan).
        if repo_sha:
            cached = get_cached_scan(repo_path, repo_sha, rule_version)
            if cached is not None:
                return cached

        cmd.append(str(repo_path))
    
    run(cmd, cwd=repo_path)
    raw = out_json.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    data = json.loads(text)

    if truncated:
        data["_truncated"] = True
        data["_truncated_reason"] = f"Scan capped at {MAX_FILES_TO_SCAN} files"

    # Cache successful full-repo scans (no target_files)
    if target_files is None:
        try:
            if "results" in data:
                # Reuse the same repo_sha / rule_version computation logic
                repo_path = Path(repo_path)
                try:
                    sha_result = run(["git", "rev-parse", "HEAD"], cwd=repo_path)
                    repo_sha = sha_result.stdout.strip()
                except Exception:
                    repo_sha = ""
                rule_version = compute_rules_version(Path(rules_path))
                if repo_sha:
                    cache_scan(repo_path, repo_sha, rule_version, data)
        except Exception:
            pass

    return data


def get_pr_diff_files(repo_path: Path, base_branch: str, head_branch: str) -> list[str]:
    """
    Get list of changed files in PR diff.
    
    Args:
        repo_path: Path to repository root
        base_branch: Base branch (e.g., 'main')
        head_branch: Head branch (PR branch)
    
    Returns:
        List of relative file paths that changed
    """
    # Fetch latest changes
    run(["git", "fetch", "origin", base_branch, head_branch], cwd=repo_path)
    
    # Get diff between base and head
    result = run(
        ["git", "diff", "--name-only", f"origin/{base_branch}...origin/{head_branch}"],
        cwd=repo_path,
    )
    
    changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return changed_files


def get_pr_diff_files_local(repo_path: Path, base_ref: str, head_ref: str) -> list[str]:
    """
    Get list of changed files between two git refs (local).
    
    Args:
        repo_path: Path to repository root
        base_ref: Base git ref (commit, branch, etc.)
        head_ref: Head git ref
    
    Returns:
        List of relative file paths that changed
    """
    result = run(
        ["git", "diff", "--name-only", base_ref, head_ref],
        cwd=repo_path,
    )
    
    changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return changed_files
