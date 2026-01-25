"""
.fixpointignore file support.
Similar to .gitignore, allows teams to exclude files/directories from scanning.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import List, Set


def read_ignore_file(repo_path: Path) -> List[str]:
    """
    Read .fixpointignore file from repo root.
    
    Args:
        repo_path: Repository root path
    
    Returns:
        List of ignore patterns (empty list if file doesn't exist)
    """
    ignore_file = repo_path / ".fixpointignore"
    
    if not ignore_file.exists():
        return []
    
    patterns = []
    for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        # Strip whitespace and comments
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    
    return patterns


def should_ignore_file(file_path: str, ignore_patterns: List[str], repo_path: Path) -> bool:
    """
    Check if a file should be ignored based on .fixpointignore patterns.
    
    Supports:
    - Exact matches: `file.py`
    - Directory matches: `dir/` or `dir/**`
    - Glob patterns: `*.py`, `test_*.py`
    - Path patterns: `src/legacy/`
    - Negation: `!important.py` (not yet implemented, but pattern supported)
    
    Args:
        file_path: Relative file path (e.g., "src/app.py")
        ignore_patterns: List of ignore patterns from .fixpointignore
        repo_path: Repository root path (for resolving absolute paths)
    
    Returns:
        True if file should be ignored, False otherwise
    """
    if not ignore_patterns:
        return False
    
    # Normalize file path (use forward slashes for consistency)
    normalized_path = file_path.replace("\\", "/")
    
    # Check each pattern
    for pattern in ignore_patterns:
        # Handle negation (future feature)
        if pattern.startswith("!"):
            # For now, we don't support negation
            continue
        
        # Normalize pattern
        pattern = pattern.replace("\\", "/")
        
        # Check if pattern matches
        if _pattern_matches(normalized_path, pattern):
            return True
    
    return False


def _pattern_matches(file_path: str, pattern: str) -> bool:
    """
    Check if a file path matches an ignore pattern.
    
    Args:
        file_path: Normalized file path (forward slashes)
        pattern: Ignore pattern
    
    Returns:
        True if matches
    """
    # Exact match
    if file_path == pattern:
        return True
    
    # Directory match (ends with /)
    if pattern.endswith("/"):
        pattern_dir = pattern.rstrip("/")
        if file_path.startswith(pattern_dir + "/") or file_path == pattern_dir:
            return True
    
    # Glob pattern (fnmatch)
    # Convert pattern to regex-like matching
    if "*" in pattern or "?" in pattern:
        # Handle directory patterns
        if "/" in pattern:
            # Pattern like "src/*.py" or "tests/**/*.py"
            if pattern.startswith("**/"):
                # Match anywhere: **/*.py
                glob_part = pattern[3:]
                if fnmatch.fnmatch(file_path, glob_part) or fnmatch.fnmatch(Path(file_path).name, glob_part):
                    return True
            elif "/" in pattern:
                # Pattern like "src/*.py"
                parts = pattern.split("/", 1)
                if file_path.startswith(parts[0] + "/"):
                    remaining = file_path[len(parts[0]) + 1:]
                    if fnmatch.fnmatch(remaining, parts[1]):
                        return True
        else:
            # Simple glob: *.py, test_*.py
            if fnmatch.fnmatch(Path(file_path).name, pattern):
                return True
    
    # Prefix match (directory)
    if "/" in pattern and not pattern.endswith("/"):
        # Pattern like "src/legacy" should match "src/legacy/file.py"
        if file_path.startswith(pattern + "/"):
            return True
    
    return False


def filter_ignored_files(
    file_paths: List[str],
    repo_path: Path,
    ignore_patterns: List[str] | None = None,
) -> List[str]:
    """
    Filter out files that match .fixpointignore patterns.
    
    Args:
        file_paths: List of relative file paths
        repo_path: Repository root path
        ignore_patterns: Optional pre-loaded ignore patterns (if None, reads from file)
    
    Returns:
        Filtered list of file paths (ignored files removed)
    """
    if ignore_patterns is None:
        ignore_patterns = read_ignore_file(repo_path)
    
    if not ignore_patterns:
        return file_paths
    
    filtered = []
    for file_path in file_paths:
        if not should_ignore_file(file_path, ignore_patterns, repo_path):
            filtered.append(file_path)
    
    return filtered
