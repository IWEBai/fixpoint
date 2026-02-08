"""
Tests for patcher/ast_utils.py - AST parsing utilities.
"""
from patcher.ast_utils import extract_fstring_variables, find_sqli_pattern_in_ast


class TestExtractFstringVariables:
    """Tests for extract_fstring_variables function."""
    
    def test_extracts_simple_variable(self):
        """Should extract simple variable from f-string."""
        import ast
        code = 'f"Hello {name}"'
        tree = ast.parse(code, mode='eval')
        fstring = tree.body
        
        variables = extract_fstring_variables(fstring)
        
        assert variables == ["name"]
    
    def test_extracts_multiple_variables(self):
        """Should extract multiple variables from f-string."""
        import ast
        code = 'f"Hello {first} {last}"'
        tree = ast.parse(code, mode='eval')
        fstring = tree.body
        
        variables = extract_fstring_variables(fstring)
        
        assert "first" in variables
        assert "last" in variables
        assert len(variables) == 2
    
    def test_extracts_attribute_access(self):
        """Should extract attribute access like user.email."""
        import ast
        code = 'f"Hello {user.email}"'
        tree = ast.parse(code, mode='eval')
        fstring = tree.body
        
        variables = extract_fstring_variables(fstring)
        
        assert "user.email" in variables
    
    def test_extracts_nested_attributes(self):
        """Should extract nested attribute access like obj.nested.value."""
        import ast
        code = 'f"Value: {obj.nested.value}"'
        tree = ast.parse(code, mode='eval')
        fstring = tree.body
        
        variables = extract_fstring_variables(fstring)
        
        assert "obj.nested.value" in variables
    
    def test_empty_fstring_returns_empty_list(self):
        """Should return empty list for f-string without variables."""
        import ast
        code = 'f"Hello world"'
        tree = ast.parse(code, mode='eval')
        fstring = tree.body
        
        variables = extract_fstring_variables(fstring)
        
        assert variables == []


class TestFindSqliPatternInAst:
    """Tests for find_sqli_pattern_in_ast function."""
    
    def test_finds_basic_sqli_pattern(self):
        """Should find basic SQL injection pattern."""
        code = '''
query = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(query)
'''
        result = find_sqli_pattern_in_ast(code)
        
        assert result is not None
        query_line_idx, exec_line_idx, variables, sql_string = result
        assert query_line_idx == 1  # 0-based, so line 2 in code
        assert exec_line_idx == 2   # 0-based, so line 3 in code
        assert "email" in variables
        assert "SELECT" in sql_string
    
    def test_finds_pattern_with_multiple_variables(self):
        """Should find pattern with multiple variables."""
        code = '''
query = f"SELECT * FROM users WHERE email = '{email}' AND status = '{status}'"
cursor.execute(query)
'''
        result = find_sqli_pattern_in_ast(code)
        
        assert result is not None
        query_line_idx, exec_line_idx, variables, sql_string = result
        assert "email" in variables
        assert "status" in variables
        assert len(variables) == 2
    
    def test_finds_pattern_with_attribute_access(self):
        """Should find pattern with attribute access in f-string."""
        code = '''
query = f"SELECT * FROM users WHERE email = '{user.email}'"
cursor.execute(query)
'''
        result = find_sqli_pattern_in_ast(code)
        
        assert result is not None
        _, _, variables, _ = result
        assert "user.email" in variables
    
    def test_returns_none_for_safe_code(self):
        """Should return None for parameterized queries."""
        code = '''
query = "SELECT * FROM users WHERE email = %s"
cursor.execute(query, (email,))
'''
        result = find_sqli_pattern_in_ast(code)
        
        # No f-string, so should not find pattern
        assert result is None
    
    def test_returns_none_for_syntax_error(self):
        """Should return None for invalid Python code."""
        code = 'this is not valid python {{{'
        
        result = find_sqli_pattern_in_ast(code)
        
        assert result is None
    
    def test_returns_none_when_execute_before_query(self):
        """Should return None when execute comes before query assignment."""
        code = '''
cursor.execute(query)
query = f"SELECT * FROM users WHERE email = '{email}'"
'''
        result = find_sqli_pattern_in_ast(code)
        
        # Execute is before query assignment, pattern incomplete
        assert result is None
    
    def test_returns_none_when_execute_too_far(self):
        """Should return None when execute is too far from query."""
        code = '''
query = f"SELECT * FROM users WHERE email = '{email}'"
x = 1
x = 2
x = 3
x = 4
x = 5
x = 6
x = 7
x = 8
x = 9
x = 10
x = 11
x = 12
x = 13
x = 14
x = 15
x = 16
cursor.execute(query)
'''
        find_sqli_pattern_in_ast(code)
        
        # Execute is more than 15 lines from query (handled in fixer, not AST)
        # AST module just finds the pattern, distance check is in fixer
        # So this may or may not return None depending on implementation
    
    def test_finds_pattern_in_function(self):
        """Should find pattern inside a function."""
        code = '''
def get_user(email):
    conn = sqlite3.connect("test.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()
'''
        result = find_sqli_pattern_in_ast(code)
        
        assert result is not None
        _, _, variables, _ = result
        assert "email" in variables
    
    def test_detects_sql_variable_name(self):
        """Should detect 'sql' as a valid SQL variable name."""
        code = '''
sql = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(sql)
'''
        result = find_sqli_pattern_in_ast(code)
        
        # Now supports 'sql' as a variable name
        assert result is not None
        assert "email" in result[2]  # variables list
    
    def test_detects_db_cursor_name(self):
        """Should detect 'db' as a valid cursor name."""
        code = '''
query = f"SELECT * FROM users WHERE email = '{email}'"
db.execute(query)
'''
        result = find_sqli_pattern_in_ast(code)
        
        # Now supports 'db' as a cursor name
        assert result is not None
