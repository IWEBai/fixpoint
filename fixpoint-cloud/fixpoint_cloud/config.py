from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"
    webhook_secret: str = ""
    github_webhook_secret: str = ""
    github_app_id: str | None = None
    github_app_private_key_path: str | None = None
    github_app_private_key_pem_base64: str | None = None
    skip_webhook_verification: bool = False
    fixpoint_mode: str = "warn"
    environment: str = "development"

    # Engine control
    engine_mode: str = "stub"  # stub|local|live
    engine_repo_path: str | None = None
    engine_base_ref: str | None = None
    engine_head_ref: str | None = None
    enable_engine: bool = False  # legacy flag; treated as engine_mode=local when true
    local_repo_path: str | None = None  # legacy alias for engine_repo_path

    # Infra
    rq_queue: str = "fixpoint"
    git_timeout: int = 120
    max_runtime_seconds: int | None = None
    artifact_root: str = "/artifacts"
    engine_version: str | None = None

    # Security
    api_key: str | None = None  # If set, management endpoints require X-API-Key header
    allowed_origins: str = "*"  # Comma-separated CORS origins; "*" for open dev
    max_request_body_size: int = 1_048_576  # 1 MB webhook body limit

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def rules_path(self) -> Path:
        return Path("rules")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[arg-type]

    # Backwards compatibility: honor ENABLE_ENGINE/LOCAL_REPO_PATH if set
    if settings.enable_engine and settings.engine_mode == "stub":
        settings.engine_mode = "local"
    if settings.local_repo_path and not settings.engine_repo_path:
        settings.engine_repo_path = settings.local_repo_path

    return settings
