# Railo Implementation Checklist - Technical Details

**Status:** Planning Phase  
**Last Updated:** March 4, 2026

---

## PHASE 0: Fix Marketing (Week 1)

### 0.1 Update Documentation

- [ ] `README.md` line 5: Change "AI-powered" → "Deterministic security"
  - Current: "Railo is an AI-powered DevSecOps platform"
  - New: "Railo is a deterministic DevSecOps platform"

- [ ] `README.md` Philosophy section: Add clarity
  - [ ] Add explicit statement: "No AI/LLM for fixes"
  - [ ] Link to rule-based vs. AI comparison

- [ ] `docs/PROJECT_DESCRIPTION.md` sections 2.2 and 5:
  - [ ] Update vision statement
  - [ ] Emphasize "deterministic" and "rule-based"

- [ ] `docs/INTRODUCTION.md` (if exists):
  - [ ] Fix all "AI-powered" references
  - [ ] Clarify "deterministic" in first 3 sentences

- [ ] GitHub Marketplace listing:
  - [ ] Update description to remove AI references
  - [ ] Add: "Rule-based, deterministic security fixes"

- [ ] `frontend/README.md`:
  - [ ] Update tagline/description

### 0.2 Code Comments

- [ ] Review `core/` for "AI" references and update
- [ ] Review `patcher/` for "AI" references and update
- [ ] Add docstring to entry points clarifying rule-based approach

---

## PHASE 1: One-Click Safe Fix PRs (Week 2-3)

### 1.1 Design & Planning

- [ ] **Decision Log:** Document why separate PRs?
  - File: `docs/FIX_PR_DESIGN.md`
  - Content: Problem statement, Dependabot comparison, branch strategy

- [ ] **Branch Naming Convention**
  - [ ] Define pattern: `railo/fix-{vuln_type}-{timestamp}-{file_hash}`
  - [ ] Add to `docs/ARCHITECTURE.md`
  - [ ] Example: `railo/fix-sqli-20260304-1234567-auth`

### 1.2 New Module: PR Creation Service

**File:** `core/fix_pr_service.py` (NEW)

```python
# Functions to implement:
def create_fix_pr_branch(
    repo_path: Path,
    base_branch: str,
    findings: list[dict],
    original_pr_number: int
) -> tuple[bool, str]:
    """
    Create new branch off base_branch with fixes applied.
    Returns (success, new_branch_name)
    """
    # 1. Create new branch from base_branch
    # 2. Apply fixes to all files
    # 3. Commit changes with bot signature
    # 4. Return new branch name
    pass

def build_fix_pr_metadata(
    findings: list[dict],
    original_pr_number: int,
    original_pr_url: str,
    original_pr_author: str
) -> tuple[str, str]:
    """
    Build PR title and body.
    Returns (title, body)
    """
    # Generate PR title with vulnerability type
    # Generate rich description with:
    # - Link to original PR
    # - Risk assessment
    # - CWE/OWASP tags
    # - What changed
    pass

def estimate_fix_safety(findings: list[dict]) -> float:
    """
    Return safety score 0-100 for this fix.
    Considers: confidence, diff size, logic changes.
    """
    pass
```

- [ ] Create file with above function signatures
- [ ] Add unit tests: `tests/test_fix_pr_service.py`
  - [ ] Test branch creation
  - [ ] Test metadata generation
  - [ ] Test safety estimation

### 1.3 Modify: Webhook Handler

**File:** `webhook/server.py` → `process_pr_webhook()`

**Current flow (around line 850):**

```python
# ENFORCE MODE: Apply fixes to existing PR branch
if effective_mode == "enforce":
    # ... apply fixes to head_branch
    commit_and_push_to_existing_branch(...)
```

**New flow:**

