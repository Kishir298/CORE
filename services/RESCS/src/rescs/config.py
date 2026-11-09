"""Application configuration loaded from environment variables and ``.env``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from rescs import __version__

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Runtime configuration for the RESCS application.

    Every value is overridable through an environment variable prefixed
    with ``RESCS_`` (for example ``RESCS_API_KEY``) or through the local
    ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_prefix="RESCS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RESCS"
    version: str = __version__
    environment: str = Field(default="development", alias="RESCS_ENV")
    log_level: LogLevel = "INFO"

    api_key: str = ""
    api_key_owner: str = ""
    require_signed_owner: bool = False
    required_mount: str = ""
    database_url: str = "sqlite:///rescs_dev.db"
    storage_dir: str = "rescs_storage"
    auto_create_schema: bool = True
    request_id_header: str = "X-Request-ID"

    # v0.2 resource governance. Zero means "unlimited".
    max_records_per_owner: int = 0
    max_files_per_owner: int = 0
    max_bytes_per_owner: int = 0
    max_file_size: int = 0
    max_metadata_bytes: int = 65536
    max_bulk_batch: int = 100
    audit_retention_days: int = 90
    # Maximum accepted TTL in seconds (0 = unlimited). Defaults to 365 days.
    max_ttl_seconds: int = 31536000
    # Payloads at/above this size stream instead of buffering fully in memory.
    streaming_threshold_bytes: int = 8388608

    # Object-store backend selection: local (default), memory or s3.
    storage_backend: str = "local"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_path_prefix: str = ""

    # Rate limiting (in-memory, single-instance).
    rate_limit_enabled: bool = False
    rate_limit_general_per_minute: int = 100
    rate_limit_writes_per_minute: int = 60
    rate_limit_uploads_per_minute: int = 20

    @field_validator("api_key")
    @classmethod
    def _validate_api_key(cls, value: str) -> str:
        if not value or len(value) < 16:
            raise ValueError(
                "RESCS_API_KEY must be set and at least 16 characters long"
            )
        return value

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError(
                f"unknown RESCS_ENV {value!r}; expected development, test or production"
            )
        return value

    @field_validator(
        "max_records_per_owner",
        "max_files_per_owner",
        "max_bytes_per_owner",
        "max_file_size",
        "max_metadata_bytes",
        "audit_retention_days",
        "max_ttl_seconds",
        "streaming_threshold_bytes",
    )
    @classmethod
    def _validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("governance limits must be >= 0 (0 means unlimited)")
        return value

    @field_validator("storage_backend")
    @classmethod
    def _validate_backend(cls, value: str) -> str:
        if value not in {"local", "s3", "memory"}:
            raise ValueError("RESCS_STORAGE_BACKEND must be local, s3, or memory")
        return value

    @field_validator("max_bulk_batch")
    @classmethod
    def _validate_bulk_batch(cls, value: int) -> int:
        if not 1 <= value <= 1000:
            raise ValueError("RESCS_MAX_BULK_BATCH must be between 1 and 1000")
        return value

    @field_validator("rate_limit_general_per_minute", "rate_limit_writes_per_minute", "rate_limit_uploads_per_minute")
    @classmethod
    def _validate_rate(cls, value: int) -> int:
        if value < 0:
            raise ValueError("rate limits must be >= 0 (0 disables that bucket)")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
