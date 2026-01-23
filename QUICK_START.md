# Quick Start - Where to Run Commands

## Prerequisites

Before running any commands, make sure you have:

1. **GitHub CLI installed** (`gh`)
   - Check: `gh --version`
   - Install: https://cli.github.com/

2. **⚠️ AUTHENTICATE FIRST (Required!)**
   ```powershell
   gh auth login
   ```
   - Choose: GitHub.com
   - Choose: HTTPS
   - Choose: Login with a web browser
   - Follow the prompts to authenticate
   - **You MUST do this before running any `gh` commands!**

3. **PowerShell or Terminal open**
   - Windows: PowerShell or Command Prompt
   - Mac/Linux: Terminal

---

## Where to Run Commands

### Step 1: Open Terminal/PowerShell

**Windows:**
- Press `Win + X` → Select "Windows PowerShell" or "Terminal"
- Or search "PowerShell" in Start menu

**Mac/Linux:**
- Press `Cmd + Space` (Mac) or `Ctrl + Alt + T` (Linux)
- Type "Terminal" and press Enter

---

### Step 2: Navigate to Project Directory

```powershell
# Change to the AuditShield project directory
cd e:\auditshield
```

**Verify you're in the right place:**
```powershell
# Should show: e:\auditshield
pwd

# Should list files like README.md, main.py, etc.
ls
```

---

### Step 3: Run Setup Commands

**All commands should be run from `e:\auditshield` directory:**

```powershell
# You should be here:
cd e:\auditshield

# Step 1: Create GitHub Release
gh release create v0.1.0 --title "v0.1.0 - Warn-First Release" --notes-file RELEASE_NOTES.md

# Step 2: Set up demo repository
.\scripts\setup_demo.ps1

# Step 3: Create PR A (violation)
.\scripts\create_pr_violation.ps1

# Step 4: Create PR B (clean)
.\scripts\create_pr_clean.ps1
```

---

## Visual Guide

```
┌─────────────────────────────────────┐
│   PowerShell / Terminal Window     │
├─────────────────────────────────────┤
│  PS e:\auditshield>                 │  ← You should see this prompt
│                                     │
│  PS e:\auditshield> gh release ... │  ← Type commands here
│  PS e:\auditshield> .\scripts\...  │  ← Run scripts here
│                                     │
└─────────────────────────────────────┘
```

---

## Troubleshooting

### ⚠️ "To get started with GitHub CLI, please run: `gh auth login`"
**This is the most common issue!**

**Solution:**
```powershell
gh auth login
```
- Follow the prompts:
  1. Choose: `GitHub.com`
  2. Choose: `HTTPS`
  3. Choose: `Login with a web browser`
  4. Press Enter → Browser opens
  5. Authorize GitHub CLI
  6. Return to terminal

**Verify authentication:**
```powershell
gh auth status
```
Should show: `✓ Logged in to github.com as [your-username]`

### "Command not found: gh"
- Install GitHub CLI: https://cli.github.com/
- Restart terminal after installation

### "Cannot find path 'e:\auditshield'"
- Check if you're in the right directory: `pwd`
- Navigate to project: `cd e:\auditshield`

### "Script execution is disabled"
- Run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- Then try again

### "Repository already exists"
- The demo repo might already exist
- Delete it first: `gh repo delete zariffromlatif/autopatcher-demo-python --yes`
- Or use a different name in the scripts

---

## What Each Command Does

1. **`gh release create`** → Creates GitHub Release v0.1.0
2. **`.\scripts\setup_demo.ps1`** → Creates demo repository
3. **`.\scripts\create_pr_violation.ps1`** → Creates PR with violation
4. **`.\scripts\create_pr_clean.ps1`** → Creates PR with clean code

---

**Start here:** Open PowerShell, navigate to `e:\auditshield`, then run the commands above.
