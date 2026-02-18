"""
Tests for command injection fixer.
"""
from __future__ import annotations

import pytest

from patcher.fix_command_injection import apply_fix_command_injection, propose_fix_command_injection


@pytest.fixture
def tmp_repo(tmp_path):
    return tmp_path


def test_fixes_os_system(tmp_repo):
    """os.system(cmd) should be converted to subprocess.run(shlex.split(cmd), shell=False)."""
    f = tmp_repo / "script.py"
    f.write_text('import os\n\ncmd = input("> ")\nos.system(cmd)\n')
    assert apply_fix_command_injection(tmp_repo, "script.py") is True
    content = f.read_text()
    assert "subprocess.run(shlex.split(cmd), shell=False)" in content
    assert "os.system" not in content
    assert "import subprocess" in content
    assert "import shlex" in content


def test_fixes_subprocess_shell_true(tmp_repo):
    """subprocess.run(cmd, shell=True) should use shell=False and shlex.split."""
    f = tmp_repo / "script.py"
    f.write_text('import subprocess\n\ncmd = "ls -la"\nsubprocess.run(cmd, shell=True)\n')
    assert apply_fix_command_injection(tmp_repo, "script.py") is True
    content = f.read_text()
    assert "shell=False" in content
    assert "shell=True" not in content
    assert "shlex.split" in content


def test_skips_safe_code(tmp_repo):
    """subprocess.run(cmd, shell=False) should not be changed."""
    f = tmp_repo / "script.py"
    f.write_text('import subprocess\n\nsubprocess.run(["ls", "-la"], shell=False)\n')
    assert apply_fix_command_injection(tmp_repo, "script.py") is False


def test_returns_false_for_missing_file(tmp_repo):
    assert apply_fix_command_injection(tmp_repo, "nonexistent.py") is False


def test_propose_returns_list(tmp_repo):
    f = tmp_repo / "script.py"
    f.write_text("os.system('ls')\n")
    result = propose_fix_command_injection(tmp_repo, "script.py")
    assert result is not None
    assert isinstance(result, list)
    assert len(result) > 0
