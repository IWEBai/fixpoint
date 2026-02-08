"""
Tests for hardcoded secrets detection and fixing.
"""
from patcher.detect_secrets import find_hardcoded_secrets
from patcher.fix_secrets import apply_fix_secrets, propose_fix_secrets


class TestDetectSecrets:
    """Tests for secrets detection."""
    
    def test_detects_password_assignment(self, temp_repo):
        """Should detect hardcoded password in variable assignment."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
password = "super_secret_password_123"
''')
        
        text = app_file.read_text()
        secrets = find_hardcoded_secrets(text)
        
        assert len(secrets) >= 1
        assert secrets[0].var_name == "password"
        assert secrets[0].confidence in ("high", "medium")
    
    def test_detects_api_key_assignment(self, temp_repo):
        """Should detect hardcoded API key."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
api_key = "sk_test_fake_key_for_unit_testing_only_1234"
''')
        
        text = app_file.read_text()
        secrets = find_hardcoded_secrets(text)
        
        assert len(secrets) >= 1
        assert "api_key" in secrets[0].var_name.lower()
    
    def test_detects_secret_in_dict(self, temp_repo):
        """Should detect hardcoded secret in dictionary."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
config = {
    "password": "database_password_12345",
    "host": "localhost"
}
''')
        
        text = app_file.read_text()
        secrets = find_hardcoded_secrets(text)
        
        assert len(secrets) >= 1
    
    def test_detects_secret_in_function_call(self, temp_repo):
        """Should detect hardcoded secret in function argument."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
db.connect(host="localhost", password="my_db_password_123")
''')
        
        text = app_file.read_text()
        secrets = find_hardcoded_secrets(text)
        
        assert len(secrets) >= 1
    
    def test_detects_aws_access_key(self, temp_repo):
        """Should detect AWS access key pattern."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
''')
        
        text = app_file.read_text()
        secrets = find_hardcoded_secrets(text)
        
        assert len(secrets) >= 1
        assert secrets[0].confidence == "high"
    
    def test_ignores_placeholder_values(self, temp_repo):
        """Should ignore placeholder values."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
password = "your_password_here"
api_key = "<YOUR_API_KEY>"
secret = "changeme"
token = "xxx"
''')
        
        text = app_file.read_text()
        secrets = find_hardcoded_secrets(text)
        
        # Should not detect placeholders
        assert len(secrets) == 0
    
    def test_ignores_short_values(self, temp_repo):
        """Should ignore very short values."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
password = "test"
secret = "12345"
''')
        
        text = app_file.read_text()
        secrets = find_hardcoded_secrets(text)
        
        assert len(secrets) == 0


class TestFixSecrets:
    """Tests for secrets fixing."""
    
    def test_fixes_hardcoded_password(self, temp_repo):
        """Should replace hardcoded password with os.environ.get()."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import sqlite3

db_password = "my_secret_password_123"
db = sqlite3.connect("test.db")
''')
        
        result = apply_fix_secrets(temp_repo, "app.py")
        
        assert result is True
        fixed = app_file.read_text()
        assert "os.environ.get" in fixed
        assert '"my_secret_password_123"' not in fixed
        # os import should be present (either added or already there)
        assert "import os" in fixed or "from os" in fixed
    
    def test_preserves_existing_os_import(self, temp_repo):
        """Should not duplicate os import."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import os
import sqlite3

db_password = "my_secret_password_123"
''')
        
        result = apply_fix_secrets(temp_repo, "app.py")
        
        assert result is True
        fixed = app_file.read_text()
        # Should only have one import os
        assert fixed.count("import os") == 1
    
    def test_returns_false_for_safe_code(self, temp_repo):
        """Should return False for code with no secrets."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import os

password = os.environ.get("PASSWORD")
''')
        
        result = apply_fix_secrets(temp_repo, "app.py")
        
        assert result is False


class TestProposeSecretsFix:
    """Tests for secrets fix proposals."""
    
    def test_proposes_fix_for_secret(self, temp_repo):
        """Should propose fix for hardcoded secret."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
api_key = "sk_test_fake_key_for_unit_testing_only_1234"
''')
        
        proposal = propose_fix_secrets(temp_repo, "app.py")
        
        assert proposal is not None
        assert "API_KEY" in proposal["suggested_env_var"]
        assert proposal["confidence"] in ("high", "medium")
    
    def test_returns_none_for_safe_code(self, temp_repo):
        """Should return None for code with no secrets."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import os

password = os.environ.get("PASSWORD")
''')
        
        proposal = propose_fix_secrets(temp_repo, "app.py")
        
        # No secrets to fix
        assert proposal is None
