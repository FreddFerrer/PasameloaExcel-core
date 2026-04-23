from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.exporters.excel_exporter import ExcelBytesExporter
from app.schemas.export import ChangeSetSummary, ExportExcelRequest
from app.schemas.row import MovementRow
from app.services.export_service import ExportService
from app.services.learning_logger import LearningLogger


def test_export_service_generates_excel_and_logs():
    tmp_path = Path("tests/.test_tmp") / uuid.uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        fixed_now = datetime(2026, 1, 2, 3, 4, 5)
        logger = LearningLogger(logs_dir=tmp_path / "learning")
        service = ExportService(
            exporter=ExcelBytesExporter(working_temp_dir=tmp_path / "runtime"),
            learning_logger=logger,
            now_provider=lambda: fixed_now,
        )

        request = ExportExcelRequest(
            document_id="doc-sensitive-123",
            filename="extracto-enero.pdf",
            download_filename="Resumen banco enero 2026.pdf",
            bank_detected="bank-x",
            template_detected="template-a",
            template_confidence=0.87,
            parse_status="needs_review",
            rows=[
                MovementRow(
                    row_id="row-1",
                    fecha="01/01/2026",
                    descripcion="PAGO SERVICIO",
                    debito=1500.0,
                    credito=None,
                    saldo=48500.0,
                    pagina=1,
                    confianza=0.78,
                    raw_preview="sensitive text",
                    issues=["low_confidence"],
                )
            ],
            change_set=ChangeSetSummary(
                rows_edited=1,
                rows_added=0,
                rows_deleted=0,
                fields_corrected={"descripcion": 1},
                error_patterns=["descripcion_fragmentada"],
            ),
        )

        excel_bytes, file_name = service.export_excel(request)

        assert excel_bytes[:2] == b"PK"
        assert file_name == "Resumen_banco_enero_2026.xlsx"

        logs = list((tmp_path / "learning").glob("feedback-*.jsonl"))
        assert logs
        record = json.loads(logs[0].read_text(encoding="utf-8").splitlines()[0])
        assert record["summary_after"]["total_rows"] == 1
        assert record["summary_after"]["updated_rows_count"] == 0
        assert record["client_change_set"]["rows_edited"] == 1
        assert record["client_change_set"]["fields_corrected"]["descripcion"] == 1
        assert record["diff_audit"]["rows_original_count"] == 1
        assert record["diff_audit"]["rows_final_count"] == 1
        assert record["diff_audit"]["row_id_matches"] == 1
        assert "rows" not in record
        assert record["privacy"]["raw_rows_stored"] is False
        assert record["privacy"]["full_cell_values_stored"] is False
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_export_service_uses_source_filename_when_download_name_is_missing() -> None:
    class _Exporter:
        @staticmethod
        def export(_rows):
            return b"PK\x03\x04"

    class _Logger:
        @staticmethod
        def log_export_feedback(_request):
            return None

    service = ExportService(
        exporter=_Exporter(),
        learning_logger=_Logger(),
        now_provider=lambda: datetime(2026, 1, 2, 3, 4, 5),
    )
    request = ExportExcelRequest(
        document_id="doc-1",
        filename="extracto_original.pdf",
        rows=[
            MovementRow(
                row_id="row-1",
                fecha="01/01/2026",
                descripcion="PAGO SERVICIO",
                debito=1500.0,
                credito=None,
                saldo=48500.0,
                pagina=1,
                confianza=0.78,
                raw_preview=None,
                issues=[],
            )
        ],
        change_set=ChangeSetSummary(),
    )

    _bytes, output_name = service.export_excel(request)
    assert output_name == "extracto_original_20260102_030405.xlsx"

