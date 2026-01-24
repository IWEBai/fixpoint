"""
Tests for core/fixer.py - the fixing engine.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.fixer import process_findings


class TestProcessFindings:
    """Tests for process_findings function."""
    
    def test_empty_findings_returns_no_changes(self, temp_repo):
        """Should return no changes for empty findings list."""
        rules_path = temp_repo / "rules.yaml"
        rules_path.write_text("rules: []")
        
        any_changes, processed = process_findings(temp_repo, [], rules_path)
        
        assert any_changes is False
        assert processed == []
    
    def test_processes_sql_injection_findings(self, temp_repo):
        """Should process SQL injection findings and apply fixes."""
        # Create vulnerable file
        app_file = temp_repo / "app.py"
        app_file.write_text('''import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()
''')
        
        rules_path = temp_repo / "rules.yaml"
        rules_path.write_text("rules: []")
        
        # Create a finding that looks like Semgrep output
        findings = [
            {
                "check_id": "custom.sql-injection-fstring",
                "path": str(app_file),
                "start": {"line": 6, "col": 5},
                "end": {"line": 6, "col": 60},
                "extra": {"message": "SQL injection vulnerability"},
            }
        ]
        
        any_changes, processed = process_findings(temp_repo, findings, rules_path)
        
        assert any_changes is True
        assert len(processed) == 1
        assert processed[0]["fixed"] is True
        
        # Verify the file was actually fixed
        fixed_content = app_file.read_text()
        assert 'f"SELECT' not in fixed_content
        assert "%s" in fixed_content
    
    def test_handles_relative_path(self, temp_repo):
        """Should handle relative file paths in findings."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import sqlite3

def get_user(email):
    cursor = None
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
''')
        
        rules_path = temp_repo / "rules.yaml"
        rules_path.write_text("rules: []")
        
        # Use relative path
        findings = [
            {
                "check_id": "sqli-fstring",
                "path": "app.py",  # Relative path
                "start": {"line": 5},
                "extra": {"message": "SQL injection"},
            }
        ]
        
        any_changes, processed = process_findings(temp_repo, findings, rules_path)
        
        assert len(processed) == 1
        assert processed[0]["file"] == "app.py"
    
    def test_non_sqli_finding_not_fixed(self, temp_repo):
        """Should not fix non-SQL injection findings."""
        app_file = temp_repo / "app.py"
        app_file.write_text('print("hello")')
        
        rules_path = temp_repo / "rules.yaml"
        rules_path.write_text("rules: []")
        
        findings = [
            {
                "check_id": "other-rule",  # Not SQL injection
                "path": str(app_file),
                "start": {"line": 1},
                "extra": {"message": "Some other issue"},
            }
        ]
        
        any_changes, processed = process_findings(temp_repo, findings, rules_path)
        
        assert any_changes is False
        assert len(processed) == 1
        assert processed[0]["fixed"] is False
    
    def test_multiple_findings(self, temp_repo):
        """Should process multiple findings."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import sqlite3

def get_user(email):
    cursor = None
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
''')
        
        other_file = temp_repo / "other.py"
        other_file.write_text('x = 1')
        
        rules_path = temp_repo / "rules.yaml"
        rules_path.write_text("rules: []")
        
        findings = [
            {
                "check_id": "sql-injection",
                "path": str(app_file),
                "start": {"line": 5},
                "extra": {"message": "SQL injection"},
            },
            {
                "check_id": "other-rule",
                "path": str(other_file),
                "start": {"line": 1},
                "extra": {"message": "Other issue"},
            },
        ]
        
        any_changes, processed = process_findings(temp_repo, findings, rules_path)
        
        assert len(processed) == 2
        # First should be fixed (SQL injection)
        assert processed[0]["fixed"] is True
        # Second should not be fixed (other rule)
        assert processed[1]["fixed"] is False
