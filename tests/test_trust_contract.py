"""
Tests for the Fixpoint trust contract and safety decision reporting.
"""
from __future__ import annotations

from pathlib import Path

from core.trust_contract import (
    DecisionReport,
    SUPPORTED_EXTENSIONS,
    filter_supported_files,
    write_safety_report,
)


def test_filter_supported_files_respects_extension_allowlist(tmp_path: Path) -> None:
    files = [
        "app.py",
        "script.js",
        "view.tsx",
        "README.md",
        "style.css",
    ]
    decision = DecisionReport(mode_requested="enforce", mode_effective="enforce")

    filtered = filter_supported_files(files, decision)

    # Only supported extensions remain
    assert set(filtered) == {"app.py", "script.js", "view.tsx"}

    rail = decision.rails.get("extensions") or {}
    assert rail.get("status") == "ok"
    assert rail.get("initial_count") == len(files)
    assert rail.get("supported_count") == len(filtered)
    assert rail.get("filtered_out") == len(files) - len(filtered)
    assert set(rail.get("supported_extensions") or []) >= set(SUPPORTED_EXTENSIONS)


def test_time_budget_rail_records_timeout() -> None:
    decision = DecisionReport(mode_requested="enforce", mode_effective="enforce")

    decision.mark_time_budget(elapsed=120.0, max_runtime_seconds=90.0, timed_out=True)

    rail = decision.rails.get("time_budget") or {}
    assert rail.get("status") == "blocked"
    assert rail.get("elapsed") == 120.0
    assert rail.get("max_runtime_seconds") == 90.0
    assert any("Time budget exceeded" in r for r in decision.reasons)


def test_max_diff_rail_records_block_and_reason() -> None:
    decision = DecisionReport(mode_requested="enforce", mode_effective="enforce")

    decision.mark_max_diff_lines(ok=False, added=600, removed=500, max_diff_lines=500)

    rail = decision.rails.get("max_diff_lines") or {}
    assert rail.get("status") == "blocked"
    assert rail.get("total_changed_lines") == 1100
    assert rail.get("max_allowed") == 500
    assert any("Diff too large" in r for r in decision.reasons)


def test_write_safety_report_creates_json(tmp_path: Path) -> None:
    decision = DecisionReport(mode_requested="warn", mode_effective="warn")
    decision.status = "report_only"
    decision.set_summary(
        violations_found=3,
        violations_fixed=0,
        files_touched=1,
        check_ids=["sql-injection", "hardcoded-secret"],
    )

    path = write_safety_report(tmp_path, decision, filename="safety-report-test.json")
    assert path.exists()

    text = path.read_text(encoding="utf-8")
    assert '"violations_found": 3' in text
    assert '"mode_requested": "warn"' in text