```python
# ENFORCE MODE: Create separate fix PR
if effective_mode == "enforce":
    # 1. Create new branch with fixes
    fix_branch_ok, fix_branch = create_fix_pr_branch(
        repo_path, base_branch, findings_to_process, pr_number
    )

    if fix_branch_ok:
        # 2. Push new branch
        # 3. Open PR
        pr_title, pr_body = build_fix_pr_metadata(...)
        fix_pr_url = open_or_get_pr(
            owner, repo_name,
            head=fix_branch,
            base=base_branch,
            title=pr_title,
            body=pr_body
        )

        # 4. Request review from original PR author
        # 5. Add labels: "railo-fix", "security"

        # 6. Comment on ORIGINAL PR with link
        comment_on_original_pr(
            owner, repo_name, pr_number,
            f"I've created a fix PR: {fix_pr_url}"
        )
```

- [ ] Locate current enforce mode block (around line 857)
- [ ] Refactor to call `create_fix_pr_branch()`
- [ ] Update git operations to use new branch
- [ ] Add PR creation call
- [ ] Add original PR comment

### 1.4 Enhance: `github_bot/open_or_get_pr.py`

**Current:** Only used in CLI mode

**Changes needed:**

- [ ] Keep existing function signature compatible
- [ ] Add optional parameters:

  ```python
  def open_or_get_pr(
      owner, repo, head, base,
      title, body,
      labels: list[str] | None = None,  # NEW
      assignee: str | None = None,  # NEW
      request_reviewers: list[str] | None = None,  # NEW
  ) -> dict:  # Changed: return dict with url, number, etc.
  ```

- [ ] Implement new parameters using PyGithub
- [ ] Return dict with: `{"url", "number", "html_url", ...}`

- [ ] Add PR comment function:

  ```python
  def comment_on_pr(owner, repo, pr_number, body: str) -> bool:
      """Add comment to existing PR."""
      pass
  ```

- [ ] Add label function:
  ```python
  def add_pr_labels(owner, repo, pr_number, labels: list[str]) -> bool:
      """Add labels to PR."""
      pass
  ```

### 1.5 Update: PR Comment Generator

**File:** `core/pr_comments.py`

Add function for original PR notification:

```python
def generate_fix_pr_comment(fix_pr_number: int, fix_pr_url: str) -> str:
    """
    Generate comment for original PR.
    Links to the fix PR.
    """
    return f"""
## Railo Security Fix Available

I've detected **{count} security vulnerabilities** in this PR and created fixes:

🔗 **[View Fix PR #{fix_pr_number}]({fix_pr_url})**

The fixes are ready to merge separately. This keeps your original PR clean!

---
[Security Dashboard](app.railo.dev) • [Docs](https://docs.railo.dev)
"""
```

- [ ] Add this function
- [ ] Call from webhook when announcing fix PR

### 1.6 Update: Fork PR Handling

**Current:** Downgrades enforce → warn for forks  
**New:** Still downgrade, but add explicit message

- [ ] Update fork detection comment (around line 790):

  ```python
  fork_notice = """
  **Fork PR detected:** Railo cannot push fixes to forks (no write access).

  Instead, review the proposed fixes in the comments above and apply them manually.

  [Learn more about fork PRs](https://docs.railo.dev/forks)
  """
  ```

### 1.7 Testing

**File:** `tests/test_fix_pr_creation.py` (NEW)

- [ ] Test with mock repo:
  - [ ] Create vulnerable code in PR
  - [ ] Verify fix PR is created
  - [ ] Verify branch name follows convention
  - [ ] Verify PR description includes all required info
  - [ ] Verify original PR comment is created
  - [ ] Verify labels are applied

- [ ] Test fork PR:
  - [ ] Verify fix PR is NOT created for forks
  - [ ] Verify warn mode is used instead

- [ ] Test branch conflicts:
  - [ ] Simulate merge conflict scenario
  - [ ] Verify graceful handling

### 1.8 Documentation

- [ ] Update `README.md` with new workflow diagram

  ```
  Before (Patch Existing PR):
  Developer PR → Railo patches → Developer reviews

  After (Create Fix PR):
  Developer PR → Railo creates Fix PR → Developer merges → Clean merge
  ```

- [ ] Add section: "For Developers"
  - What to expect when Railo finds vulnerabilities
  - How fix PRs work
  - How to review and merge

- [ ] Add FAQ:
  - "Why separate PRs?"
  - "Can I merge both PRs at once?"
  - "What if fix PR breaks tests?"

