"""
SARIF (Static Analysis Results Interchange Format) utilities for Fixpoint.

Generates a minimal SARIF 2.1.0 document from Semgrep findings so results
can be surfaced in GitHub Code Scanning and other compatible tools.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple, Set


SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def _relative_path(repo_path: Path, raw_path: str) -> str:
    """Return path relative to repo root for SARIF URIs."""
    p = Path(raw_path)
    if p.is_absolute():
        try:
            return str(p.relative_to(repo_path))
        except ValueError:
            return p.name
    return str(p)


def generate_sarif(
    findings: List[Dict[str, Any]],
    repo_path: Path,
    tool_name: str = "Fixpoint",
) -> Dict[str, Any]:
    """
    Generate a minimal SARIF 2.1.0 document from Semgrep findings.

    Args:
        findings: List of Semgrep findings (as returned from semgrep_scan)
        repo_path: Path to repository root
        tool_name: Name of the tool (default: \"Fixpoint\")

    Returns:
        dict representing a SARIF 2.1.0 document
    """
    repo_path = Path(repo_path)

    rules_index: Dict[str, int] = {}
    rules: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []

    # Deduplicate results by (relative path, start_line, end_line, rule_id).
    seen_keys: Set[Tuple[str, int, int, str]] = set()

    for finding in findings or []:
        check_id = finding.get("check_id") or "unknown-rule"
        rule_id = str(check_id)

        extra = finding.get("extra", {}) or {}
        metadata = extra.get("metadata", {}) or {}
        message = extra.get("message", "") or rule_id
        cwe = metadata.get("cwe")
        owasp = metadata.get("owasp")
        severity = str(metadata.get("severity") or extra.get("severity") or "WARNING").upper()
        confidence = metadata.get("confidence")
        help_uri = metadata.get("help_uri")

        # Register rule if new
        if rule_id not in rules_index:
            rule: Dict[str, Any] = {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": message},
                "fullDescription": {"text": message},
                "help": {"text": message},
                "properties": {},
            }
            props = rule["properties"]
            if cwe:
                props["cwe"] = cwe
            if owasp:
                props["owasp"] = owasp
            # Map to SARIF/GitHub security-severity band (0.0–10.0 as string).
            severity_map = {"ERROR": "8.9", "WARNING": "6.0", "WARN": "6.0", "INFO": "3.0"}
            props["security-severity"] = severity_map.get(severity, "6.0")
            if confidence:
                props["confidence"] = confidence
            if help_uri:
                rule["helpUri"] = help_uri
            else:
                # Fallback help URI for Fixpoint rules; stable pattern per rule id.
                rule["helpUri"] = f"https://github.com/IWEBai/fixpoint/docs/rules/{rule_id}"

            rules_index[rule_id] = len(rules)
            rules.append(rule)

        # Build result entry
        raw_path = finding.get("path", "")
        rel_path = _relative_path(repo_path, raw_path)
        rel_uri = rel_path.replace("\\", "/")
        start = finding.get("start", {}) or {}
        end = finding.get("end", {}) or {}

        start_line = int(start.get("line", 1) or 1)
        start_col = int(start.get("col", 1) or 1)
        end_line = int(end.get("line", start_line) or start_line)
        end_col = int(end.get("col", start_col) or start_col)

        # Dedup key: same file, region, and rule id.
        dedup_key = (rel_uri, start_line, end_line, rule_id)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        message_text = message

        # Try to capture a small snippet/context region for the finding.
        region: Dict[str, Any] = {
            "startLine": start_line,
            "startColumn": start_col,
            "endLine": end_line,
            "endColumn": end_col,
        }
        try:
            file_path = repo_path / rel_path
            if file_path.exists():
                lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                if 1 <= start_line <= len(lines):
                    # Slice inclusive of end_line if possible
                    start_idx = max(0, start_line - 1)
                    end_idx = min(len(lines), max(start_line, end_line))
                    snippet_lines = lines[start_idx:end_idx] or [lines[start_idx]]
                    snippet_text = "\n".join(snippet_lines)[:500]
                    region["snippet"] = {"text": snippet_text}
                # Optional 2-line context around region
                if lines:
                    context_start = max(1, start_line - 2)
                    context_end = min(len(lines), max(end_line, start_line) + 2)
                    region["contextRegion"] = {
                        "startLine": context_start,
                        "endLine": context_end,
                    }
        except Exception:
            # Snippet/context are best-effort; ignore failures.
            pass

        result: Dict[str, Any] = {
            "ruleId": rule_id,
            "ruleIndex": rules_index[rule_id],
            "message": {"text": message_text},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": rel_uri},
                        "region": region,
                    }
                }
            ],
            "properties": {},
        }

        # Attach per-result severity/confidence for richer UIs.
        res_props = result["properties"]
        if severity:
            res_props["severity"] = severity
        if confidence:
            res_props["confidence"] = confidence

        results.append(result)

    sarif: Dict[str, Any] = {
        "version": SARIF_VERSION,
        "$schema": SARIF_SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool_name,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return sarif

