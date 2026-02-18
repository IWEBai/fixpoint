"""
Patch planning utilities for Fixpoint.

Creates a lightweight \"patch plan\" from Semgrep findings before any
fixes are applied. The plan is used for safety guardrails (sensitive
paths, dependency changes, max files changed, etc.) in enforce mode.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any


@dataclass
class PatchPlan:
    """
    Lightweight description of the prospective changes Fixpoint would make.

    NOTE: This is intentionally conservative and does not try to predict
    exact hunks or diff sizes. It focuses on:
    - which files are likely to change
    - which rules/check_ids are involved
    so that safety guardrails can decide whether enforce mode is allowed.
    """

    repo_path: Path
    findings: List[Dict[str, Any]]
    target_files: List[str]
    rules: List[str]

    @property
    def changed_files(self) -> List[str]:
        """Return the list of unique files that may be modified."""
        # target_files is already de-duplicated, but keep the property for clarity
        return list(self.target_files)


def _relative_path(repo_path: Path, raw_path: str) -> str:
    """
    Convert a raw path (which may be absolute) into a path relative to repo_path.
    Falls back to filename when relative conversion is not possible.
    """
    p = Path(raw_path)
    if p.is_absolute():
        try:
            return str(p.relative_to(repo_path))
        except ValueError:
            return p.name
    return str(p)


def generate_patch_plan(
    repo_path: Path,
    findings: List[Dict[str, Any]],
    rules_path: Path,  # kept for future rule-specific logic
) -> PatchPlan:
    """
    Generate a PatchPlan from Semgrep findings.

    The plan does NOT apply any changes. It only:
    - collects the set of files that have findings
    - records which rules/check_ids are involved
    """
    repo_path = Path(repo_path)

    files_set = set()
    rules_set = set()

    for finding in findings or []:
        raw_path = finding.get("path")
        if not raw_path:
            continue
        rel_path = _relative_path(repo_path, raw_path)
        files_set.add(rel_path)

        check_id = finding.get("check_id")
        if check_id:
            rules_set.add(str(check_id))

    target_files = sorted(files_set)
    rules = sorted(rules_set)

    return PatchPlan(
        repo_path=repo_path,
        findings=list(findings or []),
        target_files=target_files,
        rules=rules,
    )

