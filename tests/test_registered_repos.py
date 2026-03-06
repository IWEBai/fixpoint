"""
Tests for registered_repos table and the installation lifecycle handlers.
Covers:
  - register_repos / deregister_repos / get_registered_repos DB functions
  - installation webhook: initial repo registration on created event
  - installation webhook: repo deactivation on deleted event
  - installation_repositories webhook: added / removed arrays
"""
from __future__ import annotations

import json
import uuid

import pytest

from core.db import (
    init_db,
    set_db_path,
    upsert_installation,
    register_repos,
    deregister_repos,
    get_registered_repos,
    remove_installation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Point the DB layer at a fresh in-memory-ish SQLite file for each test."""
    db_file = tmp_path / "test_railo.db"
    set_db_path(db_file)
    init_db()
    yield db_file
    set_db_path(None)  # reset so other tests are unaffected


def _seed_installation(inst_id: int = 1001, login: str = "octocat") -> None:
    upsert_installation(installation_id=inst_id, account_login=login, account_type="User")


# ---------------------------------------------------------------------------
# Unit tests: DB functions
# ---------------------------------------------------------------------------

def test_register_repos_basic(tmp_db):
    _seed_installation()
    repos = [
        {"id": 1, "full_name": "octocat/hello-world"},
        {"id": 2, "full_name": "octocat/dotfiles"},
    ]
    register_repos(1001, repos)

    result = get_registered_repos(installation_ids=[1001])
    names = {r["repo_full_name"] for r in result}
    assert names == {"octocat/hello-world", "octocat/dotfiles"}
    assert all(r["active"] == 1 for r in result)


def test_register_repos_idempotent(tmp_db):
    """Calling register_repos twice for the same repo should not duplicate it."""
    _seed_installation()
    repo = [{"id": 10, "full_name": "octocat/hello-world"}]
    register_repos(1001, repo)
    register_repos(1001, repo)  # second call

    result = get_registered_repos(installation_ids=[1001])
    assert len(result) == 1
    assert result[0]["active"] == 1


def test_register_repos_reactivates_removed(tmp_db):
    """A repo that was deregistered should come back as active when re-added."""
    _seed_installation()
    repos = [{"id": 5, "full_name": "octocat/repo-five"}]
    register_repos(1001, repos)
    deregister_repos(1001, repos)

    # Confirm it's inactive
    inactive = get_registered_repos(installation_ids=[1001], active_only=True)
    assert len(inactive) == 0

    # Re-add it
    register_repos(1001, repos)
    active = get_registered_repos(installation_ids=[1001], active_only=True)
    assert len(active) == 1
    assert active[0]["active"] == 1
    assert active[0]["removed_at"] is None


def test_deregister_repos_specific(tmp_db):
    _seed_installation()
    repos = [
        {"id": 1, "full_name": "octocat/a"},
        {"id": 2, "full_name": "octocat/b"},
    ]
    register_repos(1001, repos)
    deregister_repos(1001, [{"full_name": "octocat/a"}])

    active = {r["repo_full_name"] for r in get_registered_repos(installation_ids=[1001])}
    assert active == {"octocat/b"}


def test_deregister_repos_all_on_empty_list(tmp_db):
    """Empty list should deactivate ALL repos for the installation."""
    _seed_installation()
    register_repos(1001, [{"id": 1, "full_name": "octocat/a"}, {"id": 2, "full_name": "octocat/b"}])
    deregister_repos(1001, [])  # empty = all

    active = get_registered_repos(installation_ids=[1001], active_only=True)
    assert len(active) == 0


def test_remove_installation_deactivates_repos(tmp_db):
    """remove_installation() should also deactivate all repos."""
    _seed_installation()
    register_repos(1001, [{"id": 1, "full_name": "octocat/a"}])
    remove_installation(1001)

    # Installation row gone
    from core.db import get_all_installations
    insts = get_all_installations()
    assert all(i["installation_id"] != 1001 for i in insts)

    # Repo deactivated
    active = get_registered_repos(installation_ids=[1001], active_only=True)
    assert len(active) == 0


def test_get_registered_repos_no_filter(tmp_db):
    """get_registered_repos() with no filter returns all active repos."""
    upsert_installation(installation_id=1001, account_login="orgA")
    upsert_installation(installation_id=1002, account_login="orgB")
    register_repos(1001, [{"full_name": "orgA/repo1"}])
    register_repos(1002, [{"full_name": "orgB/repo2"}])

    all_repos = get_registered_repos()
    names = {r["repo_full_name"] for r in all_repos}
    assert names == {"orgA/repo1", "orgB/repo2"}


# ---------------------------------------------------------------------------
# Integration tests: webhook handler
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_db, monkeypatch):
    """Flask test client with signature verification disabled."""
    monkeypatch.setenv("SKIP_WEBHOOK_VERIFICATION", "true")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
    monkeypatch.setenv("WEBHOOK_SECRET", "")
    from webhook.server import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _post(client, payload: dict, event: str):
    body = json.dumps(payload).encode()
    delivery_id = f"rr-test-{uuid.uuid4().hex}"
    return client.post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": "sha256=skip",
            "X-GitHub-Delivery": delivery_id,
        },
    )


def test_installation_created_registers_repos(client, tmp_db):
    payload = {
        "action": "created",
        "installation": {
            "id": 2001,
            "account": {"login": "testorg", "type": "Organization"},
        },
        "repositories": [
            {"id": 10, "full_name": "testorg/app"},
            {"id": 11, "full_name": "testorg/infra"},
        ],
    }
    resp = _post(client, payload, "installation")
    assert resp.status_code == 200

    repos = get_registered_repos(installation_ids=[2001])
    names = {r["repo_full_name"] for r in repos}
    assert names == {"testorg/app", "testorg/infra"}


def test_installation_deleted_deactivates_repos(client, tmp_db):
    # Pre-seed
    upsert_installation(installation_id=3001, account_login="gone-user")
    register_repos(3001, [{"full_name": "gone-user/secret-project"}])

    payload = {
        "action": "deleted",
        "installation": {
            "id": 3001,
            "account": {"login": "gone-user", "type": "User"},
        },
    }
    resp = _post(client, payload, "installation")
    assert resp.status_code == 200

    active = get_registered_repos(installation_ids=[3001], active_only=True)
    assert len(active) == 0


def test_installation_repositories_added_and_removed(client, tmp_db):
    upsert_installation(installation_id=4001, account_login="myorg")
    register_repos(4001, [{"full_name": "myorg/existing"}, {"full_name": "myorg/to-remove"}])

    payload = {
        "action": "added",
        "installation": {
            "id": 4001,
            "account": {"login": "myorg", "type": "Organization"},
        },
        "repositories_added": [{"id": 99, "full_name": "myorg/new-repo"}],
        "repositories_removed": [{"id": 50, "full_name": "myorg/to-remove"}],
    }
    resp = _post(client, payload, "installation_repositories")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["added"] == 1
    assert data["removed"] == 1

    active = {r["repo_full_name"] for r in get_registered_repos(installation_ids=[4001])}
    assert "myorg/new-repo" in active
    assert "myorg/existing" in active
    assert "myorg/to-remove" not in active
