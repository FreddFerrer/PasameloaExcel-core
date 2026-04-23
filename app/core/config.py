from __future__ import annotations

import json
from json import JSONDecodeError
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PasameloaExcel Backend"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    app_log_level: str = "INFO"
    app_log_json: bool = True
    app_log_to_file: bool = True
    app_log_file_name: str = "application.log"
    app_log_max_bytes: int = 5_000_000
    app_log_backup_count: int = 3

    learning_logs_dir: Path = Path(__file__).resolve().parents[1] / "logs" / "learning"
    support_logs_dir: Path = Path(__file__).resolve().parents[1] / "logs" / "support"
    app_logs_dir: Path = Path(__file__).resolve().parents[1] / "logs" / "app"
    working_temp_dir: Path = Path(__file__).resolve().parents[2] / ".runtime" / "tmp"
    support_email_enabled: bool = False
    support_email_to: str | None = None
    support_email_from: str | None = None
    support_smtp_host: str | None = None
    support_smtp_port: int = 587
    support_smtp_username: str | None = None
    support_smtp_password: str | None = None
    support_smtp_use_tls: bool = True

    cors_allowed_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    enforce_origin_check: bool = False

    rate_limit_enabled: bool = False
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    rate_limit_trust_proxy: bool = True
    rate_limit_exempt_paths: list[str] = ["/api/v1/health"]

    issue_row_confidence_threshold: float = 0.8

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        enable_decoding=False,
    )

    @field_validator(
        "cors_allowed_origins",
        "cors_allow_methods",
        "cors_allow_headers",
        "rate_limit_exempt_paths",
        mode="before",
    )
    @classmethod
    def parse_list_settings(cls, value: object) -> list[str] | object:
        if value is None:
            return []
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                except JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in raw.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.rate_limit_requests <= 0:
            raise ValueError("APP_RATE_LIMIT_REQUESTS debe ser mayor a 0.")
        if self.rate_limit_window_seconds <= 0:
            raise ValueError("APP_RATE_LIMIT_WINDOW_SECONDS debe ser mayor a 0.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
