# Getting Started with Railo

Railo is an automated security-fix bot that installs as a **GitHub App**. Once installed on your organization or repository, Railo watches every pull request, scans for security vulnerabilities, and opens a companion fix PR — all without any workflow files or self-hosted infrastructure.

---

## Table of Contents

1. [Install the Railo GitHub App](#phase-a-install-the-railo-github-app)
2. [How Railo Processes a PR](#phase-b-how-railo-processes-a-pr)
3. [Reading Railo's Output](#phase-c-reading-railos-output)
4. [CI Monitoring and Auto-merge](#phase-d-ci-monitoring-and-auto-merge)
5. [Operation Modes](#phase-e-operation-modes)
6. [Dashboard](#phase-f-dashboard)
7. [Configuration](#configuration)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software   | Version | Check Command      | Install Link           |
| ---------- | ------- | ------------------ | ---------------------- |
| Python     | 3.12+   | `python --version` | https://python.org     |
| Git        | 2.30+   | `git --version`    | https://git-scm.com    |
| GitHub CLI | Latest  | `gh --version`     | https://cli.github.com |

### GitHub CLI Authentication

**You must authenticate before running any `gh` commands:**

```bash
gh auth login
```

Follow the prompts:

1. Choose: `GitHub.com`
2. Choose: `HTTPS`
3. Choose: `Login with a web browser`
4. Press Enter, copy the code, paste in browser
5. Authorize GitHub CLI

**Verify authentication:**

```bash
gh auth status
# Should show: ✓ Logged in to github.com as [your-username]
```

---

## Phase A: Install the Railo GitHub App

### Step 1 — Start installation

Visit the Railo app page on GitHub and click **Install**. GitHub will prompt you to select where to install it:

- **All repositories** in your organization, or
- **Only select repositories** (recommended to start)

### Step 2 — Authorize & complete

GitHub redirects back to Railo after you authorize. Railo records the installation and registers your selected repositories. No additional configuration is needed — Railo is now active.

### Step 3 — Verify

Open any repository where Railo was installed and create a test PR. You should see a **Railo** check-run appear within a few seconds of opening the PR.

> **Permissions Railo requests:** `contents: read`, `pull-requests: write`, `checks: write`, `statuses: write`, `metadata: read`.

---

## Phase B: How Railo Processes a PR

Every time a PR is **opened** or **synchronized** (new commit pushed), GitHub sends a webhook event to Railo. Here is what happens:

| Step                       | What Railo does                                                                                                                                     |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **B1 — Receive webhook**   | Validates the HMAC-SHA256 signature using the shared webhook secret. Rejects unsigned or tampered payloads with HTTP 401.                           |
| **B2 — Idempotency check** | Stores the GitHub delivery ID and ignores exact retries. If the same event arrives twice, Railo returns `{"status": "duplicate"}` and does nothing. |
| **B3 — Kill-switch**       | If `RAILO_KILL_SWITCH=1` is set, Railo stops immediately (HTTP 503). Used during incidents to halt all processing.                                  |
| **B4 — Repository check**  | Verifies the repository is registered and not individually disabled in the admin dashboard.                                                         |
| **B5 — Rate limiting**     | Enforces per-PR rate limits to prevent "synchronize storms" from overwhelming the system.                                                           |
| **B6 — Enqueue**           | Puts the scan job onto a background RQ queue. Returns **HTTP 202** to GitHub immediately so the webhook does not time out.                          |

Processing then continues asynchronously in a worker process.

---

## Phase C: Reading Railo's Output

After scanning, Railo creates several artifacts on the PR:

### Check run

A **Railo Security Scan** check run appears in the PR's Checks tab:

- `success` — no security findings
- `failure` — findings detected (in warn mode)
- `neutral` — findings detected and a fix PR was opened (in fix mode)

Diff annotations are added directly to the **Files changed** tab showing the affected line. Click an annotation to see the rule ID and suggested remediation.

### PR comment (warn mode)

When findings are detected in warn mode, Railo posts a comment like:

```
🔍 Railo found 2 security issue(s)

| File | Rule | Line | Proposed fix |
|------|------|------|--------------|
| app/db.py | sqli.parameterized-query | 47 | Use parameterized queries |
| utils/auth.py | secrets.hardcoded-password | 12 | Use environment variable |

To apply these fixes automatically, switch to fix mode.
```

### Fix PR (fix/auto-merge mode)

When Railo is in **fix** or **auto-merge** mode it:

1. Checks out the PR's head branch into a temporary workspace
2. Runs targeted patchers for each finding type (SQLi, XSS, Secrets, Command Injection, Path Traversal, SSRF)
3. Commits the changes and pushes a new branch named `railo/fix-<vuln>-<sha>-pr<N>-<timestamp>`
4. Opens a companion PR with the title **"Railo: Fix \<vuln type\> (\<N\> issue(s)) from PR #\<N\>"**
5. Posts a comment on your original PR linking to the fix PR with a Safety Score (0–100)

The original PR is **never modified**. Railo always works on a separate branch.

> **Safety Score** is a 0–100 heuristic: higher means the patch is smaller and more targeted. A score below 60 triggers a warning in the fix PR description.

---

## Phase D: CI Monitoring and Auto-merge

When `railo_mode = auto_merge`, Railo also monitors the CI pipeline on its fix PRs:

| CI result                    | Railo action                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------ |
| **All checks pass** (Tier A) | Posts a comment: _"All checks passed — this fix PR is safe to merge."_                           |
| **A check fails** (Tier B)   | Reverts the fix branch and posts a comment explaining what failed. The original PR remains open. |

Railo determines auto-merge eligibility by checking whether the fix PR's head SHA matches the latest push, all required status checks have passed, and the PR has not been manually closed or merged by a human.

> Railo **never force-merges**. If any required check fails, it reverts rather than bypassing CI.

---

## Phase E: Operation Modes

Set the mode per-repository via the dashboard or the `FIXPOINT_MODE` environment variable:

| Mode         | Behavior                                                                                                                    |
| ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `warn`       | Posts a comment with proposed fixes. Does not create a branch or open a PR. Status check set to **failure** to block merge. |
| `fix`        | Creates a fix PR. Posts a link comment on the original PR. Status check set to **neutral**.                                 |
| `auto_merge` | Same as `fix`, plus auto-merges the fix PR when CI passes.                                                                  |

### Mode downgrade rules

Railo automatically downgrades the mode to protect against unsafe operations:

- **Fork PRs:** `fix` → `warn` (no write access to the fork)
- **Force-warn org:** `fix` → `warn` (set by an admin during incidents)
- **Time budget exceeded:** `fix` → `warn` (scan took longer than `max_runtime_seconds`)
- **No push permission:** `fix` → `warn` (token lacks `contents: write`)

When a downgrade occurs, Railo records the reason in the audit log and displays a notice in its PR comment.

### Guardrails that block auto-fix

Even in `fix` mode, Railo will refuse to commit if any guardrail fires:

| Guardrail           | Condition                                                             |
| ------------------- | --------------------------------------------------------------------- |
| **Max diff lines**  | Patch touches more than `max_diff_lines` (default: 200) lines         |
| **Diff quality**    | Patch quality score below threshold (non-minimal changes detected)    |
| **Low confidence**  | All findings below the confidence gate threshold                      |
| **Loop prevention** | Latest commit author is the Railo bot (prevents infinite retry loops) |

---

## Phase F: Dashboard

The Railo dashboard is available at `https://<your-railo-host>/dashboard` (requires GitHub OAuth login).

### Key views

| View             | URL                   | Description                                            |
| ---------------- | --------------------- | ------------------------------------------------------ |
| **Runs**         | `/dashboard`          | Recent scan runs with status, timing, and vuln counts  |
| **Repositories** | `/dashboard/repos`    | All registered repositories and their settings         |
| **Org policy**   | `/dashboard/org`      | Organization-wide mode and rule overrides              |
| **Audit log**    | `/dashboard/audit`    | Full audit trail of every Railo decision               |
| **Metrics**      | `/api/metrics/health` | JSON health snapshot (runs/hr, failures, queue depths) |
| **Prometheus**   | `/metrics`            | Prometheus text-format scrape endpoint                 |

### Security team workflow

1. Log in at `/dashboard` with your GitHub account
2. Review the **Runs** view for any recent `fix_pr_failed` or `enforce_guardrails_blocked` events
3. Use **Org policy** to enable/disable specific Semgrep rule IDs without redeploying
4. Use the **Kill-switch** toggle to pause all processing immediately during an incident
5. Export the **Audit log** for compliance reporting

### Manager/executive workflow

1. The `/api/metrics/health` endpoint provides a JSON summary suitable for uptime dashboards:
   ```json
   {
     "runs_per_hour": 12,
     "failed_runs_24h": 1,
     "reverts_24h": 0,
     "queue_depths": { "default": 0, "high": 0 }
   }
   ```
2. The `/metrics` Prometheus endpoint can be scraped by Grafana or Datadog for trend charts

---

## Configuration

Railo reads an optional `.fixpoint.yml` file from the root of each repository:

```yaml
# .fixpoint.yml
max_runtime_seconds: 90 # Abort scan after this many seconds
max_diff_lines: 200 # Refuse to commit patch larger than this
baseline_mode: false # Filter pre-existing findings (set baseline_sha below)
baseline_sha: "" # Git SHA to diff against for baseline filtering
```

All fields are optional. If the file is absent or invalid, Railo uses safe defaults and posts an error comment explaining what is misconfigured.

---

## Troubleshooting

### No check run appears on my PR

- Confirm the Railo GitHub App is installed on the repository. Go to **Settings → Integrations → GitHub Apps** and verify Railo is listed.
- Check that the PR action is `opened` or `synchronize`. Railo ignores other actions (e.g., `labeled`, `closed`).
- If `RAILO_KILL_SWITCH=1` is set, Railo returns HTTP 503 and does nothing.

### Webhook returns 401

- The webhook secret configured in GitHub does not match `GITHUB_WEBHOOK_SECRET`/`WEBHOOK_SECRET` in Railo's environment.
- Ensure you are using HMAC-SHA256 (`X-Hub-Signature-256` header), not the legacy SHA-1 header.

### Fix PR not created even in fix mode

Check the original PR for a Railo error comment. Common causes:

| Error                        | Cause                                                              |
| ---------------------------- | ------------------------------------------------------------------ |
| `enforce_guardrails_blocked` | Patch exceeded `max_diff_lines` or quality check failed            |
| `fix_pr_failed`              | Git push failed — check branch protection rules on the base branch |
| `low_confidence`             | Semgrep findings were below the confidence gate                    |
| `loop_prevention`            | Latest commit is from the Railo bot; will retry on next human push |

### Railo is posting repeated comments

This can happen if delivery-ID idempotency is disabled or the Redis store is unavailable. Check that `REDIS_URL` is set and reachable. Railo falls back to in-memory deduplication when Redis is unavailable, which is lost on restart.

---

## Next Steps

- [API Reference](./API_REFERENCE.md) — full webhook and REST API documentation
- [Environment Variables](./ENVIRONMENT_VARIABLES.md) — all configuration options
- [Architecture](./ARCHITECTURE.md) — system design and data flow
- [Runbook](./RUNBOOK.md) — on-call procedures and incident response
- [ROADMAP](../ROADMAP.md) — upcoming features

---

_Railo — automated security fixes for every pull request_
