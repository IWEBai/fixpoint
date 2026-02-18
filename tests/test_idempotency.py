"""
Idempotency tests for Fixpoint fixers.

The core property is:

    fix(fix(code)) == fix(code)

for all supported vulnerability types. These tests use small synthetic
fixtures to keep runtime fast while still exercising the main patchers.
"""
from __future__ import annotations

from pathlib import Path

from core.fixer import process_findings


def _run_fix_once(
    temp_repo: Path,
    contents: str,
    *,
    check_id: str,
    filename: str = "app.py",
) -> str:
    target = temp_repo / filename
    target.write_text(contents, encoding="utf-8")

    findings = [
        {
            "check_id": check_id,
            "path": filename,
            "start": {"line": 1, "col": 1},
            "end": {"line": 1, "col": max(1, len(contents))},
            "extra": {
                "message": "Synthetic finding for idempotency test",
                "metadata": {"confidence": "high"},
            },
        }
    ]

    # rules_path is unused by current implementation but required by signature.
    rules_path = temp_repo / "rules.yaml"
    rules_path.write_text("rules: []", encoding="utf-8")

    process_findings(temp_repo, findings, rules_path)
    return target.read_text(encoding="utf-8")


def test_sql_injection_fixer_idempotent(temp_repo):
    vulnerable = '''import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()
'''

    once = _run_fix_once(
        temp_repo,
        vulnerable,
        check_id="custom.sql-injection-fstring",
        filename="app.py",
    )
    twice = _run_fix_once(
        temp_repo,
        once,
        check_id="custom.sql-injection-fstring",
        filename="app.py",
    )

    assert twice == once


def test_secrets_fixer_idempotent(temp_repo):
    vulnerable = '''import sqlite3

db_password = "my_secret_password_123"
db = sqlite3.connect("test.db")
'''

    once = _run_fix_once(
        temp_repo,
        vulnerable,
        check_id="custom.hardcoded-secret",
        filename="app.py",
    )
    twice = _run_fix_once(
        temp_repo,
        once,
        check_id="custom.hardcoded-secret",
        filename="app.py",
    )

    assert twice == once


def test_xss_template_fixer_idempotent(temp_repo):
    vulnerable = '''<html>
<body>
    <p>{{ user_input|safe }}</p>
</body>
</html>
'''

    once = _run_fix_once(
        temp_repo,
        vulnerable,
        check_id="custom.xss-safe-filter",
        filename="template.html",
    )
    twice = _run_fix_once(
        temp_repo,
        once,
        check_id="custom.xss-safe-filter",
        filename="template.html",
    )

    assert twice == once


def test_xss_python_fixer_idempotent(temp_repo):
    vulnerable = '''from django.utils.safestring import mark_safe

def render_html(user_input):
    return mark_safe(user_input)
'''

    once = _run_fix_once(
        temp_repo,
        vulnerable,
        check_id="custom.xss-mark-safe",
        filename="views.py",
    )
    twice = _run_fix_once(
        temp_repo,
        once,
        check_id="custom.xss-mark-safe",
        filename="views.py",
    )

    assert twice == once


def test_command_injection_fixer_idempotent(temp_repo):
    vulnerable = 'import os\n\ncmd = input("> ")\nos.system(cmd)\n'

    once = _run_fix_once(
        temp_repo,
        vulnerable,
        check_id="custom.command-injection",
        filename="script.py",
    )
    twice = _run_fix_once(
        temp_repo,
        once,
        check_id="custom.command-injection",
        filename="script.py",
    )

    assert twice == once


def test_path_traversal_fixer_idempotent(temp_repo):
    vulnerable = (
        'base = "uploads"\n'
        "path = os.path.join(base, user_input)\n"
        "with open(path) as fp:\n"
        "    fp.read()\n"
    )

    once = _run_fix_once(
        temp_repo,
        vulnerable,
        check_id="custom.path-traversal",
        filename="script.py",
    )
    twice = _run_fix_once(
        temp_repo,
        once,
        check_id="custom.path-traversal",
        filename="script.py",
    )

    assert twice == once


def test_js_secrets_fixer_idempotent(temp_repo):
    vulnerable = 'const apiKey = "sk_live_abc123def456";\n'

    once = _run_fix_once(
        temp_repo,
        vulnerable,
        check_id="custom.javascript-hardcoded-secret",
        filename="config.js",
    )
    twice = _run_fix_once(
        temp_repo,
        once,
        check_id="custom.javascript-hardcoded-secret",
        filename="config.js",
    )

    assert twice == once


def test_js_dom_xss_fixer_idempotent(temp_repo):
    vulnerable = "el.innerHTML = userInput;\n"

    once = _run_fix_once(
        temp_repo,
        vulnerable,
        check_id="custom.javascript-dom-xss",
        filename="app.js",
    )
    twice = _run_fix_once(
        temp_repo,
        once,
        check_id="custom.javascript-dom-xss",
        filename="app.js",
    )

    assert twice == once

