# Fixpoint Environment Variables Reference

This document lists all environment variables used by Fixpoint.

---

## Required Variables

### GITHUB_TOKEN

GitHub Personal Access Token for API operations.

| Property | Value |
|----------|-------|
| Required | Yes |
| Default | None |
| Used by | Webhook server, CLI, GitHub Action |

**Required permissions:**
- `repo` - Full control of private repositories
- `write:discussion` - Write PR comments (included in `repo`)

**Example:**
```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

### WEBHOOK_SECRET

Secret for validating GitHub webhook signatures.

| Property | Value |
|----------|-------|
| Required | Yes (for webhook server) |
| Default | Empty (fails without it) |
| Used by | Webhook server |

**Generate a secure secret:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Example:**
```bash
WEBHOOK_SECRET=a1b2c3d4e5f6...
```

---

## Mode Configuration

### FIXPOINT_MODE

Controls whether Fixpoint applies fixes or just warns.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `warn` |
| Values | `warn`, `enforce` |
| Used by | Webhook server |

**Modes:**
- `warn` - Post comments with suggested fixes, don't modify code
- `enforce` - Automatically apply fixes and commit

**Example:**
```bash
FIXPOINT_MODE=warn
```

### ENVIRONMENT

Indicates the deployment environment.

| Property | Value |
|----------|-------|
| Required | No |
| Default | None |
| Values | `production`, `development`, `test` |
| Used by | Security module |

When set to `production`, all security checks are strictly enforced.

**Example:**
```bash
ENVIRONMENT=production
```

---

## Server Configuration

### PORT

HTTP port for the webhook server.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `5000` |
| Used by | Webhook server |

**Example:**
```bash
PORT=8080
```

### DEBUG

Enable Flask debug mode.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `false` |
| Values | `true`, `false` |
| Used by | Webhook server |

**Warning:** Never enable in production!

**Example:**
```bash
DEBUG=false
```

### GIT_TIMEOUT

Timeout in seconds for git operations.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `120` |
| Used by | Webhook server |

**Example:**
```bash
GIT_TIMEOUT=180
```

---

## Security Configuration

### ALLOWED_REPOS

Comma-separated list of repositories allowed to trigger processing.

| Property | Value |
|----------|-------|
| Required | No |
| Default | Empty (all allowed) |
| Format | `owner/repo,owner/repo2` |
| Used by | Webhook server |

When set, only listed repositories can trigger Fixpoint.

**Example:**
```bash
ALLOWED_REPOS=myorg/backend,myorg/frontend
```

### DENIED_REPOS

Comma-separated list of repositories blocked from processing.

| Property | Value |
|----------|-------|
| Required | No |
| Default | Empty (none blocked) |
| Format | `owner/repo,owner/repo2` |
| Used by | Webhook server |

Takes precedence over `ALLOWED_REPOS`.

**Example:**
```bash
DENIED_REPOS=myorg/legacy-app,myorg/untrusted
```

### SKIP_WEBHOOK_VERIFICATION

Skip webhook signature verification (development only).

| Property | Value |
|----------|-------|
| Required | No |
| Default | `false` |
| Values | `true`, `false` |
| Used by | Webhook server |

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

| Property | Value |
|----------|-------|
| Default | `warn` |
| Values | `warn`, `enforce` |

**Example:**
```yaml
- uses: AyeWebDev/fixpoint@v1
  with:
    mode: warn
```

### INPUT_BASE_BRANCH

Base branch to compare against.

| Property | Value |
|----------|-------|
| Default | Repository default branch |

**Example:**
```yaml
- uses: AyeWebDev/fixpoint@v1
  with:
    base_branch: main
```

---

## GitHub Actions Environment

These are automatically set by GitHub Actions:

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | Automatic token for the workflow |
| `GITHUB_REPOSITORY` | Owner/repo format |
| `GITHUB_REF` | Git ref that triggered the workflow |
| `GITHUB_SHA` | Commit SHA |
| `GITHUB_HEAD_REF` | Head branch (for PRs) |
| `GITHUB_BASE_REF` | Base branch (for PRs) |

---

## Future/Optional Variables

These are planned for future releases:

### REDIS_URL

Redis connection URL for distributed rate limiting and caching.

| Property | Value |
|----------|-------|
| Required | No (Phase 2) |
| Default | None (uses in-memory) |
| Format | `redis://host:port/db` |

**Example:**
```bash
REDIS_URL=redis://localhost:6379/0
```

### DATABASE_URL

Database connection URL for metrics storage.

| Property | Value |
|----------|-------|
| Required | No (Phase 2) |
| Default | None (uses in-memory) |
| Format | Database connection string |

**Example:**
```bash
DATABASE_URL=postgresql://user:pass@localhost/fixpoint
```

---

## Example .env File

```bash
# Required
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
WEBHOOK_SECRET=your_secure_secret_here

# Mode
AUDITSHIELD_MODE=warn
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

---

## Validation

Fixpoint validates required variables at startup. Missing required variables will cause:

- Webhook server: Requests rejected with 401
- CLI: Error message and exit
- GitHub Action: Workflow failure

Check logs for specific error messages if configuration is incorrect.
