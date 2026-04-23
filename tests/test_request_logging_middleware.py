from __future__ import annotations

import logging


def test_request_logging_middleware_emits_http_event_and_sets_request_id_header(client, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="backend.http"):
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")

    records = [record for record in caplog.records if record.name == "backend.http" and record.msg == "http_request_completed"]
    assert records
    record = records[-1]
    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "path", None) == "/api/v1/health"
    assert getattr(record, "status_code", None) == 200
    assert isinstance(getattr(record, "duration_ms", None), (float, int))
