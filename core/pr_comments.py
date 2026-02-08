"""
PR comment utilities for Fixpoint.
Creates clear, actionable comments explaining fixes.
"""
from __future__ import annotations

import os
import re
from typing import Optional
from github import Github, Auth
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
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        
        # Build comment body
        comment_body = "## ⚡ Fixpoint AutoPatch\n\n"
        comment_body += "I've automatically applied security fixes to this PR.\n\n"
        
        comment_body += "### What was found\n\n"
        for finding in findings:
            file_path = _sanitize_file_path(finding.get("path", ""))
            start_line = int(finding.get("start", {}).get("line", 0))
            message = _sanitize_for_markdown(finding.get("extra", {}).get("message", "Security violation"))
            check_id = _sanitize_for_markdown(finding.get("check_id", ""), max_length=100)
            metadata = finding.get("extra", {}).get("metadata", {})
            cwe = metadata.get("cwe", "")
            owasp = metadata.get("owasp", "")
            
            comment_body += f"- **{file_path}:{start_line}** - {message}\n"
            comment_body += f"  - Rule: `{check_id}`\n"
            if cwe or owasp:
                tags = " | ".join(t for t in [cwe, owasp] if t)
                comment_body += f"  - CWE/OWASP: `{tags}`\n"
        
        comment_body += "\n### What changed\n\n"
        comment_body += "Applied deterministic fixes:\n\n"
        
        # Group findings by file to get descriptions
        fixes_by_file = {}
        for finding in findings:
            file_path = finding.get("path", "")
            check_id = finding.get("check_id", "").lower()
            if file_path not in fixes_by_file:
                fixes_by_file[file_path] = []
            
            # Determine fix description based on check_id
            if "sql" in check_id or "sqli" in check_id:
                desc = "SQL injection → parameterized query"
            elif "secret" in check_id or "password" in check_id:
                desc = "Hardcoded secret → environment variable"
            elif "xss" in check_id or "safe" in check_id:
                desc = "XSS → removed unsafe pattern"
            elif "command" in check_id:
                desc = "Command injection → safe subprocess"
            elif "path" in check_id or "traversal" in check_id:
                desc = "Path traversal → added validation"
            elif "ssrf" in check_id:
                desc = "SSRF → added URL validation"
            elif "eval" in check_id:
                desc = "eval → safe alternative recommended"
            elif "innerhtml" in check_id or "dom" in check_id:
                desc = "DOM XSS → textContent"
            else:
                desc = "Security fix applied"
            
            fixes_by_file[file_path].append(desc)
        
        for file_path in files_fixed:
            safe_path = _sanitize_file_path(file_path)
            descriptions = fixes_by_file.get(file_path, ["Security fix applied"])
            unique_descs = list(dict.fromkeys(descriptions))  # Dedupe preserving order
            for desc in unique_descs:
                comment_body += f"- ✅ `{safe_path}` - {desc}\n"
        
        comment_body += "\n### Safety\n\n"
        comment_body += "- ✅ Minimal diff (only security fixes)\n"
        comment_body += "- ✅ No refactoring or formatting changes\n"
        comment_body += "- ✅ Deterministic fix (same input → same output)\n"
        comment_body += "- ✅ Full audit trail via Git commit\n"
        
        comment_body += "\n### How to revert\n\n"
        comment_body += "If you need to revert this fix:\n\n"
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
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        
        # IDEMPOTENCY: Check for existing comment from Fixpoint for this SHA
        existing_comment = None
        if head_sha:
            comments = pr.get_issue_comments()
            for comment in comments:
                # Check if comment is from Fixpoint and mentions this SHA
                if "Fixpoint" in comment.body and head_sha[:8] in comment.body:
                    existing_comment = comment
                    break
        
        comment_body = "## ⚡ Fixpoint - Compliance Check (Warn Mode)\n\n"
        comment_body += "I found compliance violations in this PR. Here are the suggested fixes:\n\n"
        
        comment_body += "### What was found\n\n"
        for finding in findings:
            file_path = _sanitize_file_path(finding.get("path", ""))
            start_line = int(finding.get("start", {}).get("line", 0))
            message = _sanitize_for_markdown(finding.get("extra", {}).get("message", "Security violation"))
            check_id = _sanitize_for_markdown(finding.get("check_id", ""), max_length=100)
            metadata = finding.get("extra", {}).get("metadata", {})
            cwe = metadata.get("cwe", "")
            owasp = metadata.get("owasp", "")
            
            comment_body += f"- **{file_path}:{start_line}** - {message}\n"
            comment_body += f"  - Rule: `{check_id}`\n"
            if cwe or owasp:
                tags = " | ".join(t for t in [cwe, owasp] if t)
                comment_body += f"  - CWE/OWASP: `{tags}`\n"
        
        comment_body += "\n### Proposed fixes\n\n"
        for fix in proposed_fixes:
            file_path = _sanitize_file_path(fix.get("file", ""))
            line = int(fix.get("line", 0))
            before = _sanitize_code_block(fix.get("before", "").strip())
            after = _sanitize_code_block(fix.get("after", "").strip())
            
            comment_body += f"**{file_path}:{line}**\n\n"
            comment_body += "```diff\n"
            comment_body += f"- {before}\n"
            comment_body += f"+ {after}\n"
            comment_body += "```\n\n"
        
        comment_body += "### Next steps\n\n"
        comment_body += "**Option 1: Apply fixes manually**\n"
        comment_body += "Review and apply the suggested fixes above.\n\n"
        comment_body += "**Option 2: Enable enforce mode**\n"
        comment_body += "Set `FIXPOINT_MODE=enforce` to automatically apply fixes.\n\n"
        
        if fork_notice:
            comment_body += fork_notice + "\n\n"
        
        comment_body += "---\n"
        comment_body += "*This is warn mode - no changes were applied. "
        comment_body += "Review the suggestions and apply manually, or enable enforce mode.*"
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
        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")
        pr = r.get_pull(pr_number)
        
        # Sanitize inputs
        safe_message = _sanitize_for_markdown(message)
        
        comment_body = "## ⚠️ Fixpoint - Action Required\n\n"
        
        if error_type == "permissions":
            comment_body += "I found security violations but couldn't push fixes due to permission issues.\n\n"
            comment_body += "**Action required:** Please ensure Fixpoint has write access to this repository.\n\n"
        elif error_type == "branch_protection":
            comment_body += "I found security violations but couldn't push fixes due to branch protection rules.\n\n"
            comment_body += "**Action required:** Please temporarily allow Fixpoint to push, or apply the fix manually.\n\n"
        else:
            comment_body += f"I found security violations but encountered an issue: {safe_message}\n\n"
        
        comment_body += f"**Details:** {safe_message}\n\n"
        comment_body += "---\n"
        comment_body += "*This message was generated by Fixpoint.*"
        
        comment = pr.create_issue_comment(comment_body)
        return comment.html_url
        
    except Exception as e:
        print(f"Warning: Failed to post error comment: {e}")
        return ""
