# How to Use Railo — A Step-by-Step Guide

**For complete beginners. No prior knowledge required.**

---

## Table of Contents

1. [What Is Railo?](#1-what-is-railo)
2. [How Does It Work?](#2-how-does-it-work)
3. [Choose Your Setup Method](#3-choose-your-setup-method)
4. [Method A: Install the GitHub App (Easiest)](#4-method-a-install-the-github-app-easiest)
5. [Method B: Add as a GitHub Action](#5-method-b-add-as-a-github-action)
6. [Method C: Run from the Command Line](#6-method-c-run-from-the-command-line)
7. [Understanding Warn vs Enforce Mode](#7-understanding-warn-vs-enforce-mode)
8. [What Happens When You Open a Pull Request](#8-what-happens-when-you-open-a-pull-request)
9. [Reading the Results](#9-reading-the-results)
10. [Try It Yourself — Demo Walkthrough](#10-try-it-yourself--demo-walkthrough)
11. [What Vulnerabilities Does Railo Fix?](#11-what-vulnerabilities-does-railo-fix)
12. [Example Fixes](#12-example-fixes)
13. [Configuring Railo](#13-configuring-railo)
14. [Frequently Asked Questions](#14-frequently-asked-questions)
15. [Troubleshooting](#15-troubleshooting)
16. [Getting Help](#16-getting-help)

---

## 1. What Is Railo?

**Railo** is a tool that automatically finds and fixes security vulnerabilities in your code — right inside your GitHub pull requests.

Think of it as a security reviewer that:
- Reads through the code you changed in a pull request
- Spots common security mistakes (like SQL injection, hardcoded passwords, cross-site scripting)
- Either **warns you** about the problems or **fixes them automatically**

**Key points:**
- It is **free** during the beta period
- It works with **Python** and **JavaScript/TypeScript** code
- It does **not** use AI — all fixes are rule-based and predictable
- Same problem → same fix, every time

---

## 2. How Does It Work?

Here's the basic flow:

```
You open (or update) a Pull Request on GitHub
        ↓
Railo automatically scans the changed files
        ↓
If vulnerabilities are found:
  • Warn mode  → Railo posts a comment showing what's wrong and how to fix it
  • Enforce mode → Railo commits the fix directly to your PR branch
        ↓
A status check ("fixpoint/compliance") appears on your PR:
  • ✅ PASS = No issues (or all issues were auto-fixed)
  • ❌ FAIL = Issues found that need your attention
```

**You don't need to do anything manually** — Railo runs every time you push code to a pull request.

---

## 3. Choose Your Setup Method

There are three ways to use Railo. Pick the one that fits your situation:

| Method | Best For | Difficulty | Time to Set Up |
|--------|----------|------------|----------------|
| **A. GitHub App** | Teams, organizations, multiple repos | Easiest | ~1 minute |
| **B. GitHub Action** | Individual repos, CI/CD pipelines | Easy | ~5 minutes |
| **C. Command Line** | Local testing, one-off scans | Moderate | ~10 minutes |

> **Recommendation:** If you just want to try Railo, go with **Method A** (GitHub App). It's one click and works immediately.

---

## 4. Method A: Install the GitHub App (Easiest)

This is the fastest way to get started. No code changes needed.

### Step 1: Open the Install Link

Go to: **[https://github.com/apps/railo-cloud/installations/new](https://github.com/apps/railo-cloud/installations/new)**

### Step 2: Choose Where to Install

You'll see a screen asking where to install the app:

- **Your personal account** — Railo will be available for your personal repositories
- **Your organization** — Railo will be available for organization repositories

Click on the account or organization you want.

### Step 3: Select Repositories

Choose which repositories Railo should scan:

- **All repositories** — Railo will scan every repo in the account
- **Only select repositories** — Pick specific repos from a list

> **Tip:** Start with one or two repos to see how it works before enabling it everywhere.

### Step 4: Click "Install"

That's it! Railo is now installed.

### Step 5: Verify It's Working

1. Go to one of the repos you selected
2. Open a pull request (or push a new commit to an existing one)
3. Wait about 30–60 seconds
4. Look for:
   - A **check run** called `fixpoint/compliance` in the PR's "Checks" tab
   - A **comment** from Railo (if vulnerabilities were found)

### What Permissions Does It Need?

| Permission | Why |
|------------|-----|
| **Contents** (read & write) | To read your code and push fixes |
| **Pull requests** (read & write) | To post fix comments on PRs |
| **Statuses** (read & write) | To show pass/fail check results |

---

## 5. Method B: Add as a GitHub Action

Use this if you prefer to manage Railo through your CI/CD workflow files.

### Step 1: Create the Workflow File

In your repository, create the file `.github/workflows/fixpoint.yml`:

```yaml
name: Fixpoint

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

      - name: Fixpoint
        uses: IWEBai/fixpoint@v1
        with:
          mode: warn    # or "enforce" for auto-fix
          base_branch: ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Step 2: Commit and Push

```bash
git add .github/workflows/fixpoint.yml
git commit -m "Add Fixpoint security scanner"
git push
```

### Step 3: Open a Pull Request

Create a PR against your main branch. The Fixpoint workflow will run automatically.

### Step 4: Check the Results

1. Go to the **Actions** tab in your repository
2. You should see a "Fixpoint" workflow running
3. When it completes, check the PR for comments and status checks

---

## 6. Method C: Run from the Command Line

Use this for local testing or one-off scans on your machine.

### Prerequisites

- **Python 3.12+** — [Download here](https://python.org)
- **Git 2.30+** — [Download here](https://git-scm.com)
- **Semgrep** — Required for scanning (Linux and Mac only; not supported on Windows)

### Step 1: Clone the Repository

```bash
git clone https://github.com/IWEBai/fixpoint.git
cd fixpoint
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
pip install semgrep
```

### Step 3: Scan a Project

**Scan in warn mode** (shows problems but doesn't change code):

```bash
python main.py /path/to/your/project --warn-mode
```

**Scan and auto-fix** (enforce mode — modifies files):

```bash
python main.py /path/to/your/project
```

**Scan only PR changes** (compares two branches):

```bash
python main.py /path/to/your/project --pr-mode --base-ref main --head-ref feature-branch
```

> **Note:** Semgrep does not run on Windows. Use WSL (Windows Subsystem for Linux) or a Linux/Mac machine.

---

## 7. Understanding Warn vs Enforce Mode

Railo has two operating modes. You should always **start with warn mode**.

### Warn Mode (Default — Recommended to Start)

```
mode: warn
```

What happens:
- Railo **scans** your code for vulnerabilities
- Railo **posts a comment** on the PR describing what it found and how to fix it
- The status check shows **❌ FAIL** (to alert you)
- **Your code is NOT changed** — you decide what to do

This is the safe choice. You review the suggestions and apply them yourself.

### Enforce Mode

```
mode: enforce
```

What happens:
- Railo **scans** your code for vulnerabilities
- Railo **commits the fix** directly to your PR branch
- The status check shows **✅ PASS** (because the issue is resolved)
- **Your code IS changed** — Railo pushes a commit

Use this after you've used warn mode for a while and trust the fixes Railo produces.

### How to Switch Modes

**GitHub Action:** Change `mode: warn` to `mode: enforce` in your workflow file.

**GitHub App:** The mode is controlled by server configuration. During the beta, the default is `warn`. Contact support to change it.

---

## 8. What Happens When You Open a Pull Request

Here's exactly what happens, step by step:

```
1. You push code to a PR (or open a new PR)
           ↓
2. GitHub sends a webhook event to Railo
           ↓
3. Railo clones your repository
           ↓
4. Railo compares the base branch (e.g. "main") with your PR branch
           ↓
5. Only the files you CHANGED are scanned (not the whole repo)
           ↓
6. Railo runs Semgrep security rules against those files
           ↓
7. If vulnerabilities are found:
   • Warn mode:  Posts a comment + sets check to FAIL
   • Enforce mode: Commits fix + sets check to PASS
           ↓
8. If NO vulnerabilities are found:
   • Sets check to PASS (your code is clean!)
```

**Important:** Railo only looks at the files you changed in the PR. It won't flag pre-existing issues in other files.

---

## 9. Reading the Results

### The Status Check

On your PR page, scroll down to the checks section. You'll see:

```
✅ fixpoint/compliance — All checks have passed    ← No issues found (or all fixed)
❌ fixpoint/compliance — 2 vulnerabilities found    ← Issues need attention
```

### PR Comments (Warn Mode)

When Railo finds a problem in warn mode, it posts a comment like this:

> **🔒 Fixpoint Security Finding**
>
> **SQL Injection** (CWE-89) found in `app.py` line 42
>
> ```python
> # ❌ Current code (vulnerable)
> query = f"SELECT * FROM users WHERE email = '{email}'"
> cursor.execute(query)
>
> # ✅ Suggested fix
> query = "SELECT * FROM users WHERE email = %s"
> cursor.execute(query, (email,))
> ```

### Annotations on the Diff

Railo also adds inline annotations directly on the code in the "Files changed" tab. Look for highlighted lines with security warnings — they appear right next to the problematic code.

### Auto-Fix Commits (Enforce Mode)

In enforce mode, you'll see a new commit from Railo in your PR:

```
fixpoint: fix SQL injection in app.py
```

The commit contains the exact fix, visible in the PR's commit history.

---

## 10. Try It Yourself — Demo Walkthrough

Want to see Railo in action without touching your real code? Follow this 5-minute demo.

### Step 1: Fork the Demo Repository

Go to [https://github.com/IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo) and click **Fork**.

### Step 2: Install Railo on Your Fork

Go to [https://github.com/apps/railo-cloud/installations/new](https://github.com/apps/railo-cloud/installations/new) and select your fork.

### Step 3: Create a Branch with Vulnerable Code

In your forked repo, create a new file called `test_vuln.py`:

```python
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cur.execute(query)
    return cur.fetchone()

API_KEY = "sk-secret-1234567890abcdef"
```

This file has **two** vulnerabilities:
1. **SQL Injection** — The query uses an f-string with user input
2. **Hardcoded Secret** — The API key is committed in plain text

### Step 4: Open a Pull Request

Create a PR from your branch to `main`.

### Step 5: Watch Railo Work

Within about 60 seconds:
- Railo scans the PR
- A check run appears
- In warn mode: a comment is posted showing the fixes
- In enforce mode: a commit is pushed with the fixes applied

### What You Should See

**SQL Injection fix:**
```python
# Before
query = f"SELECT * FROM users WHERE email = '{email}'"
cur.execute(query)

# After
query = "SELECT * FROM users WHERE email = %s"
cur.execute(query, (email,))
```

**Hardcoded Secret fix:**
```python
# Before
API_KEY = "sk-secret-1234567890abcdef"

# After
API_KEY = os.environ.get("API_KEY")
```

---

## 11. What Vulnerabilities Does Railo Fix?

### Python

| Vulnerability | What It Looks For | What It Does |
|---------------|-------------------|--------------|
| **SQL Injection** | f-strings, string concatenation, `.format()`, `%` formatting in SQL queries | Converts to parameterized queries (`%s` placeholders) |
| **Hardcoded Secrets** | Passwords, API keys, tokens, database URIs assigned as string literals | Replaces with `os.environ.get("VAR_NAME")` |
| **XSS (Templates)** | `|safe` filter, `{% autoescape off %}` in Jinja/Django templates | Removes the unsafe filter/tag |
| **XSS (Python)** | `mark_safe()`, `SafeString()` | Replaces with `escape()` |
| **Command Injection** | `os.system()`, `subprocess.call()` with `shell=True` | Converts to list-based `subprocess` (no shell) |
| **Path Traversal** | `os.path.join()` with user-controlled input | Adds path validation checks |
| **SSRF** | `requests.get()`, `urlopen()` with dynamic URLs | Flags for review (detection + guidance) |

### JavaScript / TypeScript

| Vulnerability | What It Looks For | What It Does |
|---------------|-------------------|--------------|
| **Hardcoded Secrets** | `apiKey = "xxx"`, `password = "xxx"` | Replaces with `process.env.API_KEY` |
| **DOM XSS** | `element.innerHTML = userInput` | Replaces with `element.textContent = ...` |
| **eval()** | `eval()` with user input | Flags for review (detection + guidance) |

---

## 12. Example Fixes

### SQL Injection

```python
# ❌ BEFORE — vulnerable to SQL injection
def get_user(email):
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()

# ✅ AFTER — Railo's fix (parameterized query)
def get_user(email):
    query = "SELECT * FROM users WHERE email = %s"
    cursor.execute(query, (email,))
    return cursor.fetchone()
```

### Hardcoded Secrets

```python
# ❌ BEFORE — secret exposed in source code
DATABASE_PASSWORD = "super_secret_123"
API_KEY = "sk-live-abcdef1234567890"

# ✅ AFTER — reads from environment variables
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD")
API_KEY = os.environ.get("API_KEY")
```

### Command Injection

```python
# ❌ BEFORE — user input executed as shell command
import os
os.system(f"ping {hostname}")

# ✅ AFTER — safe subprocess with argument list
import subprocess
subprocess.run(["ping", hostname])
```

### XSS (Templates)

```html
<!-- ❌ BEFORE — user input rendered without escaping -->
<p>{{ user_input|safe }}</p>

<!-- ✅ AFTER — safe rendering (auto-escaped) -->
<p>{{ user_input }}</p>
```

### JavaScript Secrets

```javascript
// ❌ BEFORE — API key committed in code
const apiKey = "sk-live-1234567890abcdef";

// ✅ AFTER — reads from environment
const apiKey = process.env.API_KEY;
```

---

## 13. Configuring Railo

### Ignoring Files or Directories

Create a `.fixpointignore` file in your repository root to skip certain files:

```
# Skip test files
tests/
test_*.py

# Skip vendor/third-party code
vendor/
node_modules/

# Skip a specific file
legacy/old_code.py
```

### Branch Protection (Optional but Recommended)

To prevent merging PRs that have unresolved security issues:

1. Go to your repo's **Settings → Branches → Branch protection rules**
2. Click **Add rule**
3. Set the branch name pattern (e.g. `main`)
4. Check **"Require status checks to pass before merging"**
5. Search for and select: `fixpoint/compliance`
6. Click **Save changes**

Now PRs with security vulnerabilities cannot be merged until the issues are resolved.

### Creating a Baseline

If your codebase has existing vulnerabilities that you don't want Railo to flag on every PR:

```bash
python main.py baseline create --sha <commit-sha>
```

This creates a baseline snapshot. Railo will only flag **new** vulnerabilities introduced after that point.

---

## 14. Frequently Asked Questions

### Is Railo free?

**Yes.** Railo is free during the beta period. No credit card required.

### Will Railo break my code?

**No.** In warn mode (the default), Railo never changes your code — it only posts comments. In enforce mode, it applies well-tested, deterministic fixes. All fixes are visible as Git commits, so you can review and revert them.

### Does Railo use AI to generate fixes?

**No.** All fixes are rule-based and deterministic. The same vulnerable code will always produce the same fix. There are no AI hallucinations or unpredictable outputs.

### What languages are supported?

Python and JavaScript/TypeScript (`.py`, `.js`, `.ts`, `.jsx`, `.tsx`).

### Does it scan my entire codebase?

**No.** Railo only scans the files that were **changed in the pull request**. This keeps scans fast and focused.

### Can I use Railo on private repositories?

**Yes.** Railo works on both public and private repositories.

### What if I disagree with a fix?

In warn mode, you simply ignore the suggestion — your code is untouched. In enforce mode, you can revert the commit Railo made or adjust the code yourself.

### Does Railo auto-merge my PR?

**Never.** Railo will never merge a PR. It only scans, comments, or commits fixes. Merging is always your decision.

### What if Railo scans code that shouldn't be scanned?

Add a `.fixpointignore` file (see [Configuring Railo](#13-configuring-railo)) to exclude files or directories.

### How fast is the scan?

Typically **30–60 seconds** after you push code to a PR.

---

## 15. Troubleshooting

### Railo didn't run on my PR

**Check these things:**

1. **Is Railo installed?** Go to your repo's **Settings → Integrations → GitHub Apps** and verify Railo is listed.
2. **Is the PR against the right branch?** Railo triggers on `opened`, `synchronize`, and `reopened` events.
3. **Try pushing a new commit** to the PR to re-trigger the scan.

### The status check doesn't appear

- If using the **GitHub Action**: Check the **Actions** tab for errors. Make sure the workflow file is in `.github/workflows/`.
- If using the **GitHub App**: The check may take up to 60 seconds to appear. Refresh the page.

### "Permission denied" errors in logs

Make sure the GitHub Action has these permissions in your workflow file:

```yaml
permissions:
  contents: write
  pull-requests: write
  statuses: write
```

### Railo flagged code that isn't actually vulnerable

Open an issue at [https://github.com/IWEBai/fixpoint/issues](https://github.com/IWEBai/fixpoint/issues) with the code snippet. We treat false positives seriously and will update the rules.

### I want to uninstall Railo

- **GitHub App:** Go to **Settings → Integrations → GitHub Apps → Railo → Configure → Uninstall**
- **GitHub Action:** Delete the `.github/workflows/fixpoint.yml` file

---

## 16. Getting Help

| Channel | Link |
|---------|------|
| **Email** | [support@fixpoint.dev](mailto:support@fixpoint.dev) |
| **GitHub Issues** | [github.com/IWEBai/fixpoint/issues](https://github.com/IWEBai/fixpoint/issues) |
| **GitHub Discussions** | [github.com/IWEBai/fixpoint/discussions](https://github.com/IWEBai/fixpoint/discussions) |
| **Website** | [iwebai.space](https://www.iwebai.space) |
| **Reddit** | [r/IWEBai](https://www.reddit.com/r/IWEBai/) |

---

## Quick Reference Card

```
┌──────────────────────────────────────────────────────┐
│                   RAILO QUICK REF                    │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Install (GitHub App):                               │
│  github.com/apps/railo-cloud/installations/new       │
│                                                      │
│  Install (GitHub Action):                            │
│  uses: IWEBai/fixpoint@v1                            │
│                                                      │
│  Modes:                                              │
│    warn    → Comments only (safe, start here)        │
│    enforce → Auto-commits fixes                      │
│                                                      │
│  Status Check:                                       │
│    ✅ fixpoint/compliance = PASS (clean)             │
│    ❌ fixpoint/compliance = FAIL (issues found)      │
│                                                      │
│  Ignore files:  .fixpointignore                      │
│  Support:       support@fixpoint.dev                 │
│                                                      │
│  Languages: Python, JavaScript, TypeScript           │
│  Fixes: SQLi, Secrets, XSS, CmdInj, PathTrav, SSRF │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

_Railo by [IWEB](https://www.iwebai.space) — Free beta. No AI. No backlog._
