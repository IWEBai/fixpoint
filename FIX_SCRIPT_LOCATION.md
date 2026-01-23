# ⚠️ Fix: Run Scripts from Correct Directory

## The Problem

You're trying to run scripts from inside the demo repo (`autopatcher-demo-python`), but the scripts are located in the main `auditshield` directory.

## The Solution

**Always run scripts from `e:\auditshield`, NOT from inside the demo repo!**

## Correct Steps

```powershell
# 1. Make sure you're in the main auditshield directory
cd e:\auditshield

# 2. Verify you're in the right place (should show auditshield files)
ls
# Should show: README.md, main.py, scripts/, etc.

# 3. Run the scripts from here
.\scripts\create_pr_violation.ps1
.\scripts\create_pr_clean.ps1
```

## What Happens

The scripts will:
1. Check if the demo repo exists locally
2. Clone it if needed (or use existing)
3. Navigate into it automatically
4. Create branches and PRs
5. Return you to the auditshield directory

**You don't need to `cd` into `autopatcher-demo-python` yourself!**

## Quick Fix for Current Situation

If you're currently inside `autopatcher-demo-python`:

```powershell
# Go back to main directory
cd e:\auditshield

# Then run the scripts
.\scripts\create_pr_violation.ps1
```
