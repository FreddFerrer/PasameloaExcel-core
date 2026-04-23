from __future__ import annotations

from app.core.dependencies import get_extract_preview_use_case
from app.main import app
from app.schemas.preview import ExtractPreviewResponse, PreviewSummary
from app.schemas.row import MovementRow


class FakeExtractPreviewUseCase:
    def execute(self, *, pdf_bytes: bytes, filename: str) -> ExtractPreviewResponse:
        assert pdf_bytes
        return ExtractPreviewResponse(
            document_id="doc-test",
            filename=filename,
            bank_detected="test-bank",
            template_detected="template-1",
            template_confidence=0.91,
            parse_status="ok_auto",
            summary=PreviewSummary(
                total_rows=1,
                low_confidence_rows=0,
                rows_with_issues=0,
                total_debito=100.0,
                total_credito=0.0,
            ),
            rows=[
                MovementRow(
                    row_id="row-1",
                    fecha="01/01/2026",
                    descripcion="PAGO PROVEEDOR",
                    debito=100.0,
                    credito=None,
                    saldo=900.0,
                    pagina=1,
                    confianza=0.96,
                    raw_preview="01/01/2026 PAGO PROVEEDOR 100,00",
                    issues=[],
                )
            ],
        )


def test_extract_preview_endpoint(client):
    app.dependency_overrides[get_extract_preview_use_case] = lambda: FakeExtractPreviewUseCase()
    try:
        response = client.post(
            "/api/v1/extract-preview",
            files={"file": ("extracto.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == "doc-test"
    assert body["template_detected"] == "template-1"
    assert body["rows"][0]["descripcion"] == "PAGO PROVEEDOR"

