"""
Command injection fixer.
Converts os.system and subprocess with shell=True to safe list-based subprocess.
"""
from __future__ import annotations

import ast
from pathlib import Path


def _ensure_imports(text: str) -> str:
    """Ensure subprocess and shlex are imported."""
    lines = text.splitlines()
    has_subprocess = "subprocess" in text and ("import subprocess" in text or "from subprocess" in text)
    has_shlex = "shlex" in text and ("import shlex" in text or "from shlex" in text)

    if has_subprocess and has_shlex:
        return text

    import_section_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and ("import " in stripped or "from " in stripped):
            import_section_end = i + 1
        elif import_section_end > 0 and stripped and not stripped.startswith("#"):
            break

    to_add = []
    if not has_subprocess:
        to_add.append("import subprocess")
    if not has_shlex:
        to_add.append("import shlex")

    if to_add:
        insert_line = import_section_end
        for imp in to_add:
            lines.insert(insert_line, imp)
            insert_line += 1

    return "\n".join(lines)


def _get_source_for_node(source: str, node: ast.AST) -> str:
    """Extract source code for a node (approximate for simple cases)."""
    if hasattr(ast, "get_source_segment") and source:
        return ast.get_source_segment(source, node) or ""
    return ""


def _fix_os_system(node: ast.Call, source: str) -> tuple[str, str] | None:
    """Convert os.system(cmd) to subprocess.run(shlex.split(cmd), shell=False)."""
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != "system":
        return None
    if not node.args:
        return None

    arg = node.args[0]
    if hasattr(ast, "get_source_segment") and source:
        arg_src = ast.get_source_segment(source, arg) or "arg"
    else:
        arg_src = "cmd"

    old = _get_source_for_node(source, node) or f"os.system({arg_src})"
    new = f"subprocess.run(shlex.split({arg_src}), shell=False)"
    return old, new


def _fix_subprocess_shell(node: ast.Call, source: str) -> tuple[str, str] | None:
    """Convert subprocess.X(cmd, shell=True) to subprocess.X(shlex.split(cmd), shell=False)."""
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr not in ("run", "call", "check_call", "check_output", "Popen"):
        return None
    if not node.args:
        return None

    has_shell_true = False
    for kw in node.keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            has_shell_true = True
            break

    if not has_shell_true:
        return None

    arg = node.args[0]
    if hasattr(ast, "get_source_segment") and source:
        arg_src = ast.get_source_segment(source, arg) or "cmd"
    else:
        arg_src = "cmd"

    old = _get_source_for_node(source, node)
    if not old:
        return None

    # Simple replacement: wrap first arg and change shell=True to shell=False
    new_arg = f"shlex.split({arg_src}) if isinstance({arg_src}, str) else {arg_src}"
    new = old.replace(arg_src, new_arg, 1).replace("shell=True", "shell=False").replace("shell = True", "shell=False")
    return old, new


def apply_fix_command_injection(repo_path: Path, target_relpath: str) -> bool:
    """
    Apply command injection fix: convert os.system/subprocess+shell to safe subprocess.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        return False

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    source = text

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False

    replacements: list[tuple[int, str, str]] = []  # (line_no, old, new)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if (getattr(node.func.value, "id", None) == "os" and node.func.attr == "system"):
                    result = _fix_os_system(node, source)
                    if result:
                        old, new = result
                        line_no = node.lineno
                        replacements.append((line_no, old, new))
                elif getattr(node.func.value, "id", None) == "subprocess":
                    result = _fix_subprocess_shell(node, source)
                    if result:
                        old, new = result
                        line_no = node.lineno
                        replacements.append((line_no, old, new))

    if not replacements:
        return False

    # Apply replacements first (before adding imports, to preserve line numbers)
    seen_lines = set()
    lines = text.splitlines(True)

    for line_no, old, new in replacements:
        if line_no in seen_lines:
            continue
        idx = line_no - 1
        if idx < 0 or idx >= len(lines):
            continue
        line = lines[idx]
        if old in line:
            lines[idx] = line.replace(old, new, 1)
            seen_lines.add(line_no)

    if not seen_lines:
        return False

    # Add imports after replacements
    text = _ensure_imports("".join(lines))
    target_file.write_text(text, encoding="utf-8")
    return True


def propose_fix_command_injection(repo_path: Path, target_relpath: str) -> list[dict] | None:
    """Propose fixes for command injection (warn mode)."""
    # Simplified: return indication that fix would apply
    return [{"file": target_relpath, "line": 0, "before": "os.system(cmd)", "after": "subprocess.run(shlex.split(cmd), shell=False)"}]
