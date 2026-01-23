# Demo Repository Setup Guide

This guide helps you set up `autopatcher-demo-python` as a sample repository for users to try AuditShield.

## Repository Requirements

The demo repo should have:

1. ✅ **PR with violation** — Shows warn mode comment + status check
2. ✅ **PR with clean code** — Shows PASS status
3. ✅ **Workflow installed** — `.github/workflows/auditshield.yml` configured

## Setup Steps

### 1. Create Demo Repository

```bash
# Create new repo: autopatcher-demo-python
gh repo create autopatcher-demo-python --public --clone
cd autopatcher-demo-python
```

### 2. Add Sample Code with Violation

Create `app.py` with SQL injection vulnerability:

```python
# app.py
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # SQL injection vulnerability
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    
    return cursor.fetchone()
```

### 3. Add Clean Code Example

Create `app_clean.py`:

```python
# app_clean.py
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # Safe parameterized query
    query = "SELECT * FROM users WHERE email = ?"
    cursor.execute(query, (email,))
    
    return cursor.fetchone()
```

### 4. Install AuditShield Workflow

Create `.github/workflows/auditshield.yml`:

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
          mode: warn  # Start in warn mode
          base_branch: ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Replace `zariffromlatif/auditshield@v0.1.0` with your actual repository path.**

### 5. Configure Required Check (Make it a Gate)

1. Go to **Settings → Branches → Branch protection rules**
2. Enable **"Require status checks to pass before merging"**
3. Select: `auditshield/compliance`
4. Save

Now AuditShield will actually block merges until violations are fixed.

### 6. Create PRs

**PR #1: Violation (should FAIL in warn mode)**

```bash
# Create branch
git checkout -b feature/add-user-lookup

# Add vulnerable code
echo 'import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE email = '\''{email}'\''"
    cursor.execute(query)
    return cursor.fetchone()' > app.py

git add app.py
git commit -m "Add user lookup function"
git push origin feature/add-user-lookup

# Create PR
gh pr create --title "Add user lookup" --body "Adds user lookup function"
```

**PR #2: Clean Code (should PASS)**

```bash
# Create branch
git checkout -b feature/add-safe-user-lookup

# Add safe code
echo 'import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE email = ?"
    cursor.execute(query, (email,))
    return cursor.fetchone()' > app.py

git add app.py
git commit -m "Add safe user lookup function"
git push origin feature/add-safe-user-lookup

# Create PR
gh pr create --title "Add safe user lookup" --body "Adds safe user lookup function"
```

### 7. Verify Demo Works

1. **PR #1 (Violation):**
   - ✅ AuditShield posts comment with proposed fix
   - ✅ Status check shows **FAIL** with context `auditshield/compliance`
   - ✅ Comment shows before/after diff
   - ✅ Merge is **blocked** (if required check configured)

2. **PR #2 (Clean):**
   - ✅ Status check shows **PASS**
   - ✅ No comments (no violations)
   - ✅ Merge allowed

### 8. Add README to Demo Repo

Create `README.md`:

```markdown
# AuditShield Demo Repository

This repository demonstrates AuditShield in action.

## What You'll See

- **PR with violation** → Warn mode comment + FAIL status check
- **PR with clean code** → PASS status check

## Try It Yourself

1. Fork this repository
2. Create a PR with SQL injection vulnerability
3. Watch AuditShield propose a fix (warn mode)
4. Switch to enforce mode to auto-apply fixes

## Learn More

- [AuditShield Documentation](https://github.com/your-org/auditshield)
- [Installation Guide](https://github.com/your-org/auditshield#install)
```

## Testing Checklist

- [ ] PR with violation shows warn mode comment
- [ ] PR with violation shows FAIL status check
- [ ] PR with clean code shows PASS status check
- [ ] Workflow runs successfully
- [ ] Comments are clear and actionable
- [ ] Status checks appear in PR checks section

## Notes

- Keep demo repo public for easy access
- Update demo repo link in main AuditShield README
- Add screenshots/GIFs if possible (powerful for adoption)
