# Phase 2 Setup Guide

This guide explains how to set up and use AuditShield Phase 2 features.

## Features

Phase 2 adds:
- **PR Diff Scanning**: Only scan changed files in PRs (faster, more relevant)
- **Webhook Server**: Automatic processing when PRs are opened/updated
- **Push to Existing Branch**: Fixes pushed directly to PR branch (no new PRs)
- **Warn Mode**: Comment-only mode (proposes fixes, doesn't apply) - **NEW**
- **Status Checks**: GitHub status checks (PASS/FAIL gates) - **NEW**
- **Expanded Fixer**: Handles any variable name (not just {email}) - **NEW**

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Update your `.env` file:

```env
GITHUB_TOKEN=your_token_here
GITHUB_OWNER=your_username
GITHUB_REPO=your_repo

# Webhook server configuration
WEBHOOK_SECRET=generate_a_random_secret_here
PORT=5000
DEBUG=false

# AuditShield mode: "warn" (comment only) or "enforce" (apply fixes)
# Default: warn (safer, builds trust)
AUDITSHIELD_MODE=warn
```

### 3. Usage Options

#### Option A: PR Diff Mode (CLI)

Manually scan a PR's changed files:

```bash
python main.py /path/to/repo \
  --pr-mode \
  --base-ref main \
  --head-ref feature-branch
```

#### Option B: Push to Existing PR Branch

Fix and push directly to an existing PR:

```bash
python main.py /path/to/repo \
  --push-to-existing feature-branch
```

#### Option C: Webhook Server (Recommended)

Start the webhook server for automatic processing:

```bash
# Default: warn mode (comment only)
AUDITSHIELD_MODE=warn python webhook_server.py

# Or enforce mode (apply fixes)
AUDITSHIELD_MODE=enforce python webhook_server.py
```

The server will:
- Listen on `http://0.0.0.0:5000/webhook` (or PORT from .env)
- Process `pull_request.opened` and `pull_request.synchronize` events
- **Warn mode:** Post comments with proposed fixes (no commits)
- **Enforce mode:** Apply fixes automatically and commit
- Set GitHub status checks (PASS/FAIL)

### 4. Configure GitHub Webhook

1. Go to your repository → Settings → Webhooks
2. Click "Add webhook"
3. Configure:
   - **Payload URL**: `https://your-domain.com/webhook`
   - **Content type**: `application/json`
   - **Secret**: Your `WEBHOOK_SECRET` from .env
   - **Events**: Select "Pull requests" (opened, synchronize)
4. Save

### 5. Test

1. Create a PR with SQL injection vulnerability
2. The webhook will automatically:
   - Scan changed files
   - Apply fixes
   - Push commit to PR branch
3. CI will rerun automatically

## How It Works

### PR Diff Scanning

Instead of scanning the entire repository, Phase 2:
1. Gets the list of changed files between base and head branches
2. Filters to relevant file types (currently Python only)
3. Scans only those files with Semgrep
4. Applies fixes to changed files only

**Benefits:**
- Faster execution
- More relevant fixes
- Less noise

### Webhook Flow

```
PR Opened/Updated
    ↓
GitHub sends webhook
    ↓
AuditShield webhook server receives event
    ↓
Clones/updates repository
    ↓
Gets PR diff (changed files)
    ↓
Scans changed files with Semgrep
    ↓
Applies deterministic fixes
    ↓
Commits and pushes to PR branch
    ↓
CI reruns automatically
```

## Troubleshooting

### Webhook not receiving events

- Check webhook URL is accessible (use ngrok for local testing)
- Verify webhook secret matches
- Check GitHub webhook delivery logs

### Fixes not being applied

- Ensure Semgrep rules match your code patterns
- Check that changed files are Python files (Phase 1 limitation)
- Verify GITHUB_TOKEN has write access to repository

### Authentication errors

- Ensure GITHUB_TOKEN has `repo` scope
- For private repos, token must have access
- Check token hasn't expired

## Security & Safety Features

Phase 2 includes comprehensive security and safety mechanisms:

### Security
- ✅ **Webhook signature verification** (HMAC-SHA256)
- ✅ **Event type allowlist** (only `pull_request`)
- ✅ **Action allowlist** (only `opened`, `synchronize`)
- ✅ **Replay protection** (prevents duplicate processing)
- ✅ **Rate limiting** (prevents DDoS on synchronize storms)

### Safety
- ✅ **Idempotency** (prevents re-applying same fix)
- ✅ **Loop prevention** (bot commits don't trigger bot again)
- ✅ **Confidence gating** (only fixes high-confidence findings)
- ✅ **Minimal diffs** (no formatting, only security fixes)
- ✅ **Branch protection handling** (graceful error handling with helpful comments)

See [PHASE2_SECURITY_CHECKLIST.md](./PHASE2_SECURITY_CHECKLIST.md) for full details.

## Testing

Before deploying to production, run the acceptance tests:

See [PHASE2_ACCEPTANCE_TEST.md](./PHASE2_ACCEPTANCE_TEST.md) for the complete test suite.

## Next Steps

Phase 2 is now functional for:
- ✅ PR diff scanning
- ✅ Webhook automation
- ✅ Push to existing branches
- ✅ Full security & safety features

Coming soon:
- 🔄 GitHub App integration (native installation)
- 🔄 AST-based detection (more accurate)
- 🔄 Inline "Fix this" buttons in PRs
- 🔄 Support for more languages and violation types
