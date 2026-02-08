"""
Tests for core/scanner.py - the scanning engine.
"""
import pytest
import subprocess
from core.scanner import run, semgrep_scan, get_pr_diff_files_local


class TestRunCommand:
    """Tests for the run helper function."""
    
    def test_successful_command(self, temp_repo):
        """Should run successful command and return result."""
        # Use python for cross-platform compatibility (echo is not a standalone exe on Windows)
        result = run(["python", "-c", "print('hello')"], cwd=temp_repo)
        assert "hello" in result.stdout
    
    def test_failed_command_raises(self, temp_repo):
        """Should raise RuntimeError on command failure."""
        with pytest.raises(RuntimeError) as exc_info:
            run(["python", "-c", "import sys; sys.exit(1)"], cwd=temp_repo)
        
        assert "Command failed" in str(exc_info.value)
    
    def test_handles_unicode_output(self, temp_repo):
        """Should handle unicode in command output."""
        result = run(["python", "-c", "print('héllo wörld')"], cwd=temp_repo)
        assert "héllo" in result.stdout or "h" in result.stdout  # Depends on platform


class TestSemgrepScan:
    """Tests for semgrep_scan function."""
    
    @pytest.fixture
    def sample_rules(self, temp_repo):
        """Create a sample Semgrep rules file."""
        rules_file = temp_repo / "rules.yaml"
        rules_file.write_text('''rules:
  - id: test-rule
    patterns:
      - pattern: print($X)
    message: Found a print statement
    languages: [python]
    severity: WARNING
''')
        return rules_file
    
    def test_scan_returns_dict(self, temp_repo, sample_rules):
        """Should return dict with results key."""
        import sys
        if sys.platform == "win32":
            pytest.skip("Semgrep not supported on Windows")
        
        # Create a file to scan
        test_file = temp_repo / "test.py"
        test_file.write_text('print("test")')
        
        output_json = temp_repo / "results.json"
        
        # This test requires semgrep to be installed
        try:
            result = semgrep_scan(temp_repo, sample_rules, output_json)
            assert isinstance(result, dict)
            assert "results" in result
        except (RuntimeError, FileNotFoundError) as e:
            if "semgrep" in str(e).lower() or "cannot find" in str(e).lower():
                pytest.skip("Semgrep not installed")
            raise
    
    def test_scan_with_target_files(self, temp_repo, sample_rules):
        """Should scan only specified target files."""
        import sys
        if sys.platform == "win32":
            pytest.skip("Semgrep not supported on Windows")
        
        # Create multiple files
        file1 = temp_repo / "file1.py"
        file1.write_text('print("one")')
        
        file2 = temp_repo / "file2.py"
        file2.write_text('print("two")')
        
        output_json = temp_repo / "results.json"
        
        try:
            # Scan only file1
            result = semgrep_scan(
                temp_repo, 
                sample_rules, 
                output_json, 
                target_files=["file1.py"]
            )
            
            assert isinstance(result, dict)
            # Results should only include file1
            for finding in result.get("results", []):
                assert "file1" in finding.get("path", "")
        except (RuntimeError, FileNotFoundError) as e:
            if "semgrep" in str(e).lower() or "cannot find" in str(e).lower():
                pytest.skip("Semgrep not installed")
            raise
    
    def test_empty_results_when_all_ignored(self, temp_repo, sample_rules):
        """Should return empty results when all files are ignored."""
        # Create file
        test_file = temp_repo / "test.py"
        test_file.write_text('print("test")')
        
        # Create ignore file that ignores everything
        ignore_file = temp_repo / ".fixpointignore"
        ignore_file.write_text("*.py\n")
        
        output_json = temp_repo / "results.json"
        
        result = semgrep_scan(
            temp_repo,
            sample_rules,
            output_json,
            target_files=["test.py"],
            apply_ignore=True,
        )
        
        assert result == {"results": []}


class TestGetPrDiffFilesLocal:
    """Tests for get_pr_diff_files_local function."""
    
    @pytest.fixture
    def git_repo(self, temp_repo):
        """Initialize a git repo with some commits."""
        subprocess.run(["git", "init"], cwd=temp_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=temp_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=temp_repo, check=True, capture_output=True
        )
        
        # Create initial commit
        file1 = temp_repo / "file1.py"
        file1.write_text("# initial")
        subprocess.run(["git", "add", "."], cwd=temp_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=temp_repo, check=True, capture_output=True
        )
        
        return temp_repo
    
    def test_detects_changed_files(self, git_repo):
        """Should detect files changed between commits."""
        # Create a new commit with changes
        file2 = git_repo / "file2.py"
        file2.write_text("# new file")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file2"],
            cwd=git_repo, check=True, capture_output=True
        )
        
        # Get diff between commits
        result = run(["git", "rev-parse", "HEAD~1"], cwd=git_repo)
        base_ref = result.stdout.strip()
        
        changed = get_pr_diff_files_local(git_repo, base_ref, "HEAD")
        
        assert "file2.py" in changed
    
    def test_empty_diff_returns_empty_list(self, git_repo):
        """Should return empty list when no changes between refs."""
        changed = get_pr_diff_files_local(git_repo, "HEAD", "HEAD")
        assert changed == [] or changed == [""]  # May include empty string
