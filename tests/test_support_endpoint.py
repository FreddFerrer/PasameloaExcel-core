from __future__ import annotations

import json

from app.core.dependencies import get_submit_extract_support_use_case
from app.main import app
from app.schemas.support import SupportSubmissionResponse


class FakeSubmitExtractSupportUseCase:
    def execute(
        self,
        *,
        pdf_bytes: bytes,
        filename: str,
        preview_json: str,
        user_note: str | None,
        session_id: str | None,
    ) -> SupportSubmissionResponse:
        assert pdf_bytes
        assert filename == "extracto.pdf"
        assert "\"document_id\": \"doc-1\"" in preview_json
        assert user_note == "necesita template"
        assert session_id == "sess-1"
        return SupportSubmissionResponse(
            ticket_id="supp_test_1",
            status="received",
            message="ok",
            forwarded_channel="backend_log_only",
        )


def test_submit_extract_to_support_endpoint(client) -> None:
    app.dependency_overrides[get_submit_extract_support_use_case] = lambda: FakeSubmitExtractSupportUseCase()
    preview = {
        "document_id": "doc-1",
        "filename": "extracto.pdf",
        "bank_detected": None,
        "template_detected": "generic_auto",
        "template_confidence": 0.01,
        "parse_status": "ok_auto",
        "quality_flag": "needs_template_support",
        "support_recommended": True,
        "quality_message": "msg",
        "low_confidence_ratio": 0.45,
        "summary": {
            "total_rows": 10,
            "low_confidence_rows": 8,
            "rows_with_issues": 10,
            "total_debito": 100.0,
            "total_credito": 50.0,
        },
        "rows": [],
    }

    try:
        response = client.post(
            "/api/v1/support/submit-extract",
            files={"file": ("extracto.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={
                "preview_json": json.dumps(preview),
                "session_id": "sess-1",
                "user_note": "necesita template",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["ticket_id"] == "supp_test_1"
    assert body["forwarded_channel"] == "backend_log_only"

