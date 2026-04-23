from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


@dataclass(slots=True)
class _Bucket:
    window_start: float
    count: int


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        requests: int,
        window_seconds: int,
        protected_prefix: str,
        exempt_paths: list[str],
        trust_proxy: bool,
    ) -> None:
        super().__init__(app)
        self.requests = requests
        self.window_seconds = window_seconds
        self.protected_prefix = protected_prefix.rstrip("/") or "/"
        self.exempt_paths = {self._normalize_path(path) for path in exempt_paths if str(path).strip()}
        self.trust_proxy = trust_proxy
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()
        self._request_counter = 0

    async def dispatch(self, request: Request, call_next):
        path = self._normalize_path(request.url.path)
        if not path.startswith(self.protected_prefix) or path in self.exempt_paths:
            return await call_next(request)

        key = self._resolve_client_ip(request)
        now = monotonic()

        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or now - bucket.window_start >= self.window_seconds:
                bucket = _Bucket(window_start=now, count=0)
                self._buckets[key] = bucket

            if bucket.count >= self.requests:
                retry_after = max(1, int(self.window_seconds - (now - bucket.window_start)))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit excedido. Intenta nuevamente en unos segundos."},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(self.requests),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            bucket.count += 1
            remaining = max(0, self.requests - bucket.count)

            self._request_counter += 1
            if self._request_counter % 500 == 0:
                self._cleanup(now)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    def _resolve_client_ip(self, request: Request) -> str:
        if self.trust_proxy:
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                first = forwarded_for.split(",")[0].strip()
                if first:
                    return first
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def _cleanup(self, now: float) -> None:
        threshold = self.window_seconds * 2
        stale_keys = [key for key, bucket in self._buckets.items() if now - bucket.window_start >= threshold]
        for key in stale_keys:
            self._buckets.pop(key, None)

    def _normalize_path(self, path: str) -> str:
        normalized = str(path).strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/") or "/"
