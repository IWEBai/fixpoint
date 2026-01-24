"""
AST utilities for parsing Python code and detecting SQL injection patterns.
Supports multiple variable names, cursor names, and injection patterns.
"""
from __future__ import annotations

import ast
import re
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass


# Common SQL variable names used in codebases
SQL_VARIABLE_NAMES = {
    "query", "sql", "stmt", "statement", "command", "cmd",
    "sql_query", "sql_stmt", "sql_command", "raw_sql",
    "select_query", "insert_query", "update_query", "delete_query",
}

# Common cursor/connection object names
CURSOR_NAMES = {
    "cursor", "cur", "c", "db", "conn", "connection",
    "db_cursor", "sql_cursor", "mycursor",
}

# Common execute method names
EXECUTE_METHODS = {"execute", "executemany", "executescript"}


@dataclass
class SQLInjectionPattern:
    """Represents a detected SQL injection pattern."""
    pattern_type: str  # "fstring", "concatenation", "format", "percent"
    var_name: str  # The variable name (query, sql, etc.)
    var_line_idx: int  # 0-based line index of variable assignment
    exec_line_idx: int  # 0-based line index of execute call
    exec_obj_name: str  # The cursor/db object name
    variables: List[str]  # Variables used in the SQL string
    sql_template: str  # The SQL string with placeholders
    original_sql: str  # Original SQL string as written


def extract_fstring_variables(fstring_node: ast.JoinedStr) -> List[str]:
    """
    Extract variable names from an f-string AST node.
    
    Args:
        fstring_node: ast.JoinedStr node (f-string)
    
    Returns:
        List of variable names found in the f-string
    """
    variables = []
    
    for part in fstring_node.values:
        if isinstance(part, ast.FormattedValue):
            # Extract variable name from FormattedValue
            if isinstance(part.value, ast.Name):
                variables.append(part.value.id)
            elif isinstance(part.value, ast.Attribute):
                # Handle attribute access like user.email
                attr_parts = []
                node = part.value
                while isinstance(node, ast.Attribute):
                    attr_parts.insert(0, node.attr)
                    node = node.value
                if isinstance(node, ast.Name):
                    attr_parts.insert(0, node.id)
                    variables.append(".".join(attr_parts))
    
    return variables


def reconstruct_fstring_sql(fstring_node: ast.JoinedStr) -> str:
    """Reconstruct SQL string from f-string AST node with {var} placeholders."""
    sql_parts = []
    for part in fstring_node.values:
        if isinstance(part, ast.Constant):
            sql_parts.append(str(part.value))
        elif isinstance(part, ast.Str):  # Python < 3.8
            sql_parts.append(part.s)
        elif isinstance(part, ast.FormattedValue):
            if isinstance(part.value, ast.Name):
                sql_parts.append(f"{{{part.value.id}}}")
            elif isinstance(part.value, ast.Attribute):
                attr_parts = []
                attr_node = part.value
                while isinstance(attr_node, ast.Attribute):
                    attr_parts.insert(0, attr_node.attr)
                    attr_node = attr_node.value
                if isinstance(attr_node, ast.Name):
                    attr_parts.insert(0, attr_node.id)
                    var_name = ".".join(attr_parts)
                    sql_parts.append(f"{{{var_name}}}")
    return "".join(sql_parts)


