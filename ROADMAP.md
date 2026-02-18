# Fixpoint Roadmap

## Strategic Path

> Simple MVP → Validate trust → Expand remediation scope → CI/CD integration → Enterprise motion

This roadmap follows the principle: **Don't build the full system immediately. Validate trust first, then expand.**

**Core Framing:** **Outside → Inside the workflow.** Fixpoint moves from after-the-fact scanning to PR-time enforcement.

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

- [x] 133 tests passing
- [x] Deterministic fixes (no AI)
- [x] Full audit trail
- [x] No false positives in fixes

---

## Phase 2 — Inside the Workflow ✅ COMPLETE

**Goal:** Move Fixpoint inside the developer workflow. Enforce merge conditions.

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

## Phase 3A — Python Extensions ✅ COMPLETE

**Status:** Complete

- [x] Command injection (os.system, subprocess shell=True)
- [x] Path traversal (os.path.join validation)
- [x] SSRF detection (requests.get/post, urlopen)

---

## Phase 3B — JavaScript/TypeScript ✅ COMPLETE

**Status:** Complete

- [x] eval detection (guidance in comments)
- [x] Hardcoded secrets → process.env
- [x] DOM XSS (innerHTML → textContent)
- [x] Scanner includes .js, .ts, .jsx, .tsx

---

## Phase 3C+ — Scale & Enterprise (Next)

**Goal:** Scale to more languages and enterprise customers.

**Status:** Planned

### Language Expansion

- [ ] Go support
- [ ] Java support
- [ ] Ruby support

### Additional Vulnerability Types

- [ ] Insecure deserialization

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

## Current Version: v1.1.0

### What's Included

- **Phase 1 — Trust Engine:** SQL injection, hardcoded secrets, XSS (templates + Python) with deterministic auto-fixes.
- **Phase 2 — Inside the Workflow:** PR diff scanning, webhook server, warn/enforce modes, status checks, idempotency, loop prevention.
- **Phase 3A — Python Extensions:** Command injection, path traversal, SSRF detection.
- **Phase 3B — JavaScript/TypeScript:** eval detection (guidance), hardcoded secrets → `process.env`, DOM XSS (innerHTML → textContent).
- **Delivery options:** GitHub Action, GitHub App (SaaS), self-hosted webhook, CLI.
- **Safety rails:** Max-diff limits, optional test-before-commit, CWE/OWASP tags in comments.
- **Quality gates:** 133+ tests, CI workflows for test/lint/Docker/release.

### What's Next

- **Phase 3C+ — Scale & Enterprise:** More languages (e.g. Go, Java, Ruby), Redis-backed infrastructure, richer metrics/logging, enterprise features (multi-repo, custom rules, compliance reporting, SSO). See section above.

---

*Fixpoint by IWEB — Last updated: February 2026*
