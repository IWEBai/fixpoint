from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from railo_cloud.models import Installation, Repository, Run, RunStatus


def create_run(
    session: Session,
    repo_owner: str,
    repo_name: str,
    pr_number: int | None,
    base_ref: str | None,
    head_ref: str | None,
    head_sha: str | None,
    mode: str | None,
    engine_version: str | None = None,
    correlation_id: str | None = None,
    summary: dict | None = None,
    artifact_paths: dict | None = None,
    fingerprint: str | None = None,
) -> Run:
    run = Run(
        id=uuid.uuid4(),
        status=RunStatus.queued.value,
        repo_owner=repo_owner,
        repo_name=repo_name,
        pr_number=pr_number,
        base_ref=base_ref,
        head_ref=head_ref,
        head_sha=head_sha,
        mode=mode,
        engine_version=engine_version,
        correlation_id=correlation_id,
        fingerprint=fingerprint,
        summary=summary,
        artifact_paths=artifact_paths,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def update_run_status(
    session: Session,
    run_id: uuid.UUID,
    status: RunStatus,
    *,
    error: str | None = None,
    summary: dict | None = None,
    job_id: str | None = None,
    artifact_paths: dict | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> Optional[Run]:
    run = session.get(Run, run_id)
    if not run:
        return None
    run.status = status.value
    if error:
        run.error = error[:2000]
    if error_code:
        run.error_code = error_code[:255]
    if error_summary:
        run.error_summary = error_summary[:1000]
    if summary is not None:
        run.summary = summary
    if job_id:
        run.job_id = job_id
    if artifact_paths is not None:
        run.artifact_paths = artifact_paths
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def list_runs(session: Session, limit: int = 50, installation_ids: list[int] | None = None) -> Iterable[Run]:
    stmt = select(Run).order_by(Run.created_at.desc()).limit(limit)
    if installation_ids is not None:
        stmt = stmt.where(Run.run_installation_id.in_(installation_ids))
    return session.scalars(stmt).all()


def get_run(session: Session, run_id: uuid.UUID) -> Optional[Run]:
    return session.get(Run, run_id)


def upsert_installation(
    session: Session,
    *,
    installation_id: int,
    account_login: str | None,
    account_type: str | None,
) -> Installation:
    inst = session.scalar(select(Installation).where(Installation.installation_id == installation_id))
    if inst:
        inst.account_login = account_login or inst.account_login
        inst.account_type = account_type or inst.account_type
    else:
        inst = Installation(
            id=uuid.uuid4(),
            installation_id=installation_id,
            account_login=account_login,
            account_type=account_type,
        )
        session.add(inst)
    session.commit()
    session.refresh(inst)
    return inst


def upsert_repository(
    session: Session,
    *,
    repo_id: int | None,
    repo_owner: str,
    repo_name: str,
    installation_id: int | None,
    enabled: bool | None = None,
    mode: str | None = None,
    baseline_ref: str | None = None,
    rails_preset: str | None = None,
) -> Repository:
    stmt = select(Repository).where(Repository.repo_owner == repo_owner, Repository.repo_name == repo_name)
    repo = session.scalar(stmt)
    if repo:
        if repo_id is not None:
            repo.repo_id = repo_id
        if installation_id is not None:
            repo.installation_id = installation_id
        if enabled is not None:
            repo.enabled = enabled
        if mode is not None:
            repo.mode = mode
        if baseline_ref is not None:
            repo.baseline_ref = baseline_ref
        if rails_preset is not None:
            repo.rails_preset = rails_preset
    else:
        repo = Repository(
            id=uuid.uuid4(),
            repo_id=repo_id,
            repo_owner=repo_owner,
            repo_name=repo_name,
            installation_id=installation_id,
            enabled=enabled if enabled is not None else False,
            mode=mode or "warn",
            baseline_ref=baseline_ref,
            rails_preset=rails_preset,
        )
        session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


def list_repos(session: Session, limit: int = 200, installation_ids: list[int] | None = None) -> list[Repository]:
    stmt = select(Repository).order_by(Repository.created_at.desc()).limit(limit)
    if installation_ids is not None:
        stmt = stmt.where(Repository.installation_id.in_(installation_ids))
    return session.scalars(stmt).all()


def get_repo(session: Session, repo_uuid: uuid.UUID) -> Optional[Repository]:
    return session.get(Repository, repo_uuid)


def get_repo_by_owner_name(session: Session, owner: str, name: str) -> Optional[Repository]:
    stmt = select(Repository).where(Repository.repo_owner == owner, Repository.repo_name == name)
    return session.scalar(stmt)

def get_analytics_summary(session: Session, installation_ids: list[int] | None = None) -> dict:
    from sqlalchemy import func
    stmt = select(Run.status, func.count().label("cnt")).group_by(Run.status)
    if installation_ids is not None:
        stmt = stmt.where(Run.run_installation_id.in_(installation_ids))
    rows = session.execute(stmt).all()
    
    total = sum(r.cnt for r in rows)
    failed = sum(r.cnt for r in rows if r.status == "failed")
    succeeded = sum(r.cnt for r in rows if r.status == "succeeded")
    
    return {
        "total_runs": total,
        "failed_runs": failed,
        "succeeded_runs": succeeded,
        "avg_duration_seconds": 0.0,
    }

def get_analytics_timeseries(session: Session, days: int = 30, installation_ids: list[int] | None = None) -> list[dict]:
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    base_stmt = (
        select(
            func.to_char(Run.created_at, 'YYYY-MM-DD').label('day'),
            Run.status,
            func.count().label('cnt')
        )
        .where(Run.created_at >= cutoff_date)
        .group_by('day', Run.status)
        .order_by('day')
    )
    if installation_ids is not None:
        base_stmt = base_stmt.where(Run.run_installation_id.in_(installation_ids))
    rows = session.execute(base_stmt).all()
    
    # Aggregate by day
    data_by_day = {}
    for r in rows:
        day_str = r.day
        if day_str not in data_by_day:
            data_by_day[day_str] = {"total_runs": 0, "failed_runs": 0, "succeeded_runs": 0}
        
        data_by_day[day_str]["total_runs"] += r.cnt
        if r.status == "failed":
            data_by_day[day_str]["failed_runs"] += r.cnt
        elif r.status == "succeeded":
            data_by_day[day_str]["succeeded_runs"] += r.cnt
            
    result = []
    for day, stats in sorted(data_by_day.items()):
        result.append({
            "date": day,
            "total_runs": stats["total_runs"],
            "failed_runs": stats["failed_runs"],
            "succeeded_runs": stats["succeeded_runs"],
        })
        
    return result
