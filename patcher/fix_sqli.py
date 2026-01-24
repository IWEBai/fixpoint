"""
SQL injection fixer using AST parsing.
Supports multiple patterns: f-strings, concatenation, .format(), % formatting.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, List
import re
from patcher.ast_utils import (
    find_all_sqli_patterns,
    find_sqli_pattern_in_ast,
    SQLInjectionPattern,
)


def _build_parameterized_sql(pattern: SQLInjectionPattern) -> str:
    """
    Convert SQL with injected variables to parameterized query.
    
    Args:
        pattern: The detected SQL injection pattern
    
    Returns:
        Parameterized SQL string with %s placeholders
    """
    sql = pattern.sql_template
    
    for var in pattern.variables:
        # Replace all forms of variable injection
        # Order matters: most specific first
        
        # 1. '{var}' pattern (quoted f-string variable)
        sql = sql.replace(f"'{{{var}}}'", "%s")
        
        # 2. "{var}" pattern (double-quoted)
        sql = sql.replace(f'"{{{var}}}"', "%s")
        
        # 3. {var} pattern (unquoted f-string variable)
        sql = sql.replace(f"{{{var}}}", "%s")
        
        # 4. For concatenation patterns, variable might appear as literal
        # Don't replace as it should already be {var} from reconstruction
    
    # For .format() patterns, replace {} and {0}, {1}, etc.
    if pattern.pattern_type == "format":
        # Replace positional {} with %s
        sql = re.sub(r'\{\}', '%s', sql)
        # Replace indexed {0}, {1}, etc.
        sql = re.sub(r'\{\d+\}', '%s', sql)
        # Replace named {name} patterns
        sql = re.sub(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}', '%s', sql)
    
    # For % patterns, %s and %d are already placeholders
    # Just ensure the string is safe
    if pattern.pattern_type == "percent":
        # Already has %s or %d placeholders, keep as is
        pass
    
    return sql


def _build_execute_line(
    var_name: str,
    cursor_name: str,
    variables: List[str],
    indent_str: str,
) -> str:
    """Build the new execute line with parameters."""
    if len(variables) == 1:
        var_tuple = f"({variables[0]},)"
    else:
        var_tuple = f"({', '.join(variables)})"
    
    return f"{indent_str}{cursor_name}.execute({var_name}, {var_tuple})\n"


def apply_fix_sqli(repo_path: Path, target_relpath: str = "app.py") -> bool:
    """
    Apply deterministic SQLi fix using AST parsing.
    Handles multiple patterns: f-strings, concatenation, .format(), % formatting.
    
    Returns True if a patch was applied, otherwise False (pattern mismatch).
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        print(f"ABORT: Target file not found: {target_file}")
        return False

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines(True)

    # Find all SQL injection patterns
    patterns = find_all_sqli_patterns(text)
    
    if not patterns:
        print("ABORT: No SQL injection patterns found.")
        return False
    
    # Process the first pattern (for now, handle one at a time)
    pattern = patterns[0]
    
    if not pattern.variables:
        print("ABORT: No variables found in SQL string.")
        return False
    
    # Check distance
    if pattern.exec_line_idx - pattern.var_line_idx > 20:
        print("ABORT: execute() call too far from query assignment.")
        return False
    
    # Get the actual lines
    query_line = lines[pattern.var_line_idx]
    exec_line = lines[pattern.exec_line_idx]
    
    # Extract indentation
    indent = len(query_line) - len(query_line.lstrip())
    indent_str = " " * indent
    
    # Build parameterized SQL
    param_sql = _build_parameterized_sql(pattern)
    
    # Determine quote type from original
    quote = '"' if '"' in query_line else "'"
    
    # Build new query line
    new_query_line = f"{indent_str}{pattern.var_name} = {quote}{param_sql}{quote}\n"
    
    # Build new execute line
    new_exec_line = _build_execute_line(
        pattern.var_name,
        pattern.exec_obj_name,
        pattern.variables,
        indent_str,
    )
    
    # Check if already patched
    query_stripped = query_line.strip()
    exec_stripped = exec_line.strip()
    new_query_stripped = new_query_line.strip()
    new_exec_stripped = new_exec_line.strip()
    
    # Check if it's already parameterized
    is_already_safe = False
    
    # No f-string/format/concat and uses %s or ? placeholder
    if all(marker not in query_stripped for marker in ['f"', "f'", ".format(", " + ", " % "]):
        if "%s" in query_stripped or "?" in query_stripped:
            if f".execute({pattern.var_name}," in exec_stripped:
                is_already_safe = True
    
    if is_already_safe:
        print("No changes needed (already parameterized).")
        return False
    
    # If already matches our fix, skip
    if query_stripped == new_query_stripped and exec_stripped == new_exec_stripped:
        print("No changes needed (already patched).")
        return False
    
    # Apply patch
    lines[pattern.var_line_idx] = new_query_line
    lines[pattern.exec_line_idx] = new_exec_line
    
    target_file.write_text("".join(lines), encoding="utf-8")
    
    print("PATCH APPLIED:")
    print(f"- {target_file}")
    print(f"  Pattern type: {pattern.pattern_type}")
    print(f"  Replaced: {query_stripped}")
    print(f"    -->  {new_query_stripped}")
    print(f"  Replaced: {exec_stripped}")
    print(f"    -->  {new_exec_stripped}")
    print(f"  Variables: {', '.join(pattern.variables)}")
    
    return True


