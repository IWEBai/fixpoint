"""
Golden tests for Fixpoint patchers.

This test suite is intentionally lightweight: it discovers golden
fixtures (if present) under tests/golden/ and verifies that applying
the corresponding fixer produces the expected output.

The initial implementation focuses on providing the structure so that
future patchers can easily add fixtures without changing test code.
"""
from __future__ import annotations

from pathlib import Path
import ast
import os
import shutil
import subprocess
import json

import pytest


GOLDEN_ROOT = Path(__file__).parent / "golden"
RULES_ROOT = Path(__file__).parent.parent / "rules"


def _assert_parses(path: Path) -> None:
    """Ensure patched file parses (Python AST or TS/JS parser)."""
    suffix = path.suffix.lower()
    content = path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".py":
        ast.parse(content)
        return

    if suffix in (".js", ".jsx", ".ts", ".tsx"):
        try:
            from tree_sitter_languages import get_language, get_parser
        except ImportError:
            pytest.skip("tree_sitter_languages not installed; skipping JS/TS parser gate")

        lang_name = "typescript" if suffix in (".ts",) else "tsx" if suffix in (".tsx", ".jsx") else "javascript"
        parser = get_parser(lang_name)
        tree = parser.parse(content.encode("utf-8", errors="replace"))
        if tree.root_node.has_error:
            raise AssertionError(f"Parser errors found in {path.name} ({lang_name})")


