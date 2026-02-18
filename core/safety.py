"""
Safety and trust mechanisms for Fixpoint.
Handles idempotency, loop prevention, and confidence gating.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Tuple, List


def compute_fix_idempotency_key(
    pr_number: int,
    head_sha: str,
    finding: dict,
) -> str:
    """
    Compute idempotency key for a fix to prevent re-applying same fix.
    
    Args:
        pr_number: PR number
        head_sha: Current HEAD commit SHA
        finding: Semgrep finding dict
    
    Returns:
        Unique idempotency key
    """
    # Combine PR number, commit SHA, file path, and line number
    file_path = finding.get("path", "")
    start_line = finding.get("start", {}).get("line", 0)
    check_id = finding.get("check_id", "")
    
    key_data = {
        "pr": pr_number,
        "sha": head_sha,
        "file": file_path,
        "line": start_line,
        "check": check_id,
    }
    
    key_str = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(key_str.encode()).hexdigest()


def is_bot_commit(commit_message: str, commit_author: str) -> bool:
    """
    Check if a commit was made by Fixpoint bot.
    
    Uses canonical marker "[fixpoint]" in commit message and bot author.
    This prevents false positives from normal commits containing words like "autopatch".
    
    Args:
        commit_message: Git commit message
        commit_author: Git commit author email/name
    
    Returns:
        True if this is a bot commit
    """
    # Canonical marker: all bot commits must start with "[fixpoint]"
    if commit_message.strip().startswith("[fixpoint]"):
        return True
    
    # Also check author (canonical bot identity)
    author_lower = commit_author.lower()
    if "fixpoint-bot" in author_lower:
        return True
    
    return False


def check_loop_prevention(repo_path: Path, head_sha: str) -> bool:
    """
    Check if the latest commit is from Fixpoint bot.
    If so, skip processing to prevent infinite loops.
    
    Args:
        repo_path: Path to repository
        head_sha: Current HEAD commit SHA
    
    Returns:
        True if we should skip (bot commit detected), False to proceed
    """
    import subprocess
    
    try:
        # Get latest commit info
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%s%n%ae", head_sha],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            commit_message = lines[0]
            commit_author = lines[1]
            
            if is_bot_commit(commit_message, commit_author):
                return True  # Skip - this is a bot commit
    except Exception:
        # If we can't check, err on the side of caution and proceed
        pass
    
    return False  # Proceed with processing


def has_recent_bot_commit(repo_path: Path, max_commits: int = 5) -> bool:
    """
    Check if any of the recent commits are from Fixpoint bot.
    
    Args:
        repo_path: Path to repository
        max_commits: Number of recent commits to check
    
    Returns:
        True if recent bot commit found
    """
    import subprocess
    
    try:
        # Get recent commits
        result = subprocess.run(
            ["git", "log", f"-{max_commits}", "--pretty=format:%s%n%ae"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        lines = result.stdout.strip().split("\n")
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                commit_message = lines[i]
                commit_author = lines[i + 1]
                
                if is_bot_commit(commit_message, commit_author):
                    return True
    except Exception:
        pass
    
    return False


def get_diff_stats(repo_path: Path) -> tuple[int, int]:
    """
    Get current diff stats (lines added, lines removed).
    
    Args:
        repo_path: Path to repository
    
    Returns:
        Tuple of (lines_added, lines_removed)
    """
    import subprocess
    
    try:
        result = subprocess.run(
            ["git", "diff", "--numstat", "--cached"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        added = 0
        removed = 0
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                try:
                    added += int(parts[0]) if parts[0] != "-" else 0
                    removed += int(parts[1]) if parts[1] != "-" else 0
                except ValueError:
                    pass
        # If no staged changes, check unstaged (for cases where we haven't staged yet)
        if added == 0 and removed == 0:
            result = subprocess.run(
                ["git", "diff", "--numstat"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    try:
                        added += int(parts[0]) if parts[0] != "-" else 0
                        removed += int(parts[1]) if parts[1] != "-" else 0
                    except ValueError:
                        pass
        return added, removed
    except Exception:
        return 0, 0


def check_max_diff_lines(repo_path: Path, max_lines: int) -> tuple[bool, int, int]:
    """
    Check if the current diff exceeds max_lines (safety rail).
    
    Args:
        repo_path: Path to repository
        max_lines: Maximum allowed total lines changed (added + removed)
    
    Returns:
        Tuple of (ok, lines_added, lines_removed).
        ok is True if diff is within limit, False if too large.
    """
    added, removed = get_diff_stats(repo_path)
    total = added + removed
    return (total <= max_lines, added, removed)


def check_confidence_gating(finding: dict) -> bool:
    """
    Gate fixes based on confidence level.
    Only apply fixes when confidence is high.
    
    Args:
        finding: Semgrep finding dict
    
    Returns:
        True if confidence is high enough to apply fix
    """
    # Check metadata confidence
    metadata = finding.get("extra", {}).get("metadata", {})
    confidence = metadata.get("confidence", "medium")
    
    # Only proceed if confidence is "high"
    if confidence == "high":
        return True
    
    # Also check severity - only fix ERROR level issues
    severity = finding.get("extra", {}).get("severity", "INFO")
    if severity == "ERROR":
        # Even if confidence isn't explicitly "high", ERROR severity is high confidence
        return True
    
    return False


def check_max_files(changed_files: Iterable[str], max_files: int) -> Tuple[bool, int]:
    """
    Check if the number of files to be changed exceeds the configured limit.

    Args:
        changed_files: Iterable of file paths that may be modified
        max_files: Maximum allowed number of files to change in a single run

    Returns:
        Tuple of (ok, count) where ok is True if within limit.
    """
    files = list({f for f in changed_files})
    count = len(files)
    return (count <= max_files, count)


def check_sensitive_paths(
    repo_path: Path,
    changed_files: Iterable[str],
    sensitive_paths_allowlist: Iterable[str] | None = None,
) -> Tuple[bool, List[str]]:
    """
    Guardrail: block auto-commit when changes touch sensitive paths
    (e.g. migrations/, infra/, auth/) unless explicitly allowed.

    Args:
        repo_path: Repository root
        changed_files: Iterable of file paths (relative to repo root)
        sensitive_paths_allowlist: Paths that are allowed even if they look sensitive

    Returns:
        Tuple of (ok, offending_files)
    """
    repo_path = Path(repo_path)
    allowlist = {str(Path(p)) for p in (sensitive_paths_allowlist or []) if p}

    # Heuristic list of sensitive path prefixes (relative to repo root)
    sensitive_prefixes = (
        "migrations/",
        "infra/",
        "infrastructure/",
        "auth/",
        "security/",
    )

    offending: List[str] = []
    for rel in changed_files:
        rel_str = str(rel).replace("\\", "/")
        if rel_str in allowlist:
            continue
        for prefix in sensitive_prefixes:
            if rel_str.startswith(prefix):
                offending.append(rel_str)
                break

    return (len(offending) == 0, offending)


def check_dependency_changes(
    repo_path: Path,
    changed_files: Iterable[str],
    allow_dependency_changes: bool,
) -> Tuple[bool, List[str]]:
    """
    Guardrail: block auto-commit when dependency / lock files change,
    unless explicitly allowed by configuration.

    Args:
        repo_path: Repository root
        changed_files: Iterable of file paths (relative to repo root)
        allow_dependency_changes: If False, block when dependency files touched

    Returns:
        Tuple of (ok, offending_files)
    """
    if allow_dependency_changes:
        return True, []

    dependency_filenames = {
        "requirements.txt",
        "pyproject.toml",
        "Pipfile",
        "Pipfile.lock",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    }

    offending: List[str] = []
    for rel in changed_files:
        name = Path(rel).name
        if name in dependency_filenames:
            offending.append(str(rel).replace("\\", "/"))

    return (len(offending) == 0, offending)


def validate_patch_plan(plan, config: dict) -> Tuple[bool, List[str]]:
    """
    Run all safety guardrails against a patch plan *before* applying fixes.

    The plan object is expected to have:
      - repo_path: Path
      - changed_files: Iterable[str]

    Config keys used:
      - max_files_changed (int)
      - sensitive_paths_allowlist (list[str])
      - allow_dependency_changes (bool)
    """
    from pathlib import Path as _Path  # avoid type confusion in signatures

    repo_path: Path = _Path(plan.repo_path)
    changed_files = list(plan.changed_files)

    reasons: List[str] = []

    # 1) Max files guardrail
    max_files = int(config.get("max_files_changed", 0) or 0)
    if max_files > 0:
        ok_files, count = check_max_files(changed_files, max_files)
        if not ok_files:
            reasons.append(
                f"Too many files would be changed ({count}, max {max_files}). "
                "Adjust max_files_changed in .fixpoint.yml to allow this."
            )

    # 2) Sensitive paths guardrail
    sensitive_allowlist = config.get("sensitive_paths_allowlist") or []
    ok_sensitive, sensitive_offending = check_sensitive_paths(
        repo_path,
        changed_files,
        sensitive_allowlist,
    )
    if not ok_sensitive and sensitive_offending:
        joined = ", ".join(sorted(sensitive_offending))
        reasons.append(
            "Changes touch sensitive paths (e.g. migrations/, infra/, auth/): "
            f"{joined}. Add explicit allow entries under sensitive_paths_allowlist "
            "in .fixpoint.yml to permit auto-fix."
        )

    # 3) Dependency changes guardrail
    allow_deps = bool(config.get("allow_dependency_changes", False))
    ok_deps, dep_offending = check_dependency_changes(
        repo_path,
        changed_files,
        allow_deps,
    )
    if not ok_deps and dep_offending:
        joined = ", ".join(sorted(dep_offending))
        reasons.append(
            "Changes affect dependency/lock files: "
            f"{joined}. Set allow_dependency_changes: true in .fixpoint.yml to allow this."
        )

    return (len(reasons) == 0, reasons)


def analyze_diff_quality(repo_path: Path) -> dict:
    """
    Analyze git diff quality to ensure minimal, focused security patches.
    
    Checks for:
    - Extra refactors (changes beyond security fixes)
    - Reordering (imports, functions, classes)
    - Unrelated whitespace changes
    
    Args:
        repo_path: Path to repository root
    
    Returns:
        Dict with keys:
        - quality_score: float (0.0-1.0, higher is better)
        - issues: list[str] - List of quality issues found
        - is_minimal: bool - True if diff is minimal and focused
    """
    import subprocess
    import re
    
    issues: List[str] = []
    score = 1.0
    
    try:
        # Get unified diff output
        result = subprocess.run(
            ["git", "diff", "--no-color"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        
        if not result.stdout.strip():
            # No diff - perfect quality
            return {
                "quality_score": 1.0,
                "issues": [],
                "is_minimal": True,
            }
        
        diff_lines = result.stdout.splitlines()
        
        # Track context to detect reordering
        in_hunk = False
        hunk_context: List[str] = []
        
        # Patterns to detect problematic changes
        import_pattern = re.compile(r'^[\+\-]\s*(import|from)\s+')
        function_pattern = re.compile(r'^[\+\-]\s*def\s+\w+')
        class_pattern = re.compile(r'^[\+\-]\s*class\s+\w+')
        
        # Track additions/removals that might indicate reordering
        added_imports: set[str] = set()
        removed_imports: set[str] = set()
        added_functions: set[str] = set()
        removed_functions: set[str] = set()
        
        # Track pure whitespace changes
        whitespace_only_changes = 0
        total_changes = 0
        
        for i, line in enumerate(diff_lines):
            if line.startswith("@@"):
                # Hunk header - reset context
                in_hunk = True
                hunk_context = []
                continue
            
            if not in_hunk:
                continue
            
            if line.startswith("\\"):
                continue
            
            # Track changes
            if line.startswith("+") or line.startswith("-"):
                total_changes += 1
                
                # Check for pure whitespace changes
                stripped = line[1:].strip()
                if not stripped:
                    whitespace_only_changes += 1
                    continue
                
                # Detect import reordering
                if import_pattern.match(line):
                    import_stmt = stripped
                    if line.startswith("+"):
                        added_imports.add(import_stmt)
                    else:
                        removed_imports.add(import_stmt)
                
                # Detect function/class reordering
                if function_pattern.match(line):
                    func_match = function_pattern.search(line)
                    if func_match:
                        func_name = func_match.group(0)
                        if line.startswith("+"):
                            added_functions.add(func_name)
                        else:
                            removed_functions.add(func_name)
                
                if class_pattern.match(line):
                    class_match = class_pattern.search(line)
                    if class_match:
                        class_name = class_match.group(0)
                        # Class reordering is suspicious
                        issues.append(f"Class definition moved: {class_name}")
                        score -= 0.1
            
            # Track context lines (unchanged)
            elif line.startswith(" "):
                hunk_context.append(line[1:])
        
        # Check for import reordering (same imports added and removed)
        reordered_imports = added_imports & removed_imports
        if reordered_imports:
            issues.append(
                f"Import reordering detected ({len(reordered_imports)} import(s) moved). "
                "Patches should not reorder imports."
            )
            score -= 0.15 * min(len(reordered_imports), 3)  # Cap penalty
        
        # Check for function reordering
        reordered_functions = added_functions & removed_functions
        if reordered_functions:
            issues.append(
                f"Function reordering detected ({len(reordered_functions)} function(s) moved). "
                "Patches should not reorder code."
            )
            score -= 0.2 * min(len(reordered_functions), 2)  # Cap penalty
        
        # Check for excessive whitespace-only changes
        if total_changes > 0:
            whitespace_ratio = whitespace_only_changes / total_changes
            if whitespace_ratio > 0.3:  # More than 30% whitespace changes
                issues.append(
                    f"Excessive whitespace-only changes ({whitespace_ratio:.1%} of diff). "
                    "Patches should focus on security fixes, not formatting."
                )
                score -= 0.2
        
        # Check for suspicious patterns that suggest refactoring
        # Look for large blocks of additions/removals that aren't security fixes
        consecutive_additions = 0
        consecutive_removals = 0
        max_consecutive = 0
        
        for line in diff_lines:
            if line.startswith("+"):
                consecutive_additions += 1
                consecutive_removals = 0
                max_consecutive = max(max_consecutive, consecutive_additions)
            elif line.startswith("-"):
                consecutive_removals += 1
                consecutive_additions = 0
                max_consecutive = max(max_consecutive, consecutive_removals)
            else:
                consecutive_additions = 0
                consecutive_removals = 0
        
        # Large consecutive blocks might indicate refactoring
        if max_consecutive > 20:
            issues.append(
                f"Large consecutive change block ({max_consecutive} lines). "
                "This may indicate refactoring beyond security fixes."
            )
            score -= 0.1
        
        # Ensure score stays in valid range
        score = max(0.0, min(1.0, score))
        
        # Consider minimal if score >= 0.7 and no critical issues
        is_minimal = score >= 0.7 and not any(
            "reordering" in issue.lower() or "refactoring" in issue.lower()
            for issue in issues
        )
        
        return {
            "quality_score": score,
            "issues": issues,
            "is_minimal": is_minimal,
        }
    
    except Exception as e:
        # If analysis fails, err on the side of caution
        return {
            "quality_score": 0.5,
            "issues": [f"Diff quality analysis failed: {e}"],
            "is_minimal": False,
        }

