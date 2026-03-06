# Railo Web App Guide

The Railo web app (available at `app.railo.dev`) is the control center for organizations that have installed the Railo GitHub App. It gives security engineers, engineering managers, and administrators a single place to monitor security activity, configure policies, and manage notifications — while developers continue to experience Railo entirely inside GitHub pull requests.

> **Developers do not need to use the web app.** Railo communicates with developers through GitHub comments, check runs, and fix PRs. The web app is for configuration and visibility.

---

## Table of Contents

1. [Signing In](#signing-in)
2. [Dashboard](#dashboard)
3. [Run History](#run-history)
4. [Analytics](#analytics)
5. [Repository Settings](#repository-settings)
6. [Organization Policy](#organization-policy)
7. [Notification Settings](#notification-settings)
8. [Admin Controls](#admin-controls)
9. [Who Uses Each Page](#who-uses-each-page)
10. [API Reference (Frontend)](#api-reference-frontend)

---

## Signing In

The web app uses GitHub OAuth. No separate account or password is required.

1. Visit `app.railo.dev`
2. Click **Sign in with GitHub**
3. Authorize Railo to read your GitHub organization memberships

Railo fetches your GitHub username, organization memberships, and installation records. After login, you will only see repositories and runs that belong to installations your GitHub account has access to.

To sign out, click your avatar in the top-right corner and select **Sign out**, or visit `/dashboard/logout`.

---

## Dashboard

**URL:** `/dashboard`  
**Audience:** Security engineers, engineering managers

The dashboard is the home page after login. It gives a quick overview of Railo activity across all repositories in your organization.

### North-star metrics

| Metric                 | What it means                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| **Fix PRs merged**     | Fix PRs whose CI passed (proxy for successfully merged fixes) — the primary success metric |
| **Fix PRs created**    | Total fix PRs opened by Railo                                                              |
| **CI success rate**    | Percentage of fix PRs where all CI checks passed                                           |
| **Failed runs (24 h)** | Runs that ended in error or failure in the last 24 hours                                   |

### Charts

| Chart                        | Description                                                     |
| ---------------------------- | --------------------------------------------------------------- |
| Fixes merged per day (line)  | Security debt reduction trend over time                         |
| Fixes created per repo (bar) | Which repositories have the most open security work             |
| Vulnerability types (pie)    | Distribution of SQLi / XSS / Secrets / Command Injection / etc. |

### Auto-merge readiness

A widget showing runs where Railo _would have_ auto-merged the fix PR under `auto_merge` mode. Useful for evaluating whether to upgrade from `fix` to `auto_merge` mode.

---

## Run History

**URL:** `/dashboard/runs` (frontend route) | API: `GET /api/runs`  
**Audience:** Security engineers

The Run History page lists every Railo run. Each row contains:

| Column     | Description                                             |
| ---------- | ------------------------------------------------------- |
| Repository | `owner/repo`                                            |
| PR         | The original pull request number                        |
| Status     | `success`, `warn_mode`, `no_findings`, `error`, etc.    |
| Job status | Internal worker state (`queued`, `completed`, `failed`) |
| Fix PR     | Link to the companion fix PR, if one was created        |
| Runtime    | How long the scan took in seconds                       |
| Timestamp  | When the run was recorded                               |

### Run detail view

Click any row to open the detail view for that run (`GET /api/runs/<id>`):

| Field                   | Description                                  |
| ----------------------- | -------------------------------------------- |
| **Violations found**    | Number of security findings detected         |
| **Violations fixed**    | Number of findings that were patched         |
| **Vulnerability types** | e.g. `["SQLi", "XSS"]`                       |
| **Fix PR number / URL** | Link to the companion PR                     |
| **CI passed**           | Whether the fix PR's CI checks passed        |
| **Correlation ID**      | Tracing ID for cross-referencing server logs |

Use the detail view for debugging failed runs or verifying that a specific vulnerability was fixed.

---

## Analytics

**URL:** `/dashboard/analytics` (frontend route) | API: `GET /api/analytics/*`  
**Audience:** Security engineers, engineering managers

The Analytics page provides security posture insights across all repositories.

### Available metrics

| Metric                   | API endpoint                            | Description                      |
| ------------------------ | --------------------------------------- | -------------------------------- |
| Summary                  | `GET /api/analytics/summary`            | Aggregated counts and rates      |
| Timeseries               | `GET /api/analytics/timeseries?days=30` | Daily run counts over time       |
| Vulnerability breakdown  | `GET /api/analytics/vulnerabilities`    | Finding counts by type           |
| Dry-run auto-merge stats | `GET /api/dashboard/dry-run-stats`      | Would-have-merged counts by repo |

### Summary fields

```json
{
  "total_runs": 120,
  "succeeded_runs": 98,
  "failed_runs": 4,
  "avg_duration_seconds": 12.4,
  "fix_merge_rate": 0.83,
  "ci_success_rate": 0.91,
  "fix_prs_created": 47,
  "fix_prs_merged": 39
}
```

`fix_prs_merged` is the **north-star metric** — it tells you how much security debt Railo has actually eliminated.

### Vulnerability breakdown

```json
{
  "data": [
    { "vuln_type": "SQLi", "count": 14 },
    { "vuln_type": "XSS", "count": 9 },
    { "vuln_type": "Secrets", "count": 6 }
  ]
}
```

Use this to prioritize which vulnerability types your team should focus on.

---

## Repository Settings

**URL:** `/dashboard/repos/<owner>/<repo>` (frontend route) | API: `GET /PUT /api/repos/<repo>/settings`  
**Audience:** Security engineers

This page controls how Railo behaves for each repository.

### Settings

| Setting               | Values           | Default | Description                                           |
| --------------------- | ---------------- | ------- | ----------------------------------------------------- |
| `enabled`             | `true` / `false` | `true`  | Whether Railo processes PRs in this repo              |
| `mode`                | `warn` / `fix`   | `warn`  | Operating mode                                        |
| `permission_tier`     | `A` / `B`        | `A`     | Tier A = safe automation; Tier B = broader automation |
| `max_diff_lines`      | integer          | `500`   | Maximum lines a fix patch may touch                   |
| `max_runtime_seconds` | integer          | `120`   | Abort scan after this many seconds                    |
| `ignore_file`         | path string      | `""`    | Path to a `.railoignore`-style file                   |
| `auto_merge_enabled`  | `true` / `false` | `false` | Enable auto-merge mode for this repo                  |

### Effective settings

`GET /api/repos/<repo>/effective-settings` returns the merged result of:

1. Repo-specific overrides (highest priority)
2. Organization policy defaults
3. Application defaults (lowest priority)

Use this endpoint to understand exactly which settings will be applied during the next scan.

---

## Organization Policy

**URL:** `/dashboard/org/<login>` (frontend route) | API: `GET /PUT /api/orgs/<login>/settings`  
**Audience:** Security engineering leads, admins

The Organization Policy page sets defaults that apply to all repositories belonging to the organization. Repo-specific settings override these defaults.

### Policy fields (same structure as repo settings)

```json
{
  "account_login": "myorg",
  "enabled": true,
  "mode": "warn",
  "max_diff_lines": 500,
  "max_runtime_seconds": 120,
  "ignore_file": "",
  "auto_merge_enabled": false,
  "permission_tier": "A"
}
```

Changes to the org policy take effect on the next PR scan. Repositories with explicit settings are not affected unless you remove those repo-level overrides.

---

## Notification Settings

**URL:** `/dashboard/notifications` (frontend route) | API: `GET /PUT /api/installations/<id>/notifications`  
**Audience:** Security engineers, on-call teams

Configure where Railo sends alerts and which events trigger them.

### Destinations

| Field               | Description                              |
| ------------------- | ---------------------------------------- |
| `slack_webhook_url` | Incoming webhook URL for a Slack channel |
| `email`             | Email address for alert delivery         |

### Event toggles

| Toggle                  | Default | Fires when                                  |
| ----------------------- | ------- | ------------------------------------------- |
| `notify_on_fix_applied` | OFF     | Railo opens a fix PR                        |
| `notify_on_ci_failure`  | OFF     | Fix PR CI checks fail                       |
| `notify_on_ci_success`  | OFF     | Fix PR CI checks pass                       |
| `notify_on_revert`      | OFF     | Railo reverts a fix branch after CI failure |

### Digest mode

When `digest_mode` is enabled, Railo batches all notifications into a single daily summary instead of sending one alert per event. This reduces noise for high-volume repositories.

To flush the digest immediately (e.g. to test your configuration):

```
POST /api/installations/<id>/notifications/digest
```

---

## Admin Controls

**URL:** `/dashboard/admin` (frontend route) | API: `GET /api/admin/*`  
**Audience:** Platform / security admin

### Kill switch

```
GET /api/admin/kill-switch
```

Returns `{ "active": true/false }`. Set `RAILO_KILL_SWITCH=1` in the environment to immediately halt all new processing. The kill switch is read at the start of every webhook event; in-flight jobs are not interrupted.

### Maintenance

```
POST /api/admin/maintenance
Headers: X-Admin-Token: <RAILO_ADMIN_TOKEN>
```

Enqueues a maintenance run that:

- Prunes runs older than the retention threshold
- Purges stale delivery-ID records
- Flushes expired in-memory idempotency keys

If Redis is unavailable, runs synchronously and returns the result inline.

---

## Who Uses Each Page

| Page                  | Security engineers | Engineering managers | Developers   |
| --------------------- | ------------------ | -------------------- | ------------ |
| Dashboard             | ✅ Daily           | ✅ Weekly            | —            |
| Run History           | ✅ Daily           | —                    | Occasionally |
| Analytics             | ✅ Weekly          | ✅ Weekly            | —            |
| Repository Settings   | ✅                 | —                    | Occasionally |
| Organization Policy   | ✅ (leads)         | —                    | —            |
| Notification Settings | ✅                 | —                    | —            |
| Admin Controls        | ✅ (admins)        | —                    | —            |

---

## API Reference (Frontend)

All endpoints are served from the same host as the web app. Responses are JSON unless noted.

| Method | Path                                           | Description                                              |
| ------ | ---------------------------------------------- | -------------------------------------------------------- |
| `GET`  | `/api/analytics/summary`                       | Dashboard summary (fix PR counts, rates)                 |
| `GET`  | `/api/analytics/timeseries`                    | Daily run counts (`?days=30`)                            |
| `GET`  | `/api/analytics/vulnerabilities`               | Finding counts by vulnerability type                     |
| `GET`  | `/api/dashboard/dry-run-stats`                 | Auto-merge readiness stats                               |
| `GET`  | `/api/runs`                                    | Recent runs list (`?limit=100`)                          |
| `GET`  | `/api/runs/<id>`                               | Single run detail                                        |
| `GET`  | `/api/audit-log`                               | Audit trail (`?repo=`, `?action=`, `?since=`, `?limit=`) |
| `GET`  | `/api/repos`                                   | All registered repositories                              |
| `GET`  | `/api/repos/<repo>/settings`                   | Repo-level settings                                      |
| `PUT`  | `/api/repos/<repo>/settings`                   | Update repo-level settings                               |
| `GET`  | `/api/repos/<repo>/effective-settings`         | Merged effective settings                                |
| `GET`  | `/api/orgs/<login>/settings`                   | Org-level policy                                         |
| `PUT`  | `/api/orgs/<login>/settings`                   | Update org-level policy                                  |
| `GET`  | `/api/installations/<id>/notifications`        | Notification settings                                    |
| `PUT`  | `/api/installations/<id>/notifications`        | Update notification settings                             |
| `POST` | `/api/installations/<id>/notifications/digest` | Flush digest queue                                       |
| `GET`  | `/api/admin/kill-switch`                       | Kill-switch status                                       |
| `POST` | `/api/admin/maintenance`                       | Trigger maintenance run                                  |
| `GET`  | `/api/metrics/health`                          | JSON ops health snapshot                                 |
| `GET`  | `/metrics`                                     | Prometheus scrape endpoint                               |

---

## Next Steps

- [Architecture](./ARCHITECTURE.md) — how the backend workers and web app interact
- [Getting Started](./GETTING_STARTED.md) — install the GitHub App and take your first scan
- [Environment Variables](./ENVIRONMENT_VARIABLES.md) — full configuration reference
- [Runbook](./RUNBOOK.md) — on-call procedures
