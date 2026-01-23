# AuditShield — Compliance Auto-Patcher

**Turn security compliance blockers into instant pull requests.**

AuditShield automatically fixes compliance-blocking security issues in your PRs, reducing time-to-merge from days to minutes.

---

## What It Is

AuditShield is a **deterministic compliance gate** that:
- Scans PR diffs for security violations (SQL injection, etc.)
- Proposes fixes in **warn mode** (comments only)
- Applies fixes in **enforce mode** (auto-commits)
- Sets GitHub status checks (PASS/FAIL gates)

**Philosophy:** Deterministic-first. Same input → same output. No AI hallucinations.

---

## Install

Add this to `.github/workflows/auditshield.yml`:

```yaml
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

      - name: AuditShield (warn-first)
        uses: zariffromlatif/auditshield@v0.1.0
        with:
          mode: warn  # change to "enforce" to auto-apply fixes (non-forks only)
          base_branch: ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Notes:**
- **Fork PRs automatically run in warn mode** (no write access to forks)
- **To enforce**, set `mode: enforce` (applies fixes automatically for non-fork PRs)

---

## Warn → Enforce

**Start in warn mode** (default) to build trust:

```yaml
- uses: zariffromlatif/auditshield@v0.1.0
  with:
    mode: warn  # Comments only, no commits
```

**Graduate to enforce mode** once you trust the fixes:

```yaml
- uses: zariffromlatif/auditshield@v0.1.0
  with:
    mode: enforce  # Auto-applies fixes
```

**Warn mode:**
- Posts PR comments with proposed fixes
- Sets status check to FAIL
- No commits made

**Enforce mode:**
- Applies fixes automatically
- Commits to PR branch
- Sets status check to PASS

---

## .auditshieldignore

Exclude files/directories from scanning (similar to `.gitignore`):

```bash
# .auditshieldignore
tests/
test_*.py
legacy/
migrations/
third_party/
```

Create `.auditshieldignore` in your repo root.

---

## Demo

**Try it now:** [autopatcher-demo-python](https://github.com/zariffromlatif/autopatcher-demo-python)

The demo repo includes:
- ✅ **PR #1 with violation** — Shows warn mode comment + FAIL status check
- ✅ **PR #2 with clean code** — Shows PASS status
- ✅ Workflow installed and working
- ✅ Required check configured (blocks merges)

**What you'll see:**
1. Open PR #1 with SQL injection violation
2. AuditShield posts comment with proposed fix
3. Status check shows **FAIL** (merge blocked)
4. Switch to enforce mode → fix auto-applied
5. Status check shows **PASS** (merge allowed)

---

## How It Works

1. **Detect** — Scans PR diff for violations (SQL injection, etc.)
2. **Propose** — Posts comment with deterministic fix (warn mode)
3. **Apply** — Commits fix to PR branch (enforce mode)
4. **Gate** — Sets status check (PASS/FAIL)

**Result:** Reduced time-to-merge for compliance-blocking findings.

---

## Status Checks

AuditShield sets GitHub status checks:

- **PASS** — No violations found
- **FAIL** — Violations found (warn mode) or fixes failed
- **PASS** — Violations found and fixed (enforce mode)

### Configure as Required Check (Block Merges)

To make AuditShield a true gate that blocks merges:

1. Go to **Settings → Branches → Branch protection rules**
2. Enable **"Require status checks to pass before merging"**
3. Select: `auditshield/compliance` (your status context)
4. Save

Now merges are blocked until compliance violations are fixed.

---

## Example Fix

**Before (non-compliant):**
```python
query = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(query)
```

**After (auto-fixed):**
```python
query = "SELECT * FROM users WHERE email = %s"
cursor.execute(query, (email,))
```

---

## Philosophy

**Deterministic-first:**
- Same input → same output
- Rule-based fixes (no AI hallucinations)
- Verifiable and reproducible
- Bounded fix space

**Trust through progression:**
- Start in warn mode (review fixes)
- Graduate to enforce mode (auto-apply)
- Time-to-merge is the metric

---

## Requirements

- Python 3.12+
- GitHub repository
- GitHub Actions (or webhook server)

---

## CLI Usage

```bash
# Warn mode (propose fixes, don't apply)
python main.py /path/to/repo --warn-mode

# Enforce mode (apply fixes)
python main.py /path/to/repo

# PR diff mode
python main.py /path/to/repo --pr-mode --base-ref main --head-ref feature-branch
```

---

## Webhook Server

For self-hosted deployments:

```bash
# Install dependencies
pip install -r requirements.txt

# Configure .env
WEBHOOK_SECRET=your_secret_here
AUDITSHIELD_MODE=warn

# Start server
python webhook_server.py
```

Configure GitHub webhook:
- URL: `https://your-domain.com/webhook`
- Events: `pull_request` (opened, synchronize)
- Secret: Your `WEBHOOK_SECRET`

---

## What AuditShield Does NOT Do

- ❌ Fix arbitrary bugs
- ❌ Refactor code
- ❌ Auto-merge PRs
- ❌ Generate creative fixes

Only deterministic, compliance-safe changes.

---

## Roadmap

- **v0.1.0** (current) — Warn mode, status checks, AST-based fixer
- **v0.2.0** — Multi-language support (JavaScript, TypeScript)
- **v0.3.0** — More violation types (PII logging, secrets)

See [ROADMAP.md](./ROADMAP.md) for details.

---

## License

[Your License Here]

---

## Support

- Issues: [GitHub Issues](https://github.com/zariffromlatif/auditshield/issues)
- Docs: [Full Documentation](./IMPLEMENTATION_LOG.md)
