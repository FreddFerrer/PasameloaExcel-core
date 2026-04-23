from __future__ import annotations

from app.application.use_cases.export_excel import ExportExcelResult
from app.core.dependencies import get_export_excel_use_case
from app.main import app


class FakeExportExcelUseCase:
    def __init__(self) -> None:
        self.last_request = None

    def execute(self, request):
        self.last_request = request
        return ExportExcelResult(content=b"PK\x03\x04fake-xlsx", filename="resultado.xlsx")


def test_export_endpoint_returns_file(client):
    fake_use_case = FakeExportExcelUseCase()
    app.dependency_overrides[get_export_excel_use_case] = lambda: fake_use_case
    payload = {
        "document_id": "doc-1",
        "filename": "extracto.pdf",
        "downloadFilename": "mi descarga personalizada.pdf",
        "bank_detected": "test-bank",
        "template_detected": "template-1",
        "template_confidence": 0.88,
        "parse_status": "ok_auto",
        "rows": [
            {
                "row_id": "row-1",
                "fecha": "01/01/2026",
                "descripcion": "PAGO",
                "debito": 100.0,
                "credito": None,
                "saldo": 900.0,
                "pagina": 1,
                "confianza": 0.95,
                "raw_preview": None,
                "issues": [],
            }
        ],
        "change_set": {
            "rows_edited": 1,
            "rows_added": 0,
            "rows_deleted": 0,
            "fields_corrected": {"descripcion": 1},
            "error_patterns": [],
        },
    }
    try:
        response = client.post("/api/v1/export-excel", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment; filename=\"resultado.xlsx\"" in response.headers["content-disposition"]
    assert fake_use_case.last_request is not None
    assert fake_use_case.last_request.download_filename == "mi descarga personalizada.pdf"


def test_export_endpoint_rejects_download_filename_too_long(client):
    payload = {
        "document_id": "doc-1",
        "filename": "extracto.pdf",
        "downloadFilename": ("A" * 81) + ".pdf",
        "bank_detected": "test-bank",
        "template_detected": "template-1",
        "template_confidence": 0.88,
        "parse_status": "ok_auto",
        "rows": [
            {
                "row_id": "row-1",
                "fecha": "01/01/2026",
                "descripcion": "PAGO",
                "debito": 100.0,
                "credito": None,
                "saldo": 900.0,
                "pagina": 1,
                "confianza": 0.95,
                "raw_preview": None,
                "issues": [],
            }
        ],
        "change_set": {
            "rows_edited": 1,
            "rows_added": 0,
            "rows_deleted": 0,
            "fields_corrected": {"descripcion": 1},
            "error_patterns": [],
        },
    }

    response = client.post("/api/v1/export-excel", json=payload)

    assert response.status_code == 422
    assert "download_filename no puede superar 80 caracteres." in response.text

