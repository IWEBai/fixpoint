"""
Property-based tests for Fixpoint fixers using Hypothesis.

Core properties:
- Patches must not introduce Python syntax errors.
- Patches must not introduce new vulnerabilities of the same class.
"""
from __future__ import annotations

import ast
import string
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st

from core.fixer import process_findings
from patcher.ast_utils import find_all_sqli_patterns
from patcher.detect_secrets import find_hardcoded_secrets
from patcher.detect_xss import find_xss_in_python


def _apply_fix_and_check(
    code: str,
    *,
    check_id: str,
    filename: str,
    detector,
    python: bool = True,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_repo = Path(tmpdir)
        target = temp_repo / filename
        target.write_text(code, encoding="utf-8")

        before_vulns = detector(code)

        findings = [
            {
                "check_id": check_id,
                "path": filename,
                "start": {"line": 1, "col": 1},
                "end": {"line": 1, "col": max(1, len(code))},
                "extra": {
                    "message": "Synthetic property test finding",
                    "metadata": {"confidence": "high"},
                },
            }
        ]

        rules_path = temp_repo / "rules.yaml"
        rules_path.write_text("rules: []", encoding="utf-8")

        process_findings(temp_repo, findings, rules_path)
        after = target.read_text(encoding="utf-8")

        if python:
            # Property: fixer must not introduce Python syntax errors.
            ast.parse(after)

        after_vulns = detector(after)

        # Property: fixes must not introduce *new* vulnerabilities of the same class.
        assert len(after_vulns) <= len(before_vulns)


_COMMENT_STRATEGY = st.text(
    alphabet=string.ascii_letters + string.digits + " _",
    min_size=0,
    max_size=40,
)


@given(comment=_COMMENT_STRATEGY)
def test_sql_injection_fix_preserves_syntax_and_no_new_vulns(comment: str):
    base = """import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()
"""
    code = base + f"# {comment}\n"

    _apply_fix_and_check(
        code,
        check_id="custom.sql-injection-fstring",
        filename="app.py",
        detector=find_all_sqli_patterns,
        python=True,
    )


@given(comment=_COMMENT_STRATEGY)
def test_secrets_fix_preserves_syntax_and_no_new_vulns(comment: str):
    base = """import sqlite3

db_password = "my_secret_password_123"
db = sqlite3.connect("test.db")
"""
    code = base + f"# {comment}\n"

    _apply_fix_and_check(
        code,
        check_id="custom.hardcoded-secret",
        filename="app.py",
        detector=find_hardcoded_secrets,
        python=True,
    )


@given(comment=_COMMENT_STRATEGY)
def test_xss_python_fix_preserves_syntax_and_no_new_vulns(comment: str):
    base = """from django.utils.safestring import mark_safe

def render_html(user_input):
    return mark_safe(user_input)
"""
    code = base + f"# {comment}\n"

    _apply_fix_and_check(
        code,
        check_id="custom.xss-mark-safe",
        filename="views.py",
        detector=find_xss_in_python,
        python=True,
    )

