"""
Tests for path traversal fixer.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from patcher.fix_path_traversal import apply_fix_path_traversal, propose_fix_path_traversal


@pytest.fixture
def tmp_repo(tmp_path):
    return tmp_path


def test_fixes_path_join_pattern(tmp_repo):
    """os.path.join(base, user_var) should get validation inserted."""
    f = tmp_repo / "script.py"
    f.write_text('base = "uploads"\npath = os.path.join(base, user_input)\nwith open(path) as fp:\n    fp.read()\n')
    assert apply_fix_path_traversal(tmp_repo, "script.py") is True
    content = f.read_text()
    assert "Path traversal denied" in content
    assert "os.path.realpath" in content


def test_includes_os_import(tmp_repo):
    """Validation uses os.path.realpath; file should have os available."""
    f = tmp_repo / "script.py"
    f.write_text('path = os.path.join("uploads", user_input)\n')
    assert apply_fix_path_traversal(tmp_repo, "script.py") is True
    content = f.read_text()
    assert "import os" in content or "from os import" in content


def test_skips_when_validation_exists(tmp_repo):
    """Should not add duplicate validation."""
    f = tmp_repo / "script.py"
    f.write_text('path = os.path.join(base, user_input)\nif not os.path.realpath(path).startswith(os.path.realpath(base)):\n    raise PermissionError("Path traversal denied")\n')
    assert apply_fix_path_traversal(tmp_repo, "script.py") is False


def test_returns_false_for_missing_file(tmp_repo):
    assert apply_fix_path_traversal(tmp_repo, "nonexistent.py") is False


def test_propose_returns_list(tmp_repo):
    f = tmp_repo / "script.py"
    f.write_text('path = os.path.join("uploads", user_input)\n')
    result = propose_fix_path_traversal(tmp_repo, "script.py")
    assert result is not None
    assert isinstance(result, list)
