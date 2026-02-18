"""
GitHub status check utilities for Fixpoint.
Sets status checks to make Fixpoint a true "gate" in GitHub.
"""
from __future__ import annotations

import os
from typing import Optional, List, Dict, Any, Tuple, Set
from dotenv import load_dotenv

load_dotenv()


def create_check_run_with_annotations(
    owner: str,
    repo: str,
    sha: str,
    findings: List[Dict[str, Any]],
    conclusion: str,
    pr_url: Optional[str] = None,
) -> Optional[str]:
    """
    Create a GitHub Check Run with inline annotations for each finding.

    This is complementary to classic status checks and powers the
    GitHub \"Checks\" UI with per-line annotations.

    Args:
        owner: Repository owner
        repo: Repository name
        sha: Commit SHA
        findings: List of Semgrep findings
        conclusion: \"success\", \"failure\", \"neutral\", etc.
        pr_url: Optional URL to link from the check run

    Returns:
        HTML URL of the created check run, or None on failure.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not found, cannot create check run")
        return None

    try:
        # Lazy import so environments without PyGithub can still import this module.
        from github import Github, Auth  # type: ignore

        g = Github(auth=Auth.Token(token))
        r = g.get_repo(f"{owner}/{repo}")

        # Build annotations (GitHub caps this at 50 per check run)
        annotations: List[Dict[str, Any]] = []
        seen_keys: Set[Tuple[str, int, int, str]] = set()

        # Track severity breakdown for a richer summary.
        counts = {"ERROR": 0, "WARNING": 0, "INFO": 0}

        for finding in findings or []:
            extra = finding.get("extra", {}) or {}
            metadata = extra.get("metadata", {}) or {}

            path = finding.get("path", "")
            start = finding.get("start", {}) or {}
            end = finding.get("end", {}) or {}

            start_line = int(start.get("line", 1) or 1)
            end_line = int(end.get("line", start_line) or start_line)

            rule_id = str(finding.get("check_id") or "unknown-rule")
            severity = str(
                metadata.get("severity") or extra.get("severity") or "WARNING"
            ).upper()

            # Normalise severity for counting/level mapping.
            sev_key = severity if severity in ("ERROR", "WARNING", "WARN", "INFO") else "WARNING"
            if sev_key == "WARN":
                sev_key = "WARNING"
            counts[sev_key] += 1

            # Dedup key to avoid spamming annotations for duplicate findings.
            dedup_key = (path or "", start_line, end_line, rule_id)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            if severity == "ERROR":
                level = "failure"
            elif severity in ("WARNING", "WARN"):
                level = "warning"
            else:
                level = "notice"

            base_message = extra.get("message") or finding.get("check_id") or "Fixpoint finding"
            cwe = metadata.get("cwe")
            owasp = metadata.get("owasp")
            confidence = metadata.get("confidence")

            details = []
            if cwe:
                details.append(f"CWE: {cwe}")
            if owasp:
                details.append(f"OWASP: {owasp}")
            if confidence:
                details.append(f"Confidence: {confidence}")

            if details:
                full_message = f"{base_message} ({'; '.join(details)})"
            else:
                full_message = base_message

            if len(annotations) < 50:
                annotations.append(
                    {
                        "path": path,
                        "start_line": start_line,
                        "end_line": end_line,
                        "annotation_level": level,
                        "message": full_message,
                        "title": rule_id,
                    }
                )

        if findings:
            summary = (
                f"{len(findings or [])} violation(s) detected by Fixpoint. "
                f"ERROR: {counts['ERROR']}, WARNING: {counts['WARNING']}, INFO: {counts['INFO']}."
            )
        else:
            summary = "No violations detected by Fixpoint."

        check_run = r.create_check_run(
            name="Fixpoint - Security Check",
            head_sha=sha,
            status="completed",
            conclusion=conclusion,
            output={
                "title": "Fixpoint - Security Check",
                "summary": summary,
                "annotations": annotations,
            },
            details_url=pr_url,
        )

        return getattr(check_run, "html_url", None)
    except Exception as e:
        print(f"Warning: Failed to create check run with annotations: {e}")
        return None
