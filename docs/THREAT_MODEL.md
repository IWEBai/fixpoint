# Fixpoint Threat Model (App/SaaS Path)

This document describes the lightweight threat model for Fixpoint's GitHub App and
SaaS-style webhook processing path. It focuses on data minimization, webhook
security, and safe execution. It is designed to evolve into a SOC 2 seed.

---

## 1. Scope and Goals

**In scope**

- GitHub App webhook ingestion and PR processing.
- Scan/fix pipeline that runs on PR diffs.
- Minimal persistence (installations, run metadata).

**Out of scope**

- Customer code hosting (Fixpoint does not store repos).
- Long-term artifact storage beyond local runtime or opt-in cache.

**Goals**

- Minimize data exposure.
- Prevent token leakage and repo content retention.
- Make replay/spoofing/abuse difficult.
- Keep fixes deterministic and auditable.

---

## 2. Data Inventory

### What we store (minimal)

- GitHub App installation IDs and repo identifiers (owner/name).
- Run metadata: PR number, head SHA, status, timestamps, and summary counts.
- Optional baseline metadata and cached results when enabled.

### What we do NOT store

- GitHub tokens (installation tokens or PATs).
- Repository contents or full source code.
- Secrets found in code or raw Semgrep findings containing secret values.
- Full webhook payloads beyond transient in-memory processing.

---

## 3. Execution Isolation

- Each webhook event is processed in a temporary working directory.
- Repositories are cloned only for the duration of the run.
- Outputs are limited to deterministic patch application and metadata.
- No shell access is exposed to end users.

---

## 4. Webhook Security

**Replay protection**

- Webhook delivery IDs are tracked to prevent reprocessing.
- Duplicate delivery IDs are rejected.

**Spoofing protection**

- HMAC-SHA256 signature verification on incoming webhook payloads.
- Supports separate secrets for GitHub App and repository webhooks.

**Abuse controls**

- Rate limiting on a per-repo/PR key.
- Allowlist/denylist for repositories.
- Mode downgrade to warn when push permissions are not available.

---

## 5. Deterministic Fix Safety

- Fixes are rule-based, no LLM use.
- Idempotency prevents re-applying the same fix.
- Safety rails (max diff size, max files, formatting expansion guard) limit impact.
- Optional baseline mode to suppress legacy findings without hiding new ones.

---

## 6. Logging and Telemetry

- Logs include metadata and status only (no code, no tokens).
- Findings summaries can include rule IDs and file paths, not secret values.
- Correlation IDs are used for traceability without persisting payloads.

---

## 7. Retention and Deletion

- Temporary repositories are deleted after each run.
- Cache and baseline files are optional and local to operator-controlled storage.
- Operators can disable cache and baseline artifacts to reduce retention.

---

## 8. SaaS-Specific Considerations

If hosted as a SaaS:

- Store only what is required to operate the service (installation IDs, run metadata).
- Keep encrypted secrets in memory only; never persist tokens.
- Use isolated worker environments per job to avoid cross-tenant data mixing.
- Provide data retention controls and audit logs for compliance.

---

## 9. Known Limitations and Future Work

- Formalized retention policies for run metadata.
- Centralized secrets scanning for logs (defense in depth).
- Externalized rate limiting and replay storage (Redis) for horizontal scaling.

---

_Last updated: February 2026._
