"""
XSS vulnerability detection for Jinja2/Django templates and Python code.
Detects unsafe patterns that can lead to Cross-Site Scripting attacks.
"""
from __future__ import annotations

import ast
import re
from typing import List
from dataclasses import dataclass
from pathlib import Path


@dataclass
class XSSVulnerability:
    """Represents a detected XSS vulnerability."""
    vuln_type: str  # "safe_filter", "mark_safe", "autoescape_off", "safestring"
    line_number: int  # 1-based line number
    column: int  # Column offset
    code_snippet: str  # The problematic code
    confidence: str  # "high", "medium", "low"
    file_type: str  # "python", "template"
    description: str  # Human-readable description


# Template patterns for XSS
TEMPLATE_XSS_PATTERNS = [
    # Jinja2/Django |safe filter - marks content as safe (no escaping)
    {
        "pattern": r'\{\{\s*[^}]+\|\s*safe\s*\}\}',
        "type": "safe_filter",
        "description": "Using |safe filter disables HTML escaping",
        "confidence": "high",
    },
    # Django {% autoescape off %} block
    {
        "pattern": r'\{%\s*autoescape\s+off\s*%\}',
        "type": "autoescape_off",
        "description": "autoescape off disables HTML escaping for entire block",
        "confidence": "high",
    },
    # Jinja2 {% autoescape false %} 
    {
        "pattern": r'\{%\s*autoescape\s+false\s*%\}',
        "type": "autoescape_off",
        "description": "autoescape false disables HTML escaping for entire block",
        "confidence": "high",
    },
    # Direct HTML output without escaping (Jinja2 raw)
    {
        "pattern": r'\{%\s*raw\s*%\}.*?\{%\s*endraw\s*%\}',
        "type": "raw_block",
        "description": "raw block outputs content without any processing",
        "confidence": "medium",
    },
]


def find_xss_in_template(content: str, file_path: str = "") -> List[XSSVulnerability]:
    """
    Find XSS vulnerabilities in Jinja2/Django template content.
    
    Args:
        content: Template file content
        file_path: Path to the file (for context)
    
    Returns:
        List of XSSVulnerability objects
    """
    vulnerabilities = []
    lines = content.split('\n')
    
    for i, line in enumerate(lines, 1):
        for pattern_info in TEMPLATE_XSS_PATTERNS:
            matches = re.finditer(pattern_info["pattern"], line, re.IGNORECASE | re.DOTALL)
            for match in matches:
                vulnerabilities.append(XSSVulnerability(
                    vuln_type=pattern_info["type"],
                    line_number=i,
                    column=match.start(),
                    code_snippet=match.group(0)[:80],  # Truncate long matches
                    confidence=pattern_info["confidence"],
                    file_type="template",
                    description=pattern_info["description"],
                ))
    
    return vulnerabilities


def find_xss_in_python(code: str) -> List[XSSVulnerability]:
    """
    Find XSS vulnerabilities in Python code (Django mark_safe, etc.).
    
    Args:
        code: Python source code
    
    Returns:
        List of XSSVulnerability objects
    """
    vulnerabilities = []
    
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return vulnerabilities
    
    lines = code.split('\n')
    
    for node in ast.walk(tree):
        # Check for mark_safe() calls
        if isinstance(node, ast.Call):
            func_name = None
            
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            
            if func_name == "mark_safe":
                # Check if the argument is user input or a variable
                is_user_input = False
                arg_str = ""
                
                if node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Name):
                        is_user_input = True
                        arg_str = arg.id
                    elif isinstance(arg, ast.Call):
                        is_user_input = True
                        arg_str = "(function call)"
                    elif isinstance(arg, ast.BinOp):
                        is_user_input = True
                        arg_str = "(string operation)"
                    elif isinstance(arg, ast.JoinedStr):
                        is_user_input = True
                        arg_str = "(f-string)"
                
                if is_user_input:
                    line_content = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                    vulnerabilities.append(XSSVulnerability(
                        vuln_type="mark_safe",
                        line_number=node.lineno,
                        column=node.col_offset,
                        code_snippet=line_content.strip()[:80],
                        confidence="high",
                        file_type="python",
                        description=f"mark_safe() used with dynamic content ({arg_str})",
                    ))
            
            # Check for format_html() misuse (when first arg is a variable)
            elif func_name == "format_html":
                if node.args and isinstance(node.args[0], (ast.Name, ast.BinOp, ast.JoinedStr)):
                    line_content = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                    vulnerabilities.append(XSSVulnerability(
                        vuln_type="format_html_misuse",
                        line_number=node.lineno,
                        column=node.col_offset,
                        code_snippet=line_content.strip()[:80],
                        confidence="medium",
                        file_type="python",
                        description="format_html() with dynamic format string",
                    ))
        
        # Check for SafeString/SafeText assignments with user input
        elif isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                func_name = None
                if isinstance(node.value.func, ast.Name):
                    func_name = node.value.func.id
                elif isinstance(node.value.func, ast.Attribute):
                    func_name = node.value.func.attr
                
                if func_name in ("SafeString", "SafeText"):
                    if node.value.args and isinstance(node.value.args[0], (ast.Name, ast.Call, ast.BinOp)):
                        line_content = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        vulnerabilities.append(XSSVulnerability(
                            vuln_type="safestring",
                            line_number=node.lineno,
                            column=node.col_offset,
                            code_snippet=line_content.strip()[:80],
                            confidence="high",
                            file_type="python",
                            description="SafeString/SafeText with dynamic content",
                        ))
    
    # Also check for Response with HTML content type without escaping
    for i, line in enumerate(lines, 1):
        # Check for HttpResponse with HTML that might not be escaped
        if "HttpResponse(" in line and "text/html" in line:
            # Look for string concatenation or f-strings
            if " + " in line or "f'" in line or 'f"' in line:
                vulnerabilities.append(XSSVulnerability(
                    vuln_type="http_response_html",
                    line_number=i,
                    column=0,
                    code_snippet=line.strip()[:80],
                    confidence="medium",
                    file_type="python",
                    description="HttpResponse with dynamic HTML content",
                ))
    
    return vulnerabilities


def find_all_xss(file_path: Path) -> List[XSSVulnerability]:
    """
    Find all XSS vulnerabilities in a file (auto-detects file type).
    
    Args:
        file_path: Path to the file
    
    Returns:
        List of XSSVulnerability objects
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        return []
    
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    suffix = file_path.suffix.lower()
    
    # Determine file type
    if suffix in (".html", ".jinja", ".jinja2", ".j2", ".djhtml"):
        return find_xss_in_template(content, str(file_path))
    elif suffix == ".py":
        return find_xss_in_python(content)
    else:
        # Try both if unknown
        vulns = find_xss_in_template(content, str(file_path))
        vulns.extend(find_xss_in_python(content))
        return vulns


def has_xss_vulnerabilities(content: str, is_python: bool = True) -> bool:
    """Quick check if content contains XSS vulnerabilities."""
    if is_python:
        return len(find_xss_in_python(content)) > 0
    else:
        return len(find_xss_in_template(content)) > 0
