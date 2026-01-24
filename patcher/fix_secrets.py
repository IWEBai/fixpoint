"""
Fixer for hardcoded secrets.
Replaces hardcoded secrets with os.environ or os.getenv() calls.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional, List, Tuple
from patcher.detect_secrets import find_hardcoded_secrets, HardcodedSecret, _suggest_env_var


def _ensure_os_import(lines: List[str]) -> Tuple[List[str], int]:
    """
    Ensure 'import os' is present in the file.
    Returns (modified lines, offset) where offset is lines added.
    """
    # Check if os is already imported
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "import os" or stripped.startswith("import os,") or stripped.startswith("import os "):
            return lines, 0
        if stripped.startswith("from os import") or "from os " in stripped:
            return lines, 0
    
    # Find the right place to add import (after other imports or at top)
    insert_pos = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip docstrings and comments at the top
        if stripped.startswith('"""') or stripped.startswith("'''") or stripped.startswith('#'):
            continue
        # Skip empty lines at top
        if not stripped:
            continue
        # Found first real line
        if stripped.startswith('import ') or stripped.startswith('from '):
            # Find last import
            for j in range(i, len(lines)):
                if lines[j].strip().startswith('import ') or lines[j].strip().startswith('from '):
                    insert_pos = j + 1
                elif lines[j].strip() and not lines[j].strip().startswith('#'):
                    break
            break
        else:
            insert_pos = i
            break
    
    # Insert import os
    lines.insert(insert_pos, "import os\n")
    return lines, 1


def _replace_string_value(line: str, old_value: str, env_var: str, default: Optional[str] = None) -> str:
    """
    Replace a hardcoded string value with os.environ.get() or os.getenv().
    
    Args:
        line: The source line
        old_value: The hardcoded value to replace
        env_var: The environment variable name
        default: Optional default value
    """
    # Find the quoted string in the line
    # Handle both single and double quotes
    for quote in ['"', "'"]:
        quoted = f'{quote}{old_value}{quote}'
        if quoted in line:
            if default:
                replacement = f'os.environ.get("{env_var}", "{default}")'
            else:
                replacement = f'os.environ.get("{env_var}")'
            return line.replace(quoted, replacement)
    
    return line


def apply_fix_secrets(repo_path: Path, target_relpath: str) -> bool:
    """
    Apply fixes to hardcoded secrets by replacing with environment variables.
    
    Returns True if a patch was applied, otherwise False.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        print(f"ABORT: Target file not found: {target_file}")
        return False
    
    text = target_file.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines(True)  # Keep line endings
    
    secrets = find_hardcoded_secrets(text)
    
    if not secrets:
        print("No hardcoded secrets found.")
        return False
    
    # Filter to high/medium confidence only
    secrets = [s for s in secrets if s.confidence in ("high", "medium")]
    
    if not secrets:
        print("No high/medium confidence secrets found.")
        return False
    
    # Process one secret at a time (deterministic)
    secret = secrets[0]
    
    # Get the line
    if secret.line_number > len(lines):
        print(f"ABORT: Line {secret.line_number} out of range")
        return False
    
    line_idx = secret.line_number - 1
    original_line = lines[line_idx]
    
    # Ensure os import is present
    lines, offset = _ensure_os_import(lines)
    line_idx += offset  # Adjust for inserted import
    
    # Find the actual value in the original source
    # We need to search for the variable assignment pattern
    original_text = text.splitlines()[secret.line_number - 1]
    
    # Try to extract the actual secret value from the line
    # Look for patterns like: var = "value" or var = 'value'
    value_match = None
    for pattern in [
        rf'{re.escape(secret.var_name)}\s*=\s*["\']([^"\']+)["\']',  # var = "value"
        rf'["\']({re.escape(secret.var_name)})["\']:\s*["\']([^"\']+)["\']',  # "key": "value"
        rf'{re.escape(secret.var_name)}\s*=\s*["\']([^"\']+)["\']',  # kwarg=value
    ]:
        match = re.search(pattern, original_text, re.IGNORECASE)
        if match:
            value_match = match.group(1) if match.lastindex == 1 else match.group(2)
            break
    
    if not value_match:
        # Try a more generic approach - find any quoted string that looks secret-like
        for quote in ['"', "'"]:
            pattern = rf'{quote}([^{quote}]{{8,}}){quote}'
            matches = list(re.finditer(pattern, original_text))
            for m in matches:
                val = m.group(1)
                # Skip obvious non-secrets
                if not val.startswith(('http://', 'https://', 'SELECT ', 'INSERT ')):
                    value_match = val
                    break
            if value_match:
                break
    
    if not value_match:
        print(f"ABORT: Could not extract secret value from line {secret.line_number}")
        return False
    
    # Build replacement
    env_var = secret.suggested_env_var
    
    # Replace in the line
    new_line = lines[line_idx]
    for quote in ['"', "'"]:
        quoted = f'{quote}{value_match}{quote}'
        if quoted in new_line:
            replacement = f'os.environ.get("{env_var}")'
            new_line = new_line.replace(quoted, replacement)
            break
    
    if new_line == lines[line_idx]:
        print(f"ABORT: Could not replace secret in line")
        return False
    
    lines[line_idx] = new_line
    
    # Write back
    target_file.write_text("".join(lines), encoding="utf-8")
    
    print("PATCH APPLIED:")
    print(f"- {target_file}")
    print(f"  Secret type: {secret.secret_type}")
    print(f"  Line {secret.line_number}: Replaced hardcoded {secret.var_name}")
    print(f"    --> Now uses: os.environ.get(\"{env_var}\")")
    print(f"  Remember to set {env_var} in your environment!")
    
    return True


def propose_fix_secrets(repo_path: Path, target_relpath: str) -> Optional[dict]:
    """
    Propose a fix for hardcoded secrets without applying it (for warn mode).
    
    Returns:
        Dict with fix proposal or None if no fix needed
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        return None
    
    text = target_file.read_text(encoding="utf-8", errors="ignore")
    secrets = find_hardcoded_secrets(text)
    
    if not secrets:
        return None
    
    # Filter to high/medium confidence
    secrets = [s for s in secrets if s.confidence in ("high", "medium")]
    
    if not secrets:
        return None
    
    secret = secrets[0]
    
    return {
        "file": str(target_relpath),
        "line": secret.line_number,
        "secret_type": secret.secret_type,
        "var_name": secret.var_name,
        "confidence": secret.confidence,
        "suggested_env_var": secret.suggested_env_var,
        "message": f"Hardcoded {secret.var_name} detected. Replace with os.environ.get(\"{secret.suggested_env_var}\")",
    }


def propose_all_fixes_secrets(repo_path: Path, target_relpath: str) -> List[dict]:
    """
    Propose fixes for all hardcoded secrets in a file.
    
    Returns:
        List of fix proposals
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        return []
    
    text = target_file.read_text(encoding="utf-8", errors="ignore")
    secrets = find_hardcoded_secrets(text)
    
    proposals = []
    for secret in secrets:
        if secret.confidence in ("high", "medium"):
            proposals.append({
                "file": str(target_relpath),
                "line": secret.line_number,
                "secret_type": secret.secret_type,
                "var_name": secret.var_name,
                "confidence": secret.confidence,
                "suggested_env_var": secret.suggested_env_var,
                "message": f"Hardcoded {secret.var_name} detected. Replace with os.environ.get(\"{secret.suggested_env_var}\")",
            })
    
    return proposals
