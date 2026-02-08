# Announcement Templates

Use these templates to share Fixpoint and get early users. Copy, customize, and post.

---

## GitHub Discussions (General / Announcements)

**Title:** Fixpoint v1.1.0 — Auto-fix security vulnerabilities in your PRs (Python + JS/TS)

**Body:**

---

We just released **Fixpoint v1.1.0** — a deterministic security patch bot that runs at PR time.

**What it does:**
- Detects SQL injection, hardcoded secrets, XSS, command injection, path traversal, SSRF (Python)
- Detects eval, secrets, DOM XSS (JavaScript/TypeScript)
- Applies **rule-based fixes** (no AI) — same input → same output
- Two modes: **warn** (comments only) or **enforce** (auto-commit fixes)

**Try it in 2 minutes:**
1. Add the [GitHub Action](https://github.com/IWEBai/fixpoint#quick-start) to your repo
2. Open a PR with vulnerable code
3. Fixpoint scans and either comments or fixes

**Demo repo:** [IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo) — fork it and open a PR to see it in action.

---

**Quick question for the community:** Would you pay for a **hosted version** (no self-hosting, no GitHub Action setup)? Or what would make Fixpoint worth paying for? Reply below — your feedback shapes what we build next.

---

*Fixpoint by [IWEB](https://www.iwebai.space) — MIT licensed.*

---

## Reddit (r/devsecops, r/devops, r/python, r/javascript)

**Title:** I built a security auto-fix bot for PRs — no AI, deterministic fixes (Python + JS/TS)

**Body:**

---

**Fixpoint** — runs at PR time and auto-fixes common vulnerabilities:

- SQL injection → parameterized queries
- Hardcoded secrets → `os.environ.get()` / `process.env`
- XSS → removes unsafe filters
- Command injection → safe subprocess
- Path traversal → path validation
- And more (JS/TS: eval, DOM XSS)

**No AI.** Rule-based. Same input → same output. Start in warn mode (comments only), graduate to enforce (auto-commit).

**Try it:** [github.com/IWEBai/fixpoint](https://github.com/IWEBai/fixpoint) — add the GitHub Action, open a PR. That's it.

Demo: [IWEBai/fixpoint-demo](https://github.com/IWEBai/fixpoint-demo)

---

**Question:** Would you pay for a hosted version (no setup, no self-hosting)? What would make it worth it for you?

---

## Twitter/X

**Tweet (under 280 chars):**

Fixpoint v1.1.0 — Auto-fix SQLi, secrets, XSS, command injection in your PRs. Python + JS/TS. No AI, deterministic. Try it: github.com/IWEBai/fixpoint 🛡️

---

**Follow-up prompt:**

Would you pay for a hosted version? Reply with what you'd need.

---

## Hacker News (Show HN)

**Title:** Show HN: Fixpoint – Auto-fix security vulnerabilities in PRs (Python + JS/TS)

**Body:**

Fixpoint is a deterministic security patch bot that runs at pull-request time. It detects SQL injection, hardcoded secrets, XSS, command injection, path traversal, SSRF (and more for JS/TS) and applies rule-based fixes — no AI, same input → same output.

You can start in warn mode (comments only) and move to enforce mode (auto-commit) when you trust it. One GitHub Action, zero config.

https://github.com/IWEBai/fixpoint

Demo repo: https://github.com/IWEBai/fixpoint-demo

I'd love feedback: Would a hosted version (no self-hosting) be useful? What would make it worth paying for?

---

## LinkedIn / Professional Post

**Title:** Shipping secure code faster: Fixpoint auto-fixes vulnerabilities at PR time

**Body:**

Security scans often find the same issues — SQL injection, hardcoded secrets, XSS — and fixing them manually slows down merges. We built **Fixpoint** to fix that.

Fixpoint runs at PR time, detects these patterns, and applies deterministic fixes. No AI, no hallucinations. Start in warn mode (review first), then enforce (auto-commit when you're ready).

Now supports Python and JavaScript/TypeScript. One GitHub Action. Open source, MIT.

Try it: [github.com/IWEBai/fixpoint](https://github.com/IWEBai/fixpoint)

---

**Question for DevOps/Security folks:** Would you pay for a hosted version? What would sway your team to adopt it?

---

*Templates last updated: February 2026*
