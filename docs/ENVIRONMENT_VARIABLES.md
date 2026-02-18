# Fixpoint Environment Variables Reference

This document lists all environment variables used by Fixpoint.

---

## Required Variables

### GITHUB_TOKEN

GitHub Personal Access Token for API operations (self-hosted mode).

| Property | Value                               |
| -------- | ----------------------------------- |
| Required | Yes (self-hosted) / No (GitHub App) |
| Default  | None                                |
| Used by  | Webhook server, CLI, GitHub Action  |

**Required permissions (self-hosted):**

- `repo` - Full control of private repositories
- `write:discussion` - Write PR comments (included in `repo`)

**Example:**

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

When using GitHub App mode, the installation token is generated automatically from the webhook payload. `GITHUB_TOKEN` is only used when no `installation` is present (legacy self-hosted).

### WEBHOOK_SECRET

Secret for validating GitHub webhook signatures (self-hosted / repo webhooks).

| Property | Value                                         |
| -------- | --------------------------------------------- |
| Required | Yes (unless GitHub App webhook secret is set) |
| Default  | Empty                                         |
| Used by  | Webhook server                                |

**Generate a secure secret:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### GITHUB_APP_WEBHOOK_SECRET

Webhook secret for GitHub App webhooks (from App settings).

| Property | Value                       |
| -------- | --------------------------- |
| Required | Yes (when using GitHub App) |
| Default  | Empty                       |
| Used by  | Webhook server              |

**Location:** GitHub App → Developer settings → Webhook → Secret

**Example:**

```bash
GITHUB_APP_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxx
```

**Dual mode:** Both `WEBHOOK_SECRET` and `GITHUB_APP_WEBHOOK_SECRET` can be set. The server tries each during signature verification.

---

## GitHub App Variables (SaaS Mode)

When running as a GitHub App, set these instead of `GITHUB_TOKEN`. The token is generated per installation from the webhook payload.

### GITHUB_APP_ID

GitHub App ID from the app settings.

| Property | Value                     |
| -------- | ------------------------- |
| Required | Yes (for GitHub App mode) |
| Default  | None                      |
| Used by  | `core/github_app_auth.py` |

### GITHUB_APP_PRIVATE_KEY

PEM content of the app's private key. Alternative: use `GITHUB_APP_PRIVATE_KEY_PATH`.

| Property | Value                                                                 |
| -------- | --------------------------------------------------------------------- |
| Required | Yes (or `GITHUB_APP_PRIVATE_KEY_PATH`)                                |
| Default  | None                                                                  |
| Format   | `-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----` |

**Note:** Use `\n` for newlines when embedding in env.

### GITHUB_APP_PRIVATE_KEY_PATH

Path to .pem file containing the private key (if not embedding in env).

| Property | Value                             |
| -------- | --------------------------------- |
| Required | Yes (or `GITHUB_APP_PRIVATE_KEY`) |
| Default  | None                              |
| Used by  | `core/github_app_auth.py`         |

**Example:**

```bash
GITHUB_APP_PRIVATE_KEY_PATH=/app/private-key.pem
```

---

## Mode Configuration

### FIXPOINT_MODE

Controls whether Fixpoint applies fixes or just warns.

| Property | Value             |
| -------- | ----------------- |
| Required | No                |
| Default  | `warn`            |
| Values   | `warn`, `enforce` |
| Used by  | Webhook server    |

**Modes:**

- `warn` - Post comments with suggested fixes, don't modify code
- `enforce` - Automatically apply fixes and commit

**Example:**

```bash
FIXPOINT_MODE=warn
```

### ENVIRONMENT

Indicates the deployment environment.

| Property | Value                               |
| -------- | ----------------------------------- |
| Required | No                                  |
| Default  | None                                |
| Values   | `production`, `development`, `test` |
| Used by  | Security module                     |

When set to `production`, all security checks are strictly enforced.

**Example:**

```bash
ENVIRONMENT=production
```

---

## Server Configuration

### PORT

HTTP port for the webhook server.

| Property | Value          |
| -------- | -------------- |
| Required | No             |
| Default  | `8000`         |
| Used by  | Webhook server |

**Example:**

```bash
PORT=8080
```

### DEBUG

Enable Flask debug mode.

| Property | Value           |
| -------- | --------------- |
| Required | No              |
| Default  | `false`         |
| Values   | `true`, `false` |
| Used by  | Webhook server  |

**Warning:** Never enable in production!

**Example:**

```bash
DEBUG=false
```

### GIT_TIMEOUT

Timeout in seconds for git operations.

| Property | Value          |
| -------- | -------------- |
| Required | No             |
| Default  | `120`          |
| Used by  | Webhook server |

