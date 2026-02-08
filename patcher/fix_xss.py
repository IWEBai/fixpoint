"""
XSS vulnerability fixer for Jinja2/Django templates and Python code.
Removes unsafe patterns that can lead to Cross-Site Scripting attacks.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, List
from patcher.detect_xss import find_xss_in_template, find_xss_in_python


def _fix_safe_filter_in_line(line: str) -> str:
    """
    Remove |safe filter from a template line.
    {{ variable|safe }} -> {{ variable }}
    """
    # Pattern: {{ anything |safe }} or {{ anything | safe }}
    # Capture the variable part and remove |safe with any surrounding whitespace
    pattern = r'(\{\{\s*[^}|]+?)\s*\|\s*safe\s*(\}\})'
    return re.sub(pattern, r'\1 \2', line)


def _fix_autoescape_off_block(content: str) -> str:
    """
    Remove autoescape off blocks, keeping the content but with autoescape on.
    {% autoescape off %}...{% endautoescape %} -> content (with default escaping)
    """
    # Django style
    content = re.sub(
        r'\{%\s*autoescape\s+off\s*%\}(.*?)\{%\s*endautoescape\s*%\}',
        r'\1',
        content,
        flags=re.DOTALL | re.IGNORECASE
    )
    
    # Jinja2 style
    content = re.sub(
        r'\{%\s*autoescape\s+false\s*%\}(.*?)\{%\s*endautoescape\s*%\}',
        r'\1',
        content,
        flags=re.DOTALL | re.IGNORECASE
    )
    
    return content


def _fix_mark_safe_in_line(line: str) -> str:
    """
    Replace mark_safe(x) with escape(x) or just x.
    This is a conservative fix - it wraps with escape() to ensure safety.
    """
    # Pattern: mark_safe(anything)
    # Replace with: escape(anything)
    pattern = r'mark_safe\(([^)]+)\)'
    
    # Check if escape is being used
    if 'escape(' in line:
        # Already using escape, just remove mark_safe wrapper
        return re.sub(pattern, r'\1', line)
    else:
        # Replace with escape()
        return re.sub(pattern, r'escape(\1)', line)


def _ensure_escape_import(lines: List[str]) -> tuple[List[str], int]:
    """
    Ensure 'from django.utils.html import escape' is present.
    Returns (modified lines, offset).
    """
    # Check if escape is already imported
    for i, line in enumerate(lines):
        if 'from django.utils.html import' in line and 'escape' in line:
            return lines, 0
        if 'from markupsafe import escape' in line:
            return lines, 0
        if 'from html import escape' in line:
            return lines, 0
    
    # Find import section
    insert_pos = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('from django') or stripped.startswith('import django'):
            insert_pos = i + 1
        elif stripped.startswith('import ') or stripped.startswith('from '):
            insert_pos = i + 1
        elif stripped and not stripped.startswith('#') and insert_pos > 0:
            break
    
    # Insert import
    lines.insert(insert_pos, "from django.utils.html import escape\n")
    return lines, 1


def apply_fix_xss_template(repo_path: Path, target_relpath: str) -> bool:
    """
    Apply XSS fixes to a template file.
    
    Returns True if a patch was applied, otherwise False.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        print(f"ABORT: Target file not found: {target_file}")
        return False
    
    content = target_file.read_text(encoding="utf-8", errors="ignore")
    original_content = content
    
    vulns = find_xss_in_template(content, str(target_file))
    
    if not vulns:
        print("No XSS vulnerabilities found in template.")
        return False
    
    # Apply fixes
    fixed_count = 0
    
    # Fix |safe filters
    safe_vulns = [v for v in vulns if v.vuln_type == "safe_filter"]
    if safe_vulns:
        lines = content.split('\n')
        for vuln in safe_vulns:
            if vuln.line_number <= len(lines):
                old_line = lines[vuln.line_number - 1]
                new_line = _fix_safe_filter_in_line(old_line)
                if old_line != new_line:
                    lines[vuln.line_number - 1] = new_line
                    fixed_count += 1
        content = '\n'.join(lines)
    
    # Fix autoescape off blocks
    autoescape_vulns = [v for v in vulns if v.vuln_type == "autoescape_off"]
    if autoescape_vulns:
        new_content = _fix_autoescape_off_block(content)
        if new_content != content:
            content = new_content
            fixed_count += len(autoescape_vulns)
    
    if content == original_content:
        print("No changes made (already safe or cannot auto-fix).")
        return False
    
    target_file.write_text(content, encoding="utf-8")
    
    print("PATCH APPLIED:")
    print(f"- {target_file}")
    print(f"  Fixed {fixed_count} XSS vulnerability(ies)")
    for vuln in vulns[:3]:  # Show first 3
        print(f"    - Line {vuln.line_number}: {vuln.vuln_type}")
    
    return True


