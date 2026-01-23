# Fork PR & Loop Prevention Fixes

## Summary

Implemented critical fixes for Phase A launch:
1. ✅ Fork PR detection and auto-downgrade to warn mode
2. ✅ Improved loop prevention with canonical marker `[auditshield]`
3. ✅ Comment idempotency (updates existing comments instead of creating duplicates)

---

## 1. Fork PR Handling ✅

### Implementation

**Webhook Mode (`webhook/server.py`):**
- Detects fork PRs: `head.repo.full_name != base.repo.full_name`
- Auto-downgrades enforce → warn for forks
- Posts notice in comment about fork downgrade
- Location: After line 106

**Action Mode (`entrypoint.py`):**
- Reads `GITHUB_EVENT_PATH` JSON
- Detects fork PRs from event payload
- Auto-downgrades enforce → warn
- Logs notice in Actions output

### Why This Matters

- Fork PRs can't be pushed to (no write access)
- Prevents confusing "why didn't it apply?" errors
- Consistent with warn-first adoption strategy

---

## 2. Loop Prevention Improvement ✅

### Before
- Checked for multiple keywords: "autopatch", "autopatcher", "auditshield"
- Could cause false positives (normal commits with these words)

### After
- **Canonical marker:** `[auditshield]` prefix in all commit messages
- **Author check:** `auditshield-bot` in commit author
- **Logic:** `message.startswith("[auditshield]") OR "auditshield-bot" in author`

### Updated Files
- `core/safety.py::is_bot_commit()` - Uses canonical marker
- `webhook/server.py` - Commit message format
- `main.py` - Commit message format
- `entrypoint.py` - Commit message format

### Commit Message Format
```
[auditshield] fix: Apply compliance fixes (2 violation(s))
```

---

## 3. Comment Idempotency ✅

### Implementation

**Before:**
- Created new comment on every synchronize event
- Could spam PR with duplicate comments

**After:**
- Checks for existing AuditShield comment with same SHA
- Updates existing comment instead of creating new one
- Location: `core/pr_comments.py::create_warn_comment()`

### Logic
```python
# Check for existing comment
if head_sha:
    for comment in pr.get_issue_comments():
        if "AuditShield" in comment.body and head_sha[:8] in comment.body:
            existing_comment.edit(new_body)  # Update
            return
    # Create new if not found
    pr.create_issue_comment(new_body)
```

---

## Files Modified

1. `core/safety.py` - Improved loop prevention
2. `core/pr_comments.py` - Added comment idempotency + fork notice
3. `webhook/server.py` - Fork detection + canonical commit messages
4. `entrypoint.py` - Fork detection + canonical commit messages
5. `main.py` - Canonical commit messages

---

## Testing Checklist

- [ ] Fork PR with enforce mode → downgrades to warn
- [ ] Fork PR comment includes notice about downgrade
- [ ] Bot commit with `[auditshield]` marker → loop prevention works
- [ ] Normal commit with "audit" in message → NOT skipped (no false positive)
- [ ] Same SHA synchronize → updates comment, doesn't create duplicate
- [ ] Different SHA synchronize → creates new comment

---

## Status

✅ **All fixes implemented and ready for testing**
