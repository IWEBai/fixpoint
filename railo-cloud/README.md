# Fixpoint Cloud

Local-first scaffold for the hosted Fixpoint stack. Runs FastAPI ingress, an RQ worker, Postgres, and Redis via Docker Compose. The worker can stub GitHub auth and optionally call the existing Fixpoint engine.

## Services

- **api**: FastAPI webhook ingress; enqueues jobs and exposes run listings.
- **worker**: RQ worker that processes queued webhooks; can run the engine when enabled.
- **postgres**: Persistence for runs.
- **redis**: Queue + rate limiting/idempotency backing store.
- **migrations**: One-shot container to apply Alembic migrations.
- **web**: Placeholder for a Next.js dashboard (to be filled in next).

## Quick start (local)

```bash
cd fixpoint-cloud
cp .env.example .env
docker-compose up --build
```

The migrations service runs `alembic upgrade head` automatically on startup. To apply migrations manually:

```bash
alembic upgrade head
```

To create a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Health: http://localhost:8000/health

Replay a fixture webhook (stubbed mode):

```bash
curl -X POST "http://localhost:8000/webhook" \
	-H "X-GitHub-Event: pull_request" \
	-H "X-Hub-Signature-256: sha256=$(echo -n '{}' | openssl dgst -sha256 -hmac devsecret | cut -d' ' -f2)" \
	-H "X-GitHub-Delivery: test" \
	-d @fixpoint-cloud/fixtures/pull_request.json \
	-H "Content-Type: application/json"
```

List runs:

```bash
curl http://localhost:8000/runs
```

Engine modes (local validation only):

- `ENGINE_MODE=stub` (default safe): queue records, no engine execution.
- `ENGINE_MODE=local`: run Fixpoint against a local repo checkout at `ENGINE_REPO_PATH` using `ENGINE_BASE_REF`/`ENGINE_HEAD_REF`. No GitHub calls.

Artifacts: worker writes per-run outputs under `/artifacts/{run_id}` (semgrep JSON, patch_plan.json) and stores their paths on the run record.

Rerun determinism: `POST /runs/{id}/rerun` (only in `ENGINE_MODE=local`) enqueues a fresh run with the same refs.

## Flags

- `ENABLE_ENGINE=false` (default) stubs engine execution; set to `true` to call the existing Fixpoint engine (requires git+semgrep availability and repo access).
- `SKIP_WEBHOOK_VERIFICATION=true` only for local replay; set to `false` with a real `WEBHOOK_SECRET` for anything remote.
- `ENGINE_MODE` / `ENGINE_REPO_PATH` / `ENGINE_BASE_REF` / `ENGINE_HEAD_REF` drive local runs with no GitHub token.
- `ENGINE_VERSION` (optional) tags runs/fingerprints with an engine version or git SHA for determinism checks across upgrades.

## To-do next

- Wire real GitHub App token exchange when creds are available.
- Fill the Next.js dashboard under `web/`.
- Add CI E2E that boots compose, replays a fixture, and asserts a run row.
