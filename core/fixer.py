"""
Core fixing engine for Fixpoint.
Processes Semgrep findings and applies deterministic fixes.

Supported vulnerability types:
- SQL Injection (Python)
- Hardcoded Secrets (Python)
- XSS (Jinja2/Django templates and Python)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any

from core.formatter import format_file


# Mapping of vulnerability patterns to fixers
# Key patterns in check_id -> fixer function name
FIXER_REGISTRY = {
    # SQL Injection patterns
    "sql-injection": "fix_sqli",
    "sqli": "fix_sqli",
    "sql_injection": "fix_sqli",
    
    # Hardcoded secrets patterns
    "hardcoded-password": "fix_secrets",
    "hardcoded-secret": "fix_secrets",
    "hardcoded_password": "fix_secrets",
    "hardcoded_secret": "fix_secrets",
    "aws-access-key": "fix_secrets",
    "github-token": "fix_secrets",
    "slack-token": "fix_secrets",
    "stripe-key": "fix_secrets",
    "private-key": "fix_secrets",
    "database-uri": "fix_secrets",
    "secret-dict": "fix_secrets",
    "secret-kwarg": "fix_secrets",
    
    # XSS patterns
    "xss": "fix_xss",
    "mark-safe": "fix_xss",
    "mark_safe": "fix_xss",
    "safe-filter": "fix_xss",
    "safe_filter": "fix_xss",
    "autoescape-off": "fix_xss",
    "autoescape_off": "fix_xss",
    "safestring": "fix_xss",
    "markup": "fix_xss",
    "format-html": "fix_xss",
    "format_html": "fix_xss",

    # Command injection patterns
    "command-injection": "fix_command_injection",
    "command_injection": "fix_command_injection",
    "os-system": "fix_command_injection",
    "subprocess-shell": "fix_command_injection",

    # Path traversal patterns
    "path-traversal": "fix_path_traversal",
    "path_traversal": "fix_path_traversal",

    # SSRF patterns
    "ssrf": "fix_ssrf",
    "requests-get": "fix_ssrf",
    "requests-post": "fix_ssrf",
    "urlopen": "fix_ssrf",

    # JavaScript/TypeScript patterns
    "javascript-eval": "fix_js_eval",
    "typescript-eval": "fix_js_eval",
    "eval-dangerous": "fix_js_eval",
    "javascript-hardcoded-secret": "fix_js_secrets",
    "typescript-hardcoded-secret": "fix_js_secrets",
    "javascript-dom-xss": "fix_js_dom_xss",
    "typescript-dom-xss": "fix_js_dom_xss",
    "dom-xss-innerhtml": "fix_js_dom_xss",
    "dom-xss-document-write": "fix_js_dom_xss",
}

# Friendly rule-key aliases used in config (e.g. "secrets" matches many IDs).
_RULE_KEY_ALIASES: Dict[str, list[str]] = {
    "sqli": ["sql-injection", "sqli"],
    "secrets": [
        "secret",
        "token",
        "password",
        "access-key",
        "private-key",
        "database-uri",
        "github-token",
        "slack-token",
        "stripe-key",
        "sendgrid-key",
    ],
    "xss": ["xss"],
    "command-injection": ["command-injection", "os-system", "subprocess-shell"],
    "path-traversal": ["path-traversal"],
    "ssrf": ["ssrf"],
    "eval": ["eval-dangerous", "javascript-eval", "typescript-eval", "eval"],
    "dom-xss": ["dom-xss", "innerhtml", "document-write"],
}


_SEVERITY_ORDER: Dict[str, int] = {
    "INFO": 1,
    "WARNING": 2,
    "WARN": 2,
    "ERROR": 3,
}


def _normalise_severity(value: Optional[str]) -> str:
    return str(value or "").upper()


def _severity_at_least(severity: str, threshold: str) -> bool:
    sev = _SEVERITY_ORDER.get(_normalise_severity(severity), 1)
    thr = _SEVERITY_ORDER.get(_normalise_severity(threshold), 1)
    return sev >= thr


def _match_rule_key(check_id_lower: str, candidates) -> Optional[str]:
    """
    Best-effort mapping from a concrete Semgrep check_id to a logical
    rule key used in configuration (e.g. "sql-injection", "hardcoded-secret").

    We intentionally use substring matching so that rules like
    "custom.sql-injection-fstring" still map to "sql-injection".
    """
    if isinstance(candidates, dict):
        keys = list(candidates.keys())
    else:
        keys = list(candidates)

    best: Optional[str] = None
    best_len = -1
    for key in keys:
        key_l = str(key).lower().strip()
        if not key_l:
            continue
        matched = False
        if key_l in check_id_lower:
            matched = True
            match_len = len(key_l)
        else:
            aliases = _RULE_KEY_ALIASES.get(key_l, [])
            match_len = -1
            for alias in aliases:
                if alias and alias in check_id_lower:
                    matched = True
                    match_len = max(match_len, len(alias))
        if matched:
            if match_len < 0:
                match_len = len(key_l)
            if best is None or match_len > best_len:
                best = key
                best_len = match_len
    return best


def _get_directory_policy(config: Dict[str, Any], relpath: str) -> Optional[Dict[str, Any]]:
    """
    Find the most specific directory policy for a given relative file path
    using longest-prefix match.
    """
    policies = config.get("directory_policies") or {}
    if not isinstance(policies, dict) or not policies:
        return None

    rel = str(relpath).replace("\\", "/")
    # directory component with trailing slash
    dir_part = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""

    best_key: Optional[str] = None
    for key in policies.keys():
        k = str(key)
        if not k.endswith("/"):
            k = k + "/"
        if dir_part.startswith(k) or rel.startswith(k):
            if best_key is None or len(k) > len(best_key):
                best_key = k

    if best_key is None:
        return None
    return policies.get(best_key) or None


def _should_auto_fix(
    finding: Dict[str, Any],
    relpath: str,
    config: Optional[Dict[str, Any]],
) -> bool:
    """
    Decide whether this finding should be auto-fixed given global rules
    configuration and per-directory policies.
    """
    if not config:
        # Backwards compatible: no config means "fix everything we know how to".
        return True

    rules_cfg = config.get("rules") or {}
    enabled_rules = rules_cfg.get("enabled") or []
    global_enforce = rules_cfg.get("enforce_per_rule") or {}
    global_severity_threshold = rules_cfg.get("severity_threshold", "ERROR")

    check_id = str(finding.get("check_id", "") or "")
    check_id_lower = check_id.lower()

    # Determine applicable directory policy (if any)
    dir_policy = _get_directory_policy(config, relpath)
    dir_enforce = (dir_policy or {}).get("enforce_per_rule") or {}
    dir_severity_threshold = (dir_policy or {}).get("severity_threshold", global_severity_threshold)

    # Map concrete check_id to a logical rule key used in config
    rule_key: Optional[str] = None

    # First try directory-specific enforce_per_rule
    if dir_enforce:
        rule_key = _match_rule_key(check_id_lower, dir_enforce)

    # Then global enforce_per_rule
    if rule_key is None and global_enforce:
        rule_key = _match_rule_key(check_id_lower, global_enforce)

    # If still unknown, try the enabled list (serves as an allowlist)
    if rule_key is None and enabled_rules:
        rule_key = _match_rule_key(check_id_lower, enabled_rules)

    # If an enabled allowlist is configured and we couldn't match this rule
    # to any enabled entry, treat it as "do not auto-fix".
    if enabled_rules and rule_key is None:
        return False

    # Determine enforcement mode for this logical rule key
    mode = "enforce"
    if rule_key is not None:
        key_str = str(rule_key)
        if key_str in global_enforce:
            mode = str(global_enforce[key_str]).lower()
        if key_str in dir_enforce:
            mode = str(dir_enforce[key_str]).lower()

    if mode != "enforce":
        # Explicitly configured as warn-only at this scope.
        return False

    # Severity gating: only auto-fix findings at or above the effective
    # severity threshold for this directory.
    severity = (finding.get("extra", {}) or {}).get("severity", "INFO")
    if not _severity_at_least(str(severity), str(dir_severity_threshold)):
        return False

    return True


def _get_fixer_for_finding(check_id: str) -> Optional[str]:
    """
    Determine which fixer to use based on the check_id.
    
    Args:
        check_id: The Semgrep rule check_id
    
    Returns:
        Fixer name or None if no fixer matches
    """
    check_id_lower = check_id.lower()
    
    for pattern, fixer in FIXER_REGISTRY.items():
        if pattern in check_id_lower:
            return fixer
    
    return None


def _propose_fixer(
    fixer_name: str,
    repo_path: Path,
    target_relpath: str,
    finding: Optional[dict] = None,
) -> Optional[dict]:
    """
    Propose a fix based on fixer name (warn mode).
    
    Args:
        fixer_name: Name of the fixer to use
        repo_path: Path to repository root
        target_relpath: Relative path to the target file
        finding: Optional Semgrep finding (for line number when proposal has line 0)
    
    Returns:
        Proposal dict with fix details or None
    """
    try:
        if fixer_name == "fix_sqli":
            from patcher.fix_sqli import propose_fix_sqli
            return propose_fix_sqli(repo_path, target_relpath)
        
        elif fixer_name == "fix_secrets":
            from patcher.fix_secrets import propose_fix_secrets
            return propose_fix_secrets(repo_path, target_relpath)
        
        elif fixer_name == "fix_xss":
            from patcher.fix_xss import propose_fix_xss
            return propose_fix_xss(repo_path, target_relpath)
        
        elif fixer_name == "fix_command_injection":
            from patcher.fix_command_injection import propose_fix_command_injection
            result = propose_fix_command_injection(repo_path, target_relpath)
            return result[0] if result else None
        
        elif fixer_name == "fix_path_traversal":
            from patcher.fix_path_traversal import propose_fix_path_traversal
            result = propose_fix_path_traversal(repo_path, target_relpath)
            return result[0] if result else None
        
        elif fixer_name == "fix_ssrf":
            from patcher.fix_ssrf import propose_fix_ssrf
            result = propose_fix_ssrf(repo_path, target_relpath)
            return result[0] if result else None
        
        elif fixer_name == "fix_js_eval":
            from patcher.fix_javascript import propose_fix_js_eval
            result = propose_fix_js_eval(repo_path, target_relpath)
            return result[0] if result else None
        
        elif fixer_name == "fix_js_secrets":
            from patcher.fix_javascript import propose_fix_js_secrets
            result = propose_fix_js_secrets(repo_path, target_relpath)
            return result[0] if result else None
        
        elif fixer_name == "fix_js_dom_xss":
            from patcher.fix_javascript import propose_fix_js_dom_xss
            result = propose_fix_js_dom_xss(repo_path, target_relpath)
            return result[0] if result else None
        
        else:
            return None
    
    except Exception as e:
        print(f"Error proposing {fixer_name}: {e}")
        return None


def _apply_fixer(fixer_name: str, repo_path: Path, target_relpath: str) -> bool:
    """
    Apply the appropriate fixer based on fixer name.
    
    Args:
        fixer_name: Name of the fixer to use
        repo_path: Path to repository root
        target_relpath: Relative path to the target file
    
    Returns:
        True if a fix was applied, False otherwise
    """
    try:
        if fixer_name == "fix_sqli":
            from patcher.fix_sqli import apply_fix_sqli
            return apply_fix_sqli(repo_path, target_relpath)
        
        elif fixer_name == "fix_secrets":
            from patcher.fix_secrets import apply_fix_secrets
            return apply_fix_secrets(repo_path, target_relpath)
        
        elif fixer_name == "fix_xss":
            from patcher.fix_xss import apply_fix_xss
            return apply_fix_xss(repo_path, target_relpath)
        
        elif fixer_name == "fix_command_injection":
            from patcher.fix_command_injection import apply_fix_command_injection
            return apply_fix_command_injection(repo_path, target_relpath)
        
        elif fixer_name == "fix_path_traversal":
            from patcher.fix_path_traversal import apply_fix_path_traversal
            return apply_fix_path_traversal(repo_path, target_relpath)
        
        elif fixer_name == "fix_ssrf":
            from patcher.fix_ssrf import apply_fix_ssrf
            return apply_fix_ssrf(repo_path, target_relpath)
        
        elif fixer_name == "fix_js_eval":
            from patcher.fix_javascript import apply_fix_js_eval
            return apply_fix_js_eval(repo_path, target_relpath)
        
        elif fixer_name == "fix_js_secrets":
            from patcher.fix_javascript import apply_fix_js_secrets
            return apply_fix_js_secrets(repo_path, target_relpath)
        
        elif fixer_name == "fix_js_dom_xss":
            from patcher.fix_javascript import apply_fix_js_dom_xss
            return apply_fix_js_dom_xss(repo_path, target_relpath)
        
        else:
            print(f"Unknown fixer: {fixer_name}")
            return False
    
    except Exception as e:
        print(f"Error applying {fixer_name}: {e}")
        return False


def process_findings(
    repo_path: Path,
    findings: list[dict],
    rules_path: Path,
    config: Optional[Dict[str, Any]] = None,
    decision_report=None,
) -> tuple[bool, list[dict]]:
    """
    Process Semgrep findings and apply fixes.
    
    Uses parallel processing for independent files (4-8 workers) to speed up fix application.
    
    Args:
        repo_path: Path to repository root
        findings: List of Semgrep finding dicts
        rules_path: Path to rules file (for determining fix type)
    
    Returns:
        Tuple of (any_changes_made, list of processed findings with fix info)
    """
    if not findings:
        return False, []
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    
    # Group findings by file for parallel processing, preserving original order
    findings_by_file: dict[str, list[dict]] = {}
    finding_to_file_map: list[tuple[dict, str]] = []  # Preserve original order
    
    for finding in findings:
        check_id = finding.get("check_id", "")
        file_path = finding.get("path")
        
        # Convert absolute path to relative path from repo root
        file_path_obj = Path(file_path)
        if file_path_obj.is_absolute():
            try:
                target_relpath = str(file_path_obj.relative_to(repo_path))
            except ValueError:
                target_relpath = file_path_obj.name
        else:
            target_relpath = str(file_path)
        
        if target_relpath not in findings_by_file:
            findings_by_file[target_relpath] = []
        findings_by_file[target_relpath].append(finding)
        finding_to_file_map.append((finding, target_relpath))
    
    # Thread-safe data structures for parallel processing
    any_changes_value = threading.Event()  # Use Event for simpler thread-safe boolean
    fixed_files_lock = threading.Lock()
    fixed_files: dict[str, set[str]] = {}  # fixer_name -> set of file paths
    touched_files_lock = threading.Lock()
    touched_files: set[str] = set()
    processed: list[dict] = []
    
    def _process_file_findings(relpath: str, file_findings: list[dict]) -> list[dict]:
        """Process all findings for a single file (thread-safe)."""
        file_processed: list[dict] = []
        
        for finding in file_findings:
            check_id = finding.get("check_id", "")
            fixer_name = _get_fixer_for_finding(check_id)
            
            changed = False
            if fixer_name and _should_auto_fix(finding, relpath, config):
                # Thread-safe check and update of fixed_files
                with fixed_files_lock:
                    if fixer_name not in fixed_files:
                        fixed_files[fixer_name] = set()
                    
                    if relpath not in fixed_files[fixer_name]:
                        # Apply fix (file I/O is generally safe for different files)
                        changed = _apply_fixer(fixer_name, repo_path, relpath)
                        if changed:
                            any_changes_value.set()  # Thread-safe set
                            fixed_files[fixer_name].add(relpath)
                            with touched_files_lock:
                                touched_files.add(relpath)
            
            file_processed.append({
                "finding": finding,
                "file": relpath,
                "check_id": check_id,
                "fixer": fixer_name,
                "fixed": changed,
            })
        
        return file_processed
    
    # Determine number of workers (4-8, based on number of files)
    num_files = len(findings_by_file)
    max_workers = min(max(4, num_files), 8) if num_files > 1 else 1
    
    # Process files in parallel, then reconstruct original order
    file_results: dict[str, list[dict]] = {}
    
    if num_files > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_process_file_findings, relpath, file_findings): relpath
                for relpath, file_findings in findings_by_file.items()
            }
            
            for future in as_completed(futures):
                try:
                    file_processed = future.result()
                    relpath = futures[future]
                    file_results[relpath] = file_processed
                except Exception as e:
                    relpath = futures[future]
                    print(f"Error processing file {relpath}: {e}")
                    # Still add findings for this file (marked as not fixed)
                    file_results[relpath] = []
                    for finding in findings_by_file[relpath]:
                        check_id = finding.get("check_id", "")
                        fixer_name = _get_fixer_for_finding(check_id)
                        file_results[relpath].append({
                            "finding": finding,
                            "file": relpath,
                            "check_id": check_id,
                            "fixer": fixer_name,
                            "fixed": False,
                        })
    else:
        # Single file - no need for parallelization
        for relpath, file_findings in findings_by_file.items():
            file_results[relpath] = _process_file_findings(relpath, file_findings)
    
    # Reconstruct processed list in original order
    for finding, relpath in finding_to_file_map:
        # Find the matching processed result for this finding
        for result in file_results.get(relpath, []):
            if result["finding"] == finding:
                processed.append(result)
                break
        else:
            # Fallback: create entry if not found
            check_id = finding.get("check_id", "")
            fixer_name = _get_fixer_for_finding(check_id)
            processed.append({
                "finding": finding,
                "file": relpath,
                "check_id": check_id,
                "fixer": fixer_name,
                "fixed": False,
            })
    
    # Check if any changes were made
    any_changes = any_changes_value.is_set()
    # Optional post-fix formatting for touched files
    if config and config.get("format_after_patch", True) and touched_files:
        import subprocess

        def _numstat_total_for_file(repo: Path, rel: str) -> int:
            """
            Return added+removed for the working-tree diff for a single file.
            Uses git numstat; returns 0 if unknown/unavailable.
            """
            rel_norm = str(rel).replace("\\", "/")
            try:
                result = subprocess.run(
                    ["git", "diff", "--numstat", "--", rel_norm],
                    cwd=repo,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                line = (result.stdout or "").strip().splitlines()
                if not line:
                    return 0
                parts = line[0].split("\t")
                if len(parts) < 2:
                    return 0
                a, r = parts[0], parts[1]
                added = int(a) if a.isdigit() else 0
                removed = int(r) if r.isdigit() else 0
                return added + removed
            except Exception:
                return 0

        max_expansion = float(config.get("max_format_expansion", 0.2) or 0.2)
        if max_expansion < 0:
            max_expansion = 0.0

        for relpath in sorted(touched_files):
            file_abs = repo_path / relpath
            if not file_abs.exists():
                continue

            baseline_total = _numstat_total_for_file(repo_path, relpath)
            try:
                before_text = file_abs.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            try:
                success, _fmt_added, _fmt_removed = format_file(repo_path, relpath, None)
                if not success:
                    continue
            except Exception as e:
                print(f"Warning: formatter failed for {relpath}: {e}")
                continue

            post_total = _numstat_total_for_file(repo_path, relpath)

            # Guardrail: if formatting expands the total diff for this file
            # beyond (1 + max_expansion) of the pre-formatting diff, revert
            # formatting for this file (keeping the security patch).
            if baseline_total > 0 and post_total > int(
                baseline_total * (1.0 + max_expansion) + 0.5
            ):
                try:
                    file_abs.write_text(before_text, encoding="utf-8")
                    print(
                        f"Warning: formatting reverted for {relpath} "
                        f"(diff expanded from {baseline_total} to {post_total} lines; "
                        f"max_format_expansion={max_expansion})"
                    )
                    if decision_report is not None:
                        from core.trust_contract import DecisionReport  # type: ignore

                        # Only record if this is actually a DecisionReport instance.
                        if isinstance(decision_report, DecisionReport):
                            decision_report.mark_formatting_expansion(
                                relpath=str(relpath),
                                baseline_total=baseline_total,
                                post_total=post_total,
                                max_expansion=max_expansion,
                            )
                except OSError:
                    # If we can't revert safely, leave as-is and rely on
                    # higher-level max_diff_lines safety rail.
                    print(
                        f"Warning: formatting expanded diff for {relpath} "
                        f"(from {baseline_total} to {post_total}); revert failed"
                    )

    return any_changes, processed


def get_supported_vulnerability_types() -> list[str]:
    """
    Get list of supported vulnerability types.
    
    Returns:
        List of vulnerability type descriptions
    """
    return [
        "SQL Injection (Python f-strings, concatenation, .format(), % formatting)",
        "Hardcoded Secrets (passwords, API keys, tokens, database credentials)",
        "XSS (Django/Jinja2 |safe filter, mark_safe(), autoescape off)",
        "Command Injection (os.system, subprocess with shell=True)",
        "Path Traversal (os.path.join with user input)",
        "SSRF (requests.get/post, urlopen with dynamic URL) — detection + guidance",
    ]


def get_fixer_info() -> dict:
    """
    Get information about available fixers.
    
    Returns:
        Dict with fixer information
    """
    return {
        "fix_sqli": {
            "name": "SQL Injection Fixer",
            "description": "Converts unsafe SQL queries to parameterized queries",
            "patterns": ["sql-injection", "sqli"],
            "languages": ["python"],
        },
        "fix_secrets": {
            "name": "Hardcoded Secrets Fixer",
            "description": "Replaces hardcoded secrets with os.environ.get()",
            "patterns": ["hardcoded-password", "hardcoded-secret", "aws-access-key", "github-token"],
            "languages": ["python"],
        },
        "fix_xss": {
            "name": "XSS Fixer",
            "description": "Removes unsafe |safe filters and mark_safe() calls",
            "patterns": ["xss", "mark-safe", "safe-filter", "autoescape-off"],
            "languages": ["python", "html/jinja2"],
        },
        "fix_command_injection": {
            "name": "Command Injection Fixer",
            "description": "Converts os.system and subprocess+shell=True to safe subprocess",
            "patterns": ["command-injection", "os-system", "subprocess-shell"],
            "languages": ["python"],
        },
        "fix_path_traversal": {
            "name": "Path Traversal Fixer",
            "description": "Adds path validation for os.path.join with user input",
            "patterns": ["path-traversal"],
            "languages": ["python"],
        },
        "fix_ssrf": {
            "name": "SSRF Fixer",
            "description": "Detection + guidance for requests.get/post, urlopen",
            "patterns": ["ssrf", "requests-get", "requests-post", "urlopen"],
            "languages": ["python"],
        },
        "fix_js_eval": {
            "name": "JavaScript eval Fixer",
            "description": "Detection only - recommends JSON.parse or safe alternative",
            "patterns": ["javascript-eval", "typescript-eval", "eval-dangerous"],
            "languages": ["javascript", "typescript"],
        },
        "fix_js_secrets": {
            "name": "JavaScript Secrets Fixer",
            "description": "Replaces hardcoded secrets with process.env",
            "patterns": ["javascript-hardcoded-secret", "typescript-hardcoded-secret"],
            "languages": ["javascript", "typescript"],
        },
        "fix_js_dom_xss": {
            "name": "JavaScript DOM XSS Fixer",
            "description": "Replaces innerHTML with textContent",
            "patterns": ["javascript-dom-xss", "typescript-dom-xss", "dom-xss-innerhtml", "dom-xss-document-write"],
            "languages": ["javascript", "typescript"],
        },
    }
