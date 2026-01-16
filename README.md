# AuditShield (Compliance Auto-Patcher) — MVP

AuditShield is a compliance-focused auto-remediation bot that **detects a small set of high-confidence security violations**, applies **deterministic fixes**, and opens **human-reviewable Pull Requests**.

It is intentionally restrictive:

- No auto-merge
- No “AI guesses”
- Minimal diffs
- Full audit trail via Git + PR

## Why this exists

Most AppSec tools (Snyk/CodeQL/Semgrep) are great at **finding** issues, but they stop at alerts.
Developers then spend hours fixing repetitive compliance-driven problems right before audits.

AuditShield’s goal is simple:

> Don’t just flag compliance blockers. **Ship the fix as a PR.**

## What it does (MVP scope)

Current MVP is a single vertical slice:

- Language: **Python**
- Detection: **Semgrep rule**
- Fix: **SQL injection via string formatting → parameterized query**
- Output: **Branch + commit + PR** on GitHub

## What it does NOT do

- It does not fix “general bugs”
- It does not refactor code
- It does not auto-merge PRs
- It does not attempt creative code generation

## Demo (one command)

You need:

- Python 3.12+ (Windows OK)
- `semgrep` installed
- A GitHub PAT in `.env` with `repo` scope

### 1) Configure environment

Create `.env` in the project root:

```env
GITHUB_TOKEN=ghp_your_token_here
GITHUB_OWNER=your_github_username
GITHUB_REPO=autopatcher-demo-python
```
