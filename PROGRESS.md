# Setup Progress Tracker

## ✅ Completed Steps

- [x] **Step 1: Create GitHub Release v0.1.0**
  - ✅ Authenticated GitHub CLI
  - ✅ Created release: https://github.com/zariffromlatif/auditshield/releases/tag/v0.1.0
  - ✅ Release includes RELEASE_NOTES.md

---

## 🔲 Remaining Steps

### Step 2: Set up demo repository
```powershell
.\scripts\setup_demo.ps1
```
**What it does:**
- Creates `autopatcher-demo-python` repository
- Adds workflow file
- Creates initial commit

### Step 3: Create PR A (violation)
```powershell
.\scripts\create_pr_violation.ps1
```
**What it does:**
- Creates branch with SQL injection vulnerability
- Opens PR
- **Copy PR URL from output** → Update README.md line 115

### Step 4: Create PR B (clean)
```powershell
.\scripts\create_pr_clean.ps1
```
**What it does:**
- Creates branch with safe code
- Opens PR
- **Copy PR URL from output** → Update README.md line 121

### Step 5: Configure required check (manual)
- Go to: https://github.com/zariffromlatif/autopatcher-demo-python/settings/branches
- Add branch protection rule for `main`
- Enable: "Require status checks to pass before merging"
- Select: `auditshield/compliance`

### Step 6: Update README and push
```powershell
git add README.md
git commit -m "Update demo PR links"
git push
```

---

## Next Command to Run

**⚠️ IMPORTANT: Run scripts from `e:\auditshield`, NOT from inside the demo repo!**

```powershell
# Make sure you're in the main auditshield directory
cd e:\auditshield

# Then run the scripts (they will handle the demo repo)
.\scripts\create_pr_violation.ps1
.\scripts\create_pr_clean.ps1
```

**Note:** The scripts automatically navigate to the demo repo directory. You don't need to `cd` into it first.
