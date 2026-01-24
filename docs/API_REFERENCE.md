# AuditShield API Reference

This document describes the webhook API for self-hosted AuditShield deployments.

---

## Webhook Endpoint

### POST /webhook

Receives GitHub webhook events for PR processing.

#### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-Hub-Signature-256` | Yes* | HMAC-SHA256 signature of the payload |
| `X-GitHub-Event` | Yes | Event type (must be `pull_request`) |
| `X-GitHub-Delivery` | Yes | Unique delivery ID (used for replay protection) |
| `Content-Type` | Yes | Must be `application/json` |

*Required unless `SKIP_WEBHOOK_VERIFICATION=true` (development only)

#### Request Body

GitHub PR webhook payload. See [GitHub Webhook Events](https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request).

**Required fields:**

```json
{
  "action": "opened | synchronize",
  "number": 1,
  "pull_request": {
    "number": 1,
    "head": {
      "ref": "feature-branch",
      "sha": "abc123...",
      "repo": {
        "full_name": "owner/repo",
        "fork": false
      }
    },
    "base": {
      "ref": "main",
      "repo": {
        "full_name": "owner/repo"
      }
    },
    "html_url": "https://github.com/owner/repo/pull/1"
  },
  "repository": {
    "full_name": "owner/repo",
    "name": "repo",
    "owner": {
      "login": "owner"
    }
  }
}
```

#### Response Codes

| Code | Status | Description |
|------|--------|-------------|
| 200 | Success | Request processed (see response body for result) |
| 400 | Bad Request | Invalid JSON payload |
| 401 | Unauthorized | Invalid signature, disallowed event, or replay detected |
| 413 | Payload Too Large | Request body exceeds 1MB limit |
| 429 | Too Many Requests | Rate limit exceeded |

#### Response Body

```json
{
  "status": "success | ignored | rate_limited | error | ...",
  "message": "Human-readable description",
  "findings_count": 0,
  "files_fixed": ["app.py"],
  "comment_url": "https://github.com/.../comments/123"
}
```

**Status values:**

| Status | Description |
|--------|-------------|
| `success` | Fixes applied successfully (enforce mode) |
| `warn_mode` | Violations found, comments posted (warn mode) |
| `no_findings` | No violations found |
| `no_changes` | No files changed in PR |
| `no_python` | No Python files changed |
| `all_ignored` | All changed files ignored by .auditshieldignore |
| `already_fixed` | All findings already fixed (idempotency) |
| `skipped` | Skipped to prevent processing loop |
| `low_confidence` | Findings too low confidence to auto-fix |
| `rate_limited` | Rate limit exceeded |
| `denied` | Repository not allowed |
| `ignored` | Event type or action not handled |
| `error` | Processing error occurred |

---

## Health Check Endpoint

### GET /health

Health check for load balancers and monitoring.

#### Response

```json
{
  "status": "healthy"
}
```

Returns HTTP 200 when service is running.

---

## Rate Limiting

AuditShield implements per-PR rate limiting to prevent abuse:

| Setting | Default | Description |
|---------|---------|-------------|
| Window | 60 seconds | Time window for rate limiting |
| Max Requests | 10 | Maximum requests per PR per window |

Rate limit key format: `pr:{owner}/{repo}:{pr_number}`

When rate limited, the API returns:
- HTTP 200 with `status: "rate_limited"`
- Message indicating to wait before retrying

---

## Security

### Webhook Signature Verification

All webhook requests must include a valid `X-Hub-Signature-256` header:

1. GitHub computes HMAC-SHA256 of the payload using your webhook secret
2. GitHub sends the signature as `sha256=<hexdigest>`
3. AuditShield verifies the signature matches

**Configuration:**
```bash
WEBHOOK_SECRET=your_secret_here
```

### Replay Protection

AuditShield tracks delivery IDs to prevent replay attacks:
- Delivery IDs are stored for 24 hours
- Duplicate deliveries are rejected with 401

### Repository Allowlist/Denylist

Control which repositories can trigger processing:

```bash
# Allow only specific repos (allowlist mode)
ALLOWED_REPOS=owner/repo1,owner/repo2

# Block specific repos (denylist mode)  
DENIED_REPOS=owner/untrusted-repo

# If both are set, denylist takes precedence
```

### Request Size Limits

Maximum payload size: 1MB

Requests exceeding this limit receive HTTP 413.

---

## Timeouts

| Operation | Timeout | Configuration |
|-----------|---------|---------------|
| Git operations | 120s | `GIT_TIMEOUT` env var |
| Webhook processing | None | Process runs to completion |

---

## GitHub Status Checks

AuditShield sets status checks on PRs:

| Context | State | Description |
|---------|-------|-------------|
| `auditshield/compliance` | success | No violations or all fixed |
| `auditshield/compliance` | failure | Violations found (warn mode) |
| `auditshield/compliance` | error | Processing error |

Configure as a required check in branch protection to block merging.

---

## PR Comments

AuditShield posts comments on PRs to explain actions:

### Fix Applied Comment (enforce mode)

```markdown
## 🔒 AuditShield AutoPatch

I've automatically applied security fixes to this PR.

### What was found
- **app.py:10** - SQL injection via f-string
  - Rule: `custom.sql-injection-fstring`

### What changed
- ✅ `app.py` - Replaced SQL string formatting with parameterized query
```

### Warn Comment (warn mode)

```markdown
## 🔒 AuditShield - Compliance Check (Warn Mode)

I found compliance violations in this PR. Here are the suggested fixes:

### Proposed fixes
**app.py:10**

\`\`\`diff
- query = f"SELECT * FROM users WHERE email = '{email}'"
+ query = "SELECT * FROM users WHERE email = %s"
\`\`\`
```

---

## Error Handling

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| Invalid webhook signature | Secret mismatch | Verify `WEBHOOK_SECRET` matches GitHub |
| Event type not allowed | Non-PR event | Configure webhook for `pull_request` only |
| Repository denied | Repo in denylist or not in allowlist | Update `ALLOWED_REPOS`/`DENIED_REPOS` |
| Rate limit exceeded | Too many requests | Wait and retry |
| Branch protection error | Can't push to protected branch | Adjust branch rules or use warn mode |

---

## Example: Configure GitHub Webhook

1. Go to **Settings → Webhooks → Add webhook**
2. Set:
   - Payload URL: `https://your-domain.com/webhook`
   - Content type: `application/json`
   - Secret: Your `WEBHOOK_SECRET` value
   - Events: Select "Pull requests"
3. Save

Test with a new PR to verify connectivity.
