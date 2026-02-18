"""
PR comment utilities for Fixpoint.
Creates clear, actionable comments explaining fixes.
"""
from __future__ import annotations

import os
import re
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


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


def create_fix_comment(
    owner: str,
    repo: str,
    pr_number: int,
    files_fixed: list[str],
    findings: list[dict],
    patch_hunks: Optional[list[str]] = None,
    max_hunks: int = 5,
    safety_snippet: Optional[str] = None,
) -> str:
    """
    Create a PR comment explaining what was fixed.
    
    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: PR number
        files_fixed: List of files that were fixed
        findings: List of findings that were fixed
    
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

        total_findings = len(findings)
        total_files = len(files_fixed)

        # Build comment body with collapsible sections and clearer structure.
        comment_body = "## ⚡ Fixpoint AutoPatch\n\n"
        comment_body += "I've automatically applied **deterministic security fixes** to this PR.\n\n"

        comment_body += f"**Summary:** Fixed `{total_findings}` finding(s) across `{total_files}` file(s).\n\n"

        # Optional trust-contract safety decision snippet
        if safety_snippet:
            comment_body += f"> {safety_snippet}\n\n"

        # What was found (collapsible)
        comment_body += "<details>\n"
        comment_body += "<summary><strong>What was found</strong></summary>\n\n"
        for finding in findings:
            file_path = _sanitize_file_path(finding.get("path", ""))
            start_line = int(finding.get("start", {}).get("line", 0))
            message = _sanitize_for_markdown(
                finding.get("extra", {}).get("message", "Security violation")
            )
            check_id = _sanitize_for_markdown(
                finding.get("check_id", ""), max_length=100
            )
            metadata = finding.get("extra", {}).get("metadata", {}) or {}
            cwe = metadata.get("cwe", "")
            owasp = metadata.get("owasp", "")

            comment_body += f"- **{file_path}:{start_line}** – {message}\n"
            comment_body += f"  - Rule: `{check_id}`\n"
            if cwe or owasp:
                tags = " | ".join(t for t in [cwe, owasp] if t)
                comment_body += f"  - CWE/OWASP: `{tags}`\n"
        if not findings:
            comment_body += "- No individual findings were attached to this run (check logs for details).\n"
        comment_body += "\n</details>\n\n"

        # Group findings by file to describe changes.
        fixes_by_file: dict[str, list[str]] = {}
        for finding in findings:
            file_path = finding.get("path", "")
            check_id = str(finding.get("check_id", "") or "").lower()
            if file_path not in fixes_by_file:
                fixes_by_file[file_path] = []

            if "sql" in check_id or "sqli" in check_id:
                desc = "SQL injection → parameterized query"
            elif "secret" in check_id or "password" in check_id:
                desc = "Hardcoded secret → environment variable"
            elif "xss" in check_id or "safe" in check_id:
                desc = "XSS → removed unsafe pattern / added escaping"
            elif "command" in check_id:
                desc = "Command injection → safe subprocess usage"
            elif "path" in check_id or "traversal" in check_id:
                desc = "Path traversal → added path validation"
            elif "ssrf" in check_id:
                desc = "SSRF → URL validation guidance"
            elif "eval" in check_id:
                desc = "Dangerous eval → safer alternative recommended"
            elif "innerhtml" in check_id or "dom" in check_id:
                desc = "DOM XSS → `textContent` / safer DOM updates"
            else:
                desc = "Security fix applied"

            fixes_by_file[file_path].append(desc)

        # What changed (collapsible, per file)
        comment_body += "<details>\n"
        comment_body += "<summary><strong>What changed (per file)</strong></summary>\n\n"
        if files_fixed:
            for file_path in files_fixed:
                safe_path = _sanitize_file_path(file_path)
                descriptions = fixes_by_file.get(file_path, ["Security fix applied"])
                unique_descs = list(dict.fromkeys(descriptions))

                comment_body += f"- `{safe_path}`\n"
                for desc in unique_descs:
                    comment_body += f"  - {desc}\n"
        else:
            comment_body += "- No files were reported as changed.\n"
        comment_body += "\n</details>\n\n"

        # Patch preview (collapsed) - limit to top N hunks
        if patch_hunks:
            comment_body += "<details>\n"
            comment_body += "<summary><strong>What changed (patch preview)</strong></summary>\n\n"
            limited = patch_hunks[: max_hunks if max_hunks > 0 else 5]
            for hunk in limited:
                safe_hunk = _sanitize_code_block(hunk, max_length=1200)
                comment_body += "```diff\n" + safe_hunk + "\n```\n\n"
            if len(patch_hunks) > len(limited):
                comment_body += f"_Showing {len(limited)} of {len(patch_hunks)} hunks._\n\n"
            comment_body += "</details>\n\n"

        # Safety rails explanation (collapsible)
        comment_body += "<details>\n"
        comment_body += "<summary><strong>Safety rails & guarantees</strong></summary>\n\n"
        comment_body += "- **Minimal diffs:** Fixpoint analyzes the git diff and rejects large, unfocused patches.\n"
        comment_body += "- **No bulk refactors:** Formatting guards cap how much code style can change in a single run.\n"
        comment_body += "- **Deterministic rules:** The same input always produces the same patch; no AI-generated code paths.\n"
        comment_body += "- **Time & scope limits:** Long-running or out-of-scope analyses degrade to report-only rather than risky changes.\n"
        comment_body += "- **Baseline-aware reporting:** Existing, known issues can be filtered so only *new* problems fail CI.\n"
        comment_body += "\n</details>\n\n"

        # Quick actions section
        comment_body += "### Quick actions\n\n"
        comment_body += "- Review the PR diff above and leave comments on any fix you want to adjust.\n"
        comment_body += "- Tune rules and severities in `.fixpoint.yml` (see the [configuration guide](https://github.com/IWEBai/fixpoint#quick-start)).\n"
        comment_body += "- Start in `mode: warn` and graduate to `enforce` once you're comfortable with the patches.\n\n"

        # How to revert
        comment_body += "### How to revert this patch set\n\n"
        comment_body += "If you need to revert this Fixpoint run entirely:\n\n"
        comment_body += "```bash\n"
        comment_body += "git revert HEAD\n"
        comment_body += "git push\n"
        comment_body += "```\n"

        comment_body += "\n---\n"
        comment_body += "*This fix was applied automatically by Fixpoint. "
        comment_body += "Please review the changes before merging.*"
        comment_body += "\n\n**[Using Fixpoint?](https://github.com/IWEBai/fixpoint#using-fixpoint) Let us know — we'd love your feedback.**"
        
        # Post comment
        comment = pr.create_issue_comment(comment_body)
        return comment.html_url
        
    except Exception as e:
        # Log error but don't fail the whole process
        print(f"Warning: Failed to post PR comment: {e}")
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

        # IDEMPOTENCY: Check for existing comment from Fixpoint for this SHA
        existing_comment = None
        if head_sha:
            comments = pr.get_issue_comments()
            for comment in comments:
                if "Fixpoint" in comment.body and head_sha[:8] in comment.body:
                    existing_comment = comment
                    break

        total_findings = len(findings)
        total_proposals = len(proposed_fixes)

        comment_body = "## ⚡ Fixpoint - Compliance Check (Warn Mode)\n\n"
        comment_body += "I found compliance violations in this PR and generated **proposed fixes** without changing your branch.\n\n"

        comment_body += f"**Summary:** `{total_findings}` finding(s), `{total_proposals}` proposed patch(es). No code was modified.\n\n"

        # Optional trust-contract safety decision snippet
        if safety_snippet:
            comment_body += f"> {safety_snippet}\n\n"

        # What was found (collapsible)
        comment_body += "<details>\n"
        comment_body += "<summary><strong>What was found</strong></summary>\n\n"
        for finding in findings:
            file_path = _sanitize_file_path(finding.get("path", ""))
            start_line = int(finding.get("start", {}).get("line", 0))
            message = _sanitize_for_markdown(
                finding.get("extra", {}).get("message", "Security violation")
            )
            check_id = _sanitize_for_markdown(
                finding.get("check_id", ""), max_length=100
            )
            metadata = finding.get("extra", {}).get("metadata", {}) or {}
            cwe = metadata.get("cwe", "")
            owasp = metadata.get("owasp", "")

            comment_body += f"- **{file_path}:{start_line}** – {message}\n"
            comment_body += f"  - Rule: `{check_id}`\n"
            if cwe or owasp:
                tags = " | ".join(t for t in [cwe, owasp] if t)
                comment_body += f"  - CWE/OWASP: `{tags}`\n"
        if not findings:
            comment_body += "- No individual findings are attached to this run (see logs/check-run annotations).\n"
        comment_body += "\n</details>\n\n"

        # Proposed fixes (collapsible, per location)
        comment_body += "<details>\n"
        comment_body += "<summary><strong>Proposed patches</strong></summary>\n\n"
        if proposed_fixes:
            for fix in proposed_fixes:
                file_path = _sanitize_file_path(fix.get("file", ""))
                line = int(fix.get("line", 0))
                before = _sanitize_code_block(str(fix.get("before", "")).strip())
                after = _sanitize_code_block(str(fix.get("after", "")).strip())

                comment_body += f"**{file_path}:{line}**\n\n"
                comment_body += "```diff\n"
                comment_body += f"- {before}\n"
                comment_body += f"+ {after}\n"
                comment_body += "```\n\n"
        else:
            comment_body += "_No concrete patches were generated for this run._\n\n"
        comment_body += "</details>\n\n"

        # Safety & behavior explanation
        comment_body += "<details>\n"
        comment_body += "<summary><strong>Why this is warn mode</strong></summary>\n\n"
        comment_body += "- Fixpoint is currently running in **warn mode**, so it **never pushes commits** to your branch.\n"
        comment_body += "- You can use this mode to tune rules and verify patch quality before enabling auto-fix (enforce mode).\n"
        comment_body += "- Proposed patches respect the same safety rails as enforce mode: minimal, deterministic changes only.\n"
        comment_body += "\n</details>\n\n"

        # Next steps / quick actions
        comment_body += "### Next steps\n\n"
        comment_body += "- **Apply manually:** Use the diffs above to patch files in this PR.\n"
        comment_body += "- **Tweak configuration:** Adjust rules and severities in `.fixpoint.yml` (see the [configuration guide](https://github.com/IWEBai/fixpoint#quick-start)).\n"
        comment_body += "- **Enable enforce mode:** Set `mode: enforce` in your workflow or `FIXPOINT_MODE=enforce` in the environment once you trust the patches.\n\n"

        if fork_notice:
            comment_body += fork_notice + "\n\n"

        comment_body += "---\n"
        comment_body += "*This is warn mode – no changes were applied automatically. "
        comment_body += "Review the suggestions and apply manually, or enable enforce mode when ready.*"
        comment_body += "\n\n**[Using Fixpoint?](https://github.com/IWEBai/fixpoint#using-fixpoint) Let us know — we'd love your feedback.**"

        if head_sha:
            comment_body += f"\n\n*Commit: `{head_sha[:8]}`*"

        # IDEMPOTENCY: Update existing comment or create new one
        if existing_comment:
            existing_comment.edit(comment_body)
            return existing_comment.html_url
        else:
            comment = pr.create_issue_comment(comment_body)
            return comment.html_url
        
    except Exception as e:
        print(f"Warning: Failed to post warn comment: {e}")
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

        comment_body = "## ⚠️ Fixpoint - Action Required\n\n"

        if error_type == "permissions":
            comment_body += "I detected security violations but **couldn't push fixes** due to permission issues.\n\n"
            comment_body += "**Action required:** Ensure the Fixpoint GitHub App / workflow token has `contents: write` on this branch.\n\n"
        elif error_type == "branch_protection":
            comment_body += "I detected security violations but **couldn't push fixes** due to branch protection rules.\n\n"
            comment_body += "**Action required:** Either temporarily allow this workflow to push to the branch, or apply the suggested fixes manually.\n\n"
        else:
            comment_body += "I detected security violations but encountered an unexpected issue while trying to apply fixes.\n\n"

        comment_body += f"**Details:** {safe_message}\n\n"

        comment_body += "### Suggested next steps\n\n"
        comment_body += "- Review the check-run annotations and PR diff to understand what would have been changed.\n"
        comment_body += "- Verify repository and branch protection settings for this workflow/token.\n"
        comment_body += "- Consult the [Fixpoint documentation](https://github.com/IWEBai/fixpoint#quick-start) for required permissions.\n\n"

        comment_body += "---\n"
        comment_body += "*This message was generated by Fixpoint to explain why automatic fixes could not be applied.*"

        comment = pr.create_issue_comment(comment_body)
        return comment.html_url
        
    except Exception as e:
        print(f"Warning: Failed to post error comment: {e}")
        return ""
