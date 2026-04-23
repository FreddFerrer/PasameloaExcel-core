from __future__ import annotations

from app.application.use_cases import (
    ExportExcelUseCase,
    ExtractPreviewUseCase,
    SubmitExtractSupportUseCase,
)
from app.schemas.export import ChangeSetSummary, ExportExcelRequest
from app.schemas.row import MovementRow


class _FakePreviewService:
    def extract_preview(self, *, pdf_bytes: bytes, filename: str):
        return {"filename": filename, "bytes": len(pdf_bytes)}


class _FakeExportService:
    def export_excel(self, request: ExportExcelRequest) -> tuple[bytes, str]:
        assert request.document_id == "doc-1"
        return b"PK\x03\x04", "out.xlsx"


class _FakeSupportService:
    def submit_extract_support(self, **kwargs):
        return {"status": "ok", **kwargs}


def test_extract_preview_use_case_rejects_non_pdf_filename() -> None:
    use_case = ExtractPreviewUseCase(preview_service=_FakePreviewService())

    try:
        use_case.execute(pdf_bytes=b"123", filename="extracto.txt")
    except ValueError as exc:
        assert "PDF" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-PDF filename")


def test_export_excel_use_case_returns_wrapped_result() -> None:
    use_case = ExportExcelUseCase(export_service=_FakeExportService())
    request = ExportExcelRequest(
        document_id="doc-1",
        rows=[MovementRow(row_id="row-1", fecha="01/01/2026", descripcion="x", debito=1.0, credito=None, saldo=1.0)],
        change_set=ChangeSetSummary(),
    )

    result = use_case.execute(request)
    assert result.content.startswith(b"PK")
    assert result.filename == "out.xlsx"
    assert "spreadsheetml" in result.media_type


def test_submit_support_use_case_requires_valid_preview_json() -> None:
    use_case = SubmitExtractSupportUseCase(support_service=_FakeSupportService())

    try:
        use_case.execute(
            pdf_bytes=b"123",
            filename="extracto.pdf",
            preview_json="{bad-json}",
            session_id=None,
            user_note=None,
        )
    except ValueError as exc:
        assert "preview_json" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid preview_json")


