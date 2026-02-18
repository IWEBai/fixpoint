"""
Language-aware formatting utilities for Fixpoint.

Formatting is **best-effort** and intentionally conservative:
- Only files that Fixpoint has already patched should be formatted.
- External formatters (black, prettier) are invoked only if available.
- On any error, formatting is skipped rather than failing the run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple, Literal
import subprocess
import difflib


FormatterLanguage = Literal["python", "javascript", "typescript", "unknown"]


def _detect_language(file_path: Path) -> FormatterLanguage:
    """Infer language from file extension."""
    ext = file_path.suffix.lower()
    if ext == ".py":
        return "python"
    if ext in {".js", ".jsx"}:
        return "javascript"
    if ext in {".ts", ".tsx"}:
        return "typescript"
    return "unknown"


def _run_black(repo_path: Path, file_path: Path) -> bool:
    """Run black on a single Python file, returning True on success."""
    try:
        subprocess.run(
            ["black", str(file_path)],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except FileNotFoundError:
        # black not installed – silently skip
        return False
    except subprocess.CalledProcessError as e:
        print(f"Warning: black failed on {file_path}: {e}")
        return False


def _run_ruff_format(repo_path: Path, file_path: Path) -> bool:
    """Run ruff format on a single Python file, returning True on success."""
    try:
        subprocess.run(
            ["ruff", "format", str(file_path)],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except FileNotFoundError:
        # ruff not installed – silently skip
        return False
    except subprocess.CalledProcessError as e:
        print(f"Warning: ruff format failed on {file_path}: {e}")
        return False


def _run_prettier_bin(repo_path: Path, file_path: Path) -> bool:
    """Run prettier (binary) on a single JS/TS file."""
    try:
        subprocess.run(
            ["prettier", "--write", str(file_path)],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except FileNotFoundError:
        return False
    except subprocess.CalledProcessError as e:
        print(f"Warning: prettier failed on {file_path}: {e}")
        return False


def _run_prettier(repo_path: Path, file_path: Path) -> bool:
    """
    Run prettier via npx on a JS/TS file.

    This assumes a Node toolchain is available; if not, we fail soft.
    """
    try:
        subprocess.run(
            # Prefer local prettier without installing packages.
            ["npx", "--no-install", "prettier", "--write", str(file_path)],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except FileNotFoundError:
        # Node / prettier not available – skip
        return False
    except subprocess.CalledProcessError as e:
        print(f"Warning: prettier failed on {file_path}: {e}")
        return False


def _diff_stats(before: str, after: str) -> Tuple[int, int]:
    """
    Compute approximate (lines_added, lines_removed) between two texts.

    Uses unified diff and counts +/- lines, ignoring headers.
    """
    added = 0
    removed = 0
    before_lines = before.splitlines(keepends=False)
    after_lines = after.splitlines(keepends=False)

    for line in difflib.unified_diff(before_lines, after_lines, n=0):
        if not line:
            continue
        if line[0] == "+" and not line.startswith("+++"):
            added += 1
        elif line[0] == "-" and not line.startswith("---"):
            removed += 1
    return added, removed


def format_file(
    repo_path: Path,
    file_path: str | Path,
    language: FormatterLanguage | None = None,
) -> Tuple[bool, int, int]:
    """
    Format a single file using language-appropriate tools.

    Returns:
        (success, lines_added, lines_removed)
    """
    repo_path = Path(repo_path)
    path = Path(file_path)
    if not path.is_absolute():
        path = repo_path / path

    if not path.exists():
        return False, 0, 0

    if language is None or language == "unknown":
        language = _detect_language(path)

    # Take snapshot before formatting
    try:
        before = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, 0, 0

    ran = False
    if language == "python":
        # Prefer ruff (fast, config-aware) if available, else black.
        ran = _run_ruff_format(repo_path, path) or _run_black(repo_path, path)
    elif language in ("javascript", "typescript"):
        # Prefer prettier binary if present, else npx (no-install).
        ran = _run_prettier_bin(repo_path, path) or _run_prettier(repo_path, path)
    else:
        # No known formatter – skip
        return False, 0, 0

    if not ran:
        return False, 0, 0

    try:
        after = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, 0, 0

    added, removed = _diff_stats(before, after)
    return True, added, removed

