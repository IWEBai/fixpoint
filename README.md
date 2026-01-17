# AuditShield (Compliance Auto-Patcher) — MVP

AuditShield is a compliance-focused auto-remediation bot that **detects a small set of high-confidence security violations**, applies **deterministic fixes**, and opens **human-reviewable Pull Requests**.

It is intentionally restrictive:

- No auto-merge
- No "AI guesses"
- Minimal diffs
- Full audit trail via Git + PR

AuditShield is built for teams preparing for **SOC2 / ISO 27001 / enterprise security audits**, where the problem is not finding issues — it's fixing them correctly and fast.

---

## Why this exists

Most AppSec tools (Snyk / CodeQL / Semgrep) are great at **finding** issues, but they stop at alerts.  
Developers then spend hours fixing repetitive compliance-driven problems right before audits.

AuditShield's goal is simple:

> Don't just flag compliance blockers. **Ship the fix as a PR.**

---

## Example (what AuditShield actually does)

### Before (non-compliant)

```python
query = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(query)
```

### Problem

- SQL injection risk
- Violates SOC2 / OWASP secure coding requirements

### After (auto-generated PR)

```python
query = "SELECT * FROM users WHERE email = %s"
cursor.execute(query, (email,))
```

AuditShield:

- Detects the violation
- Applies a deterministic fix
- Creates a branch, commit, and Pull Request
- Leaves final approval to a human

## What it does (MVP scope)

The current MVP is a single vertical slice, intentionally narrow:

- Language: Python
- Detection: Semgrep rule
- Violation: SQL injection via string formatting
- Fix: Parameterized queries
- Output: Git branch + commit + Pull Request

## What it does NOT do

AuditShield is not a general auto-fix engine:

- It does not fix arbitrary bugs
- It does not refactor code
- It does not auto-merge Pull Requests
- It does not generate creative or probabilistic fixes

Only deterministic, audit-safe changes are allowed.

## Demo (one command)

### Requirements

- Python 3.12+
- semgrep installed
- Git
- A GitHub Personal Access Token (repo scope)

### 1) Configure environment

Create a .env file in the project root:

```env
GITHUB_TOKEN=PASTE_YOUR_TOKEN_HERE
GITHUB_OWNER=your_github_username
GITHUB_REPO=your_repo_name
```

### 2) Run AuditShield

```bash
python main.py /path/to/target-repo
```

If a supported violation is found, AuditShield will:

- Apply a safe fix
- Commit the change
- Push a branch
- Open (or reuse) a Pull Request

## Intended users

- B2B SaaS startups (Seed → Series C)
- Teams preparing for SOC2 / ISO 27001 audits
- CTOs / DevOps leads tired of last-minute compliance fire drills

## Status

This is an early MVP built to validate:

- Trust model
- Developer acceptance
- CI/CD workflow integration

Coverage will expand only where fixes remain deterministic and compliance-safe.

## Vision

AuditShield becomes the compliance engineer in your CI/CD pipeline — silently fixing what must be fixed, and leaving the rest to humans.
