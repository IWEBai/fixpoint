"""
AST utilities for parsing Python code and extracting variables from f-strings.
"""
from __future__ import annotations

import ast
from typing import Optional, Tuple, List


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
                # For now, we'll use the full attribute path
                attr_parts = []
                node = part.value
                while isinstance(node, ast.Attribute):
                    attr_parts.insert(0, node.attr)
                    node = node.value
                if isinstance(node, ast.Name):
                    attr_parts.insert(0, node.id)
                    variables.append(".".join(attr_parts))
    
    return variables


def find_sqli_pattern_in_ast(code: str) -> Optional[Tuple[int, int, List[str], str]]:
    """
    Find SQL injection pattern using AST parsing.
    
    Looks for:
    - Assignment: query = f"..."
    - Execution: cursor.execute(query)
    
    Args:
        code: Python source code
    
    Returns:
        Tuple of (query_line_idx, exec_line_idx, variables, sql_string) or None
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    
    query_line_idx = None
    exec_line_idx = None
    variables = []
    sql_string = ""
    
    # Find query assignment
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "query":
                    # Check if value is an f-string
                    if isinstance(node.value, ast.JoinedStr):
                        query_line_idx = node.lineno - 1  # Convert to 0-based
                        variables = extract_fstring_variables(node.value)
                        # Reconstruct SQL string from f-string parts
                        sql_parts = []
                        for part in node.value.values:
                            if isinstance(part, ast.Constant):
                                sql_parts.append(str(part.value))
                            elif isinstance(part, ast.Str):  # Python < 3.8
                                sql_parts.append(part.s)
                            elif isinstance(part, ast.FormattedValue):
                                # Placeholder for variable - we'll extract the variable name
                                if isinstance(part.value, ast.Name):
                                    sql_parts.append(f"{{{part.value.id}}}")
                                elif isinstance(part.value, ast.Attribute):
                                    # Handle attribute access like user.email
                                    attr_parts = []
                                    attr_node = part.value
                                    while isinstance(attr_node, ast.Attribute):
                                        attr_parts.insert(0, attr_node.attr)
                                        attr_node = attr_node.value
                                    if isinstance(attr_node, ast.Name):
                                        attr_parts.insert(0, attr_node.id)
                                        var_name = ".".join(attr_parts)
                                        sql_parts.append(f"{{{var_name}}}")
                        sql_string = "".join(sql_parts)
                        break
    
    # Find cursor.execute(query) after query assignment
    if query_line_idx is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "execute":
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == "cursor":
                            # Check if first arg is just "query" (Name node)
                            if node.args and isinstance(node.args[0], ast.Name):
                                if node.args[0].id == "query":
                                    exec_line_idx = node.lineno - 1  # Convert to 0-based
                                    break
    
    if query_line_idx is not None and exec_line_idx is not None and exec_line_idx > query_line_idx:
        return (query_line_idx, exec_line_idx, variables, sql_string)
    
    return None
