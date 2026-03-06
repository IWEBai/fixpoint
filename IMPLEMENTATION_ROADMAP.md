# Railo Implementation Roadmap

**Last Updated:** March 4, 2026  
**Vision:** Transform Railo into "Dependabot for Security" through one-click fix PRs and production-grade scaling

---

## Phase 0: Immediate Fixes (Week 1) — High ROI, Low Effort

### 0.1 Fix Marketing Accuracy

- **Remove "AI-powered" from all marketing materials**
  - [ ] Update `README.md` - replace "AI-powered" with "Deterministic"
  - [ ] Update `docs/PROJECT_DESCRIPTION.md`
  - [ ] Update `frontend/` landing page messaging
  - [ ] Update GitHub Marketplace listing description
  - **Rationale:** Core value is deterministic, auditable fixes - not AI

### 0.2 Document Current State

- [ ] Create `CURRENT_CAPABILITIES.md` listing what Railo can/cannot fix
- [ ] Add comparison table: Detection vs. Auto-Fix vs. Guidance-Only
- [ ] Document safety rails that are active
- [ ] List GitHub API limits Railo respects

---

## Phase 1: Viral Growth Feature (Week 2-3) — CRITICAL

### This Is The Feature That Drives Adoption

**Goal:** Implement "One-Click Safe Fix PRs" (Dependabot-style)

### 1.1 Architecture Design

