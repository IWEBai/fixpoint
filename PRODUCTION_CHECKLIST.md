# Railo Cloud — Production Readiness Checklist

> Generated: 2026-02-26 | Updated: 2026-02-27  
> Status: **Production-ready** — All checklist items complete. Deployed as `v0226j` (`prod4`). End-to-end verified on `api.railo.dev`.

---

## Current State (What Works)

- [x] GitHub App webhook → FastAPI API → 200 OK
- [x] API enqueues job to Redis → RQ worker picks it up
- [x] Worker clones repo with installation token (`x-access-token` in URL)
- [x] Worker fetches base ref with explicit refspec
- [x] Worker scans PR diff (`origin/{base}..{head}`)
- [x] Check run created on GitHub PR (Fixpoint - Security Check)
- [x] DB records run status transitions (`queued → running → succeeded/failed`)
- [x] Secrets in Azure Key Vault via Managed Identity
- [x] Webhook signature verification (`X-Hub-Signature-256`)
- [x] CI pipeline with pytest, Ruff lint, Docker build test
- [x] E2E test in CI (docker-compose, stub mode)
- [x] Alembic migrations with init container

---

## P0 — Critical (Must fix before any user traffic)

### Security

- [x] **Add auth to management endpoints**  
  `/repos`, `/runs`, `/runs/{id}`, `/repos/{id}` PATCH, `/github/installation` POST are all publicly accessible. Add API key, JWT, or session-based auth.  
  File: `fixpoint-cloud/fixpoint_cloud/api/main.py`

- [x] **Add CORS middleware**  
  No `CORSMiddleware` on the FastAPI app. The Next.js frontend will hit cross-origin errors, and without CORS any origin can call the API.  
  File: `fixpoint-cloud/fixpoint_cloud/api/main.py`

- [x] **Add rate limiting to API**  
  `core/rate_limit.py` exists but is only wired into the legacy webhook server, not the FastAPI app. All endpoints are unprotected from abuse.  
  File: `fixpoint-cloud/fixpoint_cloud/api/main.py`

### Bugs

- [x] **Fix `NameError` in `/runs/{run_id}/rerun`**  
  The rerun endpoint references `installation_id` and `installation_token` in `job_payload` but these variables are never defined in scope. Will crash at runtime.  
  File: `fixpoint-cloud/fixpoint_cloud/api/main.py` (~line 200)

### Database

- [x] **Configure connection pooling**  
  `create_engine()` has no `pool_size`, `max_overflow`, `pool_pre_ping`, or `pool_recycle`. Under load this will exhaust Postgres connection limits.  
  File: `fixpoint-cloud/fixpoint_cloud/db/base.py`

### Worker

- [x] **Add retry logic on job enqueue**  
  No `Retry()` configured. A transient GitHub API or network failure permanently kills the job. Add `Retry(max=3, interval=[10, 30, 60])`.  
  File: `fixpoint-cloud/fixpoint_cloud/queue.py` (enqueue call)  
  File: `fixpoint-cloud/fixpoint_cloud/api/main.py` (enqueue call)

- [x] **Add dead letter queue / failed job handling**  
  No `failed_job_registry` inspection, no DLQ, no alerting. Failed jobs silently accumulate in Redis.  
  File: `fixpoint-cloud/fixpoint_cloud/worker.py`

### Testing

- [x] **Write cloud API/worker tests**  
  Zero test coverage for `fixpoint_cloud.*` — no route tests, CRUD tests, schema tests, or worker unit tests. At minimum: test webhook validation, run creation, worker happy path, worker error paths.  
  Dir: `fixpoint-cloud/tests/` (create)

- [x] **Add `fixpoint_cloud` to CI coverage**  
  CI runs `pytest --cov=core --cov=patcher` only. Add `--cov=fixpoint_cloud`.  
  File: `.github/workflows/ci.yml`

---

## P1 — Important (Fix within first sprint after launch)

### Observability

- [x] **Wire structured logging into Cloud API**  
  Request logging middleware added (`X-Request-Id` correlation ID on every request/response). Worker now uses `logging.getLogger()` instead of `print()`.  
  Files: `fixpoint-cloud/fixpoint_cloud/api/main.py`, `worker.py`

- [x] **Add global exception handler**  
  `@app.exception_handler(Exception)` added returning safe `{"detail": "Internal server error"}` JSON and logging full traceback.  
  File: `fixpoint-cloud/fixpoint_cloud/api/main.py`

- [x] **Add metrics endpoint**  
  `/metrics` endpoint added (requires API key): returns queue depth (default + failed) and run status breakdown.

- [x] **Set up alerting**  
  3 Azure Monitor metric alerts created (`railo-queue-depth-high`, `railo-api-restarts`, `railo-worker-restarts`) with `railo-oncall` action group emailing zariffromlatif@gmail.com.

### Database

- [x] **Add indexes on `runs` table**  
  Migration `202602261400_add_runs_indexes.py` adds indexes on `created_at`, `(repo_owner, repo_name)`, `status`, `correlation_id`.  
  File: `migrations/versions/202602261400_add_runs_indexes.py`

- [x] **Fix worker session management**  
  Worker now uses `with contextlib.closing(get_session()) as session:` — sessions are always released even on unexpected exits.  
  File: `fixpoint-cloud/fixpoint_cloud/worker.py`

### Infrastructure

