from __future__ import annotations

from collections.abc import Iterable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class OriginGuardMiddleware(BaseHTTPMiddleware):
    """
    Defense-in-depth guard for Origin header checks.

    Notes:
    - CORS alone is a browser control, not an auth mechanism.
    - This middleware blocks explicit disallowed Origin headers and can
      optionally require Origin for unsafe methods.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_origins: Iterable[str],
        enforce_origin_check: bool,
    ) -> None:
        super().__init__(app)
        self.enforce_origin_check = enforce_origin_check
        self.allowed_origins = {
            self._normalize_origin(origin)
            for origin in allowed_origins
            if str(origin).strip()
        }
        self.allow_all_origins = "*" in self.allowed_origins

    async def dispatch(self, request: Request, call_next):
        if self.allow_all_origins:
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin:
            normalized = self._normalize_origin(origin)
            if normalized not in self.allowed_origins:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Origin no permitido."},
                )
            return await call_next(request)

        method = request.method.upper()
        if self.enforce_origin_check and method not in SAFE_METHODS:
            return JSONResponse(
                status_code=403,
                content={"detail": "Falta el header Origin."},
            )
        return await call_next(request)

    def _normalize_origin(self, value: str) -> str:
        return str(value).strip().lower().rstrip("/")
