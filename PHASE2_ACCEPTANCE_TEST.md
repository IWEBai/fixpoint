# Phase 2 Acceptance Test

**Purpose:** Prove AuditShield Phase 2 is stable, safe, and production-ready.

**Time:** ~15 minutes

**Prerequisites:**
- AuditShield webhook server running
- GitHub webhook configured
- Test repository with write access

---

## Test Checklist

### ✅ Test 1: PR Opened → Finds Issue → Pushes Commit → CI Reruns → PR Shows Clean Diff

**Steps:**
1. Create a new branch: `test-sqli-vulnerability`
2. Add vulnerable code:
   ```python
   # app.py
   email = request.form.get('email')
   query = f"SELECT * FROM users WHERE email = '{email}'"
   cursor.execute(query)
   ```
3. Commit and push
4. Open PR to `main`
5. **Expected:** Within 30 seconds:
   - Webhook receives event
   - AuditShield scans changed files
   - Fix is applied and pushed to PR branch
   - PR comment is posted explaining the fix
   - CI reruns automatically
   - PR diff shows clean parameterized query fix

**Verification:**
- [ ] PR comment appears with explanation
- [ ] New commit appears on PR branch
- [ ] Diff shows only security fix (no formatting changes)
- [ ] CI status shows "in progress" or "passed"

---

### ✅ Test 2: PR Synchronize → Does Not Reapply Same Patch

**Steps:**
1. Using the PR from Test 1
2. Add a new commit to the PR branch (unrelated change)
3. Push to trigger `synchronize` event
4. **Expected:**
   - Webhook receives `synchronize` event
   - AuditShield checks idempotency
   - No duplicate fix is applied
   - No duplicate PR comment

**Verification:**
- [ ] Only one fix commit exists (from Test 1)
- [ ] Only one PR comment exists
- [ ] Logs show "already_fixed" or "idempotent_skip"

---

### ✅ Test 3: Already Fixed PR → Does Nothing

**Steps:**
1. Create a new branch with already-fixed code:
   ```python
   # app.py
   email = request.form.get('email')
   query = "SELECT * FROM users WHERE email = %s"
   cursor.execute(query, (email,))
   ```
2. Open PR
3. **Expected:**
   - Webhook receives event
   - AuditShield scans
   - No violations found
   - No commits pushed
   - No PR comment (or "no findings" comment)

**Verification:**
- [ ] No fix commits
- [ ] Logs show "no_findings"
- [ ] PR remains unchanged

---

### ✅ Test 4: Unsupported Pattern → Comments "Flag Only" or Exits Silently

**Steps:**
1. Create PR with unsupported violation (e.g., hardcoded secret):
   ```python
   # app.py
   api_key = "sk_live_1234567890"
   ```
2. Open PR
3. **Expected:**
   - Webhook receives event
   - AuditShield scans
   - No fix available for this pattern
   - Either: silent exit OR comment explaining "flag only"

**Verification:**
- [ ] No fix commits
- [ ] Either no comment OR comment explains pattern not supported
- [ ] Logs show appropriate status

---

### ✅ Test 5: Cannot Push (Permissions/Branch Protection) → Posts Actionable Comment

**Steps:**
1. Configure branch protection on test branch (require admin approval)
2. Create PR with SQL injection vulnerability
3. Open PR
4. **Expected:**
   - Webhook receives event
   - AuditShield finds violation
   - Attempts to push
   - Push fails due to branch protection
   - Error comment posted to PR with actionable steps

**Verification:**
- [ ] PR comment appears explaining the issue
- [ ] Comment includes actionable steps
- [ ] Logs show "error" status with branch protection details
- [ ] No partial commits

---

### ✅ Test 6: Loop Prevention → Bot Commit Does Not Trigger Bot Again

**Steps:**
1. Manually create a commit with AuditShield-style message:
   ```bash
   git commit -m "AutoPatch: Fix SQL injection (parameterized query)" \
     --author="auditshield-bot <auditshield-bot@users.noreply.github.com>"
   ```