def extract_concat_variables(node: ast.BinOp) -> Tuple[List[str], str]:
    """
    Extract variables from string concatenation.
    
    Args:
        node: BinOp node representing concatenation
    
    Returns:
        Tuple of (variables list, reconstructed SQL with {var} placeholders)
    """
    variables = []
    parts = []
    
    def walk_binop(n):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            walk_binop(n.left)
            walk_binop(n.right)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            parts.append(n.value)
        elif isinstance(n, ast.Str):  # Python < 3.8
            parts.append(n.s)
        elif isinstance(n, ast.Name):
            variables.append(n.id)
            parts.append(f"{{{n.id}}}")
        elif isinstance(n, ast.Attribute):
            attr_parts = []
            attr_node = n
            while isinstance(attr_node, ast.Attribute):
                attr_parts.insert(0, attr_node.attr)
                attr_node = attr_node.value
            if isinstance(attr_node, ast.Name):
                attr_parts.insert(0, attr_node.id)
                var_name = ".".join(attr_parts)
                variables.append(var_name)
                parts.append(f"{{{var_name}}}")
        elif isinstance(n, ast.Call):
            # Handle str(var) or similar
            if isinstance(n.func, ast.Name) and n.func.id == "str" and n.args:
                if isinstance(n.args[0], ast.Name):
                    variables.append(n.args[0].id)
                    parts.append(f"{{{n.args[0].id}}}")
    
    walk_binop(node)
    return variables, "".join(parts)


def extract_format_variables(call_node: ast.Call) -> Tuple[List[str], str]:
    """
    Extract variables from .format() call.
    
    Args:
        call_node: Call node for .format()
    
    Returns:
        Tuple of (variables list, reconstructed SQL with {var} placeholders)
    """
    variables = []
    sql_template = ""
    
    # Get the string being formatted
    if isinstance(call_node.func, ast.Attribute):
        if isinstance(call_node.func.value, ast.Constant):
            sql_template = call_node.func.value.value
        elif isinstance(call_node.func.value, ast.Str):
            sql_template = call_node.func.value.s
    
    # Extract variables from args
    for i, arg in enumerate(call_node.args):
        if isinstance(arg, ast.Name):
            variables.append(arg.id)
        elif isinstance(arg, ast.Attribute):
            attr_parts = []
            attr_node = arg
            while isinstance(attr_node, ast.Attribute):
                attr_parts.insert(0, attr_node.attr)
                attr_node = attr_node.value
            if isinstance(attr_node, ast.Name):
                attr_parts.insert(0, attr_node.id)
                variables.append(".".join(attr_parts))
    
    # Extract variables from kwargs
    for kw in call_node.keywords:
        if isinstance(kw.value, ast.Name):
            variables.append(kw.value.id)
    
    return variables, sql_template


def extract_percent_variables(node: ast.BinOp) -> Tuple[List[str], str]:
    """
    Extract variables from % formatting.
    
    Args:
        node: BinOp node with Mod operator
    
    Returns:
        Tuple of (variables list, SQL template)
    """
    variables = []
    sql_template = ""
    
    # Get the string template
    if isinstance(node.left, ast.Constant):
        sql_template = node.left.value
    elif isinstance(node.left, ast.Str):
        sql_template = node.left.s
    
    # Get the variables
    right = node.right
    if isinstance(right, ast.Name):
        variables.append(right.id)
    elif isinstance(right, ast.Tuple):
        for elt in right.elts:
            if isinstance(elt, ast.Name):
                variables.append(elt.id)
            elif isinstance(elt, ast.Attribute):
                attr_parts = []
                attr_node = elt
                while isinstance(attr_node, ast.Attribute):
                    attr_parts.insert(0, attr_node.attr)
                    attr_node = attr_node.value
                if isinstance(attr_node, ast.Name):
                    attr_parts.insert(0, attr_node.id)
                    variables.append(".".join(attr_parts))
    
    return variables, sql_template


def is_sql_like(s: str) -> bool:
    """Check if a string looks like SQL."""
    sql_keywords = r'\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|INTO|VALUES|SET)\b'
    return bool(re.search(sql_keywords, s, re.IGNORECASE))


