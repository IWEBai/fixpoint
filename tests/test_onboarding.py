"""
Tests for Milestone 3 — Install in Under 60 Seconds.

The core promise:
  Install GitHub App → Select repo → Open PR → Railo works.
  No CLI, no YAML file, no env vars required.

Covers:
  • register_repos auto-seeds repo_settings with working defaults
  • get_prior_run_count tracks first-ever scan correctly
  • generate_welcome_comment content is correct, short, and branded "Railo"
  • load_config returns safe defaults when no file exists
  • load_config discovers .railo.yml first, then .fixpoint.yml as fallback
  • RAILO_MODE env var works; FIXPOINT_MODE still accepted for backward compat
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from core.db import (
    get_prior_run_count,
    get_repo_settings,
    init_db,
    insert_run,
    register_repos,
    set_db_path,
    upsert_installation,
)
from core.pr_comments import generate_welcome_comment


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def in_memory_db(tmp_path):
    """Redirect every DB call to a fresh file-based test database."""
    set_db_path(tmp_path / "test.db")
    init_db()
    yield


def _seed_installation(installation_id: int = 1) -> None:
    upsert_installation(installation_id, "testorg", "Organization")


# ===========================================================================
# TestZeroConfigDefaults
# ===========================================================================

class TestZeroConfigDefaults:
    """register_repos seeds repo_settings so every repo works immediately."""

    def test_register_repos_seeds_settings(self):
        _seed_installation()
        register_repos(1, [{"full_name": "testorg/myrepo", "id": 101}])
        settings = get_repo_settings("testorg/myrepo")
        assert settings is not None, "repo_settings row must be created on install"

    def test_seeded_settings_enabled_by_default(self):
        _seed_installation()
        register_repos(1, [{"full_name": "testorg/myrepo", "id": 101}])
        settings = get_repo_settings("testorg/myrepo")
        assert settings["enabled"] == 1

    def test_seeded_settings_warn_mode(self):
        _seed_installation()
        register_repos(1, [{"full_name": "testorg/myrepo", "id": 101}])
        settings = get_repo_settings("testorg/myrepo")
        assert settings["mode"] == "warn"

    def test_register_repos_multiple_repos(self):
        _seed_installation()
        repos = [
            {"full_name": "testorg/repo-a", "id": 1},
            {"full_name": "testorg/repo-b", "id": 2},
            {"full_name": "testorg/repo-c", "id": 3},
        ]
        register_repos(1, repos)
        for r in repos:
            assert get_repo_settings(r["full_name"]) is not None

    def test_register_repos_does_not_overwrite_custom_settings(self):
        """INSERT OR IGNORE must not clobber pre-existing custom settings."""
        from core.db import upsert_repo_settings
        _seed_installation()
        upsert_repo_settings("testorg/myrepo", mode="strict", enabled=True)
        # Register again — settings should be unchanged
        register_repos(1, [{"full_name": "testorg/myrepo", "id": 101}])
        settings = get_repo_settings("testorg/myrepo")
        assert settings["mode"] == "strict"

    def test_register_repos_empty_list_is_noop(self):
        _seed_installation()
        # Must not raise
        register_repos(1, [])

    def test_register_repos_missing_full_name_skipped(self):
        _seed_installation()
        register_repos(1, [{"id": 999}])
        # No crash and no orphan rows


# ===========================================================================
# TestFirstRunDetection
# ===========================================================================

class TestFirstRunDetection:
    """get_prior_run_count lets us detect the first PR for a repo."""

    def test_new_repo_has_zero_runs(self):
        assert get_prior_run_count("testorg/brand-new") == 0

    def test_count_increases_after_insert(self):
        _seed_installation()
        register_repos(1, [{"full_name": "testorg/myrepo", "id": 1}])
        assert get_prior_run_count("testorg/myrepo") == 0
        insert_run(
            installation_id=1,
            repo="testorg/myrepo",
            pr_number=1,
            status="success",
        )
        assert get_prior_run_count("testorg/myrepo") == 1

    def test_count_is_per_repo(self):
        _seed_installation()
        register_repos(1, [
            {"full_name": "testorg/repo-a", "id": 1},
            {"full_name": "testorg/repo-b", "id": 2},
        ])
        insert_run(
            installation_id=1,
            repo="testorg/repo-a",
            pr_number=7,
            status="success",
        )
        assert get_prior_run_count("testorg/repo-a") == 1
        assert get_prior_run_count("testorg/repo-b") == 0

    def test_multiple_runs_counted_correctly(self):
        _seed_installation()
        register_repos(1, [{"full_name": "testorg/busy", "id": 1}])
        for i in range(5):
            insert_run(
                installation_id=1,
                repo="testorg/busy",
                pr_number=i + 1,
                status="success",
            )
        assert get_prior_run_count("testorg/busy") == 5


# ===========================================================================
# TestWelcomeComment
# ===========================================================================

class TestWelcomeComment:
    """generate_welcome_comment returns a well-formed, branded onboarding message."""

    def test_returns_string(self):
        result = generate_welcome_comment("testorg", "myrepo")
        assert isinstance(result, str)

    def test_contains_railo_branding(self):
        result = generate_welcome_comment("testorg", "myrepo")
        assert "Railo" in result

    def test_no_fixpoint_branding(self):
        result = generate_welcome_comment("testorg", "myrepo")
        assert "Fixpoint" not in result
        assert "fixpoint" not in result

    def test_mentions_no_config_required(self):
        result = generate_welcome_comment("testorg", "myrepo")
        lower = result.lower()
        # Some variation of "no configuration" or "not required"
        assert "no config" in lower or "not required" in lower or "out of the box" in lower

    def test_has_markdown_heading(self):
        result = generate_welcome_comment("testorg", "myrepo")
        assert result.startswith("#")

    def test_mentions_security_scanning(self):
        result = generate_welcome_comment("testorg", "myrepo")
        lower = result.lower()
        assert "scan" in lower or "security" in lower

    def test_mentions_fix_pr(self):
        result = generate_welcome_comment("testorg", "myrepo")
        lower = result.lower()
        assert "fix" in lower and "pr" in lower

    def test_not_excessively_long(self):
        result = generate_welcome_comment("testorg", "myrepo")
        # Should be concise — developer is mid-PR-review
        assert len(result) < 1000, f"Welcome comment too long: {len(result)} chars"

    def test_contains_railo_yml_reference(self):
        result = generate_welcome_comment("testorg", "myrepo")
        assert ".railo.yml" in result

    def test_only_appears_once_note(self):
        result = generate_welcome_comment("testorg", "myrepo")
        assert "once" in result.lower()


# ===========================================================================
# TestConfigFilenames
# ===========================================================================

class TestConfigFilenames:
    """load_config returns safe defaults when no file exists and reads .railo.yml."""

    def test_no_config_file_returns_defaults(self, tmp_path):
        from core.config import load_config
        cfg = load_config(tmp_path)
        assert isinstance(cfg, dict)
        assert "max_diff_lines" in cfg

    def test_no_config_file_max_diff_lines_positive(self, tmp_path):
        from core.config import load_config
        cfg = load_config(tmp_path)
        assert cfg["max_diff_lines"] > 0

    def test_railo_yml_is_read(self, tmp_path):
        from core.config import load_config
        (tmp_path / ".railo.yml").write_text("max_diff_lines: 999\n", encoding="utf-8")
        cfg = load_config(tmp_path)
        assert cfg["max_diff_lines"] == 999

    def test_railo_yaml_is_read(self, tmp_path):
        from core.config import load_config
        (tmp_path / ".railo.yaml").write_text("max_diff_lines: 888\n", encoding="utf-8")
        cfg = load_config(tmp_path)
        assert cfg["max_diff_lines"] == 888

    def test_fixpoint_yml_still_works(self, tmp_path):
        """Legacy .fixpoint.yml files must continue to be honoured."""
        from core.config import load_config
        (tmp_path / ".fixpoint.yml").write_text("max_diff_lines: 777\n", encoding="utf-8")
        cfg = load_config(tmp_path)
        assert cfg["max_diff_lines"] == 777

    def test_railo_yml_takes_precedence_over_fixpoint_yml(self, tmp_path):
        from core.config import load_config
        (tmp_path / ".railo.yml").write_text("max_diff_lines: 111\n", encoding="utf-8")
        (tmp_path / ".fixpoint.yml").write_text("max_diff_lines: 222\n", encoding="utf-8")
        cfg = load_config(tmp_path)
        assert cfg["max_diff_lines"] == 111


# ===========================================================================
# TestEnvVarCompat
# ===========================================================================

class TestEnvVarCompat:
    """RAILO_MODE and FIXPOINT_MODE (legacy) both resolve the operating mode."""

    def test_railo_mode_env_var_read(self, monkeypatch):
        monkeypatch.setenv("RAILO_MODE", "strict")
        monkeypatch.delenv("FIXPOINT_MODE", raising=False)
        # Reload the module attribute
        import importlib
        import webhook.server as srv
        importlib.reload(srv)
        assert srv.RAILO_MODE == "strict"

    def test_fixpoint_mode_backward_compat(self, monkeypatch):
        monkeypatch.delenv("RAILO_MODE", raising=False)
        monkeypatch.setenv("FIXPOINT_MODE", "block")
        import importlib
        import webhook.server as srv
        importlib.reload(srv)
        assert srv.RAILO_MODE == "block"

    def test_railo_mode_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("RAILO_MODE", "warn")
        monkeypatch.setenv("FIXPOINT_MODE", "block")
        import importlib
        import webhook.server as srv
        importlib.reload(srv)
        assert srv.RAILO_MODE == "warn"

    def test_default_mode_is_warn(self, monkeypatch):
        monkeypatch.delenv("RAILO_MODE", raising=False)
        monkeypatch.delenv("FIXPOINT_MODE", raising=False)
        import importlib
        import webhook.server as srv
        importlib.reload(srv)
        assert srv.RAILO_MODE == "warn"

    def test_fixpoint_alias_equals_railo_mode(self, monkeypatch):
        monkeypatch.setenv("RAILO_MODE", "strict")
        monkeypatch.delenv("FIXPOINT_MODE", raising=False)
        import importlib
        import webhook.server as srv
        importlib.reload(srv)
        assert srv.FIXPOINT_MODE == srv.RAILO_MODE
