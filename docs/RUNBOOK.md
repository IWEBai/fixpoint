# Railo Cloud — Incident Runbook

## Overview

| Component | Azure Name | Resource Group |
|---|---|---|
| API | `railo-api` | `railo-cloud` |
| Worker | `railo-worker` | `railo-cloud` |
| Database | `railo-pg` | `railo-cloud` |
| Redis | `railo-redis` | `railo-cloud` |
| Registry | `railoregistry.azurecr.io` | |
| Key Vault | `railo-kv` | `railo-cloud` |

---

## Quick commands

```bash
# Tail API logs
az containerapp logs show -n railo-api  -g railo-cloud --follow

# Tail Worker logs
az containerapp logs show -n railo-worker -g railo-cloud --follow

# List active revisions
az containerapp revision list -n railo-api    -g railo-cloud -o table
az containerapp revision list -n railo-worker -g railo-cloud -o table
```

---

## Scenarios

### 1. Worker stuck / jobs not processing

**Symptoms**: GitHub check runs not appearing, queue depth rising in `/metrics`.

**Steps**
1. Check worker logs for tracebacks:
   ```bash
   az containerapp logs show -n railo-worker -g railo-cloud --follow
   ```
2. Inspect RQ queue via Redis CLI (get Redis URL from Key Vault first):
   ```bash
   redis-cli -u "$REDIS_URL" llen railo:queue:default
   redis-cli -u "$REDIS_URL" llen railo:queue:failed
   ```
3. If dead-lettered jobs have accumulated, inspect and optionally replay:
   ```bash
   rq info --url "$REDIS_URL"
   rq requeue --all -u "$REDIS_URL"  # replay DLQ
   ```
4. Restart the worker replica:
   ```bash
   az containerapp revision restart \
     -n railo-worker -g railo-cloud \
     --revision $(az containerapp revision list -n railo-worker -g railo-cloud \
                   --query "[0].name" -o tsv)
   ```
5. If restarts don't help, redeploy the last known-good image (see [Rollback](#rollback)).

---

### 2. High error rate on API

**Symptoms**: Webhook deliveries from GitHub returning 5xx in GitHub App settings.

**Steps**
1. Check API logs for exceptions (look for `"level":"error"` in JSON logs):
   ```bash
   az containerapp logs show -n railo-api -g railo-cloud --follow | grep '"level":"error"'
   ```
2. Verify DB connectivity:
   ```bash
   az containerapp exec -n railo-api -g railo-cloud \
     --command "python -c \"from fixpoint_cloud.db.base import get_engine; get_engine().connect(); print('OK')\""
   ```
3. Verify Redis connectivity:
   ```bash
   az containerapp exec -n railo-api -g railo-cloud \
     --command "python -c \"from fixpoint_cloud.queue import get_redis_connection; get_redis_connection().ping(); print('OK')\""
   ```
4. Scale up API if CPU/memory is the bottleneck:
   ```bash
   az containerapp update -n railo-api -g railo-cloud \
     --min-replicas 2 --max-replicas 10
   ```

---

### 3. Database connections exhausted

**Symptoms**: Worker or API logs contain `too many clients` or `connection pool exhausted`.

**Steps**
1. Check active connections against Postgres (run from any container app or via `psql`):
   ```sql
   SELECT count(*) FROM pg_stat_activity;
   SELECT usename, count(*) FROM pg_stat_activity GROUP BY usename;
   ```
2. Kill idle connections if necessary:
   ```sql
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state = 'idle' AND state_change < now() - interval '10 minutes';
   ```
3. Reduce pool_size temporarily by setting environment variables:
   ```bash
   az containerapp update -n railo-api    -g railo-cloud --set-env-vars POOL_SIZE=2
   az containerapp update -n railo-worker -g railo-cloud --set-env-vars POOL_SIZE=2
   ```
4. Scale down to 1 replica and back up to flush stale connections:
   ```bash
   az containerapp update -n railo-api -g railo-cloud --min-replicas 0 --max-replicas 0
   az containerapp update -n railo-api -g railo-cloud --min-replicas 1 --max-replicas 5
   ```

---

### 4. Redis memory full

**Symptoms**: API returns 500 when enqueueing jobs. Logs show Redis `OOM` or `MISCONF`.

**Steps**
1. Check Redis memory:
   ```bash
   redis-cli -u "$REDIS_URL" info memory | grep used_memory_human
   ```
2. Inspect failed/dead queue sizes:
   ```bash
   redis-cli -u "$REDIS_URL" llen railo:queue:failed
   ```
3. Clear the failed queue if safe to do so:
   ```bash
   redis-cli -u "$REDIS_URL" del railo:queue:failed
   ```
4. Set a max-memory eviction policy if not already set:
   ```bash
   redis-cli -u "$REDIS_URL" config set maxmemory-policy allkeys-lru
   ```
5. Scale the Redis tier in Azure Portal if persistent pressure.

---

### 5. Failed webhook replay

**Situation**: A GitHub webhook delivery failed (e.g. during a redeploy) and needs to be replayed.

**Steps**
1. Go to GitHub → Settings → Developer settings → GitHub Apps → **Railo-Cloud** → Advanced → Recent Deliveries.
2. Find the failed delivery and click **Redeliver**.
3. Alternatively, replay via the API (requires `X-API-Key` header):
   ```bash
   curl -X POST https://<api-fqdn>/runs/<run_id>/rerun \
     -H "X-API-Key: $RAILO_API_KEY"
   ```

---

### 6. Rollback

**Roll back to a previous revision (zero-downtime)**:
```bash
# Find the previous good revision
az containerapp revision list -n railo-api -g railo-cloud -o table

# Activate old revision and send 100% traffic to it
az containerapp ingress traffic set -n railo-api -g railo-cloud \
  --revision-weight <old-revision-name>=100

# Same for worker (restart old revision)
az containerapp revision restart -n railo-worker -g railo-cloud \
  --revision <old-revision-name>
```

**Roll back to a specific image tag**:
```bash
TAG=abc1234  # 12-char git SHA

az containerapp update -n railo-api -g railo-cloud \
  --image railoregistry.azurecr.io/railo-api:$TAG \
  --revision-suffix rollback-$TAG

# Patch worker-app.yaml and redeploy
sed -i "s|railo-worker:.*|railo-worker:${TAG}|" worker-app.yaml
az containerapp update -n railo-worker -g railo-cloud --yaml worker-app.yaml
```

---

### 7. Graceful worker shutdown

The worker is configured with `terminationGracePeriodSeconds: 900` (15 min), giving in-flight
jobs time to finish. To manually drain:

```bash
# Scale the worker to 0 — existing pods finish their jobs then exit
az containerapp update -n railo-worker -g railo-cloud --min-replicas 0 --max-replicas 0
# Wait until revision shows Deprovisioned, then bring back
az containerapp update -n railo-worker -g railo-cloud --min-replicas 1 --max-replicas 5
```

---

## Useful queries

### Log Analytics (if connected)
```kusto
// 5xx errors in last hour
ContainerAppConsoleLogs
| where TimeGenerated > ago(1h)
| where ContainerName == "railo-api"
| where Log contains '"status":5'
| project TimeGenerated, Log
| order by TimeGenerated desc
```

### GitHub App deliveries
- Dashboard: `https://github.com/settings/apps/railo-cloud/advanced`

### Health endpoint
```bash
curl https://<api-fqdn>/health
# Expected: {"status":"ok","database":"ok","queue":"ok"}
```

### Metrics endpoint (requires API key)
```bash
curl -H "X-API-Key: $RAILO_API_KEY" https://<api-fqdn>/metrics
```
