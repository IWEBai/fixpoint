# Complete Setup Guide - All Next Steps

This guide walks you through completing all remaining setup steps for AuditShield v0.1.0.

---

## Step 1: Create GitHub Release ✅

**Using GitHub CLI (fastest):**
```bash
cd e:\auditshield
gh release create v0.1.0 \
  --title "v0.1.0 - Warn-First Release" \
  --notes-file RELEASE_NOTES.md
```

**Or use GitHub Web UI:**
1. Go to: https://github.com/zariffromlatif/auditshield/releases/new
2. Tag: `v0.1.0` (select from dropdown)
3. Title: `v0.1.0 - Warn-First Release`
4. Description: Copy entire content from `RELEASE_NOTES.md`
5. Click **"Publish release"**

**Verify:** Release appears at: https://github.com/zariffromlatif/auditshield/releases/tag/v0.1.0

---

## Step 2: Create Demo Repository

### Option A: Automated (PowerShell - Windows)

```powershell
cd e:\auditshield
.\scripts\setup_demo.ps1
```

This will:
- Create `autopatcher-demo-python` repo
- Add workflow file
- Create initial commit
- Push to GitHub

### Option B: Automated (Bash - Linux/Mac)

```bash
cd e:\auditshield
chmod +x scripts/*.sh
./scripts/create_demo_repo.sh
```

### Option C: Manual Setup

Follow `DEMO_REPO_SETUP.md` for step-by-step instructions.

---

## Step 3: Create PR A (Violation - FAIL)

### Option A: Automated (PowerShell)

```powershell
cd e:\auditshield
.\scripts\create_pr_violation.ps1
```

**After running:** Copy the PR URL from output and update `README.md` line 115.

### Option B: Automated (Bash)

```bash
cd e:\auditshield
./scripts/create_pr_violation.sh
```

**After running:** Copy the PR URL from output and update `README.md` line 115.

### Option C: Manual

```bash
cd autopatcher-demo-python
git checkout -b feature/add-user-lookup

cat > app.py << 'EOF'
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()
EOF

git add app.py
git commit -m "Add user lookup function"
git push origin feature/add-user-lookup
gh pr create --title "Add user lookup" --body "Adds user lookup function"
```

**Copy PR link** and update `README.md` line 115.

---

## Step 4: Create PR B (Clean - PASS)

### Option A: Automated (PowerShell)

```powershell
cd e:\auditshield
.\scripts\create_pr_clean.ps1
```

**After running:** Copy the PR URL from output and update `README.md` line 121.

### Option B: Automated (Bash)

```bash
cd e:\auditshield
./scripts/create_pr_clean.sh
```

**After running:** Copy the PR URL from output and update `README.md` line 121.

### Option C: Manual

```bash
cd autopatcher-demo-python
git checkout main
git checkout -b feature/add-safe-user-lookup

cat > app.py << 'EOF'
import sqlite3

def get_user(email):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE email = ?"
    cursor.execute(query, (email,))
    return cursor.fetchone()
EOF

git add app.py
git commit -m "Add safe user lookup function"
git push origin feature/add-safe-user-lookup
gh pr create --title "Add safe user lookup" --body "Adds safe user lookup function"
```

**Copy PR link** and update `README.md` line 121.

---

## Step 5: Configure Required Check (Block Merges)

1. Go to: https://github.com/zariffromlatif/autopatcher-demo-python/settings/branches
2. Click **"Add rule"** (or edit existing)
3. **Branch name pattern:** `main`
4. Check: **"Require status checks to pass before merging"**
5. Search: `auditshield/compliance`
6. Select: `auditshield/compliance`
7. Click **"Create"** (or "Save changes")

**Verify:** PR A should now show "Merge blocked" until status check passes.

---

## Step 6: Update README with Actual PR Links

After creating both PRs, edit `README.md`:

**Line 115:** Replace `/pull/1` with actual PR number
```markdown
- [PR with SQL injection violation](https://github.com/zariffromlatif/autopatcher-demo-python/pull/3)  # ← Update number
```

**Line 121:** Replace `/pull/2` with actual PR number
```markdown
- [PR with safe parameterized query](https://github.com/zariffromlatif/autopatcher-demo-python/pull/4)  # ← Update number
```

Then commit:
```bash
git add README.md
git commit -m "Update demo PR links"
git push
```

---

## Step 7: Verify Everything Works

### Check PR A (Violation)

- [ ] Go to PR A URL
- [ ] See AuditShield comment with fix proposal (diff preview)
- [ ] See status check: **FAIL** (`auditshield/compliance`)
- [ ] See "Merge blocked" (if required check configured)
- [ ] Comment shows before/after code diff

### Check PR B (Clean)

- [ ] Go to PR B URL
- [ ] See status check: **PASS** (`auditshield/compliance`)
- [ ] No AuditShield comments (no violations)
- [ ] Merge button enabled

### Test Enforce Mode (Optional)

1. Edit `.github/workflows/auditshield.yml` in demo repo
2. Change `mode: warn` → `mode: enforce`
3. Push new commit to PR A
4. Verify bot commits fix automatically
5. Status changes to **PASS**

---

## Quick Command Summary

**All steps in one go (PowerShell):**
```powershell
cd e:\auditshield

# 1. Create release
gh release create v0.1.0 --title "v0.1.0 - Warn-First Release" --notes-file RELEASE_NOTES.md

# 2. Set up demo repo
.\scripts\setup_demo.ps1

# 3. Create PRs
.\scripts\create_pr_violation.ps1
.\scripts\create_pr_clean.ps1

# 4. Update README (manual - copy PR links from output)
# Edit README.md → Update PR links

# 5. Configure required check (manual - GitHub UI)
# Go to Settings → Branches → Add rule
```

---

## Verification Checklist

- [ ] GitHub Release v0.1.0 created
- [ ] Demo repo `autopatcher-demo-python` exists
- [ ] PR A created (violation)
- [ ] PR B created (clean)
- [ ] README updated with actual PR links
- [ ] Required check configured
- [ ] PR A shows FAIL + comment
- [ ] PR B shows PASS
- [ ] Merge blocking works (PR A)

---

**Status:** All scripts and guides ready. Run commands above to complete setup.
