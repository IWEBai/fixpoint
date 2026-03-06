"""
Lightweight check_id → vulnerability category classifier.

Used wherever findings are recorded (webhook processing, dashboard queries)
to produce a consistent human-readable label for each vulnerability type.
"""
from __future__ import annotations

# Ordered list of (keywords, label) — first match wins.
_RULES: list[tuple[tuple[str, ...], str]] = [
    (("sql", "sqli"), "SQLi"),
    (("xss", "mark-safe", "safe-filter", "dom-xss"), "XSS"),
    (("hardcoded", "secret", "private-key", "api-key", "token", "password", "credential"), "Secrets"),
    (("command-injection", "os-system", "subprocess"), "Command Injection"),
    (("path-traversal", "path_traversal", "directory-traversal"), "Path Traversal"),
    (("ssrf",), "SSRF"),
    (("open-redirect",), "Open Redirect"),
    (("xxe",), "XXE"),
]

_FALLBACK = "Other"


def classify_check_id(check_id: str) -> str:
    """Return a human-readable vulnerability category for a Semgrep check_id."""
    cid = (check_id or "").lower()
    for keywords, label in _RULES:
        if any(kw in cid for kw in keywords):
            return label
    return _FALLBACK


def classify_findings(findings: list[dict]) -> list[str]:
    """Return a list of category labels (one per finding, may contain duplicates)."""
    return [classify_check_id(f.get("check_id", "")) for f in findings]
