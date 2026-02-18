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

- 133 tests passing (deterministic behavior).
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
| **core/** | Scanner (Semgrep + ignore), fixer orchestration, git ops, status checks, PR comments, safety (idempotency, loop prevention), security (webhook validation, replay protection), rate limiting, observability, metrics. **GitHub App:** `github_app_auth` (JWT → installation token). **Dashboard:** `dashboard_auth` (OAuth login), `db` (SQLite: installations, runs). |
| **patcher/** | AST-based fixers: SQLi, secrets, XSS (templates and Python), command injection, path traversal, SSRF, JS/TS. Rule-driven, no LLM. |
| **webhook/** | Flask server that receives GitHub webhooks and triggers the fix pipeline. **Static:** `landing.html`, `privacy.html` — landing page, privacy policy, dashboard UI. |
| **github_bot/** | Utilities for opening/finding PRs (used by CLI flow). |
| **rules/** | Semgrep YAML rules (e.g. SQL injection, hardcoded secrets, XSS, command injection, path traversal, SSRF). |

### Entry points

- **GitHub Action:** `action.yml` + `entrypoint.py` — used as `IWEBai/fixpoint@v1` in user workflows.
- **Webhook server:** `webhook_server.py` — for self-hosted / on-prem deployments.
- **CLI:** `main.py` — local or scripted scans (warn or enforce, full repo or PR-diff).

### Configuration

- **Environment:** `.env` (from `.env.example`): `GITHUB_TOKEN`, `WEBHOOK_SECRET`, `FIXPOINT_MODE`, `ALLOWED_REPOS`, `DENIED_REPOS`. **GitHub App (SaaS):** `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY` (or `GITHUB_APP_PRIVATE_KEY_PATH`), `GITHUB_APP_WEBHOOK_SECRET`. **Dashboard:** `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`, `DASHBOARD_SESSION_SECRET`, `BASE_URL`. **Persistence:** `FIXPOINT_DB_PATH` (SQLite).
- **Ignore list:** `.fixpointignore` (from `.fixpointignore.example`) — excludes files/dirs from scanning.

### Security and safety

- Webhook payloads verified with HMAC-SHA256 (supports dual mode: app + repo webhook secrets).
- Replay protection via delivery IDs.
- Rate limiting to reduce abuse.
- Repository allowlist/denylist.
- No secrets in logs or URLs.

### Webhook server routes

| Route | Purpose |
|-------|---------|
| `/` | Landing page (install CTA, free beta messaging) |
| `/webhook` | GitHub webhook endpoint (POST) |
| `/dashboard` | Dashboard (OAuth login, installations, recent runs) |
| `/privacy` | Privacy policy |
| `/health` | Health check |

---

## 7. Publishing and Distribution

### Rebranding and repo setup

- All prior “AuditShield” references were replaced with “Fixpoint” (and, where applicable, `FIXPOINT_MODE`, `.fixpointignore`, `fixpoint/compliance`).
- Repository home: **[github.com/IWEBai/fixpoint](https://github.com/IWEBai/fixpoint)**.
- Docker image naming and CI use “fixpoint” (e.g. `fixpoint:test`).

### Release and marketplace

- **Versions:** v1.0.0 (initial launch) and v1.1.0 (current, January 2026).
- **GitHub Releases:** Release notes and assets (e.g. source zip/tar.gz) published for each tagged version.
- **GitHub Marketplace:** The action is published as [Fixpoint - Auto-Fix Security Vulnerabilities](https://github.com/marketplace/actions/fixpoint-auto-fix-security-vulnerabilities) (description under 125 characters, branding, categories).
- **Tags:** e.g. `v1`, `v1.0.0`, `v1.1.0` for stable usage.

### Phase 1 Launch (Backdoor Launch strategy)

- **GitHub App (SaaS):** Direct install URL `github.com/apps/fixpoint-security/installations/new` — one-click install for orgs/repos. No Marketplace signup; free beta.
- **Landing page:** Served at `/` — headline, install CTA, free beta badge, support/privacy links.
- **Dashboard:** OAuth login (GitHub), installations table, recent runs table. SQLite persistence.
- **Privacy policy:** Served at `/privacy`; also `docs/PRIVACY_POLICY.md`.
- **Docs:** PHASE1_LAUNCH_CHECKLIST.md (step-by-step launch guide), PHASE1_IMPLEMENTATION_PLAN.md, GITHUB_APP_INSTALL.md. Organization-specific URLs for IWEBai.

### Demo and documentation

- **Demo repo:** [IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo) — intentionally vulnerable Python (SQLi, secrets, XSS) and a workflow that runs Fixpoint; users can fork and open a PR to see comments or auto-fixes.
- **Docs:** Top-level README; docs index; Introduction; Getting Started; API Reference (webhook); Environment Variables; Roadmap; Changelog; GITHUB_APP_INSTALL; PRIVACY_POLICY; PHASE1_LAUNCH_CHECKLIST; PHASE1_IMPLEMENTATION_PLAN; VERIFICATION_CHECKLIST; BETA_TESTER_NOTES; WEBSITE_CONTENT; ANNOUNCEMENT_TEMPLATES.
- **Community and support:** CONTRIBUTING.md, SECURITY.md (vulnerability reporting); support@fixpoint.dev; links to website, Reddit, and Discussions.

### Community and links

- **Website:** [iwebai.space](https://www.iwebai.space)
- **Reddit:** [r/IWEBai](https://www.reddit.com/r/IWEBai/)
- **GitHub Discussions:** Enabled for the repo; optional category “Who’s using Fixpoint?” for adopters to share usage.
- **Topics (repo):** e.g. security, github-action, sql-injection, xss, secrets-detection, python, devops, devsecops, automation.

---

## 8. Current Stage (as of early 2026)

### Version and phase

- **Version:** 1.1.0 (released).
- **Phases:** Phase 1 (Trust Engine), Phase 2 (Inside the Workflow), Phase 3A (Command injection, path traversal, SSRF), and Phase 3B (JavaScript/TypeScript support) are **complete**. Phase 3C+ (Scale & Enterprise) continues.

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
| **GitHub App (SaaS)** | Direct install; installation token auth; handles `pull_request`, `installation`, `installation_repositories`. |
| **Marketplace** | Listed; users can install from Marketplace. |
| **Webhook server** | Landing, dashboard (OAuth), privacy, health; SQLite persistence. |
| **Demo repo** | [IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo) — ready to fork and test. |
| **Documentation** | README; docs index; and detailed docs (Introduction, Getting Started, API_REFERENCE, ENVIRONMENT_VARIABLES, GITHUB_APP_INSTALL, PRIVACY_POLICY, PHASE1_LAUNCH_CHECKLIST, PHASE1_IMPLEMENTATION_PLAN, VERIFICATION_CHECKLIST, BETA_TESTER_NOTES, WEBSITE_CONTENT, ANNOUNCEMENT_TEMPLATES); plus ROADMAP and CHANGELOG. |
| **Tests** | 133+ tests passing (2 skipped on Windows for Semgrep). |
| **CI** | Workflows for test, lint, Docker, release. |
| **Discussions** | Enabled; welcome post and optional “Who’s using Fixpoint?” category. |

### Technical scope (current)

- **Languages:** Python and JavaScript/TypeScript (`.py`, `.js`, `.ts`, `.jsx`, `.tsx`).
- **Vulnerabilities:** SQL injection, hardcoded secrets, XSS, command injection, path traversal, SSRF (Python); eval, secrets, DOM XSS (JS/TS).
- **Delivery:** GitHub Action, **GitHub App (direct install / SaaS)**, self-hosted webhook server, CLI.
- **Web presence:** Landing page (`/`), dashboard (`/dashboard`), privacy policy (`/privacy`).
- **Safety rails:** Max-diff threshold, optional test run before commit, CWE/OWASP tags in comments.
- **Modes:** Warn (comment only) and Enforce (auto-commit).

### What’s next (from roadmap)

- **Phase 1 Launch (in progress):** Deploy webhook server; register GitHub App; direct install URL; promotion (Reddit, HN, LinkedIn).
- **Phase 2 (Marketplace):** Apply to GitHub Marketplace after traction (100+ installs).
- **Phase 3C+ — Scale & Enterprise (planned):**
  - More languages (e.g. Go, Java, Ruby).
  - Infrastructure: e.g. Redis, retries, metrics, structured logging.
  - Enterprise: e.g. multi-repo, custom rules, compliance reporting, SSO.

---

## 9. How People Use Fixpoint

1. **GitHub App (SaaS):** Install from direct URL `github.com/apps/fixpoint-security/installations/new`; Fixpoint runs on every PR in selected repos. No GITHUB_TOKEN needed—installation token auto-generated.
2. **GitHub Action (primary):** Add a workflow that uses `IWEBai/fixpoint@v1`; Fixpoint runs on every PR (warn or enforce).
3. **Self-hosted webhook:** Run `webhook_server.py`, point GitHub webhooks at it; same behavior as the Action but on-prem.
4. **CLI:** Run `main.py` against a repo path (warn or enforce, optional PR-diff mode) for local or scripted use.

---

## 10. Principles (Unchanged)

- **Will not:** Auto-merge PRs, use AI/LLM for fixes, fix arbitrary bugs, or refactor code.
- **Will:** Support human review (warn mode), keep full audit trail, minimize diffs, stay deterministic, and optimize for time-to-merge.

---

## 11. One-Paragraph Summary

**Fixpoint** is an open-source security auto-fix tool by **IWEB** that runs at pull-request time. It detects SQL injection, hardcoded secrets, XSS, command injection, path traversal, SSRF (Python), and eval, secrets, DOM XSS (JavaScript/TypeScript). It applies **deterministic, rule-based fixes** (no AI). It is delivered as a **GitHub App** (direct install, free beta), a **GitHub Action** (`IWEBai/fixpoint@v1`), a **self-hosted webhook server** (with landing page, dashboard, privacy policy), and a **CLI**. Users can start in **warn** mode (comments only) and move to **enforce** mode (auto-commit fixes). Phase 1, 2, 3A, and 3B are complete; Phase 1 Launch (Backdoor Launch) is in progress. Community links include the IWEB website, Reddit (r/IWEBai), support@fixpoint.dev, and GitHub Discussions.

---

*Fixpoint by [IWEB](https://www.iwebai.space) — Project description document. Last updated: February 2026.*