**Example:**

```bash
GIT_TIMEOUT=180
```

---

## Security Configuration

### ALLOWED_REPOS

Comma-separated list of repositories allowed to trigger processing.

| Property | Value                    |
| -------- | ------------------------ |
| Required | No                       |
| Default  | Empty (all allowed)      |
| Format   | `owner/repo,owner/repo2` |
| Used by  | Webhook server           |

When set, only listed repositories can trigger Fixpoint.

**Example:**

```bash
ALLOWED_REPOS=myorg/backend,myorg/frontend
```

### DENIED_REPOS

Comma-separated list of repositories blocked from processing.

| Property | Value                    |
| -------- | ------------------------ |
| Required | No                       |
| Default  | Empty (none blocked)     |
| Format   | `owner/repo,owner/repo2` |
| Used by  | Webhook server           |

Takes precedence over `ALLOWED_REPOS`.

**Example:**

```bash
DENIED_REPOS=myorg/legacy-app,myorg/untrusted
```

### FIXPOINT_DISABLED_REPOS

Admin kill switch for repositories (App/SaaS operations).

| Property | Value                    |
| -------- | ------------------------ |
| Required | No                       |
| Default  | Empty (none disabled)    |
| Format   | `owner/repo,owner/repo2` |
| Used by  | Webhook server           |

**Example:**

```bash
FIXPOINT_DISABLED_REPOS=myorg/outage-repo,myorg/legacy-app
```

### FIXPOINT_DISABLED_RULES

Disable specific rule families globally during incidents (e.g. `xss`, `sqli`).

| Property | Value                                                                 |
| -------- | --------------------------------------------------------------------- |
| Required | No                                                                    |
| Default  | Empty (none disabled)                                                 |
| Format   | `sqli,secrets,xss,command-injection,path-traversal,ssrf,eval,dom-xss` |
| Used by  | Webhook server                                                        |

**Example:**

```bash
FIXPOINT_DISABLED_RULES=xss,dom-xss
```

### FIXPOINT_FORCE_WARN_ORGS

Force warn-only mode for an org during incidents (App/SaaS path).

| Property | Value               |
| -------- | ------------------- |
| Required | No                  |
| Default  | Empty (none forced) |
| Format   | `org1,org2`         |
| Used by  | Webhook server      |

**Example:**

```bash
FIXPOINT_FORCE_WARN_ORGS=myorg,customer-inc
```

### SKIP_WEBHOOK_VERIFICATION

Skip webhook signature verification (development only).

| Property | Value           |
| -------- | --------------- |
| Required | No              |
| Default  | `false`         |
| Values   | `true`, `false` |
| Used by  | Webhook server  |

**Warning:** Never use in production! This bypasses all signature verification.

**Example:**

```bash
SKIP_WEBHOOK_VERIFICATION=true  # ONLY for local testing
```

---

## GitHub Action Inputs

When using Fixpoint as a GitHub Action, these are set via `with:` in your workflow:

### INPUT_MODE

Same as `FIXPOINT_MODE`.

| Property | Value             |
| -------- | ----------------- |
| Default  | `warn`            |
| Values   | `warn`, `enforce` |

**Example:**

```yaml
- uses: IWEBai/fixpoint@v1
  with:
    mode: warn
```

### FIXPOINT_MAX_DIFF_LINES

Maximum lines changed allowed per auto-fix commit (safety rail). If exceeded, Fixpoint will not commit.

| Property | Value                         |
| -------- | ----------------------------- |
| Required | No                            |
| Default  | `500`                         |
| Used by  | Webhook server, GitHub Action |

**Example:**

```bash
FIXPOINT_MAX_DIFF_LINES=300
```

### FIXPOINT_TEST_BEFORE_COMMIT

If set, run tests before committing fixes. Commit is skipped if tests fail.

| Property | Value                         |
| -------- | ----------------------------- |
| Required | No                            |
| Default  | `false`                       |
| Values   | `true`, `false`, `1`, `0`     |
| Used by  | Webhook server, GitHub Action |

**Example:**

```bash
FIXPOINT_TEST_BEFORE_COMMIT=true
```

### FIXPOINT_TEST_COMMAND

Command to run when `FIXPOINT_TEST_BEFORE_COMMIT` is enabled (e.g. `pytest`, `npm test`).

| Property | Value                         |
| -------- | ----------------------------- |
| Required | No                            |
| Default  | `pytest`                      |
| Used by  | Webhook server, GitHub Action |

**Example:**

```bash
FIXPOINT_TEST_COMMAND=pytest
```

### INPUT_BASE_BRANCH

