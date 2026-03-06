from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from rq.job import Retry
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from core.security import (
    is_allowed_pr_action,
    is_repo_allowed,
    sanitize_repo_name,
    sanitize_repo_owner,
    validate_webhook_request,
)
from core.github_app_auth import get_installation_access_token
from railo_cloud import crud, schemas
from railo_cloud.artifacts import sanitize_artifact_paths
from railo_cloud.config import get_settings
from railo_cloud.deps import db_session
from railo_cloud.fingerprint import compute_run_fingerprint
from railo_cloud.models import RunStatus
from railo_cloud.queue import get_queue
from railo_cloud.queue import get_redis_connection

logger = logging.getLogger(__name__)

# --- Rate limiter ------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

# --- App ---------------------------------------------------------
_is_dev = get_settings().environment.lower() in ("development", "dev", "local", "test")
app = FastAPI(
    title="Railo Cloud",
    version="0.1.0",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS --------------------------------------------------------
_settings_init = get_settings()
_origins = [o.strip() for o in (_settings_init.allowed_origins or "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = get_settings()
if settings.skip_webhook_verification:
    os.environ["SKIP_WEBHOOK_VERIFICATION"] = "true"

artifact_root_path = Path(settings.artifact_root).resolve()
_MAX_BODY = settings.max_request_body_size


# --- Request body size limit ------------------------------------
@app.middleware("http")
async def _limit_body_size(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        cl = request.headers.get("content-length")
        if cl and int(cl) > _MAX_BODY:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
    return await call_next(request)


# --- Cache-Control: no-store for all /api/* routes --------------
@app.middleware("http")
async def _no_cache_api(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path.startswith("/auth/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


# --- Request correlation ID + structured logging ----------------
@app.middleware("http")
async def _log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    logger.info(
        "request method=%s path=%s status=%s request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        request_id,
    )
    return response


# --- Global exception handler -----------------------------------
@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# --- API key auth & RBAC -----------------------------------------------
from railo_cloud.auth import auth_router, require_admin, require_dev

app.include_router(auth_router, prefix="/auth", tags=["auth"])


def _serialize_run(run) -> schemas.RunResponse:
    sanitized_artifacts = sanitize_artifact_paths(run.artifact_paths, artifact_root_path)
    return schemas.RunResponse(
        id=str(run.id),
        status=run.status,
        repo_owner=run.repo_owner,
        repo_name=run.repo_name,
        pr_number=run.pr_number,
        base_ref=run.base_ref,
        head_ref=run.head_ref,
        head_sha=run.head_sha,
        mode=run.mode,
        engine_version=run.engine_version,
        job_id=run.job_id,
        correlation_id=run.correlation_id,
        fingerprint=run.fingerprint,
        error=run.error,
        error_code=run.error_code,
        error_summary=run.error_summary,
        summary=run.summary,
        artifact_paths=sanitized_artifacts,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _serialize_repo(repo) -> schemas.RepoResponse:
    return schemas.RepoResponse(
        id=str(repo.id),
        repo_id=repo.repo_id,
        repo_owner=repo.repo_owner,
        repo_name=repo.repo_name,
        installation_id=repo.installation_id,
        enabled=repo.enabled,
        mode=repo.mode,
        baseline_ref=repo.baseline_ref,
        rails_preset=repo.rails_preset,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def root() -> dict[str, str]:
    return {
        "name": "Railo Cloud",
        "status": "ok",
        "docs": "/docs",
    }


# --- API router (all dashboard/data endpoints under /api) -------
api_router = APIRouter(prefix="/api", dependencies=[Depends(require_dev)])


@app.get("/dashboard")
def dashboard_redirect():
    # Backwards-compatible entrypoint used by the web login button.
    return RedirectResponse(url="/auth/callback/github?role=admin", status_code=302)


@app.get("/metrics", dependencies=[Depends(require_dev)])
def metrics(session=Depends(db_session)):
    """Basic operational metrics: queue depth and run status breakdown."""
    from sqlalchemy import func, select
    from railo_cloud.models import Run

    try:
        redis_conn = get_redis_connection()
        queue_obj = get_queue()
        queue_len = len(queue_obj)
        failed_len = redis_conn.llen("rq:queue:failed") or 0
    except Exception:
        queue_len = -1
        failed_len = -1

    try:
        rows = session.execute(
            select(Run.status, func.count().label("cnt")).group_by(Run.status)
        ).all()
        run_counts = {r.status: r.cnt for r in rows}
    except Exception:
        run_counts = {}

    return {
        "queue": {"queued": queue_len, "failed": failed_len},
        "runs": run_counts,
    }


@app.post("/github/installation", response_model=schemas.InstallationResponse,
          dependencies=[Depends(require_admin)])
def create_installation(payload: schemas.InstallationCreate, session=Depends(db_session)):
    inst = crud.upsert_installation(
        session,
        installation_id=payload.installation_id,
        account_login=payload.account_login,
        account_type=payload.account_type,
    )
    return inst


@api_router.get("/repos", response_model=schemas.ReposList)
def list_repositories(session=Depends(db_session)):
    repos = crud.list_repos(session=session)
    return schemas.ReposList(repos=[_serialize_repo(r) for r in repos])


@api_router.patch("/repos/{repo_id}", response_model=schemas.RepoResponse,
                  dependencies=[Depends(require_admin)])
def update_repository(repo_id: uuid.UUID, payload: schemas.RepoUpdate, session=Depends(db_session)):
    repo = crud.get_repo(session, repo_id)
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    repo = crud.upsert_repository(
        session,
        repo_id=repo.repo_id,
        repo_owner=repo.repo_owner,
        repo_name=repo.repo_name,
        installation_id=repo.installation_id,
        enabled=payload.enabled if payload.enabled is not None else repo.enabled,
        mode=payload.mode or repo.mode,
        baseline_ref=payload.baseline_ref if payload.baseline_ref is not None else repo.baseline_ref,
        rails_preset=payload.rails_preset if payload.rails_preset is not None else repo.rails_preset,
    )
    return _serialize_repo(repo)


@api_router.get("/runs", response_model=schemas.RunsList)
def list_runs(session=Depends(db_session)):
    runs = crud.list_runs(session=session)
    return schemas.RunsList(runs=[_serialize_run(r) for r in runs])


@api_router.get("/runs/{run_id}", response_model=schemas.RunResponse)
def get_run(run_id: uuid.UUID, session=Depends(db_session)):
    run = crud.get_run(session, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _serialize_run(run)


@api_router.get("/analytics/summary", response_model=schemas.AnalyticsSummaryResponse)
def get_analytics_summary_endpoint(session=Depends(db_session)):
    data = crud.get_analytics_summary(session)
    return schemas.AnalyticsSummaryResponse(**data)


@api_router.get("/analytics/timeseries", response_model=schemas.AnalyticsTimeseriesResponse)
def get_analytics_timeseries_endpoint(days: int = 30, session=Depends(db_session)):
    data = crud.get_analytics_timeseries(session, days=days)
    return schemas.AnalyticsTimeseriesResponse(data=data)


@api_router.get("/user/settings")
def get_user_settings():
    # Stub for user settings
    return {
        "theme": "dark",
        "notifications_enabled": True,
        "role": "admin"
    }


@api_router.post("/user/settings")
def update_user_settings(payload: dict):
    # Stub for updating user settings
    return {"status": "success", "settings": payload}


@api_router.post("/runs/{run_id}/rerun", response_model=schemas.RunResponse,
                 dependencies=[Depends(require_admin)])
def rerun(run_id: uuid.UUID, session=Depends(db_session)):
    if settings.engine_mode != "local":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rerun allowed only in local mode")

    original = crud.get_run(session, run_id)
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    # Look up installation credentials from the repository record
    installation_id: int | None = None
    installation_token: str | None = None
    repo_record = crud.get_repo_by_owner_name(session, original.repo_owner, original.repo_name)
    if repo_record and repo_record.installation_id:
        installation_id = repo_record.installation_id
        installation_token = get_installation_access_token(int(installation_id))

    correlation_id = str(uuid.uuid4())
    base_ref = original.base_ref or settings.engine_base_ref
    head_ref = original.head_ref or settings.engine_head_ref
    fingerprint = compute_run_fingerprint(
        repo_owner=original.repo_owner,
        repo_name=original.repo_name,
        base_ref=base_ref,
        head_ref=head_ref,
        head_sha=original.head_sha,
        engine_mode=settings.engine_mode,
        fixpoint_mode=original.mode,
        max_runtime_seconds=settings.max_runtime_seconds,
        artifact_root=settings.artifact_root,
        engine_version=settings.engine_version,
    )
    new_run = crud.create_run(
        session=session,
        repo_owner=original.repo_owner,
        repo_name=original.repo_name,
        pr_number=original.pr_number,
        base_ref=base_ref,
        head_ref=head_ref,
        head_sha=original.head_sha,
        mode=original.mode,
        engine_version=settings.engine_version,
        correlation_id=correlation_id,
        summary={"message": f"rerun of {run_id}"},
        fingerprint=fingerprint,
    )

    job_payload = {
        "run_id": str(new_run.id),
        "repo_owner": new_run.repo_owner,
        "repo_name": new_run.repo_name,
        "pr_number": new_run.pr_number,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "head_sha": new_run.head_sha,
        "mode": new_run.mode,
        "engine_version": settings.engine_version,
        "payload": {},
        "enable_engine": True,
        "local_repo_path": settings.local_repo_path,
        "engine_repo_path": settings.engine_repo_path,
        "engine_mode": settings.engine_mode,
        "engine_base_ref": settings.engine_base_ref,
        "engine_head_ref": settings.engine_head_ref,
        "correlation_id": correlation_id,
        "max_runtime_seconds": settings.max_runtime_seconds,
        "installation_id": installation_id,
        "installation_token": installation_token,
    }

    queue = get_queue()
    job = queue.enqueue(
        "railo_cloud.worker.handle_job",
        job_payload,
        job_id=str(new_run.id),
        at_front=False,
        retry=Retry(max=3, interval=[10, 30, 60]),
    )
    crud.update_run_status(session, new_run.id, RunStatus.queued, job_id=job.id)
    refreshed = crud.get_run(session, new_run.id) or new_run
    return _serialize_run(refreshed)


@app.post("/webhook/github", response_model=schemas.RunResponse)
@limiter.limit("60/minute")
async def webhook(request: Request, session=Depends(db_session)):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    webhook_secrets = [s for s in [settings.github_webhook_secret, settings.webhook_secret] if s]

    is_valid, error = validate_webhook_request(
        raw_body,
        signature,
        event_type,
        delivery_id,
        webhook_secrets or settings.webhook_secret,
    )
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error or "Invalid signature")

    try:
        payload: dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    if event_type != "pull_request":
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Event ignored")

    action = payload.get("action", "")
    if not is_allowed_pr_action(action):
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Action ignored")

    repo_owner_raw = payload.get("repository", {}).get("owner", {}).get("login", "")
    repo_name_raw = payload.get("repository", {}).get("name", "")
    ok_owner, owner_or_error = sanitize_repo_owner(repo_owner_raw)
    if not ok_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=owner_or_error)
    ok_repo, repo_or_error = sanitize_repo_name(repo_name_raw)
    if not ok_repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=repo_or_error)

    full_repo = f"{owner_or_error}/{repo_or_error}"
    allowed, reason = is_repo_allowed(full_repo)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    allowed_engine_modes = {"stub", "local", "live"}
    engine_mode = settings.engine_mode or "stub"
    if engine_mode not in allowed_engine_modes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid engine_mode")

    pr = payload.get("pull_request", {})
    pr_number = pr.get("number") or payload.get("number")
    base_ref = pr.get("base", {}).get("ref")
    head_ref = pr.get("head", {}).get("ref")
    head_sha = pr.get("head", {}).get("sha")
    installation = payload.get("installation", {}) or {}
    installation_id = installation.get("id")
    account_login = installation.get("account", {}).get("login") if isinstance(installation.get("account"), dict) else None
    account_type = installation.get("account", {}).get("type") if isinstance(installation.get("account"), dict) else None
    correlation_id = str(uuid.uuid4())

    installation_token: str | None = None
    if installation_id:
        installation_token = get_installation_access_token(int(installation_id))
        if not installation_token:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch installation token")

    fingerprint = compute_run_fingerprint(
        repo_owner=owner_or_error,
        repo_name=repo_or_error,
        base_ref=base_ref,
        head_ref=head_ref,
        head_sha=head_sha,
        engine_mode=engine_mode,
        fixpoint_mode=settings.fixpoint_mode,
        max_runtime_seconds=settings.max_runtime_seconds,
        artifact_root=settings.artifact_root,
        engine_version=settings.engine_version,
    )

    if installation_id:
        crud.upsert_installation(
            session,
            installation_id=installation_id,
            account_login=account_login,
            account_type=account_type,
        )

    repo = crud.upsert_repository(
        session,
        repo_id=payload.get("repository", {}).get("id"),
        repo_owner=owner_or_error,
        repo_name=repo_or_error,
        installation_id=installation_id,
        enabled=True,
        mode=settings.fixpoint_mode,
    )

    effective_mode = repo.mode or settings.fixpoint_mode

    run = crud.create_run(
        session=session,
        repo_owner=owner_or_error,
        repo_name=repo_or_error,
        pr_number=pr_number,
        base_ref=base_ref,
        head_ref=head_ref,
        head_sha=head_sha,
        mode=effective_mode,
        engine_version=settings.engine_version,
        correlation_id=correlation_id,
        summary={"message": "queued"},
        fingerprint=fingerprint,
    )

    job_payload = {
        "run_id": str(run.id),
        "repo_owner": owner_or_error,
        "repo_name": repo_or_error,
        "pr_number": pr_number,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "mode": effective_mode,
        "engine_version": settings.engine_version,
        "payload": payload,
        "enable_engine": settings.enable_engine,
        "local_repo_path": settings.local_repo_path,
        "engine_repo_path": settings.engine_repo_path,
        "engine_mode": engine_mode,
        "engine_base_ref": settings.engine_base_ref,
        "engine_head_ref": settings.engine_head_ref,
        "correlation_id": correlation_id,
        "max_runtime_seconds": settings.max_runtime_seconds,
        "installation_id": installation_id,
        "installation_token": installation_token,
    }

    queue = get_queue()
    job = queue.enqueue(
        "railo_cloud.worker.handle_job",
        job_payload,
        job_id=str(run.id),
        at_front=False,
        retry=Retry(max=3, interval=[10, 30, 60]),
    )
    crud.update_run_status(session, run.id, RunStatus.queued, job_id=job.id)
    refreshed = crud.get_run(session, run.id) or run

    return schemas.RunResponse.from_orm(refreshed)


# --- Analytics: vulnerability breakdown -------------------------
@api_router.get("/analytics/vulnerabilities")
def analytics_vulnerabilities(session=Depends(db_session)):
    """Vulnerability type breakdown derived from run summaries."""
    from sqlalchemy import select
    from railo_cloud.models import Run
    from collections import Counter

    rows = session.execute(
        select(Run.summary).where(Run.summary.isnot(None))
    ).scalars().all()

    counts: Counter = Counter()
    for summary in rows:
        if isinstance(summary, dict):
            for vuln in summary.get("vulnerabilities", []):
                vtype = vuln.get("type") or vuln.get("vuln_type") or vuln.get("rule_id", "unknown")
                counts[vtype] += 1

    data = [{"name": k, "count": v} for k, v in counts.most_common(10)]
    return {"data": data}


# --- Dashboard: dry-run stats for Tier A repos ------------------
@api_router.get("/dashboard/dry-run-stats")
def dashboard_dry_run_stats(session=Depends(db_session)):
    """Tier A dry-run stats: fix PRs that passed safety gates but weren't auto-merged."""
    from sqlalchemy import select, func
    from railo_cloud.models import Run

    rows = session.execute(
        select(Run.repo_owner, Run.repo_name, func.count().label("cnt"))
        .where(Run.summary["dry_run_eligible"].as_boolean().is_(True))
        .group_by(Run.repo_owner, Run.repo_name)
    ).all()

    by_repo = [{"repo": f"{r.repo_owner}/{r.repo_name}", "count": r.cnt} for r in rows]
    total = sum(r["count"] for r in by_repo)
    return {"would_have_auto_merged": total, "by_repo": by_repo}


# --- Installations list -----------------------------------------
@api_router.get("/installations")
def list_installations(session=Depends(db_session)):
    from sqlalchemy import select
    from railo_cloud.models import Installation

    rows = session.execute(select(Installation)).scalars().all()
    return {
        "installations": [
            {"installation_id": r.installation_id, "account_login": r.account_login or ""}
            for r in rows
        ]
    }


# --- Notification settings per installation ---------------------
@api_router.get("/installations/{installation_id}/notifications")
def get_notification_settings(installation_id: int, session=Depends(db_session)):
    # Return defaults — extend with a DB table when notification settings are persisted
    return {
        "installation_id": installation_id,
        "slack_webhook_url": "",
        "email": "",
        "notify_on_fix_applied": True,
        "notify_on_ci_failure": True,
        "notify_on_ci_success": False,
        "notify_on_revert": True,
        "digest_mode": False,
    }


@api_router.put("/installations/{installation_id}/notifications", status_code=204)
def update_notification_settings(installation_id: int, body: dict):
    # Placeholder — persist to DB when notification settings table exists
    return None


# --- Org policy settings ----------------------------------------
@api_router.get("/orgs/{slug}/settings")
def get_org_settings(slug: str, session=Depends(db_session)):
    from sqlalchemy import select
    from railo_cloud.models import Repository

    # Derive mode/enabled from repos belonging to this org
    rows = session.execute(
        select(Repository).where(Repository.repo_owner == slug)
    ).scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No repositories found for org '{slug}'")

    mode = rows[0].mode or "warn"
    enabled = any(r.enabled for r in rows)
    return {
        "account_login": slug,
        "enabled": enabled,
        "mode": mode,
        "max_diff_lines": 500,
        "max_runtime_seconds": 120,
        "ignore_file": "",
        "auto_merge_enabled": False,
        "permission_tier": "A",
    }


@api_router.put("/orgs/{slug}/settings", status_code=204)
def update_org_settings(slug: str, body: dict, session=Depends(db_session)):
    from sqlalchemy import update as sa_update
    from railo_cloud.models import Repository

    mode = body.get("mode", "warn")
    enabled = body.get("enabled", True)
    session.execute(
        sa_update(Repository)
        .where(Repository.repo_owner == slug)
        .values(mode=mode, enabled=enabled)
    )
    session.commit()
    return None


app.include_router(api_router)

# --- Serving Frontend SPA ---------------------------------------
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"

if frontend_dist.exists() or os.getenv("RAILO_SERVE_FRONTEND") == "true":
    # Mount everything else to StaticFiles, except we need a fallback for React Router
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Allow requests to /docs, /openapi.json, /redoc, /api, /auth etc. to pass through
        # if they were caught here (though normally they define their own routes earlier).
        # But since this is a catch-all at the very bottom, it only gets unmatched routes.
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        
        index_file = frontend_dist / "index.html"
        if index_file.is_file():
            return FileResponse(str(index_file))
            
        return JSONResponse(status_code=404, content={"detail": "Frontend build not found or route does not exist"})

