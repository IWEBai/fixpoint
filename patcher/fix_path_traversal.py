"""
Path traversal fixer.
Adds path validation when os.path.join is used with user input.
"""
from __future__ import annotations

import re
from pathlib import Path


def _ensure_os_import(text: str) -> str:
    """Ensure os is imported for os.path.realpath."""
    if "import os" in text or "from os import" in text:
        return text
    lines = text.splitlines()
    import_section_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and ("import " in stripped or "from " in stripped):
            import_section_end = i + 1
        elif import_section_end > 0 and stripped and not stripped.startswith("#"):
            break
    lines.insert(import_section_end, "import os")
    return "\n".join(lines)


def apply_fix_path_traversal(repo_path: Path, target_relpath: str) -> bool:
    """
    Add path traversal check for os.path.join(base, user_var) patterns.
    
    Inserts validation: ensure resolved path is under base directory.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        return False

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    text = _ensure_os_import(text)
    lines = text.splitlines(True)
    changed = False

    # Pattern: var = os.path.join(base, user_var)
    pattern = re.compile(r"^(\s*)(\w+)\s*=\s*os\.path\.join\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)\s*$")

    for i, line in enumerate(lines):
        if "os.path.join" not in line:
            continue
        m = pattern.search(line)
        if not m:
            continue
        indent, var, base, _ = m.groups()
        indent_str = indent
        # Check if validation already exists on next line
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if "Path traversal denied" in next_line or "realpath" in next_line:
                continue
        # Insert validation after assignment
        check = (
            f'{indent_str}if not os.path.realpath({var}).startswith(os.path.realpath({base})):\n'
            f'{indent_str}    raise PermissionError("Path traversal denied")\n'
        )
        lines.insert(i + 1, check)
        changed = True
        break  # One fix per file

    if changed:
        target_file.write_text("".join(lines), encoding="utf-8")
    return changed


def propose_fix_path_traversal(repo_path: Path, target_relpath: str) -> list[dict] | None:
    """Propose path traversal fix (warn mode)."""
    return [{
        "file": target_relpath,
        "line": 0,
        "before": "path = os.path.join(base, user_input)",
        "after": "path = os.path.join(base, user_input)\n# Add: if not os.path.realpath(path).startswith(os.path.realpath(base)): raise PermissionError(...)",
    }]
