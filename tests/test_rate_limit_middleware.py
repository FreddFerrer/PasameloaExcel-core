from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware.rate_limit import RateLimitMiddleware


def _client(*, trust_proxy: bool = True) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        requests=2,
        window_seconds=60,
        protected_prefix="/api/v1",
        exempt_paths=["/api/v1/health"],
        trust_proxy=trust_proxy,
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/export-excel")
    def export_excel() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_rate_limit_allows_until_limit() -> None:
    client = _client()
    r1 = client.post("/api/v1/export-excel")
    r2 = client.post("/api/v1/export-excel")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.headers.get("X-RateLimit-Limit") == "2"
    assert r2.headers.get("X-RateLimit-Remaining") == "0"


def test_rate_limit_blocks_when_exceeded() -> None:
    client = _client()
    client.post("/api/v1/export-excel")
    client.post("/api/v1/export-excel")
    r3 = client.post("/api/v1/export-excel")
    assert r3.status_code == 429
    assert r3.headers.get("X-RateLimit-Limit") == "2"
    assert r3.headers.get("X-RateLimit-Remaining") == "0"
    assert r3.headers.get("Retry-After") is not None


def test_rate_limit_exempt_path_not_limited() -> None:
    client = _client()
    for _ in range(5):
        response = client.get("/api/v1/health")
        assert response.status_code == 200


def test_rate_limit_uses_forwarded_ip_when_enabled() -> None:
    client = _client(trust_proxy=True)
    headers_a = {"X-Forwarded-For": "1.1.1.1"}
    headers_b = {"X-Forwarded-For": "2.2.2.2"}

    assert client.post("/api/v1/export-excel", headers=headers_a).status_code == 200
    assert client.post("/api/v1/export-excel", headers=headers_a).status_code == 200
    assert client.post("/api/v1/export-excel", headers=headers_b).status_code == 200
