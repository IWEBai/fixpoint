# Railo Implementation Quick Reference

**What:** Transform Railo from "patch existing PRs" → "create separate fix PRs" (Dependabot-style)  
**Why:** Separate fix PRs drive viral adoption (developers don't feel interrupted)  
**Status:** Code mostly exists; behavioral change needed  
**Timeline:** 6 weeks for full implementation

---

## Executive Summary

### The Critical Missing Piece

**Current:** Railo comments on existing PRs or patches their branch  
**New:** Railo creates separate fix PRs that developers just merge  
**Impact:** 🔥 This is the single feature that drives viral adoption

### Why This Matters

- Dependabot succeeded because it created _separate_ PRs
- Developers feel like it's helpful automation, not interruption
- Security fixes become "background infrastructure"
- Team lead: "Install Railo on all repos"

---

## Phase Overview

| Phase   | What                       | Duration | Impact                |
| ------- | -------------------------- | -------- | --------------------- |
| **0**   | Fix "AI-powered" messaging | 1 day    | Credibility fix       |
| **1**   | Implement separate fix PRs | 2 weeks  | 🔥 GAME CHANGER       |
| **2**   | Add async queue system     | 1 week   | Production ready      |
| **2.4** | Add CI-wait + revert       | 1 week   | Safety guardian       |
| **3**   | Build analytics dashboard  | 1 week   | Insights + monitoring |

**Total:** 6 weeks for production-grade release

---

## Phase 1: The Game-Changer (2 weeks)

### What Gets Built

```
Developer opens PR with bug
  ↓
Railo detects vulnerability
  ↓
Railo creates FIX PR (separate, against main)
  ↓
Developer reviews fix PR in isolation
  ↓
Developer clicks "Merge" on fix PR
  ↓
Repo is safer (no original PR affected)
```

### Files to Create/Modify

| File                           | Change                          | Size |
| ------------------------------ | ------------------------------- | ---- |
| `core/fix_pr_service.py`       | **NEW** - PR creation logic     | M    |
| `webhook/server.py`            | Modify enforce mode flow        | M    |
| `github_bot/open_or_get_pr.py` | Add labels, reviewers, comments | S    |
| `core/pr_comments.py`          | Add fix PR notification         | S    |
| Tests & docs                   | Full test coverage              | M    |

**Total Effort:** ~4 weeks of dev time

### Success Metric

- Fix PRs are created for 100% of detected vulnerabilities
- Developer feedback: "Feels like Copilot for security"
- GitHub Marketplace downloads spike

---

## Phase 2: Production Scaling (1 week)

### What Gets Built

```
Webhook receives PR event
  ↓
Webhook validates & queues job (returns 202 immediately)
  ↓
Background worker processes in queue
  ↓
Worker creates fix PR, monitors CI, auto-reverts if needed
```

### Why Now

- Webhook handler currently **blocks** (risky at 100+ repos)
- Need async processing for reliability
- CI failures need automatic handling

### Files to Create/Modify

| Component                      | Work                                     |
| ------------------------------ | ---------------------------------------- |
| **Redis Queue**                | Setup RQ (light, Python-native)          |
| `workers/scan_worker.py`       | **NEW** - Move webhook logic here        |
| `workers/ci_monitor_worker.py` | **NEW** - Watch CI, revert if fail       |
| `webhook/server.py`            | **Change** - Become lightweight ingester |
| `core/job_dedup.py`            | **NEW** - Prevent duplicate jobs         |
| `core/db.py`                   | **Update** - Track job status            |

**Total Effort:** ~1 week of dev time

### Success Metric

- Webhook handler returns in <100ms
- Zero race conditions on concurrent PRs
- Queue handles 100+ repos without degradation

---

## Phase 3: Dashboard (1 week)

### What Gets Built

```
Analytics Dashboard
├── Fixes created per day (chart)
├── **Fixes merged per day** (NORTH STAR)
├── Vulnerability type breakdown (pie)
├── Fix merge rate % (gauge)
└── CI success rate % (gauge)

Repo Settings UI
├── Enable/disable toggle
├── Mode picker (warn/enforce)
├── Safety rail sliders
├── .fixpointignore editor
└── Save button

Runs History (enhanced)
├── PR link (#XXX)
├── Fix PR link (✨ new)
├── Status, violations, risk score
├── CI status
└── Runtime
```

### Why Now

- Teams need to see: "How many fixes are actually being merged?"
- Repo settings should be UI, not file editing
- Observability = trust

### Files to Create/Modify

| Component                              | Work                        |
| -------------------------------------- | --------------------------- |
| `frontend/src/pages/analytics.tsx`     | **NEW** - Charts            |
| `frontend/src/pages/repo-settings.tsx` | **NEW** - Settings UI       |
| `frontend/src/pages/runs.tsx`          | **Update** - Rich cards     |
| `core/dashboard_queries.py`            | **NEW** - Analytics queries |
| `webhook/server.py`                    | Add API endpoints           |

**Total Effort:** ~1 week of dev time

### Success Metric

- Dashboard loads in <2 seconds
- Teams track "fixes merged per day" daily
- Repo settings save/load without errors

---

## What NOT to Do Yet

❌ **Auto-merge fixes** (needs PM approval for risk)  
❌ **Multi-org RBAC** (enterprise feature, later)  
❌ **Custom rules UI** (advanced, Phase 4+)  
❌ **Slack notifications** (nice-to-have, Phase 4+)  
❌ **SaaS billing** (separate workstream)

---

## Critical Success Factors

### 1. Phase 1 Must Ship First

**Why:** Phase 1 is what makes Railo viral  
Everything else is supporting infrastructure

### 2. Start with Warn-Only

**When shipping Phase 1:**

- Create fix PRs in warn mode (no auto-commit)
- Let teams review first
- Graduate to enforce after feedback

### 3. CI-Wait is Non-Negotiable

**Before Phase 2 goes to production:**

- Must revert fixes if CI fails
- Must never land broken code
- This is your reputation

### 4. Monitor "Fixes Merged Per Day"

**After Phase 3 ships:**

- Dashboard metric: % of fix PRs actually merged
- If <50% merge rate → something is wrong with fix quality
- Iterate on confidence gating

---

## Team Assignments Suggestion

| Phase | Backend             | Frontend          | DevOps        |
| ----- | ------------------- | ----------------- | ------------- |
| **0** | ✓ Marketing fix     |                   |               |
| **1** | ✓ PR creation logic | ✓ Docs/UI preview |               |
| **2** | ✓ Queue setup       |                   | ✓ Redis infra |
| **3** | ✓ API endpoints     | ✓ Charts/settings |               |

---

## Risk Mitigation Checklist

- [ ] **"Spam PRs"** → Start warn-only, monitor merge rate
- [ ] **"Bad fixes land"** → Implement CI-wait before shipping
- [ ] **"Parent PR breaks"** → Use separate branch strategy
- [ ] **"Rate limits hit"** → Dedup + backoff already coded
- [ ] **"Webhook timeout"** → Move to async in Phase 2

---

## Deployment Strategy

### Week 2 (End of Phase 1)

- [ ] Ship to 5 beta customers
- [ ] Watch: Do they create fix PRs? Do they merge them?
- [ ] Collect feedback on UX

### Week 4 (End of Phase 2)

- [ ] Roll out to all customers
- [ ] Zero downtime (async queue allows gradual migration)
- [ ] Monitor queue health, worker uptime

### Week 6 (End of Phase 3)

- [ ] GA with analytics dashboard
- [ ] Teams start tracking "fixes merged per day"
- [ ] Viral loop begins

---

## Metrics to Track

### Phase 1

- ✅ Fix PRs created (should be 100% of fixable vulnerabilities)
- ✅ Fix PRs merged (should be >50%)
- ✅ Customer install rate (GitHub Marketplace)

### Phase 2

- ✅ Webhook latency (<100ms)
- ✅ Queue job success rate (>99%)
- ✅ Worker uptime (>99.9%)
- ✅ Fix PR creation latency (<5 min)

### Phase 3

- ✅ Dashboard load time (<2s)
- ✅ "Fixes merged per day" trend
- ✅ Fix merge rate % (target: >75%)

---

## Next Actions (This Week)

1. **Schedule design review** for Phase 1 architecture
   - Separate branch strategy: `main` vs `base_branch`?
   - PR naming convention
   - Notification strategy

2. **Assign Phase 1 lead** (backend engineer)
   - Will own fix PR creation logic
   - Coordinate with frontend for UX

3. **Assign Phase 2 lead** (backend/DevOps)
   - Queue setup, worker architecture
   - CI monitor implementation

4. **Setup dev environment**
   - Add Redis to docker-compose
   - Test RQ with dummy jobs

5. **Create GitHub issue** for Phase 1
   - Link to this doc
   - List all subtasks
   - Set 2-week deadline

---

## Questions Before Starting

**For PM:**

1. When does invest in analytics dashboard (Phase 3)?
2. Ever auto-merge fix PRs? (Requires deep trust)
3. Slack notifications in MVP or later?

**For Engineering:**

1. Redis already available infrastructure?
2. How to test queue system locally?
3. Who owns worker deployment?

**For Design:**

1. How should fix PR look visually? (Link from original PR?)
2. Repo settings UI placement?
3. Analytics dashboard placement?

---

## Success Looks Like

**1 Month In:**

```
"We installed Railo yesterday. This morning,
I had 3 security fix PRs waiting for me.
I merged all of them in 5 minutes.
Best DevSecOps tool yet."
```

**3 Months In:**

```
"We installed Railo on all 50 repos.
We're merging 20+ security fixes per week.
Our CISO is happy. Developers don't complain.
We're telling everyone about it."
```

---

## One-Liner for the Board

> "Railo becomes Dependabot for security: automatic fix PRs that developers merge in one click."