- [ ] **Design Decision:** Where to create fix PRs?
  - Option A: Separate branch off `main` (Dependabot style)
  - Option B: Separate branch off `base_branch` (PR's target)
  - Recommend: **Option B** (safer, doesn't affect main)
- [ ] **Naming Convention**
  - Branch: `railo/fix-{vulnerability_type}-{timestamp}-{file_hash}`
  - PR Title: `Railo: Fix {vulnerability_type} in {file}`
  - PR Description: Risk score, confidence, CWE/OWASP tags, original PR link
  - Example: `Railo: Fix SQL injection in auth.py`

### 1.2 Core Implementation — Webhook Handler Changes

**File:** `webhook/server.py` → `process_pr_webhook()`

- [ ] **NEW: Fix PR Creation Logic**

  ```python
  def create_fix_pr(
      owner: str,
      repo: str,
      findings: list[dict],
      base_branch: str,
      original_pr_number: int,
      original_pr_url: str,
  ) -> tuple[bool, str]:
      """
      Create a separate fix PR against base_branch.
      Returns (success, pr_url)
      """
      # 1. Create new branch off base_branch
      # 2. Apply fixes to new branch
      # 3. Open PR from new branch → base_branch
      # 4. Link to original PR in description
      # 5. Set PR labels: "railo-fix", "security"
      # 6. Request review from original PR author
  ```

- [ ] **MODIFY: process_pr_webhook() flow**
  - Current: Patches existing PR branch
  - New: Creates separate fix PR
  - Keep warn mode comment in original PR for visibility
  - Enforce mode: creates fix PR without commenting original PR

- [ ] **Integrate with existing fixers**
  - Reuse `core/fixer.py` apply logic
  - Output: new branch with fixes applied
  - Create PR using `github_bot/open_or_get_pr()` (currently CLI-only)

### 1.3 Webhook Integration

- [ ] Migrate `github_bot/open_or_get_pr()` from CLI to webhook usage
- [ ] Update to accept:
  - `base_branch` (PR's target, default main)
  - `head_branch` (new fix branch name)
  - `body` (include original PR link)
- [ ] Call from webhook when:
  - Violations detected
  - Confidence checks pass
  - Safety rails allow

### 1.4 PR Templates for Fix PRs

- [ ] Create PR body with:

  ```markdown
  ## Railo Security Fix

  **Original PR:** #[original_pr_number] by @[author]

  **Vulnerability:** [type]
  **Risk Level:** [High/Medium/Low]
  **Confidence:** 98%
  **CWE/OWASP:** CWE-XXX, A1:Injection

  **What Changed:**
  This PR applies a deterministic, safe fix for the detected vulnerability.

  **Diff Summary:**

  - Lines changed: XXX
  - Files affected: XXX

  **Next Steps:**

  1. Review the changes
  2. Merge this PR to fix the vulnerability
  3. Original PR will auto-update

  [Railo Dashboard](app.railo.dev) • [Safety Rails](docs)
  ```

### 1.5 Testing & Validation

- [ ] Create test PR with vulnerable code
- [ ] Verify fix PR is created
- [ ] Verify original PR still works
- [ ] Verify both PRs can be merged independently
- [ ] Check that merging fix PR updates original PR (GitHub's auto-sync)

### 1.6 Documentation

- [ ] Update README with new workflow diagram
- [ ] Add UX walkthrough: "What developers see"
- [ ] Document fork PR handling (can't create fix PRs, use warn mode)

---

## Phase 2: Production-Grade Scaling (Week 4-5)

### This Prevents 100+ Repos From Breaking Into

### 2.1 Async Queue System

**Goal:** Replace synchronous webhook handler with async processing

- [ ] **Choose Queue Technology**
  - [ ] Evaluate: RQ (Redis Queue), Celery (heavy but scalable)
  - [ ] Recommend: **RQ** (light, Python-native, Redis-backed)
  - [ ] Setup: `pip install rq rq-dashboard`

- [ ] **Implementation**
  - [ ] Create `workers/scan_worker.py` - main fixer logic
  - [ ] Create `workers/verify_worker.py` - CI status polling (Phase 2.4)
  - [ ] Create `workers/notify_worker.py` - dashboard updates
  - [ ] Webhook handler becomes lightweight ingester:

    ```python
    from rq import Queue

    def process_pr_webhook(payload):
        q = Queue('default', connection=redis)
        job = q.enqueue(
            scan_and_fix_pr,
            owner, repo, pr_number, head_sha,
            job_id=f"{owner}:{repo}:{pr_number}:{head_sha}"
        )
        return {"status": "queued", "job_id": job.id}
    ```

### 2.2 Job Deduplication at Ingestion

**Goal:** Prevent duplicate processing if same commit arrives twice

- [ ] **Dedup Key Strategy**

  ```python
  dedup_key = f"{repo_id}:{pr_number}:{head_sha}:{config_hash}"

  def should_process(dedup_key):
      # Before queueing, check if already processing
      if redis.get(f"processing:{dedup_key}"):
          return False  # Already being processed

      # Mark as processing for 30 minutes
      redis.setex(f"processing:{dedup_key}", 1800, "1")
      return True
  ```

- [ ] **Implementation**
  - [ ] Add dedup check in webhook handler (BEFORE queuing)
  - [ ] Return early with "already_processing" status
  - [ ] Store in Redis with 30-minute TTL
  - [ ] Log duplicate attempts for observability

### 2.3 Merge Conflict Prevention

**Goal:** Cancel older jobs when new commit arrives on PR

- [ ] **Branch Lock Strategy**

  ```python
  def acquire_pr_lock(repo, pr_number):
      lock_key = f"pr_lock:{repo}:{pr_number}"
      # Acquire lock for 15 minutes
      return redis.set(lock_key, current_head_sha, nx=True, ex=900)

  def release_pr_lock(repo, pr_number):
      redis.delete(f"pr_lock:{repo}:{pr_number}")
  ```

- [ ] **Cancel Logic**
  - Before creating fix PR, acquire lock with current head_sha
  - If lock exists with different sha, cancel old job
  - Prevents race conditions on same PR

### 2.4 CI-Wait + Auto-Revert (High Risk Prevention)

**CRITICAL:** Only do this in enforce mode

- [ ] **Create CI Monitor Worker**
  - [ ] After committing fix, start polling GitHub status
  - [ ] Check status checks: required_status_checks_context
  - [ ] Wait up to 5 minutes for CI to finish
  - [ ] If FAIL: revert commit, comment "CI failed"
  - [ ] If PASS: keep commit, comment "Tests passed ✅"

- [ ] **Implementation**

  ```python
  def wait_for_ci_then_verify(owner, repo, pr_number, fix_sha):
      """
      Poll CI status for 5 minutes.
      If tests fail, revert the fix commit.
      """
      max_wait = 300  # 5 minutes
      check_interval = 10  # Check every 10 seconds

      for attempt in range(max_wait // check_interval):
          status = get_commit_status(owner, repo, fix_sha)

          if status == "success":
              return True  # CI passed
          elif status == "failure":
              revert_commit(owner, repo, pr_number)
              return False
          elif status == "pending":
              time.sleep(check_interval)
              continue

      # Timeout - assume safe and keep fix
      return True
  ```

- [ ] **Add to webhook decision flow**
  - If enforce mode: queue CI-wait job
  - If warn mode: skip (already not committing)

### 2.5 Dashboard Persistence

**Goal:** Track job status in database for visibility

- [ ] **Extend `core/db.py` runs table**

  ```sql
  ALTER TABLE runs ADD COLUMN (
    job_id TEXT,
    job_status TEXT (queued, processing, completed, failed),
    fix_pr_number INTEGER,
    fix_pr_url TEXT,
    ci_passed BOOLEAN,
    runtime_seconds FLOAT
  )
  ```

- [ ] **Record at each stage**
  - When queued: status="queued"
  - When processing: status="processing"
  - When fix PR created: update fix_pr_number, fix_pr_url
  - When CI finishes: update ci_passed, runtime_seconds
  - When complete: status="completed"

### 2.6 Rate Limit Handling

**Goal:** Respect GitHub API limits gracefully

- [ ] **Current:** Already in place (`core/rate_limit.py`)
- [ ] **Enhancement:**
  - [ ] Implement exponential backoff in queue workers
  - [ ] Pause queue if rate limit approaching
  - [ ] Add metrics dashboard: "API calls remaining"

### 2.7 Annotation Capping (Already Done)

- [x] Limit to 50 per check-run
- [x] Summarize rest in comment

---

## Phase 3: Dashboard & Analytics (Week 6)

### 3.1 Vulnerability Insights Dashboard

**New URL:** `app.railo.dev/analytics`

- [ ] **Build Visualizations**
  - [ ] Chart 1: Vulnerability types over time (bar chart)
  - [ ] Chart 2: **Fixes merged per day** (line chart) — **NORTH STAR METRIC**
  - [ ] Chart 3: Fix merge rate % (funnel: created → merged)
  - [ ] Chart 4: Most common vulnerability types (pie)
  - [ ] Chart 5: Risk distribution (high/medium/low)

- [ ] **Queries needed**

  ```sql
  -- Fixes created per day
  SELECT DATE(timestamp), COUNT(*) FROM runs
  WHERE status = 'fix_pr_created'
  GROUP BY DATE(timestamp)

  -- Fixes merged per day
  SELECT DATE(pr_merged_at), COUNT(*) FROM runs
  WHERE fix_pr_number IS NOT NULL
  AND pr_merged_at IS NOT NULL
  GROUP BY DATE(pr_merged_at)

  -- Vulnerability type breakdown
  SELECT vulnerability_type, COUNT(*) FROM findings
  GROUP BY vulnerability_type
  ORDER BY COUNT(*) DESC
  ```

### 3.2 Repo Settings UI

**Current:** Manual `.fixpoint.yml` editing

**New:** Visual configuration in dashboard

- [ ] **Per-Repo Settings Page**
  - [ ] Enable/disable Railo
  - [ ] Toggle warn ↔ enforce mode
  - [ ] Configure max_diff_lines slider
  - [ ] Configure max_runtime_seconds
  - [ ] View safety rails status (active/inactive)
  - [ ] Manage ignored files (`.fixpointignore` UI editor)

- [ ] **Backend**
  - [ ] Save settings to DB (or write to repo in `repo/{id}_config.json`)
  - [ ] Override `.fixpoint.yml` with DB values if present

### 3.3 Runs History with Rich Details

**Enhance existing runs list**

- [ ] Display per run:
  - [ ] Original PR link (#XXX)
  - [ ] Fix PR link (if created) ✨
  - [ ] Status: queued → processing → completed
  - [ ] Violations found count
  - [ ] Violations fixed count
  - [ ] Risk score average
  - [ ] CI status (passed/failed/pending)
  - [ ] Runtime (ms)

- [ ] **Filter/Sort**
  - [ ] By repo
  - [ ] By status
  - [ ] By date range
  - [ ] By vulnerability type

### 3.4 Safety Rails Transparency

**New Page:** `app.railo.dev/safety-rails`

- [ ] Show which rails are active per repo:
  - [ ] Max diff lines (current limit)
  - [ ] Max runtime budget
  - [ ] Confidence gating threshold
  - [ ] Loop prevention (status)
  - [ ] Idempotency (status)
- [ ] **Explain why fix was skipped/degraded**
  - [ ] If fix PR not created: show reason
  - [ ] If mode degraded from enforce → warn: explain why

---

## Phase 4: Advanced Features (Week 7+)

### 4.1 Safety Score per Fix

- [ ] Calculate per fix:
  - Confidence score
  - Risk rating (changed logic vs. sanitization)
  - Diff size impact
  - Whether tests passed on original PR
- [ ] Use score to:
  - [ ] Auto-merge low-risk fixes (later feature)
  - [ ] Require review for high-risk
  - [ ] Display in PR description

### 4.2 Multi-Repo Policy Controls (Enterprise)

- [ ] Org-level settings:
  - Mandate enforce for certain repos
  - Block certain vulnerability types from auto-fix
  - Require approvals per vulnerability level

### 4.3 Auto-Merge Low-Risk Fixes

- [ ] Only when:
  - CI checks pass
  - Safety score > 95
  - No logic changes (only input sanitization)
  - Repo allows auto-merge

### 4.4 Slack/Email Notifications

- [ ] Alert on:
  - Fix PR created (with link)
  - CI failed (with details)
  - Fix PR merged (celebration emoji)

---

## Phase 5: SaaS & Monetization

### 5.1 Business Tier Gating

- [ ] Free: warn mode only, basic fixes
- [ ] Pro: enforce mode, all fixes, dashboard
- [ ] Team: multi-repo, policy controls, API

### 5.2 Billing Integration

- [ ] Stripe integration
- [ ] Usage-based or per-repo pricing

---

---

## Implementation Priority Matrix

| Feature                 | Phase | Effort | Impact          | Deadline |
| ----------------------- | ----- | ------ | --------------- | -------- |
| **One-click fix PRs**   | 1     | M      | 🔥🔥🔥 CRITICAL | Week 2-3 |
| **Async queue**         | 2     | M      | 🔥🔥 HIGH       | Week 4   |
| **Job dedupe**          | 2     | S      | 🔥🔥 HIGH       | Week 4   |
| **CI-wait + revert**    | 2     | M      | 🔥 HIGH         | Week 5   |
| **Fix marketing**       | 0     | XS     | 🔥 HIGH         | Week 1   |
| **Dashboard analytics** | 3     | L      | 🔥 HIGH         | Week 6   |
| **Repos settings UI**   | 3     | M      | MEDIUM          | Week 6   |
| **Auto-merge**          | 4     | M      | MEDIUM          | Week 8+  |
| **Slack notifications** | 4     | S      | MEDIUM          | Week 8+  |

**Legend:** XS=<1h, S=1-4h, M=4-16h, L=16-40h

---

## Success Metrics

### Immediate (After Phase 1)

- [ ] Fix PRs created for 100% of detected vulnerabilities
- [ ] Developer feedback: "feels like background automation"
- [ ] Installation rate spike in GitHub Marketplace

### After Phase 2

- [ ] 99.9% uptime on webhook processing
- [ ] Zero "race condition" issues reported
- [ ] Handles 10+ concurrent PRs without degradation
- [ ] Zero "bad fix" incidents (CI-wait prevents)

### After Phase 3

- [ ] Tracked metric: "fixes merged per day"
- [ ] User obsession: Teams watch dashboard daily
- [ ] Viral loop: "Install Railo on all repos"

---

## Risk Mitigation

| Risk                        | Mitigation                                     |
| --------------------------- | ---------------------------------------------- |
| Fix PR spam                 | Start with warn-only, gradually enable enforce |
| CI failure breaks merge     | CI-wait + auto-revert implemented              |
| GitHub API limits           | Dedup + rate limit backoff in place            |
| Bad fixes land              | Confidence gating + lint checks before commit  |
| Developers ignore tool      | One-click PRs make it impossible to ignore     |
| Race conditions on branches | Job dedup by head_sha prevents conflicts       |

---

## Team Dependencies

- [ ] **Backend:** Implement phases 1, 2
- [ ] **Frontend:** Build dashboard (phase 3)
- [ ] **DevOps:** Deploy queue infrastructure (phase 2)
- [ ] **Product/Marketing:** Update messaging (phase 0)

---

## Next Steps

1. **This Week:** Implement Phase 0 (marketing fix) + start Phase 1 design
2. **Next Week:** Ship Phase 1 (one-click fix PRs) to beta customers
3. **Week 3+:** Iterate on feedback, implement Phase 2 (scaling)
