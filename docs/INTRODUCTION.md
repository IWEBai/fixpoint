# Why Railo?

**Stop waiting days for security reviews. Start shipping in minutes.**

Railo is a deterministic security patch bot that enforces compliance at merge time—so security findings become merged fixes, not backlog. As AI increases PR volume, Railo keeps security debt at zero.

**Positioning:** _The fixed point in your workflow where security issues are detected and corrected before merge—no AI, no wait, no backlog._

---

## 2026 Product Promise

We commit to:

- **Deterministic fixes only** — No AI/LLM for remediation. Same input → same output.
- **Python + JavaScript/TypeScript** — SQLi, secrets, XSS, command injection, path traversal, SSRF, eval, DOM XSS.
- **Safety rails** — Max-diff limits, optional test run before commit, CWE/OWASP tags in PR comments.
- **Warn then enforce** — Start with comments, graduate to auto-commit when you trust the tool.
- **Full audit trail** — Every fix is a Git commit. No black boxes.

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

Railo eliminates this bottleneck by **automatically fixing** security vulnerabilities the moment they're detected.

```
Developer opens PR
    ↓
Railo scans → finds issue → creates Fix PR
    ↓
Fix PR ready to merge (minutes later)
```

No manual intervention. No waiting. No context-switching.

---

## What Makes Railo Different

### 1. Deterministic Fixes (No AI Hallucinations)

Unlike AI-powered tools that "suggest" fixes, Railo applies **rule-based transformations**:

| Vulnerability     | Fix Applied                                      |
| ----------------- | ------------------------------------------------ |
| SQL Injection     | Converts to parameterized queries                |
| Hardcoded Secrets | Replaces with `os.environ.get()` / `process.env` |
| XSS in Templates  | Removes unsafe `\|safe` filters                  |
| XSS in Python     | Replaces `mark_safe()` with `escape()`           |
| Command Injection | Converts to list-based `subprocess`              |
| Path Traversal    | Adds path validation                             |
| JS/TS Secrets     | Replaces with `process.env.API_KEY`              |
| JS/TS DOM XSS     | Replaces `innerHTML` with `textContent`          |

**Same input → Same output. Every time.**

No LLM randomness. No "it worked last time but not this time." Just predictable, auditable fixes.

### Philosophy

- **Deterministic-first:** Same input → same output. No AI hallucinations.
- **No AI/LLM for fixes:** All fixes are rule-based and auditable.
- **Trust through transparency:** Start in warn mode, graduate to enforce when ready.
- **Safety over speed:** Max-diff limits, optional test run, CWE/OWASP tags in every finding.
- **Will not:** Auto-merge PRs, fix arbitrary bugs, refactor code, or generate creative fixes.

### 2. Trust-First Approach

Start in **warn mode** — Railo comments on PRs with proposed fixes but doesn't change anything:

```
⚡ Railo found 1 vulnerability

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
# .github/workflows/railo.yml
name: Railo
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write
  statuses: write

jobs:
  fixpoint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.head_ref }}
          fetch-depth: 0

      - uses: IWEBai/fixpoint@v1
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

SOC 2, HIPAA, PCI-DSS — Fixpoint ensures common vulnerabilities never make it to production.

### DevOps Teams

Reduce PR cycle time. Fewer security-related re-reviews means faster deployments.

---

## Real Impact

| Metric                      | Before Fixpoint | After Fixpoint |
| --------------------------- | --------------- | -------------- |
| Time to fix SQL injection   | 2-4 hours       | 0 minutes      |
| PR review cycles            | 3-5 rounds      | 1-2 rounds     |
| Developer context switches  | Multiple        | None           |
| Security team ticket volume | High            | Reduced 60%+   |

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
│     - SQL injection, secrets, XSS (Python)              │
│     - Command injection, path traversal, SSRF (Python)  │
│     - eval, secrets, DOM XSS (JavaScript/TypeScript)   │
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
│  3. FIX PR                                              │
│     Warn Mode: Comment with proposed fix                │
│     Enforce Mode: Create separate Fix PR → base branch  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  4. STATUS CHECK                                        │
│     fixpoint/compliance: PASS or FAIL                   │
│     Block merges until resolved                         │
└─────────────────────────────────────────────────────────┘
```

---

## Getting Started

### Step 1: Add the Workflow

Copy the YAML above into `.github/workflows/fixpoint.yml` in your repository.

### Step 2: Open a PR

Create a pull request with any code change. Fixpoint runs automatically.

### Step 3: Review Results

- **No vulnerabilities?** Status check passes. Merge away.
- **Vulnerabilities found?** Check the PR comment for proposed fixes.

### Step 4: Graduate to Enforce Mode

Once comfortable, change `mode: warn` to `mode: enforce` for automatic fixes.

---

## Frequently Asked Questions

### Will Railo break my code?

No. Railo only makes **safe, deterministic transformations**:

- SQL queries become parameterized (same functionality, secure)
- Secrets become environment variable lookups (same functionality, secure)
- XSS filters are removed (Django/Jinja2 auto-escapes by default)
- Command execution becomes list-based subprocess (same behavior, secure)
- Path traversal adds validation (rejects paths outside base directory)

### What if I don't want a fix applied?

Add the file to `.fixpointignore`:

```bash
# .fixpointignore
legacy/
tests/
migrations/
```

### Does it work with my language?

Currently supports **Python** (Django/Flask/Jinja2) and **JavaScript/TypeScript**.

Coming soon: Go, Java, Ruby.

### Is it free?

Yes. Fixpoint is open source under the MIT license.

### Can I self-host?

Yes. Run the webhook server on your infrastructure for full control:

```bash
docker build -t fixpoint .
docker run -p 8000:8000 fixpoint
```

---

## What's Next

We're actively developing:

- **More Languages**: Go, Java, Ruby
- **IDE Integration**: Fix vulnerabilities before you commit
- **Enterprise Features**: SSO, audit logs, custom rules (see Railo Cloud/Enterprise)

---

## Start Today

```yaml
uses: IWEBai/fixpoint@v1 # Railo GitHub Action
```

One line. Zero security debt.

---

## Questions?

- **Website:** [iwebai.space](https://www.iwebai.space)
- **Community:** [r/IWEBai on Reddit](https://www.reddit.com/r/IWEBai/)
- **Documentation:** [README.md](../README.md)
- **Issues:** [GitHub Issues](https://github.com/IWEBai/fixpoint/issues)
- **Discussions:** [GitHub Discussions](https://github.com/IWEBai/fixpoint/discussions)

---

_Railo by [IWEB](https://www.iwebai.space) — Because security shouldn't slow you down._
