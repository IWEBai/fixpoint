# AuditShield Roadmap

## Strategic Path

> Simple MVP → Validate trust → Expand remediation scope → CI/CD integration → Enterprise motion

This roadmap follows the principle: **Don't build the full system immediately. Validate trust first, then expand.**

**Core Framing:** **Outside → Inside the workflow.** AuditShield moves from after-the-fact scanning to PR-time enforcement.

---

## Phase 1 — Trust Engine ✅ COMPLETE

**Goal:** Prove that teams will accept automated compliance fixes.

**Status:** Complete

### What We Built

- **Language:** Python
- **Detection:** AST-based parsing + Semgrep rules
- **Violations:** SQL injection, hardcoded secrets, XSS
- **Fix:** Deterministic transformations
- **Output:** PR comments (warn) or commits (enforce)
- **Integration:** GitHub Action + Webhook server

### Vulnerability Coverage

| Type | Detection | Auto-Fix |
|------|-----------|----------|
| SQL Injection | f-string, concat, format, % | ✅ Parameterized queries |
| Hardcoded Secrets | Passwords, API keys, tokens | ✅ `os.environ.get()` |
| XSS (Templates) | \|safe, autoescape off | ✅ Remove unsafe filters |
| XSS (Python) | mark_safe, SafeString | ✅ Replace with escape() |

### Success Metrics

- [x] 119 tests passing
- [x] Deterministic fixes (no AI)
- [x] Full audit trail
- [x] No false positives in fixes

---

## Phase 2 — Inside the Workflow ✅ COMPLETE

**Goal:** Move AuditShield inside the developer workflow. Enforce merge conditions.

**Status:** Complete

### Core Features

#### 2.1 PR Diff Scanning ✅
- Scan only changed files in PR
- Focus on new violations

#### 2.2 PR Webhook Listening ✅
- `pull_request.opened` events
- `pull_request.synchronize` events
- Real-time remediation

#### 2.3 Push to Existing PR Branch ✅
- Update PR with fix commits
- Seamless developer experience

#### 2.4 Safety Mechanisms ✅
- **Idempotency** — Prevents re-applying same fix
- **Loop prevention** — Bot commits don't trigger bot again
- **Confidence gating** — Only fixes high-confidence findings

#### 2.5 Two-Mode Rollout ✅

**Warn Mode** (default):
- Comments on PR with proposed fixes
- Sets status check to FAIL
- No commits made

**Enforce Mode** (opt-in):
- Applies fixes automatically
- Commits to PR branch
- Sets status check to PASS

#### 2.6 Status Check Semantics ✅

- **PASS** if no violations found
- **FAIL** if violations found (warn mode)
- **PASS** if violations fixed (enforce mode)

---

## Phase 3 — Scale & Enterprise (Next)

**Goal:** Scale to more languages and enterprise customers.

**Status:** Planned

### Language Expansion

- [ ] JavaScript/TypeScript support
- [ ] Go support
- [ ] Java support

### Additional Vulnerability Types

- [ ] Path traversal detection
- [ ] Command injection detection
- [ ] Insecure deserialization
- [ ] SSRF detection

### Infrastructure

- [ ] Redis for distributed state
- [ ] Retry logic for API calls
- [ ] Prometheus metrics
- [ ] Structured logging

### Enterprise Features

- [ ] Multi-repository management
- [ ] Custom rule sets
- [ ] Compliance reporting
- [ ] SSO integration

---

## Principles

### What We Will NOT Do

- ❌ Auto-merge PRs (ever)
- ❌ Generate creative fixes
- ❌ Fix arbitrary bugs
- ❌ Refactor code
- ❌ Use AI/LLM for fixes

### What We Will Always Do

- ✅ Require human review (in warn mode)
- ✅ Provide full audit trail
- ✅ Keep diffs minimal
- ✅ Build trust through determinism
- ✅ Focus on compliance workflow acceleration
- ✅ Measure **time-to-merge** as primary metric

---

## Current Version: v1.0.0

### What's Included

- SQL injection detection + auto-fix (4 patterns)
- Hardcoded secrets detection + auto-fix
- XSS detection + auto-fix (templates + Python)
- GitHub Action integration
- Self-hosted webhook server
- Warn mode and Enforce mode
- Status checks
- 119 tests

### What's Next

- More languages (JavaScript, Go)
- More vulnerability types
- Enterprise features
- GitHub Marketplace listing

---

*Last updated: January 2026*
