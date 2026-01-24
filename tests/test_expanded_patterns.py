"""
Tests for expanded SQL injection pattern detection.
Tests multiple variable names, cursor names, and injection patterns.
"""
import pytest
from pathlib import Path
from patcher.ast_utils import find_all_sqli_patterns, SQL_VARIABLE_NAMES, CURSOR_NAMES
from patcher.fix_sqli import apply_fix_sqli, propose_fix_sqli


class TestMultipleVariableNames:
    """Tests for different SQL variable names."""
    
    @pytest.mark.parametrize("var_name", ["query", "sql", "stmt", "command", "sql_query"])
    def test_detects_various_variable_names(self, temp_repo, var_name):
        """Should detect SQL injection with different variable names."""
        app_file = temp_repo / "app.py"
        app_file.write_text(f'''
import sqlite3

def get_user(email):
    cursor = None
    {var_name} = f"SELECT * FROM users WHERE email = '{{email}}'"
    cursor.execute({var_name})
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert patterns[0].var_name == var_name
        assert "email" in patterns[0].variables


class TestMultipleCursorNames:
    """Tests for different cursor/db object names."""
    
    @pytest.mark.parametrize("cursor_name", ["cursor", "cur", "db", "conn", "c"])
    def test_detects_various_cursor_names(self, temp_repo, cursor_name):
        """Should detect SQL injection with different cursor names."""
        app_file = temp_repo / "app.py"
        app_file.write_text(f'''
import sqlite3

def get_user(email):
    {cursor_name} = None
    query = f"SELECT * FROM users WHERE email = '{{email}}'"
    {cursor_name}.execute(query)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert patterns[0].exec_obj_name == cursor_name


class TestConcatenationPatterns:
    """Tests for string concatenation SQL injection."""
    
    def test_detects_simple_concatenation(self, temp_repo):
        """Should detect simple string concatenation."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user(user_id):
    cursor = None
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert patterns[0].pattern_type == "concatenation"
        assert "user_id" in patterns[0].variables
    
    def test_detects_concatenation_with_quotes(self, temp_repo):
        """Should detect concatenation with quotes around value."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user(email):
    cursor = None
    query = "SELECT * FROM users WHERE email = '" + email + "'"
    cursor.execute(query)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert patterns[0].pattern_type == "concatenation"
    
    def test_fixes_concatenation(self, temp_repo):
        """Should fix concatenation patterns."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import sqlite3

def get_user(user_id):
    cursor = None
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
''')
        
        result = apply_fix_sqli(temp_repo, "app.py")
        
        assert result is True
        fixed = app_file.read_text()
        assert "%s" in fixed
        assert "execute(query, " in fixed


class TestFormatPatterns:
    """Tests for .format() SQL injection."""
    
    def test_detects_format_with_positional(self, temp_repo):
        """Should detect .format() with positional args."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user(email):
    cursor = None
    query = "SELECT * FROM users WHERE email = '{}'".format(email)
    cursor.execute(query)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert patterns[0].pattern_type == "format"
    
    def test_detects_format_with_index(self, temp_repo):
        """Should detect .format() with indexed args."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user(email, status):
    cursor = None
    query = "SELECT * FROM users WHERE email = '{0}' AND status = '{1}'".format(email, status)
    cursor.execute(query)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert patterns[0].pattern_type == "format"
    
    def test_fixes_format_pattern(self, temp_repo):
        """Should fix .format() patterns."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import sqlite3

def get_user(email):
    cursor = None
    query = "SELECT * FROM users WHERE email = '{}'".format(email)
    cursor.execute(query)
''')
        
        result = apply_fix_sqli(temp_repo, "app.py")
        
        assert result is True
        fixed = app_file.read_text()
        assert "%s" in fixed
        assert ".format" not in fixed


class TestPercentPatterns:
    """Tests for % formatting SQL injection."""
    
    def test_detects_percent_formatting(self, temp_repo):
        """Should detect % string formatting."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user(email):
    cursor = None
    query = "SELECT * FROM users WHERE email = '%s'" % email
    cursor.execute(query)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert patterns[0].pattern_type == "percent"
    
    def test_detects_percent_with_tuple(self, temp_repo):
        """Should detect % with tuple of values."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user(email, status):
    cursor = None
    query = "SELECT * FROM users WHERE email = '%s' AND status = '%s'" % (email, status)
    cursor.execute(query)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert patterns[0].pattern_type == "percent"


class TestMixedPatterns:
    """Tests for files with multiple patterns."""
    
    def test_detects_multiple_patterns_in_file(self, temp_repo):
        """Should detect multiple different patterns in same file."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user_by_email(email):
    cursor = None
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)

def get_user_by_id(user_id):
    cursor = None
    sql = "SELECT * FROM users WHERE id = " + str(user_id)
    cursor.execute(sql)

def get_user_by_name(name):
    cursor = None
    stmt = "SELECT * FROM users WHERE name = '{}'".format(name)
    cursor.execute(stmt)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        # Should find at least 3 patterns
        assert len(patterns) >= 3
        
        # Check variety of patterns
        pattern_types = {p.pattern_type for p in patterns}
        assert "fstring" in pattern_types
        assert "concatenation" in pattern_types
        assert "format" in pattern_types


class TestEdgeCases:
    """Tests for edge cases and false positives."""
    
    def test_ignores_already_parameterized(self, temp_repo):
        """Should not detect already parameterized queries."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user(email):
    cursor = None
    query = "SELECT * FROM users WHERE email = %s"
    cursor.execute(query, (email,))
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        # Should not find any patterns (already safe)
        assert len(patterns) == 0
    
    def test_ignores_non_sql_fstrings(self, temp_repo):
        """Should not detect f-strings that don't look like SQL."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
def greet(name):
    message = f"Hello, {name}!"
    print(message)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) == 0
    
    def test_handles_attribute_access(self, temp_repo):
        """Should handle attribute access like user.email."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''
import sqlite3

def get_user(user):
    cursor = None
    query = f"SELECT * FROM users WHERE email = '{user.email}'"
    cursor.execute(query)
''')
        
        text = app_file.read_text()
        patterns = find_all_sqli_patterns(text)
        
        assert len(patterns) >= 1
        assert "user.email" in patterns[0].variables


class TestProposeFix:
    """Tests for fix proposals (warn mode)."""
    
    def test_proposes_fix_for_fstring(self, temp_repo):
        """Should propose fix for f-string pattern."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import sqlite3

def get_user(email):
    cursor = None
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
''')
        
        proposal = propose_fix_sqli(temp_repo, "app.py")
        
        assert proposal is not None
        assert proposal["pattern_type"] == "fstring"
        assert "%s" in proposal["after"]
        assert "email" in proposal["variables"]
    
    def test_proposes_fix_for_concatenation(self, temp_repo):
        """Should propose fix for concatenation pattern."""
        app_file = temp_repo / "app.py"
        app_file.write_text('''import sqlite3

def get_user(user_id):
    cursor = None
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
''')
        
        proposal = propose_fix_sqli(temp_repo, "app.py")
        
        assert proposal is not None
        assert proposal["pattern_type"] == "concatenation"
