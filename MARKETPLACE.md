# AuditShield - GitHub Marketplace Listing

## Short Description (125 chars)
Auto-fix security vulnerabilities in PRs. Detects SQL injection, hardcoded secrets, XSS. Deterministic fixes, no AI.

## Full Description

### Turn Security Blockers into Instant Fixes

AuditShield automatically detects and fixes security vulnerabilities in your pull requests:

**What It Fixes:**
- **SQL Injection** - f-strings, concatenation, `.format()`, `%` formatting
- **Hardcoded Secrets** - Passwords, API keys, tokens, database credentials  
- **XSS (Cross-Site Scripting)** - `|safe` filter, `mark_safe()`, `autoescape off`

**How It Works:**
1. Scans PR diffs for security vulnerabilities
2. In **warn mode**: Posts comments with proposed fixes
3. In **enforce mode**: Automatically applies fixes and commits
4. Sets GitHub status checks (PASS/FAIL)

**Philosophy:**
- Deterministic fixes - same input, same output
- No AI hallucinations - rule-based transformations
- Verifiable and reproducible

### Quick Start

```yaml
- uses: zariffromlatif/auditshield@v1
  with:
    mode: warn  # or 'enforce' for auto-fix
```

### Example Fix

Before (vulnerable):
```python
query = f"SELECT * FROM users WHERE email = '{email}'"
```

After (auto-fixed):
```python
query = "SELECT * FROM users WHERE email = %s"
cursor.execute(query, (email,))
```

### Features

✅ SQL injection detection and auto-fix  
✅ Hardcoded secrets detection (AWS, GitHub, Slack, Stripe keys)  
✅ XSS detection in Django/Jinja2 templates  
✅ Warn mode (review first) and Enforce mode (auto-apply)  
✅ GitHub status checks for merge protection  
✅ `.auditshieldignore` file support  
✅ Fork PR safe (auto-downgrades to warn mode)  

### Requirements

- Python codebases
- GitHub Actions

### Links

- [Documentation](https://github.com/zariffromlatif/auditshield)
- [Getting Started Guide](https://github.com/zariffromlatif/auditshield/blob/main/docs/GETTING_STARTED.md)
- [Report Issues](https://github.com/zariffromlatif/auditshield/issues)

---

## Categories (for Marketplace)

- Security
- Code Quality
- Continuous Integration

## Tags

- security
- sql-injection
- xss
- secrets
- auto-fix
- compliance
- python
- code-scanning
