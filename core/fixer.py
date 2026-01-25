"""
Core fixing engine for Fixpoint.
Processes Semgrep findings and applies deterministic fixes.

Supported vulnerability types:
- SQL Injection (Python)
- Hardcoded Secrets (Python)
- XSS (Jinja2/Django templates and Python)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Callable


# Mapping of vulnerability patterns to fixers
# Key patterns in check_id -> fixer function name
FIXER_REGISTRY = {
    # SQL Injection patterns
    "sql-injection": "fix_sqli",
    "sqli": "fix_sqli",
    "sql_injection": "fix_sqli",
    
    # Hardcoded secrets patterns
    "hardcoded-password": "fix_secrets",
    "hardcoded-secret": "fix_secrets",
    "hardcoded_password": "fix_secrets",
    "hardcoded_secret": "fix_secrets",
    "aws-access-key": "fix_secrets",
    "github-token": "fix_secrets",
    "slack-token": "fix_secrets",
    "stripe-key": "fix_secrets",
    "private-key": "fix_secrets",
    "database-uri": "fix_secrets",
    "secret-dict": "fix_secrets",
    "secret-kwarg": "fix_secrets",
    
    # XSS patterns
    "xss": "fix_xss",
    "mark-safe": "fix_xss",
    "mark_safe": "fix_xss",
    "safe-filter": "fix_xss",
    "safe_filter": "fix_xss",
    "autoescape-off": "fix_xss",
    "autoescape_off": "fix_xss",
    "safestring": "fix_xss",
    "markup": "fix_xss",
    "format-html": "fix_xss",
    "format_html": "fix_xss",
}


def _get_fixer_for_finding(check_id: str) -> Optional[str]:
    """
    Determine which fixer to use based on the check_id.
    
    Args:
        check_id: The Semgrep rule check_id
    
    Returns:
        Fixer name or None if no fixer matches
    """
    check_id_lower = check_id.lower()
    
    for pattern, fixer in FIXER_REGISTRY.items():
        if pattern in check_id_lower:
            return fixer
    
    return None


def _apply_fixer(fixer_name: str, repo_path: Path, target_relpath: str) -> bool:
    """
    Apply the appropriate fixer based on fixer name.
    
    Args:
        fixer_name: Name of the fixer to use
        repo_path: Path to repository root
        target_relpath: Relative path to the target file
    
    Returns:
        True if a fix was applied, False otherwise
    """
    try:
        if fixer_name == "fix_sqli":
            from patcher.fix_sqli import apply_fix_sqli
            return apply_fix_sqli(repo_path, target_relpath)
        
        elif fixer_name == "fix_secrets":
            from patcher.fix_secrets import apply_fix_secrets
            return apply_fix_secrets(repo_path, target_relpath)
        
        elif fixer_name == "fix_xss":
            from patcher.fix_xss import apply_fix_xss
            return apply_fix_xss(repo_path, target_relpath)
        
        else:
            print(f"Unknown fixer: {fixer_name}")
            return False
    
    except Exception as e:
        print(f"Error applying {fixer_name}: {e}")
        return False


def process_findings(
    repo_path: Path,
    findings: list[dict],
    rules_path: Path,
) -> tuple[bool, list[dict]]:
    """
    Process Semgrep findings and apply fixes.
    
    Args:
        repo_path: Path to repository root
        findings: List of Semgrep finding dicts
        rules_path: Path to rules file (for determining fix type)
    
    Returns:
        Tuple of (any_changes_made, list of processed findings with fix info)
    """
    if not findings:
        return False, []
    
    any_changes = False
    processed = []
    
    # Track which files have been fixed for each vulnerability type
    # to avoid duplicate fixes
    fixed_files: dict[str, set[str]] = {}  # fixer_name -> set of file paths
    
    for finding in findings:
        check_id = finding.get("check_id", "")
        file_path = finding.get("path")
        
        # Convert absolute path to relative path from repo root
        file_path_obj = Path(file_path)
        if file_path_obj.is_absolute():
            try:
                target_relpath = str(file_path_obj.relative_to(repo_path))
            except ValueError:
                target_relpath = file_path_obj.name
        else:
            target_relpath = str(file_path)
        
        # Determine which fixer to use
        fixer_name = _get_fixer_for_finding(check_id)
        
        changed = False
        if fixer_name:
            # Check if we've already fixed this file for this vulnerability type
            if fixer_name not in fixed_files:
                fixed_files[fixer_name] = set()
            
            if target_relpath not in fixed_files[fixer_name]:
                changed = _apply_fixer(fixer_name, repo_path, target_relpath)
                if changed:
                    any_changes = True
                    fixed_files[fixer_name].add(target_relpath)
        
        processed.append({
            "finding": finding,
            "file": target_relpath,
            "check_id": check_id,
            "fixer": fixer_name,
            "fixed": changed,
        })
    
    return any_changes, processed


def get_supported_vulnerability_types() -> list[str]:
    """
    Get list of supported vulnerability types.
    
    Returns:
        List of vulnerability type descriptions
    """
    return [
        "SQL Injection (Python f-strings, concatenation, .format(), % formatting)",
        "Hardcoded Secrets (passwords, API keys, tokens, database credentials)",
        "XSS (Django/Jinja2 |safe filter, mark_safe(), autoescape off)",
    ]


def get_fixer_info() -> dict:
    """
    Get information about available fixers.
    
    Returns:
        Dict with fixer information
    """
    return {
        "fix_sqli": {
            "name": "SQL Injection Fixer",
            "description": "Converts unsafe SQL queries to parameterized queries",
            "patterns": ["sql-injection", "sqli"],
            "languages": ["python"],
        },
        "fix_secrets": {
            "name": "Hardcoded Secrets Fixer",
            "description": "Replaces hardcoded secrets with os.environ.get()",
            "patterns": ["hardcoded-password", "hardcoded-secret", "aws-access-key", "github-token"],
            "languages": ["python"],
        },
        "fix_xss": {
            "name": "XSS Fixer",
            "description": "Removes unsafe |safe filters and mark_safe() calls",
            "patterns": ["xss", "mark-safe", "safe-filter", "autoescape-off"],
            "languages": ["python", "html/jinja2"],
        },
    }
