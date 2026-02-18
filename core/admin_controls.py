"""
Admin controls for Fixpoint App/SaaS operations.

These controls are intentionally simple and env-driven to support
incident response without redeploying code.
"""
from __future__ import annotations

import os
from typing import Iterable, Tuple


_RULE_ALIASES: dict[str, list[str]] = {
    "sqli": ["sql-injection", "sqli"],
    "secrets": [
        "secret",
        "token",
        "password",
        "access-key",
        "private-key",
        "database-uri",
        "github-token",
        "slack-token",
        "stripe-key",
        "sendgrid-key",
    ],
    "xss": ["xss", "mark-safe", "safe-filter", "autoescape"],
    "command-injection": ["command-injection", "os-system", "subprocess-shell"],
    "path-traversal": ["path-traversal"],
    "ssrf": ["ssrf"],
    "eval": ["eval", "javascript-eval", "typescript-eval", "eval-dangerous"],
    "dom-xss": ["dom-xss", "innerhtml", "document-write"],
}


def _split_list(value: str) -> list[str]:
    return [v.strip().lower() for v in (value or "").split(",") if v.strip()]


def get_disabled_repos() -> list[str]:
    return _split_list(os.getenv("FIXPOINT_DISABLED_REPOS", ""))


def get_force_warn_orgs() -> list[str]:
    return _split_list(os.getenv("FIXPOINT_FORCE_WARN_ORGS", ""))


def get_disabled_rules() -> list[str]:
    return _split_list(os.getenv("FIXPOINT_DISABLED_RULES", ""))


def is_repo_disabled(full_repo_name: str) -> Tuple[bool, str | None]:
    if not full_repo_name:
        return False, None
    repo = full_repo_name.lower().strip()
    disabled = get_disabled_repos()
    if repo in disabled:
        return True, f"Repository '{repo}' disabled by admin controls"
    return False, None


def is_force_warn_org(owner: str | None) -> bool:
    if not owner:
        return False
    return owner.lower().strip() in get_force_warn_orgs()


def _match_rule_key(check_id_lower: str, rule_key: str) -> bool:
    key = str(rule_key or "").lower().strip()
    if not key:
        return False
    if key in check_id_lower:
        return True
    for alias in _RULE_ALIASES.get(key, []):
        if alias and alias in check_id_lower:
            return True
    return False


def filter_findings_by_rules(findings: list[dict], disabled_rules: Iterable[str]) -> tuple[list[dict], int]:
    disabled = [str(r).lower().strip() for r in disabled_rules if r]
    if not disabled:
        return findings, 0

    kept: list[dict] = []
    dropped = 0
    for f in findings or []:
        check_id = str(f.get("check_id", "") or "").lower()
        if any(_match_rule_key(check_id, rule) for rule in disabled):
            dropped += 1
            continue
        kept.append(f)

    return kept, dropped
