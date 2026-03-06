"""
Service functions for creating separate fix PRs.
Builds fix branches from the current working tree, pushes them, and opens PRs.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import Iterable, Tuple

from core.git_ops import commit_and_push_new_branch
from github_bot.open_pr import open_or_get_pr


# ---------------------------------------------------------------------------
# Vuln classification helpers
# ---------------------------------------------------------------------------

_VULN_ALIASES = {
    "sql": "sqli",
    "sqli": "sqli",
    "xss": "xss",
    "secret": "secrets",
    "password": "secrets",
    "token": "secrets",
    "command": "cmdinj",
    "path": "path",
    "ssrf": "ssrf",
    "eval": "eval",
}


def _detect_primary_vuln(findings: Iterable[dict]) -> str:
    for f in findings:
        check_id = str(f.get("check_id", "") or "").lower()
        for key, val in _VULN_ALIASES.items():
            if key in check_id:
                return val
    return "security"


def _vuln_label(check_id: str) -> str:
    """Map a Semgrep check_id to a short, human-readable vulnerability label."""
    cid = check_id.lower()
    if "sql" in cid or "sqli" in cid:
        return "SQL Injection"
    if "xss" in cid or "mark-safe" in cid or "innerhtml" in cid or "dom" in cid:
        return "XSS"
    if "secret" in cid or "password" in cid or "hardcoded" in cid or "token" in cid:
        return "Hardcoded Secret"
    if "command" in cid or "os-system" in cid or "subprocess" in cid:
        return "Command Injection"
    if "path" in cid or "traversal" in cid:
        return "Path Traversal"
    if "ssrf" in cid:
        return "SSRF"
    if "eval" in cid:
        return "Dangerous eval"
    return "Security Issue"


def generate_fix_branch_name(findings: list[dict], original_pr_number: int) -> str:
    """
    Generate a readable, human-friendly fix branch name.

    Format: railo/pr{N}-fix-{vuln}-{YYYYMMDD}
    Example: railo/pr42-fix-sqli-20260306

    - PR number first so developers immediately know which PR it relates to
    - Vuln type is human-readable, not an opaque hash
    - Date suffix provides per-day uniqueness; open_or_get_pr handles same-day idempotency
    """
    vuln = _detect_primary_vuln(findings)
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"railo/pr{original_pr_number}-fix-{vuln}-{date}"


def estimate_fix_safety(findings: list[dict]) -> float:
    """Return safety score 0-100 using heuristic based on confidence and size."""
    if not findings:
        return 0.0

    confidences: list[float] = []
    for f in findings:
        meta = (f.get("extra", {}) or {}).get("metadata", {}) or {}
        conf = meta.get("confidence") or meta.get("probability") or meta.get("severity")
        try:
            conf_val = float(conf)
        except (TypeError, ValueError):
            conf_val = 75.0
        confidences.append(conf_val)

    avg_conf = sum(confidences) / max(len(confidences), 1)
    conf_score = 10 if avg_conf < 50 else 20 if avg_conf < 75 else 40

    # Approximate size by number of findings (proxy for lines changed)
    finding_count = len(findings)
    if finding_count <= 5:
        size_score = 40
    elif finding_count <= 20:
        size_score = 30
    elif finding_count <= 50:
        size_score = 20
    else:
        size_score = 0

    # Assume low logic complexity by default; can be enhanced later
    logic_score = 20

    total = conf_score + size_score + logic_score
    return float(max(0, min(100, total)))


def estimate_fix_confidence(findings: list[dict]) -> float:
    """
    Return a 0-100 confidence score representing how certain the patches are correct.

    Uses `extra.metadata.confidence` / `probability` from Semgrep findings when
    available; falls back to 75 for findings without explicit confidence metadata.
    String values ("high", "medium", "low") are mapped to numeric equivalents.
    """
    if not findings:
        return 0.0

    _str_map = {"critical": 95.0, "high": 85.0, "medium": 65.0, "low": 40.0, "info": 20.0}

    values: list[float] = []
    for f in findings:
        meta = (f.get("extra") or {}).get("metadata") or {}
        raw = meta.get("confidence") or meta.get("probability") or meta.get("likelihood")
        if raw is None:
            values.append(75.0)
            continue
        if isinstance(raw, str):
            mapped = _str_map.get(raw.lower())
            values.append(mapped if mapped is not None else 75.0)
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            values.append(75.0)
            continue
        # Normalise 0-1 probabilities to 0-100
        if val <= 1.0:
            val *= 100.0
        values.append(max(0.0, min(100.0, val)))

    return round(sum(values) / max(len(values), 1), 1)


def build_fix_pr_metadata(
    findings: list[dict],
    original_pr_number: int,
    original_pr_url: str,
    original_pr_author: str,
    safety_score: float,
    previews: list[dict] | None = None,
    confidence: float | None = None,
) -> Tuple[str, str]:
    """Build PR title and body for the fix PR."""
    vuln_types: dict[str, int] = {}
    for f in findings:
        check_id = str(f.get("check_id", "") or "").lower()
        key = "other"
        if "sqli" in check_id or "sql" in check_id:
            key = "SQLi"
        elif "xss" in check_id:
            key = "XSS"
        elif "secret" in check_id or "password" in check_id or "token" in check_id:
            key = "Secrets"
        elif "command" in check_id:
            key = "Command Injection"
        elif "path" in check_id or "traversal" in check_id:
            key = "Path Traversal"
        elif "ssrf" in check_id:
            key = "SSRF"
        vuln_types[key] = vuln_types.get(key, 0) + 1

    total = len(findings)
    noun = "issue" if total == 1 else "issues"
    if vuln_types:
        top_vulns = ", ".join(k for k, _ in sorted(vuln_types.items(), key=lambda x: -x[1])[:3])
        title = f"Railo: fix {total} security {noun} in PR #{original_pr_number} ({top_vulns})"
    else:
        title = f"Railo: fix {total} security {noun} in PR #{original_pr_number}"

    bullet_lines = "\n".join([f"- {kind}: {count}" for kind, count in sorted(vuln_types.items())])
    if not bullet_lines:
        bullet_lines = "- Security fixes applied"

    # Compute confidence if not supplied
    effective_confidence = confidence if confidence is not None else estimate_fix_confidence(findings)

    body_parts: list[str] = []
    body_parts.append("## Railo Security Fix PR")
    body_parts.append("")
    body_parts.append(
        f"Companion fix PR for [#{original_pr_number}]({original_pr_url}) "
        f"by @{original_pr_author or 'unknown'}."
    )
    body_parts.append("")
    body_parts.append("| | |")
    body_parts.append("|--|--|")
    body_parts.append(f"| **Safety score** | {safety_score:.0f} / 100 |")
    body_parts.append(f"| **Fix confidence** | {effective_confidence:.0f}% |")
    body_parts.append(f"| **Issues fixed** | {total} |")
    body_parts.append("")
    body_parts.append("### What was fixed")
    body_parts.append("")
    body_parts.append(bullet_lines)
    body_parts.append("")

    # Before/After previews (if provided)
    previews = previews or []
    if previews:
        body_parts.append("### Code changes")
        body_parts.append("")
        shown = previews[:4]  # keep PR body compact
        for p in shown:
            file_path = str(p.get("file", ""))
            line_no = p.get("line", "")
            before = str(p.get("before", "")).strip()
            after = str(p.get("after", "")).strip()
            check_id = str(p.get("check_id", ""))
            conf = p.get("confidence")

            human_label = _vuln_label(check_id)
            label_parts = [f"`{file_path}`"]
            if line_no:
                label_parts.append(f"line {line_no}")
            if conf is not None:
                label_parts.append(f"confidence {float(conf):.0f}%")
            body_parts.append(f"**{human_label}** · {' · '.join(label_parts)}")
            body_parts.append("")
            body_parts.append("**Before:**")
            body_parts.append(f"```python\n{before}\n```")
            body_parts.append("**After:**")
            body_parts.append(f"```python\n{after}\n```")
            body_parts.append("")
        if len(previews) > len(shown):
            body_parts.append(f"_…and {len(previews) - len(shown)} more fix(es) in the diff._")
            body_parts.append("")

    body_parts.append("### Next steps")
    body_parts.append("")
    body_parts.append("- Review changes in the **Files changed** tab")
    body_parts.append("- Merge when satisfied — the original PR is untouched")
    body_parts.append("")
    body_parts.append("<!-- railo-fix -->")

    body = "\n".join(body_parts) + "\n"
    return title, body


def create_fix_pr_branch(
    repo_path: Path,
    branch_name: str,
    commit_message: str,
) -> tuple[bool, str | None]:
    """Create and push new branch with current working tree changes."""
    try:
        changed = commit_and_push_new_branch(repo_path, branch_name, commit_message)
        if not changed:
            return False, "No changes to commit"
        return True, None
    except Exception as exc:  # pragma: no cover - defensive
        return False, str(exc)


def create_fix_pr(
    findings: list[dict],
    owner: str,
    repo_name: str,
    original_pr_number: int,
    original_pr_author: str,
    original_pr_url: str,
    base_branch: str,
    repo_path: Path,
) -> tuple[bool, dict]:
    """
    Orchestrate branch creation, push, and PR opening.

    Returns (success, info)
    info contains: branch_name, fix_pr_number, fix_pr_url, safety_score, vulns_fixed
    """
    branch_name = generate_fix_branch_name(findings, original_pr_number)
    commit_message = f"[railo] fix: {len(findings)} security issue(s) for PR #{original_pr_number}"

    success, err = create_fix_pr_branch(repo_path, branch_name, commit_message)
    if not success:
        return False, {"error": err or "Failed to create branch"}

    safety = estimate_fix_safety(findings)
    confidence = estimate_fix_confidence(findings)
    title, body = build_fix_pr_metadata(
        findings,
        original_pr_number,
        original_pr_url,
        original_pr_author,
        safety,
        confidence=confidence,
    )

    try:
        pr_data = open_or_get_pr(
            owner,
            repo_name,
            head=branch_name,
            base=base_branch,
            title=title,
            body=body,
            labels=["railo-fix", "security"],
        )
    except Exception as exc:  # pragma: no cover - defensive
        return False, {"error": str(exc)}

    info = {
        "branch_name": branch_name,
        "fix_pr_number": pr_data.get("number"),
        "fix_pr_url": pr_data.get("html_url") or pr_data.get("url"),
        "safety_score": safety,
        "vulns_fixed": len(findings),
    }
    return True, info
