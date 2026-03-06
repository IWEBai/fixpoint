from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class RunResponse(BaseModel):
    id: uuid.UUID
    status: str
    repo_owner: str
    repo_name: str
    pr_number: Optional[int] = None
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    head_sha: Optional[str] = None
    mode: Optional[str] = None
    engine_version: Optional[str] = None
    job_id: Optional[str] = None
    correlation_id: Optional[str] = None
    fingerprint: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    error_summary: Optional[str] = None
    summary: Optional[dict[str, Any]] = None
    artifact_paths: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RunsList(BaseModel):
    runs: list[RunResponse] = Field(default_factory=list)


class InstallationCreate(BaseModel):
    installation_id: int
    account_login: Optional[str] = None
    account_type: Optional[str] = None


class InstallationResponse(BaseModel):
    id: uuid.UUID
    installation_id: int
    account_login: Optional[str] = None
    account_type: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RepoResponse(BaseModel):
    id: uuid.UUID
    repo_id: Optional[int] = None
    repo_owner: str
    repo_name: str
    installation_id: Optional[int] = None
    enabled: bool
    mode: str
    baseline_ref: Optional[str] = None
    rails_preset: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ReposList(BaseModel):
    repos: list[RepoResponse] = Field(default_factory=list)


class RepoUpdate(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    baseline_ref: Optional[str] = None
    rails_preset: Optional[str] = None

class AnalyticsSummaryResponse(BaseModel):
    total_runs: int
    failed_runs: int
    succeeded_runs: int
    avg_duration_seconds: float = 0.0

class TimeseriesDataPoint(BaseModel):
    date: str
    total_runs: int
    failed_runs: int
    succeeded_runs: int

class AnalyticsTimeseriesResponse(BaseModel):
    data: list[TimeseriesDataPoint] = Field(default_factory=list)
