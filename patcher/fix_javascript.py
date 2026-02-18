"""
JavaScript/TypeScript fixers.
Handles eval, hardcoded secrets, and DOM XSS.
"""
from __future__ import annotations

import re
from pathlib import Path


def apply_fix_js_eval(repo_path: Path, target_relpath: str) -> bool:
    """
    Remove or replace eval() usage.
    For JSON: eval(x) -> JSON.parse(x)
    For other: add comment recommending removal (no safe general replacement).
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        return False
    
    # Intentionally detection-only in this phase: we do not auto-fix generic
    # eval() usage because safe transformations are highly context dependent.

    # Simple case: eval(jsonString) -> JSON.parse(jsonString) when it looks like JSON
    # Pattern: eval("...") or eval(`...`) with JSON-like content is rare; usually eval(var)
    # Safer: replace eval(x) with a validated pattern - only when x is a string literal that looks like JSON
    # For now: replace eval( with /* eval removed - use JSON.parse for JSON */ JSON.parse(
    # That would break non-JSON. Better: detection only for Phase 3B, propose fix in comment.
    # Minimal fix: wrap in try/catch and suggest JSON.parse - too invasive.
    # We'll do: eval(...) -> (() => { throw new Error("eval removed: use JSON.parse for JSON or safe alternative"); })()
    # No - that breaks the code. Let's do a simple replacement: for eval("...") where content is JSON-like
    # Actually the safest deterministic fix: replace eval with Function for same-line code execution?
    # No - Function has similar risks. The standard fix is: don't use eval. Use JSON.parse for JSON.
    # For generic eval we cannot safely auto-fix. Return False - detection only, guidance in warn comment.
    return False


def apply_fix_js_secrets(repo_path: Path, target_relpath: str) -> bool:
    """
    Replace hardcoded secrets with process.env / import.meta.env.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        return False

    text = target_file.read_text(encoding="utf-8", errors="ignore")

    # Match: apiKey = "xxx" or api_key: "xxx" or const secret = "xxx"
    # Better: replace value with process.env.API_KEY etc.
    def replacer(m):
        key = m.group(1).replace("-", "_").upper()
        env_name = key if key in ("API_KEY", "API_TOKEN", "SECRET", "PASSWORD") else "API_KEY"
        return f'{m.group(1)} = process.env.{env_name} || ""'
    # Simplified: apiKey = "xxx" -> apiKey = process.env.API_KEY
    pat = re.compile(
        r'(\b(?:api_key|apiKey|access_token|accessToken|secret|password)\s*[:=]\s*)["\']([^"\']{8,})["\']',
        re.IGNORECASE
    )

    def replace_secret(m):
        prefix = m.group(1)
        env_name = "API_KEY"
        if "token" in m.group(0).lower():
            env_name = "ACCESS_TOKEN"
        elif "password" in m.group(0).lower():
            env_name = "PASSWORD"
        elif "secret" in m.group(0).lower():
            env_name = "SECRET"
        return f'{prefix}process.env.{env_name} || ""'

    new_text, n = pat.subn(replace_secret, text)
    if n > 0:
        target_file.write_text(new_text, encoding="utf-8")
        return True
    return False


def apply_fix_js_dom_xss(repo_path: Path, target_relpath: str) -> bool:
    """
    Replace innerHTML with textContent for user-controlled content.
    Note: innerHTML may be intentional for trusted HTML - this is a heuristic fix.
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        return False

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    # Simple replacement: .innerHTML = -> .textContent = (escapes HTML)
    # This can break intentional HTML rendering - use with caution
    if ".innerHTML =" in text or ".innerHTML=" in text:
        new_text = text.replace(".innerHTML =", ".textContent =").replace(".innerHTML=", ".textContent=")
        if new_text != text:
            target_file.write_text(new_text, encoding="utf-8")
            return True
    return False


def propose_fix_js_eval(repo_path: Path, target_relpath: str) -> list[dict] | None:
    return [{
        "file": target_relpath,
        "line": 0,
        "before": "eval(userInput)",
        "after": "JSON.parse(userInput)  // Only if input is JSON; otherwise remove eval",
    }]


def propose_fix_js_secrets(repo_path: Path, target_relpath: str) -> list[dict] | None:
    return [{
        "file": target_relpath,
        "line": 0,
        "before": "apiKey = \"sk_live_xxx\"",
        "after": "apiKey = process.env.API_KEY",
    }]


def propose_fix_js_dom_xss(repo_path: Path, target_relpath: str) -> list[dict] | None:
    return [{
        "file": target_relpath,
        "line": 0,
        "before": "el.innerHTML = userInput",
        "after": "el.textContent = userInput  // or use sanitization library",
    }]
