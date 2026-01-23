# Next Steps - Complete Setup Guide

## ✅ Completed

- [x] Code implementation (all features)
- [x] Documentation (README, ROADMAP, RELEASE_NOTES)
- [x] Git tagging (v0.1.0)
- [x] Code pushed to GitHub

## 🔲 Remaining Steps

### Step 1: Create GitHub Release

**Using GitHub CLI (recommended):**
```bash
cd e:\auditshield
gh release create v0.1.0 \
  --title "v0.1.0 - Warn-First Release" \
  --notes-file RELEASE_NOTES.md
```

**Or use GitHub Web UI:**
1. Go to: https://github.com/zariffromlatif/auditshield/releases/new
2. Tag: `v0.1.0`
3. Title: `v0.1.0 - Warn-First Release`
4. Description: Copy from `RELEASE_NOTES.md`
5. Publish

---

### Step 2: Set Up Demo Repository

**Option A: Use PowerShell script (Windows):**
```powershell
cd e:\auditshield
.\scripts\setup_demo.ps1
.\scripts\create_pr_violation.ps1
.\scripts\create_pr_clean.ps1
```

**Option B: Use Bash script (Linux/Mac):**
```bash
cd e:\auditshield
chmod +x scripts/*.sh
./scripts/create_demo_repo.sh
./scripts/create_pr_violation.sh
./scripts/create_pr_clean.sh
```

**Option C: Manual setup (follow DEMO_REPO_SETUP.md):**
- Create repo: `autopatcher-demo-python`
- Add workflow file
- Create PR #1 (violation)
- Create PR #2 (clean)

---

### Step 3: Configure Required Check

1. Go to demo repo: https://github.com/zariffromlatif/autopatcher-demo-python
2. **Settings → Branches → Branch protection rules**
3. Click "Add rule" (or edit existing)
4. Branch name pattern: `main`
5. Enable: **"Require status checks to pass before merging"**
6. Search and select: `auditshield/compliance`
7. Save

**Result:** Merges blocked until violations are fixed.

---

### Step 4: Update README with Actual PR Links

After creating PRs, update `README.md`:

1. **PR A link:** Replace `/pull/1` with actual PR number
2. **PR B link:** Replace `/pull/2` with actual PR number

Example:
```markdown
**PR A: Violation (FAIL + Comment)**
- [PR with SQL injection violation](https://github.com/zariffromlatif/autopatcher-demo-python/pull/3)  # ← Update this
```

---

### Step 5: Verify Everything Works

**Check PR A (Violation):**
- [ ] AuditShield workflow runs
- [ ] Comment posted with fix proposal (diff preview)
- [ ] Status check shows **FAIL**
- [ ] Merge button disabled (if required check configured)

**Check PR B (Clean):**
- [ ] AuditShield workflow runs
- [ ] Status check shows **PASS**
- [ ] No comments (no violations)
- [ ] Merge allowed

**Test Enforce Mode:**
- [ ] Update workflow: `mode: enforce`
- [ ] Push new commit to PR A
- [ ] Bot commits fix automatically
- [ ] Status changes to **PASS**

---

## Quick Commands Summary

```bash
# 1. Create release
gh release create v0.1.0 --title "v0.1.0 - Warn-First Release" --notes-file RELEASE_NOTES.md

# 2. Set up demo repo (PowerShell)
.\scripts\setup_demo.ps1
.\scripts\create_pr_violation.ps1
.\scripts\create_pr_clean.ps1

# 3. Update README with PR links (manual)
# Edit README.md → Replace /pull/1 and /pull/2 with actual PR numbers
```

---

**Status:** Scripts ready. Run commands above to complete setup.
