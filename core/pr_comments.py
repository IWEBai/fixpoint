"""
PR comment utilities for Railo.
Clean, developer-friendly comments that build trust through transparency.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _sanitize_for_markdown(text: str, max_length: int = 500) -> str:
    """
    Sanitize text for safe inclusion in GitHub markdown comments.
    
    Prevents:
    - Markdown injection (escaped special chars)
    - Excessive length (truncated)
    - HTML injection (stripped)
    
    Args:
        text: Raw text to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized text safe for markdown
    """
    if not text:
        return ""
    
    # Convert to string if needed
    text = str(text)
    
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Escape markdown special characters
    # Characters that have special meaning in markdown
    special_chars = ['\\', '`', '*', '_', '{', '}', '[', ']', '(', ')', '#', '+', '-', '.', '!', '|']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."
    
    return text


def _sanitize_file_path(path: str) -> str:
    """
    Sanitize file path for display in comments.
    
    Args:
        path: File path to sanitize
    
    Returns:
        Sanitized path
    """
    if not path:
        return ""
    
    # Remove any path traversal attempts
    path = path.replace("..", "")
    
    # Remove null bytes
    path = path.replace("\x00", "")
    
    # Limit length
    if len(path) > 200:
        path = "..." + path[-197:]
    
    return path


def _sanitize_code_block(code: str, max_length: int = 1000) -> str:
    """
    Sanitize code for display in markdown code blocks.
    
    Args:
        code: Code to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized code
    """
    if not code:
        return ""
    
    # Remove backticks that could break out of code block
    code = code.replace("```", "'''")
    
    # Truncate if too long
    if len(code) > max_length:
        code = code[:max_length - 20] + "\n... (truncated)"
    
    return code


def _extract_confidence(finding: dict) -> float | None:
    """
    Extract a 0-100 confidence value from a Semgrep finding.
    Returns None when no confidence metadata is present.
    """
    meta = (finding.get("extra") or {}).get("metadata") or {}
    raw = meta.get("confidence") or meta.get("probability") or meta.get("likelihood")
    if raw is None:
        return None
    if isinstance(raw, str):
        mapping = {"high": 90.0, "medium": 65.0, "low": 35.0,
                   "critical": 95.0, "info": 20.0}
        val = mapping.get(raw.lower())
        if val is not None:
            return val
        try:
            raw = float(raw)
        except (ValueError, TypeError):
            return None
    val = float(raw)
    # Normalise 0-1 probabilities to 0-100
    if val <= 1.0:
        val *= 100.0
    return round(max(0.0, min(100.0, val)), 1)


def _confidence_bar(pct: float) -> str:
    """Return a simple text bar for a 0-100 confidence value."""
    filled = round(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"`{bar}` {pct:.0f}%"


def _vuln_label(check_id: str) -> str:
    """Map a Semgrep check ID to a short human label."""
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


def generate_welcome_comment(owner: str, repo: str) -> str:
    """
    One-time orientation comment posted on a repo's first Railo scan.

    Keeps it very short — the developer is in the middle of opening a PR
    and just wants to know what's happening.
    """
    return (
        "## 👋 Railo is now active on this repo\n\n"
        "I scan every PR for security issues and open a separate fix PR with patches.\n\n"
        "| What I do | How |"
        "\n|-----------|-----|"
        "\n| **Detect** | Scan each PR with Semgrep rules (SQLi, XSS, secrets, and more) |"
        "\n| **Fix** | Open a companion fix PR with deterministic patches |"
        "\n| **Stay safe** | Your branch is never modified without review |"
        "\n\n"
        "No configuration required — I'm already running. "
        "To customise behaviour, add a `.railo.yml` to your repo root or visit the "
        "[Railo dashboard](https://app.railo.dev).\n\n"
        "_This message only appears once per repo._"
    )


def generate_fix_pr_notification(
    fix_pr_number: int,
    fix_pr_url: str,
    safety_score: float,
    vuln_count: int,
    vuln_types: list[str],
    findings: list[dict] | None = None,
    previews: list[dict] | None = None,
) -> str:
    """
    Generate a comment on the original PR announcing the fix PR.

    Simple narrative: Railo detected issues → opened a fix PR → here's what changed.
    Optionally shows before/after code blocks and per-finding confidence.
    """
    findings = findings or []
    previews = previews or []
    types_text = ", ".join(sorted(set(vuln_types))) if vuln_types else "security issues"

    # Confidence summary across all findings
    confs = [c for f in findings for c in [_extract_confidence(f)] if c is not None]
    avg_conf = round(sum(confs) / len(confs), 1) if confs else None

    lines: list[str] = []
    lines.append(f"## 🔒 Railo fixed {vuln_count} security issue(s)")
    lines.append("")
    lines.append(
        f"Railo scanned this PR, found **{vuln_count} {types_text}** issue(s), "
        f"and opened a companion fix PR with deterministic patches."
    )
    lines.append("")

    # Scores block
    score_parts = [f"**Safety score:** {safety_score:.0f}/100"]
    if avg_conf is not None:
        score_parts.append(f"**Fix confidence:** {_confidence_bar(avg_conf)}")
    lines.append("  \n".join(score_parts))
    lines.append("")

    # Fix PR CTA — the only action the developer needs to take
    lines.append(f"### 👉 [Review fix PR #{fix_pr_number}]({fix_pr_url})")
    lines.append("")

    # Before/After previews
    if previews:
        lines.append("### What changed")
        lines.append("")
        shown = previews[:3]  # cap at 3 to keep comment readable
        for p in shown:
            file_path = _sanitize_file_path(str(p.get("file", "")))
            line_no = p.get("line", "")
            before = _sanitize_code_block(str(p.get("before", "")).strip())
            after = _sanitize_code_block(str(p.get("after", "")).strip())
            vuln = _vuln_label(str(p.get("check_id", "")))
            conf = p.get("confidence")

            header = f"`{file_path}`" + (f" line {line_no}" if line_no else "")
            if conf is not None:
                header += f" — confidence {_confidence_bar(float(conf))}"
            lines.append(f"**{vuln}** · {header}")
            lines.append("")
            lines.append("**Before:**")
            lines.append(f"```python\n{before}\n```")
            lines.append("**After:**")
            lines.append(f"```python\n{after}\n```")
            lines.append("")
        if len(previews) > len(shown):
            lines.append(
                f"_…and {len(previews) - len(shown)} more fix(es) — "
                f"[see the full diff]({fix_pr_url}/files)_"
            )
            lines.append("")
    elif findings:
        # No before/after available; show a compact findings table
        lines.append("### What was found")
        lines.append("")
        lines.append("| File | Issue | Confidence |")
        lines.append("|------|-------|-----------|")
        for f in findings[:5]:
            fp = _sanitize_file_path(f.get("path", ""))
            ln = (f.get("start") or {}).get("line", "")
            label = _vuln_label(str(f.get("check_id", "")))
            c = _extract_confidence(f)
            conf_str = f"{c:.0f}%" if c is not None else "—"
            lines.append(f"| `{fp}`:{ln} | {label} | {conf_str} |")
        if len(findings) > 5:
            lines.append(f"| … | +{len(findings) - 5} more | |")
        lines.append("")

    lines.append("---")
    lines.append(
        "_Your branch was not modified. "
        "Review and merge the fix PR when you're happy with the changes._"
    )
    return "\n".join(lines)


def create_fix_comment(
    owner: str,
    repo: str,
    pr_number: int,
    files_fixed: list[str],
    findings: list[dict],
    patch_hunks: Optional[list[str]] = None,
    max_hunks: int = 5,
    safety_snippet: Optional[str] = None,
    token: Optional[str] = None,
) -> str:
    """Post a comment on the original PR summarising what enforce-mode fixed."""
    token = token or os.getenv("GITHUB_TOKEN")
    if not token:
        return ""
    try:
        from github import Github, Auth  # type: ignore

        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)

        total_findings = len(findings)
        total_files = len(files_fixed)

        # Confidence summary
        confs = [c for f in findings for c in [_extract_confidence(f)] if c is not None]
        avg_conf = round(sum(confs) / len(confs), 1) if confs else None

        comment_body = f"## ✅ Railo fixed {total_findings} security issue(s)\n\n"
        comment_body += f"Patched `{total_findings}` finding(s) across `{total_files}` file(s). "
        comment_body += "Your branch now contains the fixes.\n\n"

        if avg_conf is not None:
            comment_body += f"**Fix confidence:** {_confidence_bar(avg_conf)}\n\n"

        if safety_snippet:
            comment_body += f"> {safety_snippet}\n\n"

        # Findings table
        if findings:
            comment_body += "### What was fixed\n\n"
            comment_body += "| File | Issue | Line | Confidence |\n"
            comment_body += "|------|-------|------|-----------|\n"
            for f in findings:
                fp = _sanitize_file_path(f.get("path", ""))
                ln = (f.get("start") or {}).get("line", "")
                label = _vuln_label(str(f.get("check_id", "")))
                c = _extract_confidence(f)
                conf_str = f"{c:.0f}%" if c is not None else "—"
                comment_body += f"| `{fp}` | {label} | {ln} | {conf_str} |\n"
            comment_body += "\n"

        # Patch preview — top N hunks
        if patch_hunks:
            limited = patch_hunks[: max_hunks if max_hunks > 0 else 5]
            comment_body += "<details>\n"
            comment_body += "<summary><strong>Patch preview</strong></summary>\n\n"
            for hunk in limited:
                safe_hunk = _sanitize_code_block(hunk, max_length=1200)
                comment_body += "```diff\n" + safe_hunk + "\n```\n\n"
            if len(patch_hunks) > len(limited):
                comment_body += f"_Showing {len(limited)} of {len(patch_hunks)} hunks._\n\n"
            comment_body += "</details>\n\n"

        comment_body += "---\n"
        comment_body += "_Railo — automated security fixes. Please review before merging._"

        comment = pr.create_issue_comment(comment_body)
        return comment.html_url
    except Exception as e:
        logger.warning("Failed to post fix comment: %s", e)
        return ""


def create_warn_comment(
    owner: str,
    repo: str,
    pr_number: int,
    findings: list[dict],
    proposed_fixes: list[dict],
    fork_notice: str = "",
    head_sha: Optional[str] = None,
    safety_snippet: Optional[str] = None,
    token: Optional[str] = None,
) -> str:
    """
    Create a PR comment in warn mode (propose fixes without applying).
    
    Implements idempotency: updates existing comment for same SHA instead of creating duplicates.
    
    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: PR number
        findings: List of Semgrep findings
        proposed_fixes: List of proposed fixes (file, line, before, after)
        fork_notice: Optional notice about fork PR downgrade
        head_sha: Current HEAD SHA (for idempotency - updates existing comment if same SHA)
        token: Optional GitHub token override; falls back to GITHUB_TOKEN env var
    
    Returns:
        Comment URL or empty string if failed
    """
    token = token or os.getenv("GITHUB_TOKEN")
    if not token:
        return ""
    
    try:
        # Lazy import so local/dev/test environments without PyGithub can still import the module.
        from github import Github, Auth  # type: ignore

        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)

        # IDEMPOTENCY: Check for existing Railo comment for this SHA
        existing_comment = None
        if head_sha:
            comments = pr.get_issue_comments()
            for comment in comments:
                if "Railo" in comment.body and head_sha[:8] in comment.body:
                    existing_comment = comment
                    break

        total_findings = len(findings)
        _total_proposals = len(proposed_fixes)  # noqa: F841

        # --- Confidence summary ---
        confs = [c for f in findings for c in [_extract_confidence(f)] if c is not None]
        avg_conf = round(sum(confs) / len(confs), 1) if confs else None

        # --- Header: simple and scannable ---
        comment_body = f"## 🔍 Railo found {total_findings} security issue(s)\n\n"

        # Scores inline
        score_line = "Your branch is **unchanged**."  
        if avg_conf is not None:
            score_line += f"  Fix confidence: {_confidence_bar(avg_conf)}"
        comment_body += score_line + "\n\n"

        # Optional trust-contract safety decision snippet
        if safety_snippet:
            comment_body += f"> {safety_snippet}\n\n"

        # --- Before/After blocks — the main content ---
        if proposed_fixes:
            comment_body += "### Proposed fixes\n\n"
            for fix in proposed_fixes:
                file_path = _sanitize_file_path(fix.get("file", ""))
                line = int(fix.get("line", 0))
                before = _sanitize_code_block(str(fix.get("before", "")).strip())
                after = _sanitize_code_block(str(fix.get("after", "")).strip())
                check_id = str(fix.get("check_id", ""))
                vuln = _vuln_label(check_id)
                conf = fix.get("confidence")
                # Per-fix confidence — fall back to finding metadata
                if conf is None and findings:
                    for f in findings:
                        if f.get("path", "") == file_path:
                            conf = _extract_confidence(f)
                            break

                header = f"`{file_path}`" + (f" line {line}" if line else "")
                if conf is not None:
                    header += f" — confidence {_confidence_bar(float(conf))}"
                comment_body += f"**{vuln}** · {header}\n\n"
                comment_body += "**Before:**\n"
                comment_body += f"```python\n{before}\n```\n"
                comment_body += "**After:**\n"
                comment_body += f"```python\n{after}\n```\n\n"
        else:
            # Fallback: findings table
            comment_body += "### What was found\n\n"
            comment_body += "| File | Issue | Line | Confidence |\n"
            comment_body += "|------|-------|------|-----------|\n"
            for f in findings:
                fp = _sanitize_file_path(f.get("path", ""))
                ln = (f.get("start") or {}).get("line", "")
                label = _vuln_label(str(f.get("check_id", "")))
                c = _extract_confidence(f)
                conf_str = f"{c:.0f}%" if c is not None else "—"
                comment_body += f"| `{fp}` | {label} | {ln} | {conf_str} |\n"
            comment_body += "\n"

        # --- How to apply / next steps ---
        comment_body += "### Apply these fixes\n\n"
        comment_body += "| Option | How |\n"
        comment_body += "|--------|-----|\n"
        comment_body += "| **Auto-apply** | Switch to `fix` mode and Railo opens a fix PR automatically |\n"
        comment_body += "| **Apply manually** | Copy the diffs above into your editor |\n"
        comment_body += "| **Dismiss** | Add `# railo: ignore` on the flagged line |\n"
        comment_body += "\n"

        if fork_notice:
            comment_body += fork_notice + "\n\n"

        if head_sha:
            comment_body += f"\n\n*Commit: `{head_sha[:8]}`*"

        comment_body += "\n---\n"
        comment_body += "_Railo — automated security fixes. Your branch was not modified._"

        # IDEMPOTENCY: Update existing comment or create new one
        if existing_comment:
            existing_comment.edit(comment_body)
            return existing_comment.html_url
        else:
            comment = pr.create_issue_comment(comment_body)
            return comment.html_url
        
    except Exception as e:
        logger.warning("Failed to post warn comment: %s", e)
        return ""


def create_error_comment(
    owner: str,
    repo: str,
    pr_number: int,
    error_type: str,
    message: str,
) -> str:
    """
    Create a PR comment explaining why a fix couldn't be applied.
    
    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: PR number
        error_type: Type of error (e.g., "permissions", "branch_protection")
        message: Error message
    
    Returns:
        Comment URL or empty string if failed
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return ""
    
    try:
        # Lazy import so local/dev/test environments without PyGithub can still import the module.
        from github import Github, Auth  # type: ignore

        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)

        safe_message = _sanitize_for_markdown(message)

        comment_body = "## ⚠️ Railo — Action Required\n\n"

        if error_type == "permissions":
            comment_body += "Railo detected security issues but **couldn't open a fix PR** due to permission issues.\n\n"
            comment_body += "**Action required:** Ensure the Railo GitHub App token has `contents: write` on this repository.\n\n"
        elif error_type == "branch_protection":
            comment_body += "Railo detected security issues but **couldn't push the fix branch** due to branch protection rules.\n\n"
            comment_body += "**Action required:** Allow Railo's token to push to this repository, or apply the suggested fixes manually from the check-run annotations.\n\n"
        else:
            comment_body += "Railo detected security issues but encountered an unexpected problem while preparing the fix PR.\n\n"

        comment_body += f"**Details:** {safe_message}\n\n"

        comment_body += "### Suggested next steps\n\n"
        comment_body += "- Review the check-run annotations on the **Files changed** tab for affected lines.\n"
        comment_body += "- Verify the Railo GitHub App has the required repository permissions.\n"
        comment_body += "- See the [Railo docs](https://app.railo.dev/docs) for the permissions required.\n\n"

        comment_body += "---\n"
        comment_body += "_Railo — automated security fixes._"

        comment = pr.create_issue_comment(comment_body)
        return comment.html_url
        
    except Exception as e:
        logger.warning("Failed to post error comment: %s", e)
        return ""
