"""
Tests for JavaScript/TypeScript fixers.
"""
from __future__ import annotations

import pytest

from patcher.fix_javascript import (
    apply_fix_js_secrets,
    apply_fix_js_dom_xss,
    propose_fix_js_eval,
    propose_fix_js_secrets,
    propose_fix_js_dom_xss,
)


@pytest.fixture
def tmp_repo(tmp_path):
    return tmp_path


def test_fixes_js_secrets(tmp_repo):
    """apiKey = "xxx" should be replaced with process.env.API_KEY."""
    f = tmp_repo / "config.js"
    f.write_text('const apiKey = "sk_live_abc123def456";\n')
    assert apply_fix_js_secrets(tmp_repo, "config.js") is True
    content = f.read_text()
    assert "process.env.API_KEY" in content
    assert "sk_live_" not in content


def test_fixes_js_dom_xss(tmp_repo):
    """innerHTML = should be replaced with textContent =."""
    f = tmp_repo / "app.js"
    f.write_text('el.innerHTML = userInput;\n')
    assert apply_fix_js_dom_xss(tmp_repo, "app.js") is True
    content = f.read_text()
    assert "textContent" in content
    assert "innerHTML" not in content


def test_skips_safe_js(tmp_repo):
    """textContent = should not be changed."""
    f = tmp_repo / "app.js"
    f.write_text('el.textContent = userInput;\n')
    assert apply_fix_js_dom_xss(tmp_repo, "app.js") is False


def test_propose_returns_list(tmp_repo):
    assert propose_fix_js_eval(tmp_repo, "a.js") is not None
    assert propose_fix_js_secrets(tmp_repo, "a.js") is not None
    assert propose_fix_js_dom_xss(tmp_repo, "a.js") is not None
