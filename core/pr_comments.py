"""
PR comment utilities for AuditShield.
Creates clear, actionable comments explaining fixes.
"""
from __future__ import annotations

import os
from typing import Optional
from github import Github, Auth
from dotenv import load_dotenv

load_dotenv()


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
        comment_body = "## 🔒 AuditShield AutoPatch\n\n"
        comment_body += "I've automatically applied security fixes to this PR.\n\n"
        
        comment_body += "### What was found\n\n"
        for finding in findings:
            file_path = finding.get("path", "")
            start_line = finding.get("start", {}).get("line", 0)
            message = finding.get("extra", {}).get("message", "Security violation")
            check_id = finding.get("check_id", "")
            
            comment_body += f"- **{file_path}:{start_line}** - {message}\n"
            comment_body += f"  - Rule: `{check_id}`\n"
        
        comment_body += "\n### What changed\n\n"
        comment_body += "Applied deterministic fixes:\n\n"
        for file_path in files_fixed:
            comment_body += f"- ✅ `{file_path}` - Replaced SQL string formatting with parameterized query\n"
        
        comment_body += "\n### Safety\n\n"
        comment_body += "- ✅ Minimal diff (only security fixes)\n"
        comment_body += "- ✅ No refactoring or formatting changes\n"
        comment_body += "- ✅ Deterministic fix (same input → same output)\n"
        comment_body += "- ✅ Full audit trail via Git commit\n"
        
        comment_body += "\n### How to revert\n\n"
        comment_body += "If you need to revert this fix:\n\n"
        comment_body += "```bash\n"
        comment_body += f"git revert HEAD\n"
        comment_body += "git push\n"
        comment_body += "```\n"
        
        comment_body += "\n---\n"
        comment_body += "*This fix was applied automatically by AuditShield. "
        comment_body += "Please review the changes before merging.*"
        
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
        
        # IDEMPOTENCY: Check for existing comment from AuditShield for this SHA
        existing_comment = None
        if head_sha:
            comments = pr.get_issue_comments()
            for comment in comments:
                # Check if comment is from AuditShield and mentions this SHA
                if "AuditShield" in comment.body and head_sha[:8] in comment.body:
                    existing_comment = comment
                    break
        
        comment_body = "## 🔒 AuditShield - Compliance Check (Warn Mode)\n\n"
        comment_body += "I found compliance violations in this PR. Here are the suggested fixes:\n\n"
        
        comment_body += "### What was found\n\n"
        for finding in findings:
            file_path = finding.get("path", "")
            start_line = finding.get("start", {}).get("line", 0)
            message = finding.get("extra", {}).get("message", "Security violation")
            check_id = finding.get("check_id", "")
            
            comment_body += f"- **{file_path}:{start_line}** - {message}\n"
            comment_body += f"  - Rule: `{check_id}`\n"
        
        comment_body += "\n### Proposed fixes\n\n"
        for fix in proposed_fixes:
            file_path = fix.get("file", "")
            line = fix.get("line", 0)
            before = fix.get("before", "").strip()
            after = fix.get("after", "").strip()
            
            comment_body += f"**{file_path}:{line}**\n\n"
            comment_body += "```diff\n"
            comment_body += f"- {before}\n"
            comment_body += f"+ {after}\n"
            comment_body += "```\n\n"
        
        comment_body += "### Next steps\n\n"
        comment_body += "**Option 1: Apply fixes manually**\n"
        comment_body += "Review and apply the suggested fixes above.\n\n"
        comment_body += "**Option 2: Enable enforce mode**\n"
        comment_body += "Set `AUDITSHIELD_MODE=enforce` to automatically apply fixes.\n\n"
        
        if fork_notice:
            comment_body += fork_notice + "\n\n"
        
        comment_body += "---\n"
        comment_body += "*This is warn mode - no changes were applied. "
        comment_body += "Review the suggestions and apply manually, or enable enforce mode.*"
        
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
        
        comment_body = "## ⚠️ AuditShield - Action Required\n\n"
        
        if error_type == "permissions":
            comment_body += "I found security violations but couldn't push fixes due to permission issues.\n\n"
            comment_body += "**Action required:** Please ensure AuditShield has write access to this repository.\n\n"
        elif error_type == "branch_protection":
            comment_body += "I found security violations but couldn't push fixes due to branch protection rules.\n\n"
            comment_body += "**Action required:** Please temporarily allow AuditShield to push, or apply the fix manually.\n\n"
        else:
            comment_body += f"I found security violations but encountered an issue: {message}\n\n"
        
        comment_body += f"**Details:** {message}\n\n"
        comment_body += "---\n"
        comment_body += "*This message was generated by AuditShield.*"
        
        comment = pr.create_issue_comment(comment_body)
        return comment.html_url
        
    except Exception as e:
        print(f"Warning: Failed to post error comment: {e}")
        return ""
