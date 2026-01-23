# Phase A Launch Checklist (v0.1.0)

## Code Correctness ✅

### Fork PR Handling ✅
- [x] **Fork PRs auto-downgrade to warn mode** (no push attempts)
  - ✅ Implemented in `webhook/server.py` (webhook mode)
  - ✅ Implemented in `entrypoint.py` (Action mode)
  - ✅ Detects: `head.repo.full_name != base.repo.full_name`
  - ✅ Downgrades enforce → warn automatically
  - ✅ Posts notice in comment about fork downgrade

### Loop Prevention ✅
- [x] **Enforce mode does not loop on synchronize**
  - ✅ Checks latest commit for bot indicators
  - ✅ Uses canonical marker `[auditshield]` in commit messages
  - ✅ Checks commit author: `auditshield-bot`
  - ✅ Skips processing if bot commit detected

### Idempotency ✅
- [x] **Does not re-comment repeatedly on same SHA**
  - ✅ Updates existing comment if same SHA detected
  - ✅ Uses SHA in comment footer for matching
  - ✅ Prevents comment spam on synchronize events

### File Filtering ✅
- [x] **.auditshieldignore works in PR mode and repo mode**
  - ✅ Integrated into `core/scanner.py`
  - ✅ Applied in `main.py` (CLI)
  - ✅ Applied in `webhook/server.py` (webhook)
  - ✅ Applied in `entrypoint.py` (Action)

---

## GitHub Action Usability ✅

### Workflow Snippet ✅
- [x] **Canonical workflow snippet in README**
  - ✅ Warn mode default (recommended)
  - ✅ Enforce mode opt-in
  - ✅ Clear permissions documented

### Permissions Documentation ✅
- [x] **Required permissions documented:**
  - ✅ `contents: write` (only needed for enforce mode)
  - ✅ `pull-requests: write` (for comments)
  - ✅ `statuses: write` (for status checks)
  - ✅ Explicitly listed in README workflow

### Version Tagging ✅
- [x] **Tagged release: v0.1.0**
  - ✅ Tag created: `v0.1.0`
  - ✅ Release notes: `RELEASE_NOTES.md`
  - ✅ Users can pin to version

---

## Demo Readiness

### Demo Repository
- [ ] **Demo repo with PR that triggers warn mode**
  - [ ] PR with violation (shows warn comment + FAIL status)
  - [ ] PR with clean code (shows PASS status)
  - [ ] Workflow installed and working

### Loom Video
- [ ] **Loom video showing:**
  - [ ] Warn mode → comment posted
  - [ ] Opt-in enforce → commit applied
  - [ ] Status passes after fix
  - [ ] Short "why this matters" close

---

## Distribution

### Post-Launch
- [ ] **Post on relevant places:**
  - [ ] r/devops (careful tone)
  - [ ] r/Python
  - [ ] r/netsec (careful tone)
  - [ ] Hacker News "Show HN" (if polished)
  - [ ] LinkedIn + X (short)

---

## Implementation Details

### Commit Message Format
- ✅ **Canonical marker:** `[auditshield] fix: ...`
- ✅ All bot commits use this format
- ✅ Loop prevention checks for this marker

### Loop Prevention Logic
```python
# Check 1: Commit message starts with "[auditshield]"
if commit_message.strip().startswith("[auditshield]"):
    return True  # Bot commit

# Check 2: Author is auditshield-bot
if "auditshield-bot" in commit_author.lower():
    return True  # Bot commit
```

### Fork PR Detection
```python
# Webhook mode
head_repo = pr["head"]["repo"]["full_name"]
base_repo = pr["base"]["repo"]["full_name"]
is_fork = head_repo != base_repo

# Action mode
# Reads GITHUB_EVENT_PATH JSON
```

### Comment Idempotency
```python
# Check for existing comment with same SHA
if head_sha:
    for comment in pr.get_issue_comments():
        if "AuditShield" in comment.body and head_sha[:8] in comment.body:
            existing_comment.edit(new_body)  # Update instead of create
            return
```

---

## Known Limitations

1. **Status API (not Checks API)**
   - Works for MVP
   - Checks API requires GitHub App (Phase 2+)

2. **In-memory stores**
   - Idempotency/rate limiting lost on restart
   - Use Redis in production

3. **Python only**
   - By design for Phase 1
   - Multi-language in Phase 2

---

## Testing Before Launch

- [ ] Test fork PR downgrade (enforce → warn)
- [ ] Test loop prevention (bot commit → skip)
- [ ] Test comment idempotency (same SHA → update, not duplicate)
- [ ] Test .auditshieldignore in PR mode
- [ ] Test status checks (PASS/FAIL logic)
- [ ] Test warn mode comment format
- [ ] Test enforce mode commit format

---

**Status:** ✅ Code correctness complete. Demo and distribution pending.