def _semgrep_results_for_file(target_path: Path) -> list[str]:
    """Return semgrep check_ids for a single file; skips if semgrep missing."""
    if shutil.which("semgrep") is None:
        pytest.skip("semgrep not available; skipping semgrep regression gate")
    if not RULES_ROOT.exists():
        pytest.skip("rules directory missing; skipping semgrep regression gate")

    output_path = target_path.with_suffix(target_path.suffix + ".semgrep.json")
    cmd = [
        "semgrep",
        "--config",
        str(RULES_ROOT),
        "--json",
        "--output",
        str(output_path),
        str(target_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Semgrep failed: {proc.stdout}\n{proc.stderr}")
    data = json.loads(output_path.read_text(encoding="utf-8", errors="replace"))
    return [str(r.get("check_id", "")).lower() for r in data.get("results", [])]


def _family_match(check_id: str, family_tokens: list[str]) -> bool:
    return any(token in check_id for token in family_tokens)


def _family_tokens_for_suite(suite_name: str) -> list[str]:
    if suite_name == "fix_sqli":
        return ["sql-injection", "sqli"]
    if suite_name == "fix_secrets":
        return ["secret", "password", "token", "access-key", "private-key", "database-uri", "github-token", "slack-token", "stripe-key", "sendgrid-key"]
    if suite_name == "fix_xss":
        return ["xss", "mark-safe", "safe-filter", "autoescape"]
    if suite_name == "fix_command":
        return ["command-injection", "os-system", "subprocess-shell"]
    if suite_name == "fix_path":
        return ["path-traversal"]
    if suite_name == "fix_js":
        return ["javascript", "typescript", "dom-xss", "eval", "hardcoded-secret"]
    return []


def _iter_golden_cases():
    """
    Yield (suite_name, input_path, expected_path) triples for all
    *.input files under tests/golden/.
    """
    if not GOLDEN_ROOT.exists():
        return
    for suite_dir in sorted(p for p in GOLDEN_ROOT.iterdir() if p.is_dir()):
        suite_name = suite_dir.name
        for input_file in sorted(suite_dir.rglob("*.input")):
            expected_file = input_file.with_suffix("").with_suffix(".expected")
            yield suite_name, input_file, expected_file


@pytest.mark.parametrize(
    "suite_name,input_path,expected_path",
    list(_iter_golden_cases()) or [],
)
def test_golden_fixtures(temp_repo, suite_name: str, input_path: Path, expected_path: Path):
    """
    Generic golden test runner.

    Each suite directory under tests/golden/ maps to a specific fixer:

      tests/golden/fix_sqli/       -> patcher.fix_sqli.apply_fix_sqli
      tests/golden/fix_secrets/    -> patcher.fix_secrets.apply_fix_secrets
      tests/golden/fix_xss/        -> patcher.fix_xss.apply_fix_xss
      tests/golden/fix_command/    -> patcher.fix_command_injection.apply_fix_command_injection
      tests/golden/fix_path/       -> patcher.fix_path_traversal.apply_fix_path_traversal
      tests/golden/fix_js/         -> patcher.fix_javascript.apply_* helpers

    The mapping is intentionally best-effort; suites without a known
    fixer name are skipped.
    """
    # Copy input into temp_repo as a simple file with the same basename.
    target_name = input_path.name.replace(".input", "")
    target_path = temp_repo / target_name
    target_path.write_text(input_path.read_text(encoding="utf-8"), encoding="utf-8")

    if not expected_path.exists():
        raise AssertionError(
            f"Missing expected snapshot for {input_path.name}. "
            "Add a .expected file or run with FIXPOINT_UPDATE_GOLDENS=1."
        )

    # Optional semgrep gate: capture findings before fix
    semgrep_gate = os.getenv("FIXPOINT_SEMGREP_GATE", "").lower() in ("1", "true", "yes")
    before_check_ids: list[str] = []
    if semgrep_gate:
        before_check_ids = _semgrep_results_for_file(target_path)

    # Dispatch to the appropriate fixer based on suite_name.
    changed = False
    if suite_name == "fix_sqli":
        from patcher.fix_sqli import apply_fix_sqli

        changed = apply_fix_sqli(temp_repo, target_name)
    elif suite_name == "fix_secrets":
        from patcher.fix_secrets import apply_fix_secrets

        changed = apply_fix_secrets(temp_repo, target_name)
    elif suite_name == "fix_xss":
        from patcher.fix_xss import apply_fix_xss

        changed = apply_fix_xss(temp_repo, target_name)
    elif suite_name == "fix_command":
        from patcher.fix_command_injection import apply_fix_command_injection

        changed = bool(apply_fix_command_injection(temp_repo, target_name))
    elif suite_name == "fix_path":
        from patcher.fix_path_traversal import apply_fix_path_traversal

        changed = bool(apply_fix_path_traversal(temp_repo, target_name))
    elif suite_name == "fix_js":
        # For JS/TS we support multiple fixers; golden suites can choose
        # which one to exercise.
        from patcher.fix_javascript import (
            apply_fix_js_eval,
            apply_fix_js_secrets,
            apply_fix_js_dom_xss,
        )

        # Try all; at least one should apply for the fixture.
        changed = any(
            fn(temp_repo, target_name)
            for fn in (apply_fix_js_eval, apply_fix_js_secrets, apply_fix_js_dom_xss)
        )
    else:
        pytest.skip(f"Unknown golden suite '{suite_name}', add mapping in test_golden.py")

    assert changed, f"Expected fixer to modify {target_name} in suite {suite_name}"

    # Parser gate: patched file must parse
    _assert_parses(target_path)

    actual = target_path.read_text(encoding="utf-8")
    expected = expected_path.read_text(encoding="utf-8")

    if actual != expected:
        if os.getenv("FIXPOINT_UPDATE_GOLDENS") in ("1", "true", "yes"):
            expected_path.write_text(actual, encoding="utf-8")
        else:
            raise AssertionError(
                f"Golden snapshot mismatch for {input_path.name}. "
                "Run with FIXPOINT_UPDATE_GOLDENS=1 to refresh expected output."
            )

    # Optional semgrep gate: no new findings for same rule family
    if semgrep_gate:
        family_tokens = _family_tokens_for_suite(suite_name)
        if family_tokens:
            after_check_ids = _semgrep_results_for_file(target_path)
            before_family = [c for c in before_check_ids if _family_match(c, family_tokens)]
            after_family = [c for c in after_check_ids if _family_match(c, family_tokens)]
            if len(after_family) > len(before_family):
                raise AssertionError(
                    f"Semgrep gate failed: new findings introduced for {suite_name}. "
                    f"Before={len(before_family)} After={len(after_family)}"
                )


def test_golden_suite_can_be_empty():
    """
    When no golden fixtures exist yet, this test ensures the suite
    does not fail the entire test run. It simply asserts that discovery
    either produced cases (covered by parametrised test) or that the
    golden root is empty, which is acceptable for initial rollout.
    """
    if not GOLDEN_ROOT.exists():
        # No golden fixtures configured yet – this is fine.
        pytest.skip("No golden fixtures configured yet")

    has_any = any(_iter_golden_cases())
    assert has_any or not any(GOLDEN_ROOT.iterdir())


def test_golden_snapshots_present_for_all_inputs():
    if not GOLDEN_ROOT.exists():
        pytest.skip("No golden fixtures configured yet")
    missing: list[str] = []
    for suite_dir in sorted(p for p in GOLDEN_ROOT.iterdir() if p.is_dir()):
        for input_file in sorted(suite_dir.rglob("*.input")):
            expected_file = input_file.with_suffix("").with_suffix(".expected")
            if not expected_file.exists():
                missing.append(str(expected_file))
    assert not missing, "Missing golden expected files: " + ", ".join(missing)

