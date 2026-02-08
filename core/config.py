"""
Configuration loader for Fixpoint.
Loads repo-specific settings from .fixpoint.yml / .fixpoint.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


# Default configuration values
DEFAULT_MAX_DIFF_LINES = 500
DEFAULT_TEST_BEFORE_COMMIT = False
DEFAULT_TEST_COMMAND = "pytest"


def load_config(repo_path: Path) -> dict[str, Any]:
    """
    Load Fixpoint configuration from repo root.
    
    Searches for .fixpoint.yml or .fixpoint.yaml in repo_path.
    Environment variables override config file values:
    - FIXPOINT_MAX_DIFF_LINES
    - FIXPOINT_TEST_BEFORE_COMMIT
    - FIXPOINT_TEST_COMMAND
    
    Args:
        repo_path: Path to repository root
    
    Returns:
        Config dict with keys: max_diff_lines, test_before_commit, test_command
    """
    config: dict[str, Any] = {
        "max_diff_lines": DEFAULT_MAX_DIFF_LINES,
        "test_before_commit": DEFAULT_TEST_BEFORE_COMMIT,
        "test_command": DEFAULT_TEST_COMMAND,
    }
    
    for name in (".fixpoint.yml", ".fixpoint.yaml"):
        config_path = repo_path / name
        if config_path.exists():
            try:
                raw = config_path.read_text(encoding="utf-8", errors="replace")
                data = yaml.safe_load(raw) or {}
                if isinstance(data, dict):
                    if "max_diff_lines" in data:
                        val = data["max_diff_lines"]
                        if isinstance(val, (int, float)) and val > 0:
                            config["max_diff_lines"] = int(val)
                    if "test_before_commit" in data:
                        config["test_before_commit"] = bool(data["test_before_commit"])
                    if "test_command" in data:
                        cmd = data["test_command"]
                        if isinstance(cmd, str) and cmd.strip():
                            config["test_command"] = cmd.strip()
            except Exception:
                pass
            break
    
    # Environment overrides
    env_max = os.getenv("FIXPOINT_MAX_DIFF_LINES")
    if env_max is not None:
        try:
            config["max_diff_lines"] = int(env_max)
        except ValueError:
            pass
    
    env_test = os.getenv("FIXPOINT_TEST_BEFORE_COMMIT", "").lower()
    if env_test in ("1", "true", "yes"):
        config["test_before_commit"] = True
    elif env_test in ("0", "false", "no"):
        config["test_before_commit"] = False
    
    env_cmd = os.getenv("FIXPOINT_TEST_COMMAND")
    if env_cmd and isinstance(env_cmd, str):
        config["test_command"] = env_cmd.strip()
    
    return config


def get_max_diff_lines(repo_path: Path) -> int:
    """Get max allowed diff lines for auto-fix."""
    return load_config(repo_path)["max_diff_lines"]


def get_test_before_commit(repo_path: Path) -> bool:
    """Whether to run tests before committing fixes."""
    return load_config(repo_path)["test_before_commit"]


def get_test_command(repo_path: Path) -> str:
    """Command to run before committing (e.g. pytest, npm test)."""
    return load_config(repo_path)["test_command"]
