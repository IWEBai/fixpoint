"""
SQL injection fixer using AST parsing.
Handles any variable name, not just {email}.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import ast
from patcher.ast_utils import find_sqli_pattern_in_ast, extract_fstring_variables


def apply_fix_sqli(repo_path: Path, target_relpath: str = "app.py") -> bool:
    """
    Apply deterministic SQLi fix using AST parsing.
    Handles any variable name in f-strings, not just {email}.
    
    Returns True if a patch was applied, otherwise False (pattern mismatch).
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        print(f"ABORT: Target file not found: {target_file}")
        return False

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines(True)

    # Use AST to find the pattern
    result = find_sqli_pattern_in_ast(text)
    
    if result is None:
        print("ABORT: Did not find expected f-string query assignment pattern.")
        return False
    
    query_line_idx, exec_line_idx, variables, sql_string = result
    
    if not variables:
        print("ABORT: No variables found in f-string.")
        return False
    
    if exec_line_idx <= query_line_idx:
        print("ABORT: execute() call not found after query assignment.")
        return False
    
    # Check if execute is within reasonable distance (15 lines)
    if exec_line_idx - query_line_idx > 15:
        print("ABORT: execute() call too far from query assignment.")
        return False
    
    # Get the actual lines for context
    query_line = lines[query_line_idx]
    exec_line = lines[exec_line_idx]
    
    # Extract indentation
    indent = len(query_line) - len(query_line.lstrip())
    indent_str = " " * indent
    
    # Reconstruct parameterized SQL
    # Replace all variable placeholders with %s
    param_sql = sql_string
    for var in variables:
        # Replace {var} and '{var}' patterns
        param_sql = param_sql.replace(f"'{var}'", "%s").replace(f"{var}", "%s")
        # Also handle {var} directly
        param_sql = param_sql.replace(f"{{{var}}}", "%s")
    
    # Determine quote type from original query line
    quote = '"' if '"' in query_line else "'"
    
    # Build new lines
    new_query_line = f"{indent_str}query = {quote}{param_sql}{quote}\n"
    
    # Build execute line with all variables as tuple
    if len(variables) == 1:
        var_tuple = f"({variables[0]},)"
    else:
        var_tuple = f"({', '.join(variables)},)"
    new_exec_line = f"{indent_str}cursor.execute(query, {var_tuple})\n"
    
    # Check if already patched
    query_stripped = query_line.strip()
    exec_stripped = exec_line.strip()
    new_query_stripped = new_query_line.strip()
    new_exec_stripped = new_exec_line.strip()
    
    # Check if it's already parameterized (no f-string, uses %s or ?)
    if "f\"" not in query_stripped and "f'" not in query_stripped:
        if "%s" in query_stripped or "?" in query_stripped:
            if "execute(query," in exec_stripped:
                print("No changes needed (already parameterized).")
                return False
    
    # If already matches our fix, skip
    if query_stripped == new_query_stripped and exec_stripped == new_exec_stripped:
        print("No changes needed (already patched).")
        return False
    
    # Apply patch
    lines[query_line_idx] = new_query_line
    lines[exec_line_idx] = new_exec_line
    
    target_file.write_text("".join(lines), encoding="utf-8")
    
    print("PATCH APPLIED:")
    print(f"- {target_file}")
    print(f"  Replaced: {query_stripped}")
    print(f"    -->  {new_query_stripped}")
    print(f"  Replaced: {exec_stripped}")
    print(f"    -->  {new_exec_stripped}")
    print(f"  Variables: {', '.join(variables)}")
    
    return True


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

    result = find_sqli_pattern_in_ast(text)
    
    if result is None:
        return None
    
    query_line_idx, exec_line_idx, variables, sql_string = result
    
    if not variables:
        return None
    
    query_line = lines[query_line_idx].strip()
    exec_line = lines[exec_line_idx].strip()
    
    # Build proposed fix
    param_sql = sql_string
    for var in variables:
        param_sql = param_sql.replace(f"'{var}'", "%s").replace(f"{var}", "%s").replace(f"{{{var}}}", "%s")
    
    quote = '"' if '"' in query_line else "'"
    indent = len(lines[query_line_idx]) - len(lines[query_line_idx].lstrip())
    indent_str = " " * indent
    
    if len(variables) == 1:
        var_tuple = f"({variables[0]},)"
    else:
        var_tuple = f"({', '.join(variables)},)"
    
    new_query = f"{indent_str}query = {quote}{param_sql}{quote}"
    new_exec = f"{indent_str}cursor.execute(query, {var_tuple})"
    
    return {
        "file": str(target_relpath),
        "line": query_line_idx + 1,  # 1-based for display
        "before": query_line,
        "after": new_query,
        "exec_before": exec_line,
        "exec_after": new_exec,
        "variables": variables,
    }


def main():
    # Local manual test mode
    demo_repo = Path(r"E:\autopatcher-demo-python")
    apply_fix_sqli(demo_repo)


if __name__ == "__main__":
    main()