---

## PHASE 2: Async Queue System (Week 4)

### 2.1 Setup Queue Infrastructure

**Dependencies:**

- [ ] Add to `requirements.txt`:

  ```
  rq==1.13.0
  redis>=4.0.0
  ```

- [ ] Create worker config:

  ```python
  # workers/config.py
  from rq import Queue
  from redis import Redis

  redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

  QUEUES = {
      'high': Queue('high', connection=redis_conn),
      'default': Queue('default', connection=redis_conn),
      'low': Queue('low', connection=redis_conn),
  }
  ```

- [ ] Create `docker-compose.yml` entry for Redis (dev):
  ```yaml
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  ```

### 2.2 Create Worker Processes

**File:** `workers/scan_worker.py` (NEW)

```python
"""
Main worker: scans PR, applies fixes, creates fix PR.
This runs in background queue.
"""

def scan_and_fix_pr(
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    base_branch: str,
    installation_id: int,
    correlation_id: str,
) -> dict:
    """
    Main worker job.
    Returns: {status, message, fix_pr_url, violations_found, violations_fixed}
    """
    # This is essentially the current process_pr_webhook logic
    # moved to async worker
    pass
```

- [ ] Extract current webhook logic into this function
- [ ] Handle timeouts gracefully
- [ ] Update DB with status changes

**File:** `workers/ci_monitor_worker.py` (NEW)

```python
def wait_for_ci_and_revert(
    owner: str,
    repo: str,
    pr_number: int,
    fix_sha: str,
    fix_pr_number: int,
) -> bool:
    """
    Wait for CI checks, revert if failed.
    Returns: True if CI passed, False if reverted.
    """
    pass
```

### 2.3 Modify: Webhook Handler (Become Ingester)

**File:** `webhook/server.py` → `process_pr_webhook()`

**New behavior:**

```python
def process_pr_webhook(payload: dict, correlation_id: str) -> dict:
    """
    Lightweight ingester: validate, dedupe, queue job.
    Returns immediately (no blocking).
    """

    # 1. Validate payload (existing checks)
    # 2. Check deduplication
    if already_processing(payload):
        return {"status": "skipped_duplicate"}

    # 3. Queue immediate job
    from workers.config import QUEUES
    from workers.scan_worker import scan_and_fix_pr

    job = QUEUES['default'].enqueue(
        scan_and_fix_pr,
        owner=...,
        repo=...,
        pr_number=...,
        job_id=f"{owner}:{repo}:{pr_number}:{head_sha}"
    )

    # 4. Return immediately
    return {
        "status": "queued",
        "job_id": job.id,
        "message": "Processing PR in background"
    }
```

- [ ] Remove all blocking logic from webhook handler
- [ ] Keep only validation, allow-list checks, dedup
- [ ] Return 202 Accepted with job ID

### 2.4 Implement Job Deduplication

**File:** `core/job_dedup.py` (NEW)

```python
def get_dedup_key(owner: str, repo: str, pr_number: int, head_sha: str) -> str:
    """Generate unique key for this PR+commit."""
    return f"{owner}:{repo}:{pr_number}:{head_sha}"

def is_already_processing(dedup_key: str) -> bool:
    """Check if this job is currently being processed."""
    redis = get_redis_client()
    return redis.exists(f"processing:{dedup_key}")

def mark_processing(dedup_key: str, ttl_seconds: int = 1800) -> bool:
    """Mark this job as currently processing."""
    redis = get_redis_client()
    return redis.set(
        f"processing:{dedup_key}",
        "1",
        nx=True,  # Only set if not exists
        ex=ttl_seconds  # Expire after 30 mins
    )

def unmark_processing(dedup_key: str) -> bool:
    """Mark this job as complete."""
    redis = get_redis_client()
    return redis.delete(f"processing:{dedup_key}")
```

- [ ] Create file with above functions
- [ ] Call in webhook handler before queueing
- [ ] Call after worker completes (success or failure)

### 2.5 Update Database Schema

**File:** `core/db.py`