def apply_all_fixes(repo_path: Path, target_relpath: str = "app.py") -> int:
    """
    Apply all SQL injection fixes in a file.
    
    Returns number of fixes applied.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath
    
    if not target_file.exists():
        return 0
    
    fixes_applied = 0
    max_iterations = 10  # Safety limit
    
    for _ in range(max_iterations):
        if apply_fix_sqli(repo_path, target_relpath):
            fixes_applied += 1
        else:
            break
    
    return fixes_applied


def propose_fix_sqli(repo_path: Path, target_relpath: str) -> Optional[dict]:
    """
    Propose a fix without applying it (for warn mode).
    
    Returns:
        Dict with fix proposal or None if no fix needed
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        return None

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines(True)

    # Find all patterns
    patterns = find_all_sqli_patterns(text)
    
    if not patterns:
        return None
    
    pattern = patterns[0]
    
    if not pattern.variables:
        return None
    
    query_line = lines[pattern.var_line_idx].strip()
    exec_line = lines[pattern.exec_line_idx].strip()
    
    # Build proposed fix
    param_sql = _build_parameterized_sql(pattern)
    
    quote = '"' if '"' in query_line else "'"
    indent = len(lines[pattern.var_line_idx]) - len(lines[pattern.var_line_idx].lstrip())
    indent_str = " " * indent
    
    if len(pattern.variables) == 1:
        var_tuple = f"({pattern.variables[0]},)"
    else:
        var_tuple = f"({', '.join(pattern.variables)})"
    
    new_query = f"{indent_str}{pattern.var_name} = {quote}{param_sql}{quote}"
    new_exec = f"{indent_str}{pattern.exec_obj_name}.execute({pattern.var_name}, {var_tuple})"
    
    return {
        "file": str(target_relpath),
        "line": pattern.var_line_idx + 1,  # 1-based for display
        "pattern_type": pattern.pattern_type,
        "before": query_line,
        "after": new_query,
        "exec_before": exec_line,
        "exec_after": new_exec,
        "variables": pattern.variables,
    }


def propose_all_fixes(repo_path: Path, target_relpath: str) -> List[dict]:
    """
    Propose all fixes for a file (for warn mode).
    
    Returns:
        List of fix proposals
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        return []

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines(True)

    patterns = find_all_sqli_patterns(text)
    proposals = []
    
    for pattern in patterns:
        if not pattern.variables:
            continue
        
        query_line = lines[pattern.var_line_idx].strip()
        exec_line = lines[pattern.exec_line_idx].strip()
        
        param_sql = _build_parameterized_sql(pattern)
        
        quote = '"' if '"' in query_line else "'"
        indent = len(lines[pattern.var_line_idx]) - len(lines[pattern.var_line_idx].lstrip())
        indent_str = " " * indent
        
        if len(pattern.variables) == 1:
            var_tuple = f"({pattern.variables[0]},)"
        else:
            var_tuple = f"({', '.join(pattern.variables)})"
        
        new_query = f"{indent_str}{pattern.var_name} = {quote}{param_sql}{quote}"
        new_exec = f"{indent_str}{pattern.exec_obj_name}.execute({pattern.var_name}, {var_tuple})"
        
        proposals.append({
            "file": str(target_relpath),
            "line": pattern.var_line_idx + 1,
            "pattern_type": pattern.pattern_type,
            "before": query_line,
            "after": new_query,
            "exec_before": exec_line,
            "exec_after": new_exec,
            "variables": pattern.variables,
        })
    
    return proposals


def main():
    # Local manual test mode
    demo_repo = Path(r"E:\autopatcher-demo-python")
    apply_fix_sqli(demo_repo)


if __name__ == "__main__":
    main()