Base branch to compare against.

| Property | Value                     |
| -------- | ------------------------- |
| Default  | Repository default branch |

**Example:**

```yaml
- uses: IWEBai/fixpoint@v1
  with:
    base_branch: main
```

---

## GitHub Actions Environment

These are automatically set by GitHub Actions:

| Variable            | Description                         |
| ------------------- | ----------------------------------- |
| `GITHUB_TOKEN`      | Automatic token for the workflow    |
| `GITHUB_REPOSITORY` | Owner/repo format                   |
| `GITHUB_REF`        | Git ref that triggered the workflow |
| `GITHUB_SHA`        | Commit SHA                          |
| `GITHUB_HEAD_REF`   | Head branch (for PRs)               |
| `GITHUB_BASE_REF`   | Base branch (for PRs)               |

---

## Dashboard Variables (Phase 1)

### GITHUB_OAUTH_CLIENT_ID

GitHub OAuth App client ID for dashboard login.

| Property | Value               |
| -------- | ------------------- |
| Required | Yes (for dashboard) |
| Used by  | Dashboard OAuth     |

**Create:** GitHub → Settings → Developer settings → OAuth Apps → New OAuth App

### GITHUB_OAUTH_CLIENT_SECRET

GitHub OAuth App client secret.

| Property | Value               |
| -------- | ------------------- |
| Required | Yes (for dashboard) |
| Used by  | Dashboard OAuth     |

### DASHBOARD_SESSION_SECRET

Secret for signing session cookies.

| Property | Value               |
| -------- | ------------------- |
| Required | Yes (for dashboard) |
| Used by  | Flask session       |

**Generate:** `python -c "import secrets; print(secrets.token_hex(32))"`

### BASE_URL

Base URL for OAuth redirect (e.g. `https://fixpoint.dev`).

| Property | Value                     |
| -------- | ------------------------- |
| Required | Yes (for dashboard OAuth) |
| Default  | `http://localhost:8000`   |
| Used by  | OAuth callback URL        |

### FIXPOINT_DB_PATH

Path to SQLite database file.

| Property | Value                           |
| -------- | ------------------------------- |
| Required | No                              |
| Default  | `fixpoint.db` in project root   |
| Used by  | Dashboard (installations, runs) |

---

## Future/Optional Variables

These are planned for future releases:

### REDIS_URL

Redis connection URL for distributed rate limiting and caching.

| Property | Value                  |
| -------- | ---------------------- |
| Required | No (Phase 2)           |
| Default  | None (uses in-memory)  |
| Format   | `redis://host:port/db` |

**Example:**

```bash
REDIS_URL=redis://localhost:6379/0
```

### DATABASE_URL

Database connection URL for metrics storage.

| Property | Value                      |
| -------- | -------------------------- |
| Required | No (Phase 2)               |
| Default  | None (uses in-memory)      |
| Format   | Database connection string |

**Example:**

```bash
DATABASE_URL=postgresql://user:pass@localhost/fixpoint
```

---

## Example .env File

**Self-hosted mode:**

```bash
# Required
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
WEBHOOK_SECRET=your_secure_secret_here

# Mode
FIXPOINT_MODE=warn
ENVIRONMENT=production

# Server
PORT=8000
DEBUG=false
GIT_TIMEOUT=120

# Security (optional)
ALLOWED_REPOS=myorg/backend,myorg/frontend
# DENIED_REPOS=myorg/untrusted

# NEVER in production
# SKIP_WEBHOOK_VERIFICATION=true
```

**GitHub App mode (SaaS):**

```bash
# GitHub App (no GITHUB_TOKEN needed - token from webhook)
GITHUB_APP_ID=12345
GITHUB_APP_PRIVATE_KEY_PATH=/app/private-key.pem
GITHUB_APP_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxx

WEBHOOK_SECRET=  # Optional for repo webhooks if dual mode

# Mode, Server, Security - same as above
FIXPOINT_MODE=warn
ENVIRONMENT=production
PORT=8000
```

**With Dashboard:**

```bash
# Add to GitHub App mode config
GITHUB_OAUTH_CLIENT_ID=xxx
GITHUB_OAUTH_CLIENT_SECRET=xxx
DASHBOARD_SESSION_SECRET=your_session_secret
BASE_URL=https://fixpoint.dev
FIXPOINT_DB_PATH=/data/fixpoint.db
```

---

## Validation

Fixpoint validates required variables at startup. Missing required variables will cause:

- Webhook server: Requests rejected with 401
- CLI: Error message and exit
- GitHub Action: Workflow failure

Check logs for specific error messages if configuration is incorrect.