```python
# Add to runs table:
ALTER TABLE runs ADD COLUMN (
    job_id TEXT,
    job_status TEXT,          # queued, processing, completed, failed
    fix_pr_number INTEGER,
    fix_pr_url TEXT,
    ci_passed BOOLEAN,
    runtime_seconds FLOAT
);
```

- [ ] Update `insert_run()` to accept new fields
- [ ] Create `update_run_job_status()` function
- [ ] Create `update_run_with_fix_pr()` function
- [ ] Add queries for dashboard

### 2.6 Testing

- [ ] Integration test with mock Redis
- [ ] Verify job is queued
- [ ] Verify dedup prevents duplicates
- [ ] Verify webhook returns immediately

---

## PHASE 2.4: CI-Wait + Auto-Revert (Week 5)

### 2.4.1 Create CI Monitor

**File:** `workers/ci_monitor_worker.py`

```python
from github import Github, Auth
import time

def wait_for_ci_and_revert(
    owner: str,
    repo: str,
    pr_number: int,
    fix_sha: str,
    fix_pr_number: int,
    max_wait_seconds: int = 300,
) -> dict:
    """
    Monitor CI status for fix PR.
    If tests fail, revert the commit.

    Returns: {status, ci_passed, message}
    """

    def get_status():
        g = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")))
        r = g.get_repo(f"{owner}/{repo}")
        status = r.get_commit(fix_sha).get_combined_status()
        return status.state  # pending, success, failure, error

    # Poll for up to 5 minutes
    elapsed = 0
    while elapsed < max_wait_seconds:
        status = get_status()

        if status == "success":
            return {
                "status": "success",
                "ci_passed": True,
                "message": "CI checks passed ✅"
            }
        elif status == "failure":
            # REVERT THE COMMIT
            revert_commit(owner, repo, fix_pr_number, fix_sha)
            return {
                "status": "failure",
                "ci_passed": False,
                "message": "CI checks failed. Fix reverted. ❌"
            }
        elif status == "error":
            return {
                "status": "error",
                "ci_passed": False,
                "message": "CI error. Fix reverted. ❌"
            }

        time.sleep(10)  # Check every 10 seconds
        elapsed += 10

    # Timeout - assume safe
    return {
        "status": "timeout",
        "ci_passed": True,
        "message": "CI check timeout. Assuming safe. ✓"
    }

def revert_commit(owner: str, repo: str, pr_number: int, commit_sha: str) -> bool:
    """Revert the specific commit from PR branch."""
    # Use git revert or reset
    pass
```

- [ ] Implement `get_status()` using GitHub API
- [ ] Implement `revert_commit()` using git
- [ ] Add to worker queue

### 2.4.2 Integrate into Webhook

When enforce mode creates fix PR:

```python
# After fix PR is created:
job = QUEUES['low'].enqueue(
    wait_for_ci_and_revert,
    owner=owner,
    repo=repo,
    pr_number=fix_pr_number,
    fix_sha=new_commit_sha,
    job_id=f"ci_monitor:{owner}:{repo}:{fix_pr_number}"
)
```

- [ ] Queue CI monitor job after fix PR creation
- [ ] Store job_id in DB
- [ ] Update PR comment when CI finishes

### 2.4.3 Testing

- [ ] Mock GitHub API to return failure status
- [ ] Verify commit is reverted
- [ ] Mock timeout scenario
- [ ] Verify graceful handling

---

## PHASE 3: Dashboard Analytics (Week 6)

### 3.1 Database Queries

**File:** `core/dashboard_queries.py` (NEW)

```python
def get_fixes_created_per_day(installation_ids: list[int], days: int = 30) -> list[dict]:
    """Return: [{date, count}, ...]"""
    pass

def get_fixes_merged_per_day(installation_ids: list[int], days: int = 30) -> list[dict]:
    """NORTH STAR METRIC"""
    pass

def get_vulnerability_breakdown(installation_ids: list[int]) -> list[dict]:
    """Return: [{type, count}, ...]"""
    pass

def get_fix_merge_rate(installation_ids: list[int]) -> float:
    """Return: % of created fixes that were merged"""
    pass

def get_ci_success_rate(installation_ids: list[int]) -> float:
    """Return: % of fix PRs where CI passed"""
    pass
```

