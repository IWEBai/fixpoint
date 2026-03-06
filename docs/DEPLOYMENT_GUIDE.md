# Railo Cloud — Deployment Guide

> Last updated: 2026-02-27

## Table of Contents

- [Prerequisites](#prerequisites)
- [Architecture Overview](#architecture-overview)
- [Automated Deploy (CI/CD)](#automated-deploy-cicd)
- [Manual Deploy](#manual-deploy)
- [First-Time Setup (Fresh Environment)](#first-time-setup-fresh-environment)
- [Database Migrations](#database-migrations)
- [Rollback](#rollback)
- [Secret Rotation](#secret-rotation)
- [Environment Variables Reference](#environment-variables-reference)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool             | Version | Purpose                                   |
| ---------------- | ------- | ----------------------------------------- |
| Azure CLI (`az`) | 2.60+   | Container Apps, ACR, Key Vault management |
| Docker Desktop   | 28+     | Build container images locally            |
| Python           | 3.12+   | Run tests, migrations                     |
| Git              | 2.40+   | Source control                            |

You must be logged in to both Azure and ACR:

```powershell
az login
az account set --subscription 02453eb5-bdac-41d5-943f-c281dfaa310b
az acr login --name railoregistry
```

---

## Architecture Overview

```
GitHub webhook
    │
    ▼
railo-api (FastAPI, port 8000)  ──▶  Redis (rq queue: "fixpoint")
    │                                       │
    ▼                                       ▼
Postgres (railo-postgres)           railo-worker (RQ Worker)
                                        │
                                        ▼
                                    GitHub API (check runs, PR comments)
```

| Resource           | Azure Name                 | Type                           |
| ------------------ | -------------------------- | ------------------------------ |
| API                | `railo-api`                | Container App                  |
| Worker             | `railo-worker`             | Container App                  |
| Container Registry | `railoregistry.azurecr.io` | ACR (Basic)                    |
| Database           | `railo-postgres`           | Postgres Flexible Server       |
| Queue              | `railo-redis`              | Azure Cache for Redis          |
| Secrets            | `railo-kv`                 | Key Vault                      |
| Identity           | `railo-mi`                 | User-Assigned Managed Identity |
| Environment        | `railo-env`                | Container Apps Environment     |
| Resource Group     | `railo-cloud`              | Region: East Asia              |

---

## Automated Deploy (CI/CD)

The preferred deploy method. Defined in `.github/workflows/deploy.yml`.

### How it works

1. **Trigger**: Push to `main` or manual `workflow_dispatch`
2. **Build**: Docker image built from `fixpoint-cloud/docker/Dockerfile`, tagged with 12-char git SHA
3. **Push**: Same image pushed to ACR as both `railo-api:<tag>` and `railo-worker:<tag>`
4. **Deploy**: Both container apps updated with the new image via `az containerapp update`

### Required GitHub Secrets

Before the CD pipeline works, add these secrets to the GitHub repository settings:

| Secret                  | Value                                          | How to get it                                         |
| ----------------------- | ---------------------------------------------- | ----------------------------------------------------- |
| `AZURE_CLIENT_ID`       | Service principal / app registration client ID | `az ad app show --id <app-name> --query appId -o tsv` |
| `AZURE_TENANT_ID`       | Azure AD tenant ID                             | `az account show --query tenantId -o tsv`             |
| `AZURE_SUBSCRIPTION_ID` | `02453eb5-bdac-41d5-943f-c281dfaa310b`         | `az account show --query id -o tsv`                   |

These use OIDC federated credentials (no long-lived secrets). Set up the federated credential:

```bash
az ad app federated-credential create \
  --id <app-object-id> \
  --parameters '{
    "name": "github-deploy",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:<owner>/<repo>:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

### Triggering a deploy

```bash
# Option 1: Push to main
git push origin main

# Option 2: Manual trigger with custom tag
# Go to Actions → "Deploy to Azure Container Apps" → Run workflow
# Optionally specify an image tag (defaults to git SHA)
```

### Monitoring a deploy

Watch the GitHub Actions run, then verify:

```powershell
az containerapp revision list -n railo-api -g railo-cloud `
  --query "[0].{name:name, running:properties.runningState}" -o table

az containerapp revision list -n railo-worker -g railo-cloud `
  --query "[0].{name:name, running:properties.runningState}" -o table
```

---

## Manual Deploy

Use this when CI/CD is not yet configured or you need to deploy a hotfix.

### Step 1 — Build the image

```powershell
cd E:\fixpoint-cloud

# Use a unique tag (date + letter works well)
$TAG = "v0227a"

docker build -f fixpoint-cloud/docker/Dockerfile `
  -t railoregistry.azurecr.io/railo-api:$TAG `
  -t railoregistry.azurecr.io/railo-worker:$TAG .
```

> **Important**: Always use unique image tags. Azure caches `:latest` and won't pull fresh images.

### Step 2 — Push to ACR

```powershell
az acr login --name railoregistry
docker push railoregistry.azurecr.io/railo-api:$TAG
docker push railoregistry.azurecr.io/railo-worker:$TAG
```

### Step 3 — Deploy API

```powershell
az containerapp update -n railo-api -g railo-cloud `
  --image railoregistry.azurecr.io/railo-api:$TAG `
  --revision-suffix $TAG
```

### Step 4 — Deploy Worker

The worker uses a YAML file because it needs command array and KEDA scaling config:

```powershell
# Edit worker-app.yaml: update image tag and revisionSuffix
# image: railoregistry.azurecr.io/railo-worker:<TAG>
# revisionSuffix: <TAG>

az containerapp update -n railo-worker -g railo-cloud `
  --yaml worker-app.yaml
```

### Step 5 — Verify

```powershell
# Check revisions are running
az containerapp revision list -n railo-api -g railo-cloud `
  --query "[].{name:name, running:properties.runningState}" -o table

az containerapp revision list -n railo-worker -g railo-cloud `
  --query "[].{name:name, running:properties.runningState}" -o table

# Health check
Invoke-WebRequest -Uri https://api.railo.dev/health -UseBasicParsing

# Check metrics (requires API key)
Invoke-WebRequest -Uri https://api.railo.dev/metrics `
  -Headers @{"X-API-Key"="<your-api-key>"} -UseBasicParsing
```

### Step 6 — End-to-end test

Push a commit to a PR on an installed repo and verify:

1. Webhook delivery shows 200 in GitHub App settings
2. A new run appears in the database with status `succeeded`
3. A check run appears on the PR

---

## First-Time Setup (Fresh Environment)

Use `scripts/azure/deploy_container_apps.ps1` for a complete from-scratch provisioning. It creates:

1. Resource group, ACR, storage account
2. Postgres Flexible Server, Redis cache
3. Managed identity + Key Vault with all secrets
4. Container Apps environment
5. API, Worker, and Web container apps

```powershell
# Set required env vars
$env:RAILO_PG_PASS = "<strong-password>"
$env:RAILO_GITHUB_WEBHOOK_SECRET = "<webhook-secret>"
$env:RAILO_GITHUB_PRIVATE_KEY_PATH = "path/to/github-app.pem"

# Run the provisioning script
.\scripts\azure\deploy_container_apps.ps1
```

After provisioning:

1. Configure custom domain (see below)
2. Update GitHub App webhook URL to `https://api.railo.dev/webhook/github`
3. Set the `API_KEY` env var on the API container app
4. Run database migrations

### Custom Domain Setup

```powershell
# 1. Add DNS records at your registrar:
#    CNAME: api → railo-api.<env-fqdn>
#    TXT:   asuid.api → <domain-verification-id>

# 2. Get the verification ID
az containerapp show -n railo-api -g railo-cloud `
  --query "properties.customDomainVerificationId" -o tsv

# 3. Add and bind the hostname
az containerapp hostname add -n railo-api -g railo-cloud `
  --hostname api.railo.dev

az containerapp hostname bind -n railo-api -g railo-cloud `
  --hostname api.railo.dev --environment railo-env --validation-method CNAME
```

---

## Database Migrations

Migrations live in `migrations/versions/`. Run them against production:

### Option A — Direct SQL (for simple index/DDL changes)

```powershell
$pw = ([regex]::Match(
  (az keyvault secret show --vault-name railo-kv --name pg-conn --query value -o tsv),
  '://[^:]+:([^@]+)@'
)).Groups[1].Value

python -c "
import psycopg2
conn = psycopg2.connect(
    host='railo-postgres.postgres.database.azure.com',
    dbname='railo', user='railo_admin',
    password='$pw', sslmode='require'
)
conn.autocommit = True
cur = conn.cursor()
cur.execute('CREATE INDEX IF NOT EXISTS ix_runs_created_at ON runs (created_at)')
print('Done')
conn.close()
"
```

### Option B — Alembic (for schema changes)

```bash
# From the container (if alembic is installed in the image)
az containerapp exec -n railo-api -g railo-cloud \
  --command "alembic upgrade head"

# Or set DATABASE_URL locally and run:
export DATABASE_URL="postgresql+psycopg://..."
alembic upgrade head
```

---

## Rollback

### Quick rollback — traffic shift (zero downtime)

```powershell
# List revisions to find the last good one
az containerapp revision list -n railo-api -g railo-cloud -o table

# Shift 100% traffic to the old revision
az containerapp ingress traffic set -n railo-api -g railo-cloud `
  --revision-weight <old-revision-name>=100

# For the worker (no ingress — restart old revision)
az containerapp revision restart -n railo-worker -g railo-cloud `
  --revision <old-revision-name>
```

### Full rollback — redeploy old image

```powershell
$OLD_TAG = "v0226j"  # last known-good tag

az containerapp update -n railo-api -g railo-cloud `
  --image railoregistry.azurecr.io/railo-api:$OLD_TAG `
  --revision-suffix rollback

# Update worker-app.yaml with $OLD_TAG, then:
az containerapp update -n railo-worker -g railo-cloud `
  --yaml worker-app.yaml
```

### Verify rollback

```powershell
Invoke-WebRequest -Uri https://api.railo.dev/health -UseBasicParsing
# Should return {"status":"ok"}
```

### Database rollback

If a migration needs reverting:

```bash
alembic downgrade -1   # revert last migration
alembic downgrade <revision_id>  # revert to specific revision
```

> **Warning**: Schema rollbacks can break running code. Deploy the matching code revision first, then roll back the schema.

---

## Secret Rotation

All secrets are stored in Azure Key Vault (`railo-kv`) and referenced by Container Apps via managed identity. Rotating a secret requires updating it in Key Vault, then restarting the apps so they pick up the new value.

### Rotate GitHub webhook secret

```powershell
# 1. Generate a new secret
$newSecret = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})

# 2. Update in Key Vault
az keyvault secret set --vault-name railo-kv `
  -n github-webhook-secret --value $newSecret

# 3. Update in GitHub App settings
#    GitHub → Settings → Developer settings → GitHub Apps → Railo-Cloud
#    → Webhook → Secret → paste $newSecret

# 4. Restart API to pick up new secret
az containerapp revision restart -n railo-api -g railo-cloud `
  --revision (az containerapp revision list -n railo-api -g railo-cloud `
    --query "[0].name" -o tsv)
```

### Rotate GitHub App private key

```powershell
# 1. Generate new key in GitHub App settings → Private keys → Generate
# 2. Download the .pem file

# 3. Update in Key Vault
az keyvault secret set --vault-name railo-kv `
  -n github-private-key --file path/to/new-key.pem

# 4. Revoke the old key in GitHub App settings

# 5. Restart both apps
az containerapp revision restart -n railo-api -g railo-cloud `
  --revision (az containerapp revision list -n railo-api -g railo-cloud --query "[0].name" -o tsv)
az containerapp revision restart -n railo-worker -g railo-cloud `
  --revision (az containerapp revision list -n railo-worker -g railo-cloud --query "[0].name" -o tsv)
```

### Rotate Postgres password

```powershell
# 1. Change password on the server
az postgres flexible-server update -n railo-postgres -g railo-cloud `
  --admin-password "<new-password>"

# 2. Update connection string in Key Vault
$newConn = "postgresql+psycopg://railo_admin:<new-password>@railo-postgres.postgres.database.azure.com:5432/railo"
az keyvault secret set --vault-name railo-kv -n pg-conn --value $newConn

# 3. Restart both apps
az containerapp revision restart -n railo-api -g railo-cloud `
  --revision (az containerapp revision list -n railo-api -g railo-cloud --query "[0].name" -o tsv)
az containerapp revision restart -n railo-worker -g railo-cloud `
  --revision (az containerapp revision list -n railo-worker -g railo-cloud --query "[0].name" -o tsv)
```

### Rotate Redis key

```powershell
# 1. Regenerate the Redis key
az redis regenerate-key -n railo-redis -g railo-cloud --key-type Primary

# 2. Get the new key
$newKey = az redis list-keys -n railo-redis -g railo-cloud --query primaryKey -o tsv
$redisHost = az redis show -n railo-redis -g railo-cloud --query hostName -o tsv
$newRedisUrl = "redis://:$newKey@${redisHost}:6379/0"

# 3. Update in Key Vault
az keyvault secret set --vault-name railo-kv -n redis-url --value $newRedisUrl

# 4. Restart both apps
az containerapp revision restart -n railo-api -g railo-cloud `
  --revision (az containerapp revision list -n railo-api -g railo-cloud --query "[0].name" -o tsv)
az containerapp revision restart -n railo-worker -g railo-cloud `
  --revision (az containerapp revision list -n railo-worker -g railo-cloud --query "[0].name" -o tsv)
```

### Rotate API key (management endpoints)

```powershell
# 1. Generate new key
$newApiKey = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})

# 2. Update on the container app
az containerapp update -n railo-api -g railo-cloud `
  --set-env-vars "API_KEY=$newApiKey"

# 3. Update any clients/scripts using the old key
Write-Host "New API key: $newApiKey — update your scripts and dashboards."
```

---

## Environment Variables Reference

### railo-api

| Variable                 | Source                              | Description                                |
| ------------------------ | ----------------------------------- | ------------------------------------------ |
| `DATABASE_URL`           | Key Vault (`pg-conn`)               | Postgres connection string                 |
| `REDIS_URL`              | Key Vault (`redis-url`)             | Redis connection string                    |
| `GITHUB_APP_ID`          | Key Vault (`github-app-id`)         | GitHub App ID (`2914293`)                  |
| `GITHUB_WEBHOOK_SECRET`  | Key Vault (`github-webhook-secret`) | Webhook HMAC secret                        |
| `GITHUB_APP_PRIVATE_KEY` | Key Vault (`github-private-key`)    | GitHub App private key (PEM)               |
| `ENGINE_MODE`            | Plain text                          | `live` / `local` / `stub`                  |
| `FIXPOINT_MODE`          | Plain text                          | `warn` / `enforce`                         |
| `API_KEY`                | Plain text env var                  | Key for management endpoints               |
| `ENVIRONMENT`            | Plain text                          | `production` disables `/docs` and `/redoc` |
| `ALLOWED_ORIGINS`        | Plain text                          | Comma-separated CORS origins               |

### railo-worker

Same Key Vault secrets as API. Additionally:

- Command: `python -m fixpoint_cloud.worker`
- `terminationGracePeriodSeconds: 600`
- `minReplicas: 1`

---

## Troubleshooting

| Symptom                               | Likely Cause                             | Fix                                                                                                |
| ------------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Webhook returns 404                   | Route mismatch                           | Ensure GitHub App URL is `https://api.railo.dev/webhook/github`                                    |
| Worker not picking up jobs            | Redis connectivity or KEDA trigger issue | Check worker logs, verify Redis URL matches                                                        |
| `Permission denied: /artifacts`       | Non-root user lacks dir permissions      | Ensure Dockerfile creates `/artifacts` with `appuser` ownership                                    |
| `terminationGracePeriodSeconds` error | Value > 600                              | Azure max is 600 seconds                                                                           |
| Image not updating after deploy       | Tag reuse                                | Always use unique tags (never `:latest`)                                                           |
| `IndentationError` on worker start    | Syntax error in worker.py                | Run `python -c "import py_compile; py_compile.compile('worker.py', doraise=True)"` before building |

For more detailed incident procedures, see [RUNBOOK.md](RUNBOOK.md).
