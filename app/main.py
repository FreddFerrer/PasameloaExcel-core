from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.extraction import router as extraction_router
from app.api.routers.health import router as health_router
from app.core.config import get_settings
from app.core.middleware import (
    OriginGuardMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
)
from app.core.logging_config import setup_logging

settings = get_settings()
setup_logging(
    settings.app_log_level,
    json_logs=settings.app_log_json,
    log_to_file=settings.app_log_to_file,
    logs_dir=settings.app_logs_dir,
    file_name=settings.app_log_file_name,
    max_bytes=settings.app_log_max_bytes,
    backup_count=settings.app_log_backup_count,
)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)
app.add_middleware(
    OriginGuardMiddleware,
    allowed_origins=settings.cors_allowed_origins,
    enforce_origin_check=settings.enforce_origin_check,
)
if settings.rate_limit_enabled:
    app.add_middleware(
        RateLimitMiddleware,
        requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
        protected_prefix=settings.api_v1_prefix,
        exempt_paths=settings.rate_limit_exempt_paths,
        trust_proxy=settings.rate_limit_trust_proxy,
    )
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(extraction_router, prefix=settings.api_v1_prefix)

