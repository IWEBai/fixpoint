# AuditShield Roadmap

## Strategic Path

> Simple MVP → Validate trust → Expand remediation scope → CI/CD integration → Enterprise motion

This roadmap follows the principle: **Don't build the full system immediately. Validate trust first, then expand.**

**Core Framing:** **Outside → Inside the workflow.** AuditShield moves from after-the-fact scanning to PR-time enforcement.

---

## Phase 1 — Trust Engine (Current MVP) ✅

**Goal:** Prove that teams will accept automated compliance fixes.

**Status:** In Progress

### What We're Building

- **Language:** Python only
- **Detection:** Semgrep rules
- **Violation:** SQL injection via string formatting
- **Fix:** Parameterized queries (deterministic)
- **Output:** Git branch + commit + Pull Request
- **Integration:** CLI-based, manual execution

### Success Metrics

- [ ] Teams accept automated PRs without rejection
- [ ] Developers trust the fixes (low revert rate)
- [ ] Compliance teams approve the audit trail
- [ ] No false positives in fixes

### Key Constraints (Trust-Building)

- ❌ No auto-merging
- ❌ No creative fixes
- ❌ No probabilistic changes
- ✅ Deterministic fixes only
- ✅ Minimal diffs
- ✅ Full audit trail

### Current Limitations (By Design)

- Only processes first finding (MVP scope)
- Hardcoded to specific SQL injection pattern
- Single language (Python)
- CLI-based (not integrated into CI/CD)

---

## Phase 2 — Inside the Workflow

**Goal:** Move AuditShield inside the developer workflow. Enforce merge conditions.

**Status:** In Progress ✅

### Core Concept

**Async → Sync:** Move from after-the-fact scanning to PR-time enforcement.

**Outside → Inside:** Live in PRs/CI, not separate dashboards.

**Warn → Enforce:** Start with comments, graduate to status checks.

### Core Features

#### 2.1 PR Diff Scanning ✅

- ✅ Scan only changed files in PR
- ✅ Focus on new violations (not entire codebase)
- ✅ Faster execution
- ✅ More relevant fixes
- See `core/scanner.py` for implementation

#### 2.2 PR Webhook Listening ✅

- ✅ Listen to `pull_request.opened` events
- ✅ Listen to `pull_request.synchronize` events
- ✅ Automatic scanning on PR creation/update
- ✅ Real-time remediation
- See `webhook/server.py` and `webhook_server.py`

#### 2.3 Push to Existing PR Branch ✅

- ✅ Instead of creating new branches, push to existing PR
- ✅ Update PR with fix commit
- ✅ Seamless developer experience
- See `core/git_ops.py` for implementation

#### 2.4 Safety Mechanisms ✅

- ✅ **Idempotency** — Prevents re-applying same fix
- ✅ **Loop prevention** — Bot commits don't trigger bot again
- ✅ **Confidence gating** — Only fixes high-confidence findings
- See `core/safety.py` for implementation

#### 2.5 Two-Mode Rollout (Next)

**Warn Mode** (default):
- Comments on PR with findings
- Proposes fixes without applying
- No merge blocking
- Builds trust gradually

**Enforce Mode** (opt-in):
- Sets status check results
- Can apply fixes automatically
- Blocks merge until compliant
- Requires team trust

**Adoption Path:** Teams start in warn mode, graduate to enforce mode.

#### 2.6 Status Check Semantics (Next)

Set GitHub status check results:

- **PASS** if no violations found
- **FAIL** if violation found and not fixed
- **PASS** if violation found and fixed by bot commit

This is what makes AuditShield a **gate** in GitHub terms.

#### 2.7 GitHub App Integration (Coming Soon)

- Native GitHub App installation
- Fine-grained permissions
- Better security model
- Repository-level configuration

#### 2.8 AST-Based Detection + Transformation (Future)

- Move from regex to AST parsing
- More accurate pattern matching
- Support for complex code structures
- Better variable extraction

#### 2.9 Propose → Apply Model (Future)

**Propose Mode:**
- Comments with fix suggestions
- Developer reviews and applies manually
- Lower risk, higher trust

**Apply Mode:**
- Automatically commits fixes
- Requires explicit opt-in
- Higher automation, requires trust

### Expanded Coverage (Still Deterministic)

- **Languages:** Python, JavaScript, TypeScript, Go
- **Violations:**
  - SQL injection (all patterns)
  - PII logging
  - Weak crypto (hardcoded secrets)
  - Secrets in code
  - Misconfigurations (security headers, etc.)

### Success Metrics

- [ ] 80%+ of compliance violations auto-fixed
- [ ] <5% false positive rate
- [ ] <2% revert rate
- [ ] Integration in 10+ production repos
- [ ] **Time-to-merge reduced by 50%+ for compliance-blocking PRs**

---

## Phase 3 — Enterprise Motion

**Goal:** Scale to enterprise customers with advanced features.

**Status:** Future

### Enterprise Features

- **Multi-repository management**
- **Custom rule sets** (organization-specific)
- **Compliance reporting** (SOC2, ISO 27001)
- **Metrics collection** (CSV export, email reports - NO dashboard yet)
- **Policy enforcement** (block merges until fixed)
- **SSO integration**
- **Role-based access control**

### Business Model

- **Self-service:** Free tier for open source
- **Team:** $X/month per repository
- **Enterprise:** Custom pricing, dedicated support

---

## Principles

### What We Will NOT Do

- ❌ Auto-merge PRs (ever)
- ❌ Generate creative fixes
- ❌ Fix arbitrary bugs
- ❌ Refactor code
- ❌ Expand beyond deterministic fixes (initially)

### What We Will Always Do

- ✅ Require human review (in warn mode)
- ✅ Provide full audit trail
- ✅ Keep diffs minimal
- ✅ Build trust through determinism
- ✅ Focus on compliance workflow acceleration
- ✅ Measure **time-to-merge** as primary metric

### AI/LLM Position

**Deterministic-first:** All fixes use rule-based templates.

**LLM as constrained helper** (future, optional):
- Only for formatting/refinement
- Within deterministic templates
- Verified by tests/lints
- Minimal, explainable patches

**Current:** Program repair first. LLM optional later.

---

## Timeline (Tentative)

- **Q1 2026:** Phase 1 validation (Trust Engine)
- **Q2 2026:** Phase 2 development (Inside workflow, warn → enforce)
- **Q3 2026:** Phase 2 launch (Status checks, GitHub App)
- **Q4 2026:** Phase 3 planning (Enterprise features)

**Note:** Timeline depends entirely on Phase 1 validation. If trust isn't proven, we iterate on Phase 1 before moving forward.

---

## Founder Advice

> "If you try to build the full v2 system immediately: You will overbuild, you will slow down, you will miss market learning."

**Focus:** Validate Phase 1 completely before expanding scope.

**Key Insight:** **Outside → Inside** is the winning strategy. Live in PRs/CI, not dashboards.