- [ ] Create file with above signatures
- [ ] Implement SQL queries
- [ ] Add unit tests with mock data

### 3.2 Frontend: Analytics Page

**File:** `frontend/src/pages/analytics.tsx` (NEW)

```typescript
export default function Analytics() {
  // 1. Fetch metrics from API
  // 2. Render 5 charts:
  //    - Fixes created (bar)
  //    - Fixes merged (line) — HIGHLIGHT THIS
  //    - Vulnerability types (pie)
  //    - Fix merge rate % (gauge)
  //    - CI success rate (gauge)

  return (
    <div className="analytics">
      <h1>Railo Security Metrics</h1>
      <Chart1 data={createdPerDay} />
      <Chart2 data={mergedPerDay} />  {/* NORTH STAR */}
      <Chart3 data={vulnerabilityTypes} />
      <Chart4 value={mergeRate} />
      <Chart5 value={ciSuccessRate} />
    </div>
  )
}
```

- [ ] Create page component
- [ ] Add chart library (Recharts, Chart.js, etc.)
- [ ] Connect to API endpoint (see 3.3)

### 3.3 API Endpoints

**File:** `webhook/server.py`

Add routes:

```python
@app.route("/api/analytics/fixes-created", methods=["GET"])
def api_fixes_created():
    # days = request.args.get('days', 30)
    # data = get_fixes_created_per_day(...)
    # return jsonify(data)
    pass

@app.route("/api/analytics/fixes-merged", methods=["GET"])
def api_fixes_merged():
    # NORTH STAR METRIC
    pass

@app.route("/api/analytics/vulnerabilities", methods=["GET"])
def api_vulnerabilities():
    pass

@app.route("/api/analytics/merge-rate", methods=["GET"])
def api_merge_rate():
    pass
```

- [ ] Create endpoints
- [ ] Add auth (OAuth only)
- [ ] Return JSON

### 3.4 Repo Settings UI

**File:** `frontend/src/pages/repo-settings.tsx` (NEW)

Form with:

- [ ] **Enable/Disable Toggle**

  ```typescript
  <Toggle
    label="Enable Railo"
    value={repoEnabled}
    onChange={(v) => updateRepo({enabled: v})}
  />
  ```

- [ ] **Mode Selection**

  ```typescript
  <Select
    label="Mode"
    options={['warn', 'enforce']}
    value={mode}
    onChange={(v) => updateRepo({mode: v})}
  />
  ```

- [ ] **Safety Rails Sliders**

  ```typescript
  <Slider
    label="Max Diff Lines"
    min={100}
    max={2000}
    value={maxDiffLines}
    onChange={(v) => updateRepo({max_diff_lines: v})}
  />

  <Slider
    label="Max Runtime (seconds)"
    min={10}
    max={300}
    value={maxRuntime}
    onChange={(v) => updateRepo({max_runtime_seconds: v})}
  />
  ```

- [ ] **Ignored Files Editor**

  ```typescript
  <TextArea
    label=".fixpointignore"
    value={ignoreFile}
    onChange={(v) => updateRepo({ignore_file: v})}
    placeholder="**/.git/\nnode_modules/"
  />
  ```

- [ ] **Save Button**
  ```typescript
  <Button onClick={() => saveRepoSettings()} color="primary">
    Save Settings
  </Button>
  ```

### 3.5 Backend: Repo Settings API

**File:** `webhook/server.py`

```python
@app.route("/api/repos/<repo_id>/settings", methods=["GET"])
def get_repo_settings(repo_id):
    # Return current settings from DB
    pass

@app.route("/api/repos/<repo_id>/settings", methods=["PUT"])
def update_repo_settings(repo_id):
    # Update settings in DB
    # Optionally write to .fixpoint.yml
    pass
```

- [ ] Add endpoints
- [ ] Store settings in `repo_settings` DB table
- [ ] Test with frontend

### 3.6 Runs History Enhancement

**File:** `frontend/src/pages/runs.tsx` (Update)

Current: Simple list  
New: Rich cards with:

- [ ] PR link (#XXX)
- [ ] Fix PR link (if exists) ✨
- [ ] Status badge
- [ ] Violation counts
- [ ] Risk score
- [ ] CI status
- [ ] Runtime (ms)

```typescript
<RunsTable
  columns={[
    'PR', 'Fix PR', 'Status', 'Violations Found', 'Violations Fixed',
    'Risk Score', 'CI Status', 'Runtime'
  ]}
  data={runs}
  onRowClick={(run) => navigateTo(`/runs/${run.id}`)}
/>
```

- [ ] Update query to include new fields
- [ ] Update table/card display
- [ ] Add sorting/filtering

### 3.7 Testing

- [ ] Test queries with mock data
- [ ] Test API endpoints
- [ ] Test frontend charts render
- [ ] Test repo settings save/load

---

## Phase 4 & Beyond: Future Features

### 4.1 Auto-Merge Low-Risk Fixes

- [ ] Define "low-risk" criteria
- [ ] Implement auto-merge logic
- [ ] Add approval workflow

### 4.2 Slack/Email Notifications

- [ ] Slack webhook integration
- [ ] Email templates
- [ ] Notification preferences per repo

### 4.3 Multi-Org Management

- [ ] Org-level settings
- [ ] Cross-repo analytics
- [ ] Policy controls

### 4.4 Advanced Rule Management

- [ ] UI to enable/disable rules per repo
- [ ] Custom rule creation
- [ ] Rule import/export

---

## Testing Strategy

### Unit Tests

- [ ] `tests/test_fix_pr_service.py` - Phase 1
- [ ] `tests/test_job_dedup.py` - Phase 2
- [ ] `tests/test_ci_monitor.py` - Phase 2.4
- [ ] `tests/test_dashboard_queries.py` - Phase 3

### Integration Tests

- [ ] Mock GitHub API for full PR workflow
- [ ] Queue with mock Redis
- [ ] Dashboard API with live DB

### E2E Tests

- [ ] Real GitHub repo (private test repo)
- [ ] End-to-end: Push vulnerable code → Observe fix PR

---

## Deployment Checklist

### Environment Variables

- [ ] `REDIS_URL` for queue system (Phase 2)
- [ ] `RQ_DASHBOARD_PORT` optional (Phase 2)

### Database Migrations

- [ ] Schema changes (Phase 2, 3)
- [ ] Run migrations in staging first

### Docker Updates

- [ ] Add Redis service (Phase 2)
- [ ] Add worker containers (Phase 2)

### Monitoring

- [ ] Queue job success/failure rate
- [ ] API response times
- [ ] Database query performance
- [ ] Worker uptime

---

## Success Criteria Per Phase

### Phase 0 ✓

- [ ] All marketing materials updated
- [ ] No "AI-powered" references remain
- [ ] Messaging emphasizes "deterministic"

### Phase 1 ✓

- [ ] Fix PRs created for 100% of fixable vulnerabilities
- [ ] Separate PR branch exists with correct name
- [ ] Original PR receives notification comment
- [ ] All tests passing

### Phase 2 ✓

- [ ] Webhook handler returns in <100ms
- [ ] Jobs queued without blocking
- [ ] Dedup prevents duplicate processing
- [ ] Queue handles 10+ concurrent jobs
- [ ] Zero race conditions on branches
- [ ] All tests passing

### Phase 2.4 ✓

- [ ] CI status polled after fix PR created
- [ ] Failed fixes automatically reverted
- [ ] No "broken fix" incidents

### Phase 3 ✓

- [ ] Analytics dashboard loads < 2 sec
- [ ] Charts update in real-time
- [ ] Repo settings UI works end-to-end
- [ ] All tests passing

---

## Known Risks & Mitigations

| Risk                          | Mitigation                                                   | Status     | Phase  |
| ----------------------------- | ------------------------------------------------------------ | ---------- | ------ |
| Breaking webhook timeout      | Async queue (RQ + Redis)                                     | ✅ Done    | 2      |
| Fix PR spam                   | Start warn-only, enable enforce gradually                    | ✅ Done    | 1      |
| CI failure lands bad fix      | CI-wait + revert worker (comment stub; full revert pending)  | ⚠️ Partial | 2.4    |
| Developers ignore tool        | One-click PRs make it essential                              | ✅ Done    | 1      |
| Database bottleneck           | Query optimization, caching                                  | ⬜ Later   | 3+     |
| GitHub API rate limits        | `call_github_api` retry/backoff + webhook dedup              | ✅ Done    | 2      |
| Race conditions               | Job dedup by head_sha                                        | ✅ Done    | 2      |
| GitHub annotation cap (50)    | `status_checks.py` enforces `< 50` guard                     | ✅ Done    | 1      |
| App uninstall leaves stale DB | `remove_installation()` on `installation.deleted` event      | ✅ Done    | 1      |
| Secrets in env vars           | Azure Container Apps Key Vault refs (worker-app.yaml)        | ✅ Done    | deploy |
| Large monorepo scan           | Diff-only scanning via `target_files` in scanner.py          | ✅ Done    | 1      |
| Org-level policy enforcement  | Per-repo settings in place; org defaults not yet implemented | ⬜ Later   | 4+     |
| Full git revert push          | Requires git clone + push; current impl posts PR comment     | ⬜ Later   | 2.4    |

---

## Production Readiness Audit (March 2026)

### Risk 1 — Installation lifecycle ✅ Complete

- `installation` created/updated: `upsert_installation()` in [core/db.py](core/db.py)
- `installation_repositories` added/removed: `upsert_installation()` called
- `installation.deleted`: **now handled** — `remove_installation()` deletes the
  row; historical `runs` rows are kept for audit.
- Remaining: `installation_repositories` removed-repos sub-event does not yet
  deactivate per-repo settings.

### Risk 2 — GitHub API rate limiting ✅ Complete

- Webhook rate limiting: `core/rate_limit.py` (10 req/min per PR, Redis-backed)
- GitHub annotation cap: `core/status_checks.py` guards at 50 per check run
- **New**: `call_github_api(fn, *args)` in `core/rate_limit.py` wraps any
  PyGithub call with exponential back-off on `RateLimitExceededException` and
  retries on transient 5xx errors. Used in `workers/ci_monitor_worker.py`.
  Other hot-paths (webhook/server.py) should be migrated to use it over time.

### Risk 3 — Secret handling ✅ Complete (via deployment)

- All secrets (GitHub private key, webhook secret, Redis URL, DB conn) are
  stored in **Azure Key Vault** and injected as env vars at runtime via
  Container Apps managed-identity references (`worker-app.yaml` lines 26–38).
- Python code only reads `os.getenv(...)` — no SDK calls to Key Vault needed.
- No plain-text secrets in code, Dockerfile, or git history.

### Risk 4 — Org-level policies ⬜ Roadmap

- Current: per-repo settings (`repo_settings` table, `RepoSettings` UI page).
- Needed for large teams: org-default mode/thresholds that per-repo settings
  inherit unless overridden.
- Planned for Phase 4.

### Risk 5 — Repo scanning limits ✅ Complete

- Scanner accepts `target_files` for PR-diff-only mode (see `core/scanner.py`).
- Webhook handler extracts changed PR files → `filter_supported_files()` →
  passed as `target_files` to scanner. Full-repo scan never triggered by default.
- `max_diff_lines` setting in `repo_settings` provides an additional size gate.

### Risk 6 — CI revert ⚠️ Partial (MVP)

- CI poller is live: polls combined status, marks `ci_passed` in DB.
- On failure: posts a PR comment requesting manual revert (safe MVP default).
- Full automated revert (git clone → `git revert` → push) is planned but not
  yet implemented. See `workers/ci_monitor_worker.py::revert_commit()`.

---

## Questions for Product/Engineering

1. **Fork PR Behavior:** Keep warn-only or silent fail?
2. **Auto-Merge:** Ever auto-merge fix PRs? (requires PM approval)
3. **Notifications:** Slack integration priority?
4. **Pricing:** Free tier limits? (blocks Phase 5 work)
5. **SLA:** Uptime target? (affects monitoring/alerts)
