# Fixpoint — Full Project Description

From inception to current stage. A complete, in-detail description of the Fixpoint project by IWEB.

---

## 1. Origin and Naming

- **Earlier name:** The project was originally developed under the name **AuditShield** (or similar). All references to that name were later updated across the codebase.
- **Current name:** **Fixpoint** — chosen to reflect the product’s role: a fixed point in the development workflow where security issues are detected and corrected before merge.
- **Organization:** The project is owned and maintained by **IWEB** (GitHub: [IWEBai](https://github.com/IWEBai)). IWEB builds AI, ML, Big Data, and software solutions.
- **License:** MIT. The code is open for use, modification, and distribution; IWEB retains copyright and the project can be used commercially (including by IWEB as a SaaS or commercial offering).

---

## 2. Vision and Problem

### The problem

- Security scans often find the same classes of issues (SQL injection, hardcoded secrets, XSS) in pull requests.
- Fixing them manually is repetitive and slows down merges.
- Developers lose context; security and release cycles stretch from days to a week or more.

### The vision

- **Fixpoint** runs at PR time, inside the workflow.
- It **detects** well-defined vulnerability patterns and **applies deterministic fixes** (no AI/LLM).
- Same input → same output. Teams can start in **warn** mode (comments only), then move to **enforce** mode (auto-commit fixes) once they trust the tool.
- Goal: reduce time-to-merge for security-related fixes from days to minutes, without sacrificing safety or auditability.

### What Fixpoint does *not* do

- It does not fix arbitrary bugs, refactor code, auto-merge PRs, or generate creative fixes.
- It does not use AI/LLMs for remediation. All fixes are rule-based and deterministic.

---

## 3. Strategic Path and Phases

The roadmap follows: **Simple MVP → Validate trust → Expand scope → CI/CD integration → Enterprise.**

**Core idea:** Move from “outside” (after-the-fact scanning) to **inside the workflow** (PR-time enforcement).

---

## 4. Phase 1 — Trust Engine (Complete)

**Goal:** Prove that teams will accept automated security fixes.

### What was built

- **Language:** Python (application and fix logic).
- **Detection:** Semgrep rules plus custom AST-based parsing for precise code patterns.
- **Vulnerability coverage:**
  - **SQL injection:** f-strings, concatenation, `.format()`, `%` formatting → converted to parameterized queries.
  - **Hardcoded secrets:** Passwords, API keys, tokens, database URIs → replaced with `os.environ.get()` (or equivalent).
  - **XSS (templates):** `|safe` filter, `{% autoescape off %}` → unsafe patterns removed.
  - **XSS (Python):** `mark_safe()`, `SafeString()` → replaced with `escape()`.
- **Output:** PR comments (warn) or direct commits (enforce).
- **Integration:** GitHub Action and a self-hosted webhook server.

### Success criteria met

- 119 tests passing (deterministic behavior).
- No AI; full audit trail; no known false positives in the applied fixes.

---

## 5. Phase 2 — Inside the Workflow (Complete)

**Goal:** Make Fixpoint part of the developer workflow and enforce merge conditions.

### Features delivered

- **PR diff scanning:** Only changed files in the PR are scanned.
- **Webhook handling:** Listens for `pull_request` (opened, synchronize, reopened); runs in real time.
- **Push to existing PR branch:** Fixes are committed to the PR branch so the author sees one updated branch.
- **Safety:**
  - **Idempotency:** Same fix is not applied twice.
  - **Loop prevention:** Commits from the bot do not trigger another run.
  - **Confidence gating:** Only high-confidence findings are auto-fixed.
- **Two modes:**
  - **Warn (default):** Post comments with proposed fixes; set status check to FAIL; no commits.
  - **Enforce:** Apply fixes, commit, set status check to PASS.
- **Status check:** `fixpoint/compliance` — PASS when there are no violations or all are fixed; FAIL when violations remain (e.g. in warn mode).

---

## 6. Technical Architecture

### Components

| Component | Role |
|-----------|------|
| **core/** | Scanner (Semgrep + ignore), fixer orchestration, git ops, status checks, PR comments, safety (idempotency, loop prevention), security (webhook validation, replay protection), rate limiting, observability, metrics. |
| **patcher/** | AST-based fixers: SQLi, secrets, XSS (templates and Python). Rule-driven, no LLM. |
| **webhook/** | Flask server that receives GitHub webhooks and triggers the fix pipeline. |
| **github_bot/** | Utilities for opening/finding PRs (used by CLI flow). |
| **rules/** | Semgrep YAML rules (e.g. SQL injection, hardcoded secrets, XSS). |

### Entry points

- **GitHub Action:** `action.yml` + `entrypoint.py` — used as `IWEBai/fixpoint@v1` in user workflows.
- **Webhook server:** `webhook_server.py` — for self-hosted / on-prem deployments.
- **CLI:** `main.py` — local or scripted scans (warn or enforce, full repo or PR-diff).

### Configuration

- **Environment:** `.env` (from `.env.example`): e.g. `GITHUB_TOKEN`, `WEBHOOK_SECRET`, `FIXPOINT_MODE`, `ALLOWED_REPOS`, `DENIED_REPOS`.
- **Ignore list:** `.fixpointignore` (from `.fixpointignore.example`) — excludes files/dirs from scanning.

### Security and safety

- Webhook payloads verified with HMAC-SHA256.
- Replay protection via delivery IDs.
- Rate limiting to reduce abuse.
- Repository allowlist/denylist.
- No secrets in logs or URLs.

---

## 7. Publishing and Distribution

### Rebranding and repo setup

- All prior “AuditShield” references were replaced with “Fixpoint” (and, where applicable, `FIXPOINT_MODE`, `.fixpointignore`, `fixpoint/compliance`).
- Repository home: **[github.com/IWEBai/fixpoint](https://github.com/IWEBai/fixpoint)**.
- Docker image naming and CI use “fixpoint” (e.g. `fixpoint:test`).

### Release and marketplace

- **Version:** v1.0.0 (January 2026).
- **GitHub Release:** Release notes and assets (e.g. source zip/tar.gz) published for v1.0.0.
- **GitHub Marketplace:** The action is published as [Fixpoint - Auto-Fix Security Vulnerabilities](https://github.com/marketplace/actions/fixpoint-auto-fix-security-vulnerabilities) (description under 125 characters, branding, categories).
- **Tags:** e.g. `v1`, `v1.0.0` for stable usage.

### Demo and documentation

- **Demo repo:** [IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo) — intentionally vulnerable Python (SQLi, secrets, XSS) and a workflow that runs Fixpoint; users can fork and open a PR to see comments or auto-fixes.
- **Docs:** README, Introduction, Getting Started, API Reference (webhook), Environment Variables, Roadmap, Changelog.
- **Community and support:** CONTRIBUTING.md, SECURITY.md (vulnerability reporting); links to website, Reddit, and Discussions.

### Community and links

- **Website:** [iwebai.space](https://www.iwebai.space)
- **Reddit:** [r/IWEBai](https://www.reddit.com/r/IWEBai/)
- **GitHub Discussions:** Enabled for the repo; optional category “Who’s using Fixpoint?” for adopters to share usage.
- **Topics (repo):** e.g. security, github-action, sql-injection, xss, secrets-detection, python, devops, devsecops, automation.

---

## 8. Current Stage (as of early 2026)

### Version and phase

- **Version:** 1.0.0 (1.1.0 in development).
- **Phases:** Phase 1 (Trust Engine), Phase 2 (Inside the Workflow), and Phase 3A/3B (Python + JS/TS) are **complete**. Phase 3 (Scale & Enterprise) continues.

### 2026 Product Promise

- **Deterministic fixes only** — No AI/LLM for remediation.
- **Python + JavaScript/TypeScript** — Full coverage for common vulnerabilities.
- **Safety rails** — Max-diff, test-before-commit, CWE/OWASP tags.
- **Warn then enforce** — Trust-first rollout.

### What is live today

| Item | Status |
|------|--------|
| **GitHub repo** | Public: [IWEBai/fixpoint](https://github.com/IWEBai/fixpoint). |
| **GitHub Action** | `IWEBai/fixpoint@v1` — usable in any repo with a workflow file. |
| **Marketplace** | Listed; users can install from Marketplace. |
| **Demo repo** | [IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo) — ready to fork and test. |
| **Documentation** | README, docs (Introduction, Getting Started, API Reference, Environment Variables), ROADMAP, CHANGELOG. |
| **Tests** | 119 tests passing (2 skipped on Windows for Semgrep). |
| **CI** | Workflows for test, lint, Docker, release. |
| **Discussions** | Enabled; welcome post and optional “Who’s using Fixpoint?” category. |

### Technical scope (current)

- **Languages:** Python only.
- **Vulnerabilities:** SQL injection, hardcoded secrets, XSS, command injection, path traversal, SSRF (detection).
- **Delivery:** GitHub Action, self-hosted webhook server, CLI.
- **Safety rails:** Max-diff threshold, optional test run before commit, CWE/OWASP tags in comments.
- **Modes:** Warn (comment only) and Enforce (auto-commit).

### What’s next (from roadmap)

- **Phase 3 — Scale & Enterprise (planned):**
  - More languages (e.g. JavaScript/TypeScript, Go, Java).
  - Phase 3A delivered: command injection, path traversal, SSRF (detection).
  - Infrastructure: e.g. Redis, retries, metrics, structured logging.
  - Enterprise: e.g. multi-repo, custom rules, compliance reporting, SSO.
- **Commercial/SaaS:** Option to offer hosted Fixpoint or enterprise support (license permits; not built yet).

---

## 9. How People Use Fixpoint

1. **GitHub Action (primary):** Add a workflow that uses `IWEBai/fixpoint@v1`; Fixpoint runs on every PR (warn or enforce).
2. **Self-hosted webhook:** Run `webhook_server.py`, point GitHub webhooks at it; same behavior as the Action but on-prem.
3. **CLI:** Run `main.py` against a repo path (warn or enforce, optional PR-diff mode) for local or scripted use.

---

## 10. Principles (Unchanged)

- **Will not:** Auto-merge PRs, use AI/LLM for fixes, fix arbitrary bugs, or refactor code.
- **Will:** Support human review (warn mode), keep full audit trail, minimize diffs, stay deterministic, and optimize for time-to-merge.

---

## 11. One-Paragraph Summary

**Fixpoint** is an open-source security auto-fix tool by **IWEB** that runs at pull-request time. It detects SQL injection, hardcoded secrets, and XSS in Python code and applies **deterministic, rule-based fixes** (no AI). It is delivered as a **GitHub Action** (`IWEBai/fixpoint@v1`), a **self-hosted webhook server**, and a **CLI**. Users can start in **warn** mode (comments only) and move to **enforce** mode (auto-commit fixes). The project went through a full rebrand from its earlier name, was released as **v1.0.0** on GitHub and the GitHub Marketplace, given a **demo repo** and full **documentation**, and is currently at **Phase 2 complete** with **Phase 3 (more languages and enterprise)** planned. Community links include the IWEB website, Reddit (r/IWEBai), and GitHub Discussions.

---

*Fixpoint by [IWEB](https://www.iwebai.space) — Project description document. Last updated: February 2026.*
