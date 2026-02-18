# Phase 1 Implementation Plan

Minimal implementation plan to complete the Phase 1 checklist for the Backdoor Launch. Focus: minimal, achievable, ready for Marketplace in Phase 2.

---

## Overview

| Component | Scope | Effort |
|-----------|-------|--------|
| 1. Dashboard | Minimal: OAuth + installations + recent runs table | Medium |
| 2. Landing page | Static HTML + install CTA + free beta | Low |
| 3. Support + privacy | Email + single-page privacy policy | Low |
| 4. Branding | Logo + feature card (or placeholders) | Low |

---

## 1. Minimal Dashboard

### 1.1 Architecture

```
User → Browser → fixpoint.dev/dashboard
         ↓
    GitHub OAuth (authorize)
         ↓
    Dashboard: installations, recent runs
```

- **Stack:** Same Flask app (`webhook/server.py`) or separate `dashboard/` module; add OAuth routes.
- **Storage:** SQLite for Phase 1 (e.g. `fixpoint.db`). Tables: `installations`, `runs`, `oauth_sessions`.
- **OAuth:** GitHub OAuth App (separate from Fixpoint *GitHub App*). Scope: `read:user`, `read:org` (or `user:email` minimal).

### 1.2 Data Model

**Installations** (synced from webhook `installation` events):

| Column | Type |
|--------|------|
| id | INTEGER PK |
| installation_id | INTEGER UNIQUE (GitHub install ID) |
| account_login | TEXT |
| account_type | TEXT (Organization/User) |
| created_at | TIMESTAMP |
| updated_at | TIMESTAMP |

**Runs** (from `record_metric` and webhook processing):

| Column | Type |
|--------|------|
| id | INTEGER PK |
| installation_id | INTEGER FK |
| repo | TEXT |
| pr_number | INTEGER |
| status | TEXT (success, warn_mode, error, ...) |
| violations_found | INTEGER |
| violations_fixed | INTEGER |
| timestamp | TIMESTAMP |
| correlation_id | TEXT |

### 1.3 Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/dashboard` | GET | Redirect to GitHub OAuth if not logged in |
| `/dashboard/callback` | GET | OAuth callback, create session, redirect to dashboard |
| `/dashboard/logout` | GET | Clear session |
| `/dashboard/` | GET | Main dashboard: list installations, table of recent runs |
| `/api/dashboard/installations` | GET | JSON: installations (for current user) |
| `/api/dashboard/runs` | GET | JSON: recent runs (paginated) |

### 1.4 Implementation Steps

1. **Add SQLite layer**
   - `core/db.py`: init DB, migrations (or simple `CREATE TABLE IF NOT EXISTS`).
   - Wire `record_metric` to also insert into `runs` table when `installation_id` is available.

2. **Persist installation events**
   - In webhook handler for `installation` and `installation_repositories`: insert/update `installations` table.
   - Need to map installation → account. GitHub API: `GET /app/installations/{id}` with JWT returns `account.login`.

3. **GitHub OAuth**
   - Register OAuth App on GitHub: `https://github.com/settings/developers` → New OAuth App.
   - Callback URL: `https://fixpoint.dev/dashboard/callback` (or your domain).
   - Env: `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`.
   - Use `requests` or `authlib` for OAuth flow.

4. **Dashboard UI**
   - Single HTML page, server-rendered (Jinja2) or minimal SPA.
   - Table: timestamp, repo, status, findings, link to PR.
   - "Install Fixpoint" button → `github.com/apps/fixpoint-security/installations/new`.

### 1.5 Dependencies

- `authlib` or `requests` for OAuth.
- SQLite (stdlib).
- Optional: `Jinja2` for templates (Flask includes it).

---

## 2. Landing Page

### 2.1 Content

- **Headline:** "Auto-fix security vulnerabilities in your PRs"
- **Subhead:** "Free beta for early adopters"
- **CTA:** "Install Fixpoint" → `https://github.com/apps/fixpoint-security/installations/new`
- **Features:** 3–4 bullets (SQLi, secrets, XSS, deterministic).
- **Footer:** Support (support@fixpoint.dev), Privacy Policy link.

### 2.2 Implementation

**Option A: Static HTML in repo**

- `webhook/static/landing.html` or `landing/index.html`.
- Serve at `/` or `fixpoint.dev` root.
- Flask: `@app.route("/")` → `send_static_file("landing.html")` or `render_template`.

