from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware.origin_guard import OriginGuardMiddleware


def _client(*, allowed_origins: list[str], enforce_origin_check: bool) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        OriginGuardMiddleware,
        allowed_origins=allowed_origins,
        enforce_origin_check=enforce_origin_check,
    )

    @app.post("/api/v1/export-excel")
    def export_excel() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_origin_guard_allows_known_origin() -> None:
    client = _client(
        allowed_origins=["https://frontend.example.com"],
        enforce_origin_check=True,
    )
    response = client.post(
        "/api/v1/export-excel",
        headers={"Origin": "https://frontend.example.com"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_origin_guard_blocks_unknown_origin() -> None:
    client = _client(
        allowed_origins=["https://frontend.example.com"],
        enforce_origin_check=True,
    )
    response = client.post(
        "/api/v1/export-excel",
        headers={"Origin": "https://otro-frontend.example.com"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Origin no permitido."


def test_origin_guard_blocks_missing_origin_when_enforced() -> None:
    client = _client(
        allowed_origins=["https://frontend.example.com"],
        enforce_origin_check=True,
    )
    response = client.post("/api/v1/export-excel")
    assert response.status_code == 403
    assert response.json()["detail"] == "Falta el header Origin."


def test_origin_guard_allows_missing_origin_when_not_enforced() -> None:
    client = _client(
        allowed_origins=["https://frontend.example.com"],
        enforce_origin_check=False,
    )
    response = client.post("/api/v1/export-excel")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
