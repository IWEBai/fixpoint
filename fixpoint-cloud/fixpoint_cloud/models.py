from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from fixpoint_cloud.db.base import Base


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Run(Base):
    __tablename__ = "runs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(32), nullable=False, default=RunStatus.queued.value)
    repo_owner = Column(String(255), nullable=False)
    repo_name = Column(String(255), nullable=False)
    pr_number = Column(Integer, nullable=True)
    base_ref = Column(String(255), nullable=True)
    head_ref = Column(String(255), nullable=True)
    head_sha = Column(String(255), nullable=True)
    mode = Column(String(32), nullable=True)
    engine_version = Column(String(255), nullable=True)
    job_id = Column(String(255), nullable=True)
    correlation_id = Column(String(255), nullable=True)
    fingerprint = Column(String(255), nullable=True)
    error = Column(String(2000), nullable=True)
    error_code = Column(String(255), nullable=True)
    error_summary = Column(String(1000), nullable=True)
    artifact_paths = Column(JSON, nullable=True)
    summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "status": self.status,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "pr_number": self.pr_number,
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "head_sha": self.head_sha,
            "mode": self.mode,
            "engine_version": self.engine_version,
            "job_id": self.job_id,
            "correlation_id": self.correlation_id,
            "fingerprint": self.fingerprint,
            "error": self.error,
            "error_code": self.error_code,
            "error_summary": self.error_summary,
            "artifact_paths": self.artifact_paths,
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Installation(Base):
    __tablename__ = "installations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    installation_id = Column(Integer, nullable=False, unique=True)
    account_login = Column(String(255), nullable=True)
    account_type = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("repo_owner", "repo_name", name="uq_repo_owner_name"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(Integer, nullable=True, unique=True)
    repo_owner = Column(String(255), nullable=False)
    repo_name = Column(String(255), nullable=False)
    installation_id = Column(Integer, ForeignKey("installations.installation_id"), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default="false")
    mode = Column(String(32), nullable=False, server_default="warn")
    baseline_ref = Column(String(255), nullable=True)
    rails_preset = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
