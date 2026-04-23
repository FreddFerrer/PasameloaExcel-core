from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from app.schemas.preview import ExtractPreviewResponse, PreviewSummary
from app.services.support_service import SupportEmailConfig, SupportService


def test_support_service_logs_sanitized_event_without_storing_raw_pdf_or_rows() -> None:
    tmp_path = Path("tests/.test_tmp") / uuid.uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        service = SupportService(
            logs_dir=tmp_path / "support",
            email_config=SupportEmailConfig(
                enabled=False,
                to_address=None,
                from_address=None,
                smtp_host=None,
                smtp_port=587,
                smtp_username=None,
                smtp_password=None,
                smtp_use_tls=True,
            ),
        )

        preview = ExtractPreviewResponse(
            document_id="doc-1",
            filename="extracto.pdf",
            bank_detected=None,
            template_detected="generic_auto",
            template_confidence=0.01,
            parse_status="ok_auto",
            quality_flag="needs_template_support",
            support_recommended=True,
            quality_message="msg",
            low_confidence_ratio=0.4,
            summary=PreviewSummary(
                total_rows=10,
                low_confidence_rows=8,
                rows_with_issues=10,
                total_debito=100.0,
                total_credito=50.0,
            ),
            rows=[],
        )

        response = service.submit_extract_support(
            pdf_bytes=b"%PDF-1.4 fake",
            filename="extracto.pdf",
            preview_payload=preview.model_dump(mode="json"),
            user_note="nota",
            session_id="sess-1",
        )

        assert response.status == "received"
        assert response.forwarded_channel == "backend_log_only"

        logs = list((tmp_path / "support").glob("support-submissions-*.jsonl"))
        assert logs
        record = json.loads(logs[0].read_text(encoding="utf-8").splitlines()[0])

        assert record["event_type"] == "support_submission"
        assert record["support_recommended"] is True
        assert record["privacy"]["raw_pdf_stored"] is False
        assert "rows" not in record
        assert "preview_json" not in record
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)