def find_all_sqli_patterns(code: str) -> List[SQLInjectionPattern]:
    """
    Find all SQL injection patterns in Python code.
    
    Detects:
    - f-string patterns: query = f"SELECT ... {var}"
    - Concatenation: query = "SELECT ... " + var
    - .format(): query = "SELECT ... {}".format(var)
    - % formatting: query = "SELECT ... %s" % var
    
    Args:
        code: Python source code
    
    Returns:
        List of SQLInjectionPattern objects
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    
    patterns = []
    assignments: Dict[str, Dict[str, Any]] = {}  # var_name -> {line, type, variables, sql}
    
    # First pass: find all SQL-like assignments
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.lower() in SQL_VARIABLE_NAMES:
                    var_name = target.id
                    
                    # Check for f-string
                    if isinstance(node.value, ast.JoinedStr):
                        sql = reconstruct_fstring_sql(node.value)
                        if is_sql_like(sql):
                            variables = extract_fstring_variables(node.value)
                            if variables:  # Only if there are injected variables
                                assignments[var_name] = {
                                    "line": node.lineno - 1,
                                    "type": "fstring",
                                    "variables": variables,
                                    "sql": sql,
                                }
                    
                    # Check for concatenation
                    elif isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add):
                        variables, sql = extract_concat_variables(node.value)
                        if variables and is_sql_like(sql):
                            assignments[var_name] = {
                                "line": node.lineno - 1,
                                "type": "concatenation",
                                "variables": variables,
                                "sql": sql,
                            }
                    
                    # Check for .format()
                    elif isinstance(node.value, ast.Call):
                        if isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "format":
                            variables, sql = extract_format_variables(node.value)
                            if variables and is_sql_like(sql):
                                assignments[var_name] = {
                                    "line": node.lineno - 1,
                                    "type": "format",
                                    "variables": variables,
                                    "sql": sql,
                                }
                    
                    # Check for % formatting
                    elif isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Mod):
                        variables, sql = extract_percent_variables(node.value)
                        if variables and is_sql_like(sql):
                            assignments[var_name] = {
                                "line": node.lineno - 1,
                                "type": "percent",
                                "variables": variables,
                                "sql": sql,
                            }
    
    # Second pass: find execute calls that use these variables
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                
                # Check if it's an execute method
                if method_name in EXECUTE_METHODS:
                    # Get the object name
                    obj_name = None
                    if isinstance(node.func.value, ast.Name):
                        obj_name = node.func.value.id
                    elif isinstance(node.func.value, ast.Attribute):
                        # Handle self.cursor, db.cursor(), etc.
                        obj_name = node.func.value.attr
                    
                    # Check if object name is a known cursor/db name
                    if obj_name and obj_name.lower() in CURSOR_NAMES:
                        # Check if first argument is a tracked variable
                        if node.args and isinstance(node.args[0], ast.Name):
                            arg_name = node.args[0].id
                            if arg_name in assignments:
                                info = assignments[arg_name]
                                exec_line = node.lineno - 1
                                
                                # Check distance (within 20 lines)
                                if exec_line > info["line"] and exec_line - info["line"] <= 20:
                                    # Check if already parameterized (has second arg)
                                    if len(node.args) < 2:
                                        patterns.append(SQLInjectionPattern(
                                            pattern_type=info["type"],
                                            var_name=arg_name,
                                            var_line_idx=info["line"],
                                            exec_line_idx=exec_line,
                                            exec_obj_name=obj_name,
                                            variables=info["variables"],
                                            sql_template=info["sql"],
                                            original_sql=info["sql"],
                                        ))
    
    return patterns


# Legacy function for backward compatibility
def find_sqli_pattern_in_ast(code: str) -> Optional[Tuple[int, int, List[str], str]]:
    """
    Find SQL injection pattern using AST parsing (legacy interface).
    
    Returns:
        Tuple of (query_line_idx, exec_line_idx, variables, sql_string) or None
    """
    patterns = find_all_sqli_patterns(code)
    
    if patterns:
        p = patterns[0]  # Return first pattern for backward compatibility
        return (p.var_line_idx, p.exec_line_idx, p.variables, p.sql_template)
    
    return None