**Option B: Deploy separately**

- Vercel/Netlify for `fixpoint.dev` with static HTML.
- Install button links to GitHub App URL.

**Recommendation:** Option A. Single deploy, single domain.

### 2.3 Structure

```
/                    → Landing page
/webhook             → Webhook endpoint (existing)
/dashboard           → Dashboard (after OAuth)
/health              → Health check (existing)
```

---

## 3. Support Email + Privacy Policy

### 3.1 Support

- Create `support@fixpoint.dev` (or your domain).
- Add to README, landing page, dashboard footer.
- No code changes; mail provider setup (e.g. Google Workspace, Cloudflare Email).

### 3.2 Privacy Policy

- Single page: `https://fixpoint.dev/privacy` or `/privacy`.
- Content: what data we collect (PR diffs, repo names, installation IDs), how we use it, no selling, GitHub ToS.
- Implementation: static HTML or Markdown rendered to HTML.

**Minimal template sections:**

1. Data we collect (webhook payloads, installation IDs, repo names).
2. How we use it (running security scans, applying fixes).
3. We do not sell data.
4. GitHub's ToS applies.
5. Contact: support@fixpoint.dev.

### 3.3 Files to Add

- `docs/PRIVACY_POLICY.md` or `webhook/static/privacy.html`
- Route: `GET /privacy` → serve policy

---

## 4. Branding

### 4.1 Logo

- **Size:** 128×128 minimum (GitHub App requires; Marketplace uses larger).
- **Format:** PNG, square.
- **Placeholder:** Use a simple "F" or shield icon until final design.
- **Location:** `webhook/static/logo.png` or `assets/logo.png`.

### 4.2 Feature Card

- **Size:** 1280×640 (GitHub Marketplace).
- **Content:** Fixpoint name, tagline, maybe screenshot of PR comment.
- **Placeholder:** Solid color + text until design ready.
- **Location:** `assets/feature-card.png`.

### 4.3 Implementation

- Add `assets/` directory.
- Use placeholder images or generate simple ones (e.g. via Pillow script).
- Reference in README, landing page.

---

## 5. README / Docs Updates

### 5.1 Add to README

- Direct install link: `[Install Fixpoint](https://github.com/apps/fixpoint-security/installations/new)` (replace with actual app slug).
- "Free beta for early adopters" badge or line.
- Support: support@fixpoint.dev.
- Privacy: link to `/privacy` or fixpoint.dev/privacy.

### 5.2 New Doc

- `docs/GITHUB_APP_INSTALL.md`: How to install the app, what permissions, what happens after install.

---

## 6. Recommended Order

| Order | Task | Depends on |
|-------|------|------------|
| 1 | Privacy policy page + route | None |
| 2 | Support email (create mailbox, add to docs) | None |
| 3 | README: install URL, free beta, support, privacy | 1, 2 |
| 4 | Landing page (HTML + CTA) | 3 |
| 5 | Logo + feature card placeholders | None |
| 6 | SQLite + persist runs from metrics | Webhook |
| 7 | Persist installations from webhook | 6 |
| 8 | GitHub OAuth App + callback | None |
| 9 | Dashboard routes + UI | 6, 7, 8 |

**Fast path (1–2 days):** 1, 2, 3, 4, 5.  
**Full dashboard (1 week):** 6–9.

---

## 7. Environment Variables (New)

| Variable | Purpose |
|----------|---------|
| `GITHUB_OAUTH_CLIENT_ID` | OAuth App client ID |
| `GITHUB_OAUTH_CLIENT_SECRET` | OAuth App client secret |
| `DASHBOARD_SESSION_SECRET` | Cookie signing for OAuth session |
| `BASE_URL` | e.g. `https://fixpoint.dev` (for OAuth redirect) |

---

## 8. Deployment Notes

- Webhook URL: `https://fixpoint.dev/webhook`
- OAuth callback: `https://fixpoint.dev/dashboard/callback`
- Ensure HTTPS; cookies `Secure`, `SameSite=Lax`
- SQLite file: persistent volume (e.g. `/data/fixpoint.db`)

---

## 9. Out of Scope (Phase 1)

- Billing / Stripe
- Marketplace application
- SSO, audit logs
- Multi-tenant isolation beyond installation_id
