"""
Trust contract and safety decision reporting for Fixpoint.

This module centralises the non‑negotiable safety guarantees:

- Only auto‑fix findings covered by known rules (enforced via core.fixer).
- Never exceed max_diff_lines when committing.
- Never touch files outside supported extensions.
- Never run enforce if the overall time budget is exceeded (degrade to warn/report‑only).

It also produces a per‑run Safety Decision Report which can be written to a
JSON file and optionally summarised in PR comments or logs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import json
import uuid


# Central definition of which file extensions Fixpoint is allowed to modify.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".jinja",
    ".jinja2",
    ".j2",
    ".djhtml",
)


@dataclass
class DecisionReport:
    """
    Structured record of a single Fixpoint run's safety decisions.

    This is intentionally lightweight: the goal is to give operators and
    developers a concise answer to "why did it fix / why did it refuse?"
    without requiring them to trawl through logs.
    """

    mode_requested: str
    mode_effective: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "unknown"  # "fixed" | "report_only" | "refused" | "no_findings" | "skipped"
    summary: Dict[str, Any] = field(default_factory=dict)
    rails: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    def set_summary(
        self,
        *,
        violations_found: int,
        violations_fixed: int,
        files_touched: int,
        check_ids: Sequence[str],
    ) -> None:
        self.summary = {
            "violations_found": int(violations_found),
            "violations_fixed": int(violations_fixed),
            "files_touched": int(files_touched),
            "check_ids": sorted(set(check_ids)),
        }

    # ---- Rail helpers -------------------------------------------------

    def mark_extensions(
        self,
        *,
        initial_count: int,
        supported_count: int,
        filtered_out: int,
    ) -> None:
        self.rails["extensions"] = {
            "status": "ok",
            "initial_count": int(initial_count),
            "supported_count": int(supported_count),
            "filtered_out": int(filtered_out),
            "supported_extensions": list(SUPPORTED_EXTENSIONS),
        }

    def mark_time_budget(
        self,
        *,
        elapsed: float,
        max_runtime_seconds: float,
        timed_out: bool,
    ) -> None:
        self.rails["time_budget"] = {
            "status": "blocked" if timed_out else "ok",
            "elapsed": float(elapsed),
            "max_runtime_seconds": float(max_runtime_seconds),
        }
        if timed_out:
            self.reasons.append(
                f"Time budget exceeded ({elapsed:.1f}s > {max_runtime_seconds}s); "
                "enforce degraded to report-only."
            )

    def mark_max_diff_lines(
        self,
        *,
        ok: bool,
        added: int,
        removed: int,
        max_diff_lines: int,
    ) -> None:
        total = int(added) + int(removed)
        self.rails["max_diff_lines"] = {
            "status": "ok" if ok else "blocked",
            "total_changed_lines": total,
            "added": int(added),
            "removed": int(removed),
            "max_allowed": int(max_diff_lines),
        }
        if not ok:
            self.reasons.append(
                f"Diff too large ({total} lines, max {max_diff_lines}); "
                "refusing to commit auto-fix."
            )

    def mark_diff_quality(self, result: Dict[str, Any]) -> None:
        is_minimal = bool(result.get("is_minimal", False))
        score = float(result.get("quality_score", 0.0))
        issues = list(result.get("issues", []))
        self.rails["diff_quality"] = {
            "status": "ok" if is_minimal else "blocked",
            "quality_score": score,
            "issues": issues,
        }
        if not is_minimal:
            self.reasons.append(
                "Diff quality rail tripped; patches are not minimal or contain "
                "suspicious reordering/whitespace changes."
            )

    def mark_policy(self, *, ok: bool, reasons: Sequence[str]) -> None:
        self.rails["policy"] = {
            "status": "ok" if ok else "blocked",
            "reasons": list(reasons),
        }
        if not ok:
            for r in reasons:
                self.reasons.append(f"Policy/guardrail blocked auto-fix: {r}")

    def mark_formatting_expansion(
        self,
        *,
        relpath: str,
        baseline_total: int,
        post_total: int,
        max_expansion: float,
    ) -> None:
        """
        Record that the formatting guardrail reverted changes for a file because
        the diff expanded too much relative to the pre-formatting diff.
        """
        rail = self.rails.setdefault(
            "formatting_expansion",
            {
                "status": "ok",
                "offending_files": [],
                "max_expansion": float(max_expansion),
            },
        )
        rail["status"] = "blocked"
        offenders = rail.setdefault("offending_files", [])
        offenders.append(
            {
                "file": relpath,
                "baseline_total": int(baseline_total),
                "post_total": int(post_total),
            }
        )
        self.reasons.append(
            f"Formatting expansion rail reverted changes for {relpath} "
            f"({baseline_total} → {post_total} lines; "
            f"max_format_expansion={max_expansion})."
        )

    def mark_permissions(
        self,
        *,
        can_comment: Optional[bool],
        can_check_runs: Optional[bool],
        can_push: Optional[bool],
        note: str = "",
    ) -> None:
        """
        Record best-effort permission capabilities inferred from the token.

        We intentionally treat unknowns (None) as "not checked" rather than errors.
        """
        self.rails["permissions"] = {
            "can_comment": can_comment,
            "can_check_runs": can_check_runs,
            "can_push": can_push,
            "note": note,
        }
        if can_push is False:
            self.reasons.append(
                "Permission rail: token cannot push to this repository; "
                "enforce mode will be downgraded to warn/report-only."
            )

    def mark_baseline(self, audit: Dict[str, Any]) -> None:
        """
        Record baseline filtering metadata for auditing and transparency.
        """
        self.rails["baseline"] = {
            "status": "ok",
            "baseline_sha": audit.get("baseline_sha"),
            "filtered_count": int(audit.get("filtered_count", 0)),
            "remaining_count": int(audit.get("remaining_count", 0)),
            "age_days": audit.get("age_days"),
            "expired": bool(audit.get("expired", False)),
        }

    # ---- Serialisation helpers ----------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode_requested": self.mode_requested,
            "mode_effective": self.mode_effective,
            "status": self.status,
            "summary": self.summary,
            "rails": self.rails,
            "reasons": self.reasons,
        }

    def to_comment_snippet(self) -> str:
        """
        Produce a short, human-readable summary suitable for inclusion in
        PR comments. This is intentionally compact (one or two sentences).
        """
        status = self.status or "unknown"
        mode = self.mode_effective or self.mode_requested

        if status == "no_findings":
            return "Safety Decision: no violations found; no changes were required."

        if status == "fixed" and mode == "enforce":
            return (
                "Safety Decision: auto-fix applied in enforce mode; all safety rails "
                "passed (rule set, diff limits, extensions, time budget)."
            )

        if status in {"report_only", "refused"}:
            # Surface the first reason to avoid overwhelming the reader.
            reason = self.reasons[0] if self.reasons else "enforce disabled by safety rails."
            return f"Safety Decision: enforce disabled; {reason}"

        # Fallback for warn-mode runs where we only proposed patches.
        if mode == "warn":
            return (
                "Safety Decision: warn mode is active; proposed patches only, "
                "no changes were applied automatically."
            )

        return "Safety Decision: completed with safety rails enforced."


# ---- Convenience helpers -----------------------------------------------


def filter_supported_files(
    files: Sequence[str],
    report: Optional[DecisionReport] = None,
) -> List[str]:
    """
    Filter a list of file paths down to the supported extensions.

    Optionally records the decision in a DecisionReport.
    """
    initial_count = len(files)
    filtered = [f for f in files if f.endswith(SUPPORTED_EXTENSIONS)]
    if report is not None:
        report.mark_extensions(
            initial_count=initial_count,
            supported_count=len(filtered),
            filtered_out=initial_count - len(filtered),
        )
    return filtered


def write_safety_report(root: Path, report: DecisionReport, filename: str = "safety-report.json") -> Path:
    """
    Persist the Safety Decision Report as JSON in the given root directory.

    This is best-effort: failures are printed but should not crash the run.
    """
    try:
        root = Path(root)
        path = root / filename
        path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        return path
    except Exception as exc:  # pragma: no cover - defensive
        # We avoid importing core.observability here to keep dependencies minimal.
        print(f"Warning: failed to write safety report: {exc}")
        return Path(filename)

