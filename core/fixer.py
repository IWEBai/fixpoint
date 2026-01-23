"""
Core fixing engine for AuditShield.
Processes Semgrep findings and applies deterministic fixes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


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
    
    # Import fixers dynamically
    from patcher.fix_sqli import apply_fix_sqli
    
    any_changes = False
    processed = []
    
    # Group findings by check_id to determine fix type
    for finding in findings:
        check_id = finding.get("check_id", "")
        file_path = finding.get("path")
        
        # Convert absolute path to relative path from repo root
        file_path_obj = Path(file_path)
        if file_path_obj.is_absolute():
            try:
                target_relpath = file_path_obj.relative_to(repo_path)
            except ValueError:
                target_relpath = file_path_obj.name
        else:
            target_relpath = file_path
        
        # Determine which fixer to use based on check_id
        changed = False
        if "sql-injection" in check_id.lower() or "sqli" in check_id.lower():
            changed = apply_fix_sqli(repo_path, str(target_relpath))
            if changed:
                any_changes = True
        
        processed.append({
            "finding": finding,
            "file": str(target_relpath),
            "fixed": changed,
        })
    
    return any_changes, processed
