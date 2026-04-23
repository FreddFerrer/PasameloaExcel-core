from __future__ import annotations

import logging
import uuid
from time import perf_counter

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.request_context import reset_request_id, set_request_id

logger = logging.getLogger("backend.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = set_request_id(request_id)
        started = perf_counter()

        method = request.method.upper()
        path = request.url.path
        client_ip = self._resolve_client_ip(request)
        content_type = request.headers.get("content-type", "unknown")
        content_length = self._safe_int(request.headers.get("content-length"))
        query_keys = list(request.query_params.keys())
        query_key_count = len(query_keys)
        user_agent = (request.headers.get("user-agent") or "")[:240]

        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            logger.exception(
                "http_request_failed",
                extra={
                    "event": "http_request",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": elapsed_ms,
                    "client_ip": client_ip,
                    "content_type": content_type,
                    "content_length": content_length,
                    "query_key_count": query_key_count,
                    "query_keys": query_keys[:25],
                    "user_agent": user_agent,
                },
            )
            raise
        finally:
            reset_request_id(token)

        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        route = request.scope.get("route")
        route_path = getattr(route, "path", None)

        log_fn = logger.info
        if response.status_code >= 500:
            log_fn = logger.error
        elif response.status_code >= 400:
            log_fn = logger.warning

        log_fn(
            "http_request_completed",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": method,
                "path": path,
                "route_path": route_path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
                "client_ip": client_ip,
                "content_type": content_type,
                "content_length": content_length,
                "query_key_count": query_key_count,
                "query_keys": query_keys[:25],
                "user_agent": user_agent,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response

    def _resolve_client_ip(self, request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            first = forwarded_for.split(",")[0].strip()
            if first:
                return first
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def _safe_int(self, value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


