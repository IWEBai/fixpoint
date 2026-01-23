# Technical Implementation Answers

## Q1: How do you prevent infinite fix loops on synchronize in enforce mode?

**Answer:** ✅ **Implemented via loop prevention check**

**Mechanism:**
- Before processing any PR event, we call `check_loop_prevention(repo_path, head_sha)`
- This checks if the latest commit is from AuditShield bot by:
  - Checking commit message for bot indicators: "auditshield-bot", "autopatch", "autopatcher", "auditshield"
  - Checking commit author email/name for bot indicators
- If bot commit detected → **skip processing** (returns early)
- Location: `core/safety.py::check_loop_prevention()` and `webhook/server.py:144`

**Flow:**
```
PR synchronize event → Clone repo → Check latest commit → 
If bot commit → Skip (prevent loop) 
If not bot commit → Process normally
```

**Limitation:** Currently only checks the **latest commit**. If a developer pushes a commit after the bot commit, it will process again (which is correct behavior).

---

## Q2: Are you using commit status API (statuses) or checks API (check-runs)?

**Answer:** ✅ **Using Status API (statuses), NOT Checks API**

**Implementation:**
- Using `r.get_commit(sha).create_status()` 
- Location: `core/status_checks.py:49`
- API endpoint: `POST /repos/{owner}/{repo}/statuses/{sha}`

**Status API vs Checks API:**
- **Status API** (current): Simpler, works with PAT, shows in PR checks section
- **Checks API**: More features (annotations, actions), requires GitHub App, better for CI/CD

**Current status context:** `auditshield/compliance`

**Note:** Status API is sufficient for MVP, but Checks API would be better for Phase 2+ (requires GitHub App migration).

---

## Q3: In fork PRs, do you skip enforce automatically?

**Answer:** ✅ **YES - Fork PRs auto-downgrade to warn mode**

**Implementation:**
- Detects fork PRs: `head.repo.full_name != base.repo.full_name`
- Auto-downgrades enforce → warn for forks
- Posts notice in comment about downgrade
- Location: `webhook/server.py` (webhook mode) and `entrypoint.py` (Action mode)

**What happens:**
1. Fork PR opens → Webhook received
2. Fork detected → Enforce downgraded to warn
3. Warn mode runs → Comments posted (no push attempt)
4. Status check set (FAIL if violations, PASS if none)

**Why:**
- Can't push to fork branches (no write access)
- Prevents confusing errors
- Consistent with warn-first strategy

---

## Summary

| Question | Answer | Status |
|----------|--------|--------|
| Loop prevention | ✅ Yes - checks latest commit for canonical `[auditshield]` marker | ✅ Implemented & Improved |
| Status vs Checks API | Status API (`create_status`) | ✅ Using Status API |
| Skip fork PRs | ✅ Yes - auto-downgrades enforce to warn | ✅ Implemented |

---

## Action Items

1. ✅ Loop prevention: Working correctly with canonical marker
2. ⚠️ Status API: Consider migrating to Checks API for Phase 2+ (requires GitHub App)
3. ✅ **Fork PR handling: IMPLEMENTED**

### Implementation Details

**Fork Detection:**
- Webhook mode: `head.repo.full_name != base.repo.full_name`
- Action mode: Reads `GITHUB_EVENT_PATH` JSON
- Auto-downgrades enforce → warn
- Posts notice in comment

**Loop Prevention:**
- Canonical marker: `[auditshield]` prefix in commit messages
- Author check: `auditshield-bot`
- Prevents false positives from normal commits

**Comment Idempotency:**
- Updates existing comment for same SHA
- Prevents comment spam on synchronize events
