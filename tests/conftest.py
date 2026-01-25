"""
Pytest fixtures for Fixpoint tests.
"""
import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_repo():
    """Create a temporary directory simulating a repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def vulnerable_python_file(temp_repo):
    """Create a Python file with SQL injection vulnerability."""
    app_file = temp_repo / "app.py"
    app_file.write_text('''
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()
''')
    return app_file


@pytest.fixture
def safe_python_file(temp_repo):
    """Create a Python file with safe parameterized query."""
    app_file = temp_repo / "app.py"
    app_file.write_text('''
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE email = %s"
    cursor.execute(query, (email,))
    return cursor.fetchone()
''')
    return app_file


@pytest.fixture
def mock_webhook_payload():
    """Sample GitHub webhook payload for PR event."""
    return {
        "action": "opened",
        "number": 1,
        "pull_request": {
            "number": 1,
            "head": {
                "ref": "feature-branch",
                "sha": "abc123",
                "repo": {
                    "full_name": "owner/repo",
                    "clone_url": "https://github.com/owner/repo.git",
                    "fork": False
                }
            },
            "base": {
                "ref": "main",
                "repo": {
                    "full_name": "owner/repo"
                }
            }
        },
        "repository": {
            "full_name": "owner/repo",
            "clone_url": "https://github.com/owner/repo.git"
        }
    }