2. Push to PR branch
3. This triggers `synchronize` event
4. **Expected:**
   - Webhook receives event
   - AuditShield detects bot commit
   - Processing is skipped
   - No duplicate fix

**Verification:**
- [ ] Logs show "skipped" with "bot commit detected"
- [ ] No new commits
- [ ] No duplicate PR comments

---

### ✅ Test 7: Webhook Security → Invalid Signature Rejected

**Steps:**
1. Send POST request to `/webhook` with:
   - Invalid signature
   - Valid PR payload
2. **Expected:**
   - Request rejected with 401
   - No processing occurs
   - Logs show "Invalid webhook signature"

**Verification:**
- [ ] HTTP 401 response
- [ ] No commits pushed
- [ ] Security logs show rejection

---

### ✅ Test 8: Replay Protection → Duplicate Delivery Rejected

**Steps:**
1. Send same webhook delivery ID twice
2. **Expected:**
   - First delivery processed normally
   - Second delivery rejected as replay
   - No duplicate processing

**Verification:**
- [ ] First request: 200 OK
- [ ] Second request: 401 with "replay detected"
- [ ] Only one fix applied

---

### ✅ Test 9: Confidence Gating → Low Confidence Findings Skipped

**Steps:**
1. Create PR with pattern that Semgrep flags but confidence is "medium"
2. Open PR
3. **Expected:**
   - Webhook receives event
   - AuditShield scans
   - Findings detected but confidence too low
   - No fix applied
   - Status: "low_confidence"

**Verification:**
- [ ] No fix commits
- [ ] Logs show "low_confidence"
- [ ] PR unchanged

---

### ✅ Test 10: Observability → Structured Logs with Correlation IDs

**Steps:**
1. Process any PR (e.g., Test 1)
2. Check logs
3. **Expected:**
   - Each webhook event has correlation ID
   - All log entries include correlation ID
   - Structured JSON logs available
   - Can trace full request lifecycle

**Verification:**
- [ ] Logs show correlation IDs
- [ ] Can trace event from webhook → scan → fix → comment
- [ ] Structured log format

---

## Success Criteria

**All tests must pass** for Phase 2 to be considered production-ready:

- [ ] Test 1: Basic flow works end-to-end
- [ ] Test 2: Idempotency prevents duplicate fixes
- [ ] Test 3: Already-fixed code doesn't trigger fixes
- [ ] Test 4: Unsupported patterns handled gracefully
- [ ] Test 5: Branch protection errors handled with helpful comments
- [ ] Test 6: Loop prevention works
- [ ] Test 7: Webhook security rejects invalid signatures
- [ ] Test 8: Replay protection works
- [ ] Test 9: Confidence gating works
- [ ] Test 10: Observability is functional

---

## Failure Scenarios to Watch For

**Critical failures (must fix immediately):**
- Infinite loop of bot commits
- Duplicate fixes on same PR
- Security bypass (invalid signatures accepted)
- Data loss (overwrites user code)

**Warning signs (investigate):**
- Missing PR comments
- Silent failures
- Incomplete error messages
- Performance degradation

---

## Running the Tests

1. **Setup test environment:**
   ```bash
   # Start webhook server
   python webhook_server.py
   
   # In another terminal, use ngrok for local testing
   ngrok http 5000
   ```

2. **Configure GitHub webhook:**
   - URL: `https://your-ngrok-url.ngrok.io/webhook`
   - Secret: Your `WEBHOOK_SECRET`
   - Events: `pull_request` (opened, synchronize)

3. **Run tests sequentially** (they depend on each other)

4. **Check logs** after each test

5. **Verify results** against checklist

---

## Post-Test Actions

After all tests pass:

1. ✅ Document any edge cases found
2. ✅ Update PHASE2_SETUP.md with learnings
3. ✅ Create demo video (Loom) showing Test 1
4. ✅ Prepare for production deployment

---

**Last Updated:** Phase 2 Implementation
**Status:** Ready for testing
