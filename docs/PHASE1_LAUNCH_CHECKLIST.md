# Phase 1 Launch Checklist

Complete step-by-step guide for launching Fixpoint as a GitHub App (Backdoor Launch strategy).

**Organization vs Personal:** If your repo is under an organization (e.g. IWEBai/fixpoint), use the **organization** URLs in sections 1 and 3. The app will be owned by the org. Everything else is the same.

---

## Table of Contents

1. [Register the GitHub App](#1-register-the-github-app)
2. [Update Install URL Slug](#2-update-install-url-slug)
3. [Create GitHub OAuth App](#3-create-github-oauth-app)
4. [Set Up Support Email](#4-set-up-support-email)
5. [Prepare Branding Assets](#5-prepare-branding-assets)
6. [Deploy the Webhook Server](#6-deploy-the-webhook-server)
7. [Deployment Verification](#7-deployment-verification)
8. [Launch & Promotion](#8-launch--promotion)
9. [What to Avoid in Phase 1](#9-what-to-avoid-in-phase-1)

---

## 1. Register the GitHub App

**Where:**

- **Organization (e.g. IWEBai):** [https://github.com/organizations/IWEBai/settings/apps](https://github.com/organizations/IWEBai/settings/apps) → **New GitHub App**  
  Or: **IWEBai** → **Settings** → **Developer settings** → **GitHub Apps**

- **Personal account:** [https://github.com/settings/apps](https://github.com/settings/apps) → **New GitHub App**

*Org admins only: You need org admin or Developer settings access to create apps under the organization.*

### Basic Information

| Field | Value |
|-------|-------|
| **GitHub App name** | `Fixpoint` or `Fixpoint Security` |
| **Description** | Auto-fix security vulnerabilities in your PRs. Deterministic, rule-based patches. |
| **Homepage URL** | `https://fixpoint.dev` (or your domain) |

### Webhook Configuration

| Field | Value |
|-------|-------|
| **Webhook URL** | `https://fixpoint.dev/webhook` |
| **Webhook secret** | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` — save this for `GITHUB_APP_WEBHOOK_SECRET` |
| **Webhook - Active** | ✅ Checked |

### Permissions & Events

**Repository permissions:**

| Permission | Access Level |
|------------|--------------|
| Contents | Read and write |
| Pull requests | Read and write |
| Statuses | Read and write |

**Subscribe to events:**

- [x] Pull request
- [x] Installation
- [x] Installation repositories

### Where can this GitHub App be installed?

- **Only on this account** — if you want it only on your org (or only on your user)
- **Any account** — for public distribution (recommended for Phase 1)

*For organization-owned apps: "Only on this account" = only that org; "Any account" = any org or user can install.*

### Post-creation

1. Click **Create GitHub App**
2. Go to **General** → **Generate a private key** → download the `.pem` file
3. Note your **App ID** (e.g. `12345`)
4. Note your **install URL** (e.g. `https://github.com/apps/fixpoint-security/installations/new`)

---

## 2. Update Install URL Slug

If your GitHub App slug is **not** `fixpoint-security`, update it in these files:

| File | Location | What to change |
|------|----------|----------------|
| `webhook/static/landing.html` | Line ~27 | `https://github.com/apps/fixpoint-security/installations/new` |
| `webhook/server.py` | ~line 904 | Same URL in dashboard template |
| `docs/GITHUB_APP_INSTALL.md` | Line 7 | Same URL |
| `README.md` | Line 18 | Same URL |

**Replace** `fixpoint-security` with your actual app slug (e.g. `fixpoint`).

---

## 3. Create GitHub OAuth App

**Purpose:** Dashboard login (separate from the GitHub App).

**Where:**

- **Organization (e.g. IWEBai):** [https://github.com/organizations/IWEBai/settings/apps](https://github.com/organizations/IWEBai/settings/apps) → **OAuth Apps** → **New OAuth App**  
  Or: **IWEBai** → **Settings** → **Developer settings** → **OAuth Apps**

- **Personal account:** [https://github.com/settings/developers](https://github.com/settings/developers) → **OAuth Apps** → **New OAuth App**

### OAuth App Settings

| Field | Value |
|-------|-------|
| **Application name** | Fixpoint Dashboard |
| **Homepage URL** | `https://fixpoint.dev` (or your domain) |
| **Application description** | Login for Fixpoint dashboard |
| **Authorization callback URL** | `https://fixpoint.dev/dashboard/callback` |

### Post-creation

1. Note **Client ID**
2. Generate **Client Secret** — save for `GITHUB_OAUTH_CLIENT_SECRET`

---

## 4. Set Up Support Email

Create a support mailbox for user questions.

### Option A: Google Workspace

1. Add a user or alias: `support@fixpoint.dev`
2. Configure forwarding if needed

### Option B: Cloudflare Email Routing

1. Add domain in Cloudflare
2. Email Routing → Create address → `support@fixpoint.dev`
3. Forward to your personal email

### Option C: Other Providers

- Zoho, ProtonMail, etc. — use the address that matches your domain.

### Verify

- [ ] `support@fixpoint.dev` receives test emails
- [ ] README and landing page link to `mailto:support@fixpoint.dev`

---

## 5. Prepare Branding Assets

### Logo

| Requirement | Value |
|-------------|-------|
| **Size** | 128×128 minimum (256×256 for Marketplace) |
| **Format** | PNG, square |
| **Location** | `assets/logo.png` |
| **Usage** | GitHub App settings, landing page, README |

**Placeholder:** Simple "F" or shield icon until final design.

### Feature Card (Marketplace, Phase 2)

| Requirement | Value |
|-------------|-------|
| **Size** | 1280×640 pixels |
| **Format** | PNG or JPG |
| **Location** | `assets/feature-card.png` |
| **Content** | Fixpoint name, tagline, optional screenshot |

**Placeholder:** Solid color + text until ready.

---

## 6. Deploy the Webhook Server

### Environment Variables

Set these in your deployment platform:

```bash
# ─── Required for GitHub App (SaaS) ───
GITHUB_APP_ID=12345
GITHUB_APP_PRIVATE_KEY_PATH=/app/private-key.pem
GITHUB_APP_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxx

# ─── Webhook (fallback for self-hosted) ───
WEBHOOK_SECRET=your_secret

# ─── Dashboard (optional) ───
GITHUB_OAUTH_CLIENT_ID=your_oauth_client_id
GITHUB_OAUTH_CLIENT_SECRET=your_oauth_client_secret
DASHBOARD_SESSION_SECRET=  # python -c "import secrets; print(secrets.token_hex(32))"
BASE_URL=https://fixpoint.dev

# ─── Persistence ───
FIXPOINT_DB_PATH=/data/fixpoint.db

# ─── Mode ───
FIXPOINT_MODE=warn
```

### Docker

**Option A:** Change entrypoint to webhook server.

In `Dockerfile`, replace:

```dockerfile
ENTRYPOINT ["python", "main.py"]
```

with:

```dockerfile
ENTRYPOINT ["python", "webhook_server.py"]
```

**Option B:** Keep both — create `Dockerfile.webhook` that uses `webhook_server.py`.

### Cloud Run / Railway / Heroku

1. Set start command: `python webhook_server.py`
2. Port from `PORT` env var (default 8000)
3. Mount or use persistent volume for `FIXPOINT_DB_PATH`

### Private Key

- Store the `.pem` file securely (e.g. secret manager, volume mount)
- Set `GITHUB_APP_PRIVATE_KEY_PATH` to the path inside the container

---

## 7. Deployment Verification

### Checklist

- [ ] **HTTPS** enabled
- [ ] **Domain** points to server (e.g. `fixpoint.dev`)
- [ ] **Webhook URL** `https://fixpoint.dev/webhook` is reachable
- [ ] **OAuth callback** `https://fixpoint.dev/dashboard/callback` matches OAuth App config
- [ ] **SQLite** path uses a persistent volume (`/data/fixpoint.db` or similar)
- [ ] **Private key** is available at `GITHUB_APP_PRIVATE_KEY_PATH`

### Test Endpoints

| URL | Expected |
|-----|----------|
| `https://fixpoint.dev` | Landing page |
| `https://fixpoint.dev/health` | `{"status":"healthy"}` |
| `https://fixpoint.dev/privacy` | Privacy policy |
| `https://fixpoint.dev/dashboard` | OAuth redirect or dashboard |

### Test Webhook

1. In GitHub App settings → **Advanced** → **Recent Deliveries**
2. Redeliver a test event and confirm webhook receives it

---

## 8. Launch & Promotion

### Direct Install URL

Share: `https://github.com/apps/YOUR-APP-SLUG/installations/new`

### Promotion Channels

| Channel | Notes |
|---------|-------|
| **Reddit** | r/devops, r/security, r/webdev |
| **Hacker News** | Show HN: Fixpoint – auto-fix security in PRs |
| **LinkedIn** | Post to your network |
| **Twitter/X** | Tag @github, security accounts |

### Messaging

- **Pitch:** "Free beta for early adopters"
- **Value:** "Auto-fix SQLi, secrets, XSS in PRs — no AI, deterministic"
- **CTA:** "Install in one click"

### Target

- **Goal:** 100+ repos installed
- **Feedback:** support@fixpoint.dev, GitHub Issues

---

## 9. What to Avoid in Phase 1

- [ ] **GitHub Marketplace application** — wait for Phase 2
- [ ] **Billing / Stripe** — keep it free
- [ ] **SSO, audit logs** — not needed yet
- [ ] **Heavy enterprise features** — focus on core value

---

## Quick Reference: URLs

| URL | Purpose |
|-----|---------|
| `https://fixpoint.dev` | Landing page |
| `https://fixpoint.dev/webhook` | GitHub webhook endpoint |
| `https://fixpoint.dev/dashboard` | Dashboard (OAuth login) |
| `https://fixpoint.dev/privacy` | Privacy policy |
| `https://fixpoint.dev/health` | Health check |
| `https://github.com/apps/YOUR-SLUG/installations/new` | Direct install |

---

## Summary Checklist

- [ ] GitHub App registered and configured
- [ ] Install URL slug updated everywhere
- [ ] OAuth App created for dashboard
- [ ] Support email set up
- [ ] Logo (and optional feature card) added
- [ ] Webhook server deployed
- [ ] Environment variables set
- [ ] Deployment verified
- [ ] Direct install URL shared
- [ ] Promotion started