def apply_fix_xss_python(repo_path: Path, target_relpath: str) -> bool:
    """
    Apply XSS fixes to a Python file.
    
    Returns True if a patch was applied, otherwise False.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        print(f"ABORT: Target file not found: {target_file}")
        return False
    
    content = target_file.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines(True)
    original_lines = lines.copy()
    
    vulns = find_xss_in_python(content)
    
    if not vulns:
        print("No XSS vulnerabilities found in Python file.")
        return False
    
    # Filter to fixable vulnerabilities
    fixable = [v for v in vulns if v.vuln_type in ("mark_safe", "safestring")]
    
    if not fixable:
        print("No auto-fixable XSS vulnerabilities found.")
        return False
    
    # Fix mark_safe calls
    mark_safe_vulns = [v for v in fixable if v.vuln_type == "mark_safe"]
    needs_escape_import = False
    
    for vuln in mark_safe_vulns:
        if vuln.line_number <= len(lines):
            line_idx = vuln.line_number - 1
            old_line = lines[line_idx]
            new_line = _fix_mark_safe_in_line(old_line)
            if old_line != new_line:
                lines[line_idx] = new_line
                if 'escape(' in new_line and 'escape(' not in old_line:
                    needs_escape_import = True
    
    # Add escape import if needed
    offset = 0
    if needs_escape_import:
        lines, offset = _ensure_escape_import(lines)
    
    if lines == original_lines:
        print("No changes made (already safe or cannot auto-fix).")
        return False
    
    target_file.write_text("".join(lines), encoding="utf-8")
    
    print("PATCH APPLIED:")
    print(f"- {target_file}")
    print(f"  Fixed {len(mark_safe_vulns)} XSS vulnerability(ies)")
    for vuln in mark_safe_vulns[:3]:
        print(f"    - Line {vuln.line_number}: mark_safe() -> escape()")
    
    return True


def apply_fix_xss(repo_path: Path, target_relpath: str) -> bool:
    """
    Apply XSS fixes to a file (auto-detects type).
    
    Returns True if a patch was applied, otherwise False.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        print(f"ABORT: Target file not found: {target_file}")
        return False
    
    suffix = target_file.suffix.lower()
    
    if suffix in (".html", ".jinja", ".jinja2", ".j2", ".djhtml"):
        return apply_fix_xss_template(repo_path, target_relpath)
    elif suffix == ".py":
        return apply_fix_xss_python(repo_path, target_relpath)
    else:
        # Try both
        result = apply_fix_xss_template(repo_path, target_relpath)
        if not result:
            result = apply_fix_xss_python(repo_path, target_relpath)
        return result


def propose_fix_xss(repo_path: Path, target_relpath: str) -> Optional[dict]:
    """
    Propose an XSS fix without applying it (for warn mode).
    
    Returns:
        Dict with fix proposal or None if no fix needed
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        return None
    
    content = target_file.read_text(encoding="utf-8", errors="ignore")
    suffix = target_file.suffix.lower()
    
    # Get vulnerabilities based on file type
    if suffix in (".html", ".jinja", ".jinja2", ".j2", ".djhtml"):
        vulns = find_xss_in_template(content, str(target_file))
    elif suffix == ".py":
        vulns = find_xss_in_python(content)
    else:
        vulns = find_xss_in_template(content, str(target_file))
        vulns.extend(find_xss_in_python(content))
    
    if not vulns:
        return None
    
    vuln = vulns[0]
    
    # Format for consistent display in PR comments
    before = vuln.code_snippet or "mark_safe(user_input)"
    if vuln.vuln_type == "safe_filter":
        after = before.replace("|safe", "")
    elif vuln.vuln_type == "autoescape_off":
        after = "{% autoescape on %} ... {% endautoescape %}"
    elif "mark_safe" in before:
        after = before.replace("mark_safe(", "escape(")
    elif "SafeString" in before:
        after = before.replace("SafeString(", "escape(")
    else:
        after = "Use safe escaping"
    
    return {
        "file": str(target_relpath),
        "line": vuln.line_number,
        "before": before,
        "after": after,
        "vuln_type": vuln.vuln_type,
        "confidence": vuln.confidence,
        "description": vuln.description,
        "code_snippet": vuln.code_snippet,
        "message": f"XSS vulnerability: {vuln.description}",
    }


def propose_all_fixes_xss(repo_path: Path, target_relpath: str) -> List[dict]:
    """
    Propose all XSS fixes for a file.
    
    Returns:
        List of fix proposals
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        return []
    
    content = target_file.read_text(encoding="utf-8", errors="ignore")
    suffix = target_file.suffix.lower()
    
    if suffix in (".html", ".jinja", ".jinja2", ".j2", ".djhtml"):
        vulns = find_xss_in_template(content, str(target_file))
    elif suffix == ".py":
        vulns = find_xss_in_python(content)
    else:
        vulns = find_xss_in_template(content, str(target_file))
        vulns.extend(find_xss_in_python(content))
    
    proposals = []
    for vuln in vulns:
        proposals.append({
            "file": str(target_relpath),
            "line": vuln.line_number,
            "vuln_type": vuln.vuln_type,
            "confidence": vuln.confidence,
            "description": vuln.description,
            "code_snippet": vuln.code_snippet,
            "message": f"XSS vulnerability: {vuln.description}",
        })
    
    return proposals
