# Why AuditShield?

**Stop waiting days for security reviews. Start shipping in minutes.**

---

## The Problem

Every engineering team faces the same bottleneck:

```
Developer opens PR
    ↓
Security scan finds vulnerabilities
    ↓
PR blocked for days
    ↓
Developer context-switches to fix
    ↓
Re-review, re-test, repeat
    ↓
Finally merged (3-5 days later)
```

**The result?**
- Developers frustrated by slow merges
- Security teams overwhelmed with repetitive issues
- Release cycles delayed by compliance blockers
- Same vulnerabilities found over and over again

---

## The Solution

AuditShield eliminates this bottleneck by **automatically fixing** security vulnerabilities the moment they're detected.

```
Developer opens PR
    ↓
AuditShield scans → finds issue → fixes it
    ↓
PR ready to merge (minutes later)
```

No manual intervention. No waiting. No context-switching.

---

## What Makes AuditShield Different

### 1. Deterministic Fixes (No AI Hallucinations)

Unlike AI-powered tools that "suggest" fixes, AuditShield applies **rule-based transformations**:

| Vulnerability | Fix Applied |
|---------------|-------------|
| SQL Injection | Converts to parameterized queries |
| Hardcoded Secrets | Replaces with `os.environ.get()` |
| XSS in Templates | Removes unsafe `\|safe` filters |
| XSS in Python | Replaces `mark_safe()` with `escape()` |

**Same input → Same output. Every time.**

No LLM randomness. No "it worked last time but not this time." Just predictable, auditable fixes.

### 2. Trust-First Approach

Start in **warn mode** — AuditShield comments on PRs with proposed fixes but doesn't change anything:

```
🛡️ AuditShield found 1 vulnerability

📍 app.py line 15 - SQL Injection

Before:
query = f"SELECT * FROM users WHERE email = '{email}'"

After (proposed fix):
query = "SELECT * FROM users WHERE email = %s"
cursor.execute(query, (email,))
```

Your team reviews the fixes, builds confidence, then graduates to **enforce mode** for full automation.

### 3. Zero Configuration

Add one file. That's it.

```yaml
# .github/workflows/auditshield.yml
name: AuditShield
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  statuses: write

jobs:
  auditshield:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.head_ref }}
          fetch-depth: 0

      - uses: zariffromlatif/auditshield@v1
        with:
          mode: warn
          base_branch: ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

No agents to install. No dashboards to configure. No seats to purchase.

---

## Who Is This For?

### Startups Moving Fast
Ship secure code without slowing down. Focus on features, not security fixes.

### Teams Without Security Engineers
Get enterprise-grade security automation without hiring specialists.

### Organizations With Compliance Requirements
SOC 2, HIPAA, PCI-DSS — AuditShield ensures common vulnerabilities never make it to production.

### DevOps Teams
Reduce PR cycle time. Fewer security-related re-reviews means faster deployments.

---

## Real Impact

| Metric | Before AuditShield | After AuditShield |
|--------|-------------------|-------------------|
| Time to fix SQL injection | 2-4 hours | 0 minutes |
| PR review cycles | 3-5 rounds | 1-2 rounds |
| Developer context switches | Multiple | None |
| Security team ticket volume | High | Reduced 60%+ |

---

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                     Your PR                             │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  1. SCAN                                                │
│     Semgrep + Custom AST Analysis                       │
│     - SQL Injection patterns                            │
│     - Hardcoded secrets                                 │
│     - XSS vulnerabilities                               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  2. FIX                                                 │
│     Deterministic Transformations                       │
│     - Parse code with AST                               │
│     - Apply rule-based fix                              │
│     - Preserve code style                               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  3. REPORT                                              │
│     Warn Mode: Comment with proposed fix                │
│     Enforce Mode: Commit fix to PR branch               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  4. STATUS CHECK                                        │
│     auditshield/compliance: PASS or FAIL                │
│     Block merges until resolved                         │
└─────────────────────────────────────────────────────────┘
```

---

## Getting Started

### Step 1: Add the Workflow

Copy the YAML above into `.github/workflows/auditshield.yml` in your repository.

### Step 2: Open a PR

Create a pull request with any code change. AuditShield runs automatically.

### Step 3: Review Results

- **No vulnerabilities?** Status check passes. Merge away.
- **Vulnerabilities found?** Check the PR comment for proposed fixes.

### Step 4: Graduate to Enforce Mode

Once comfortable, change `mode: warn` to `mode: enforce` for automatic fixes.

---

## Frequently Asked Questions

### Will AuditShield break my code?

No. AuditShield only makes **safe, deterministic transformations**:
- SQL queries become parameterized (same functionality, secure)
- Secrets become environment variable lookups (same functionality, secure)
- XSS filters are removed (Django/Jinja2 auto-escapes by default)

### What if I don't want a fix applied?

Add the file to `.auditshieldignore`:

```bash
# .auditshieldignore
legacy/
tests/
migrations/
```

### Does it work with my language?

Currently supports **Python** with Django/Flask/Jinja2 templates.

Coming soon: JavaScript/TypeScript, Go, Java, Ruby.

### Is it free?

Yes. AuditShield is open source under the MIT license.

### Can I self-host?

Yes. Run the webhook server on your infrastructure for full control:

```bash
docker build -t auditshield .
docker run -p 8000:8000 auditshield
```

---

## What's Next

We're actively developing:

- **More Languages**: JavaScript, TypeScript, Go, Java
- **More Vulnerability Types**: SSRF, Path Traversal, Command Injection
- **IDE Integration**: Fix vulnerabilities before you commit
- **Enterprise Features**: SSO, audit logs, custom rules

---

## Start Today

```yaml
uses: zariffromlatif/auditshield@v1
```

One line. Zero security debt.

---

## Questions?

- **Documentation**: [README.md](../README.md)
- **Issues**: [GitHub Issues](https://github.com/zariffromlatif/auditshield/issues)
- **Discussions**: [GitHub Discussions](https://github.com/zariffromlatif/auditshield/discussions)

---

*AuditShield — Because security shouldn't slow you down.*