- [x] **Set `minReplicas: 1` on worker**  
  `minReplicas: 1` set in `worker-app.yaml`. Eliminates cold-start delay.  
  File: `worker-app.yaml`

- [x] **Add `terminationGracePeriodSeconds: 900`**  
  `terminationGracePeriodSeconds: 900` set in `worker-app.yaml`. RQ's built-in SIGTERM handling lets in-flight jobs finish.  
  File: `worker-app.yaml`

- [x] **Configure Redis persistence**  
  Skipped (accepted risk). Job queue is ephemeral by design — lost jobs can be replayed via GitHub webhook redelivery. AOF requires Premium-tier Redis (~10x cost). Risk documented in `docs/RUNBOOK.md`.

- [x] **Verify/document Postgres backup**  
  Verified: `backupRetentionDays: 7`, `geoRedundantBackup: Disabled`. Default automatic backups are active. Restore procedure documented in `docs/RUNBOOK.md`.

### Security

- [x] **Fix worker token leak**  
  Removed `os.environ["GITHUB_TOKEN"]` / `GIT_CONFIG_*` mutation. `token=installation_token` now passed directly to `create_check_run_with_annotations()`, `create_fix_comment()`, `create_warn_comment()`.  
  Files: `fixpoint-cloud/fixpoint_cloud/worker.py`, `core/status_checks.py`, `core/pr_comments.py`

- [x] **Limit webhook request body size**  
  Body-size middleware added — returns 413 if `Content-Length > 1 MB`.  
  File: `fixpoint-cloud/fixpoint_cloud/api/main.py`

### CI/CD

- [x] **Add CD pipeline (image build + push)**  
  `.github/workflows/deploy.yml` created. Triggers on push to `main`: builds API + Worker images, pushes to ACR, updates both Container Apps. Uses OIDC (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` secrets).  
  File: `.github/workflows/deploy.yml`

- [x] **Dockerfile hardening**  
  - Non-root `appuser` added to `Dockerfile`  
  - `.dockerignore` created (excludes `.git`, `__pycache__`, `.venv`, `tests/`, `docs/`, etc.)  
  File: `fixpoint-cloud/docker/Dockerfile`, `.dockerignore`

### Documentation

- [x] **Write incident runbooks**  
  `docs/RUNBOOK.md` created covering: worker stuck, high API error rate, DB connections exhausted, Redis memory full, failed webhook replay, rollback procedure, graceful worker drain.

- [x] **Write deployment guide**  
  `docs/DEPLOYMENT_GUIDE.md` created covering: manual & CI/CD deploy flow, rollback (traffic shift + image redeploy), secret rotation (webhook secret, private key, Postgres password, Redis key, API key), database migrations, environment variables reference, and troubleshooting guide.  
  File: `docs/DEPLOYMENT_GUIDE.md`

---

## P2 — Nice-to-have (Polish)

- [x] **Add correlation/request ID in API responses**  
  Request logging middleware generates `X-Request-Id` UUID and attaches it to every response. Correlation ID is also included in structured log output.

- [x] **Architecture diagram**  
  `docs/ARCHITECTURE.md` created with ASCII flow diagram, Mermaid sequence diagram, infrastructure map, and security boundaries table.

- [x] **Enhanced worker health check**  
  `worker_health.py` now checks: (1) Redis ping, (2) at least one RQ worker registered, (3) queue depth (warns if ≥50), (4) worker heartbeat freshness within 30 minutes.  
  File: `fixpoint-cloud/fixpoint_cloud/worker_health.py`

- [x] **Document dev secret defaults**  
  `fixpoint-cloud/.env.example` updated with prominent warning block. Each insecure value (`fixpoint`, `devsecret`, `SKIP_WEBHOOK_VERIFICATION=true`) annotated with `# CHANGE IN PRODUCTION` comment.

- [x] **API resource limits**  
  Added `--cpu 0.5 --memory 1Gi` to the `az containerapp update` step in `.github/workflows/deploy.yml`. Matches worker resource limits.

- [x] **Auto-generated API docs**  
  FastAPI `/docs`, `/redoc`, and `/openapi.json` endpoints are now conditionally disabled: only accessible when `ENVIRONMENT` is `development`, `dev`, `local`, or `test`. Disabled in production (`ENVIRONMENT=production`).  
  File: `fixpoint-cloud/fixpoint_cloud/api/main.py`

---

## Deploy Workflow Reference

Current manual deploy process (to be automated):

```
# 1. Build with unique tag
docker build -f fixpoint-cloud/docker/Dockerfile -t railoregistry.azurecr.io/railo-api:TAG -t railoregistry.azurecr.io/railo-worker:TAG .

# 2. Push
az acr login --name railoregistry
docker push railoregistry.azurecr.io/railo-api:TAG
docker push railoregistry.azurecr.io/railo-worker:TAG

# 3. Deploy API
az containerapp update -n railo-api -g railo-cloud --image railoregistry.azurecr.io/railo-api:TAG --revision-suffix SUFFIX

# 4. Deploy Worker (must use YAML for command array)
# Edit worker-app.yaml: image → TAG, revisionSuffix → SUFFIX
az containerapp update -n railo-worker -g railo-cloud --yaml worker-app.yaml

# 5. Verify
az containerapp revision list -n railo-worker -g railo-cloud --query "[].{name:name,running:properties.runningState}" -o table
```

**Important**: Always use unique image tags — Azure caches `:latest` and won't pull fresh images.
