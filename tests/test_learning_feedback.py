from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from app.schemas.export import ChangeSetSummary, ExportExcelRequest
from app.schemas.row import MovementRow
from app.services.learning_logger import LearningLogger


def test_learning_logger_builds_diff_and_patterns():
    tmp_path = Path("tests/.test_tmp") / uuid.uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        logger = LearningLogger(logs_dir=tmp_path / "learning")
        request = ExportExcelRequest(
            document_id="doc-1",
            session_id="sess_abc",
            filename="abril.pdf",
            bank_detected=None,
            template_detected="resumen_mensual_noviembre_2025",
            template_confidence=0.1,
            parse_status="ok_auto",
            rows_original=[
                MovementRow(
                    row_id="row-1",
                    fecha="01/04/2025",
                    descripcion="",
                    debito=100.0,
                    credito=None,
                    saldo=None,
                    pagina=2,
                    confianza=0.61,
                    raw_preview=None,
                    issues=["descripcion_vacia", "footer_like_text_detected"],
                ),
                MovementRow(
                    row_id="row-2",
                    fecha="01/04/2025",
                    descripcion="POSIBLE BASURA",
                    debito=None,
                    credito=None,
                    saldo=None,
                    pagina=3,
                    confianza=0.5,
                    raw_preview=None,
                    issues=["footer_like_text_detected", "header_like_text_detected"],
                ),
                MovementRow(
                    row_id="row-4",
                    fecha="01/04/2025",
                    descripcion="PAGO IMPUESTO FOOTER-XYZ",
                    debito=70.0,
                    credito=None,
                    saldo=430.0,
                    pagina=4,
                    confianza=0.82,
                    raw_preview=None,
                    issues=["footer_like_text_detected"],
                ),
            ],
            rows_final=[
                MovementRow(
                    row_id="row-1",
                    fecha="01/04/2025",
                    descripcion="PAGO PROVEEDOR",
                    debito=None,
                    credito=100.0,
                    saldo=500.0,
                    pagina=2,
                    confianza=0.61,
                    raw_preview=None,
                    issues=[],
                ),
                MovementRow(
                    row_id="row-4",
                    fecha="01/04/2025",
                    descripcion="PAGO IMPUESTO",
                    debito=70.0,
                    credito=None,
                    saldo=430.0,
                    pagina=4,
                    confianza=0.82,
                    raw_preview=None,
                    issues=[],
                ),
                MovementRow(
                    row_id="row-3",
                    fecha="02/04/2025",
                    descripcion="MOVIMIENTO MANUAL",
                    debito=50.0,
                    credito=None,
                    saldo=450.0,
                    pagina=3,
                    confianza=1.0,
                    raw_preview=None,
                    issues=[],
                ),
            ],
            change_set=ChangeSetSummary(),
        )

        event = logger.log_export_feedback(request)

        assert event.summary_after.total_rows == 3
        assert event.summary_after.updated_rows_count == 2
        assert event.summary_after.deleted_rows_count == 1
        assert event.summary_after.added_rows_count == 1
        assert event.field_corrections.descripcion == 2
        assert event.field_corrections.debito == 1
        assert event.field_corrections.credito == 1
        assert event.field_corrections.saldo == 1

        row_event_map = {row_event.row_id: row_event for row_event in event.row_events}
        assert "descripcion_filled_when_empty" in row_event_map["row-1"].change_types
        assert "amount_side_swapped" in row_event_map["row-1"].change_types
        assert "saldo_filled_when_empty" in row_event_map["row-1"].change_types
        assert "descripcion_trimmed" in row_event_map["row-4"].change_types
        assert "row_deleted" in row_event_map["row-2"].change_types
        assert "row_added" in row_event_map["row-3"].change_types

        assert "missing_description_when_comprobante_nonzero" in event.change_patterns
        assert "footer_absorbed_into_description" in event.change_patterns
        assert "debit_credit_swapped" in event.change_patterns
        assert "saldo_missing" in event.change_patterns
        assert "parser_missed_row" in event.change_patterns
        assert "false_positive_row" in event.change_patterns

        logs = list((tmp_path / "learning").glob("feedback-*.jsonl"))
        assert logs
        record = json.loads(logs[0].read_text(encoding="utf-8").splitlines()[0])
        assert record["event_type"] == "export_confirmed"
        assert record["privacy"]["raw_pdf_stored"] is False
        assert "rows_original" not in record
        assert "rows_final" not in record
        assert "client_change_set" in record
        assert record["client_change_set"]["rows_edited"] == 0
        assert "diff_audit" in record
        assert record["diff_audit"]["rows_original_count"] == 3
        assert record["diff_audit"]["rows_final_count"] == 3
        assert record["diff_audit"]["row_id_matches"] == 2
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_learning_logger_detects_single_updated_row_when_row_ids_match():
    tmp_path = Path("tests/.test_tmp") / uuid.uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        logger = LearningLogger(logs_dir=tmp_path / "learning")
        request = ExportExcelRequest(
            document_id="doc-match-1",
            template_detected="4_resumen_cta_abril_2025",
            change_set=ChangeSetSummary(rows_edited=1),
            rows_original=[
                MovementRow(
                    row_id="row-1",
                    fecha="01/04/2025",
                    descripcion="PAGO SERVICIO",
                    debito=100.0,
                    credito=None,
                    saldo=900.0,
                    pagina=78,
                    confianza=0.91,
                    raw_preview=None,
                    issues=[],
                )
            ],
            rows_final=[
                MovementRow(
                    row_id="row-1",
                    fecha="01/04/2025",
                    descripcion="PAGO SERVICIO EDITADO",
                    debito=100.0,
                    credito=None,
                    saldo=900.0,
                    pagina=78,
                    confianza=0.91,
                    raw_preview=None,
                    issues=[],
                )
            ],
        )

        event = logger.log_export_feedback(request)
        assert event.summary_after.updated_rows_count == 1
        assert event.summary_after.deleted_rows_count == 0
        assert event.summary_after.added_rows_count == 0
        assert len(event.row_events) == 1
        assert event.row_events[0].row_id == "row-1"
        assert "descripcion_rewritten" in event.row_events[0].change_types
        assert "descripcion_extended" in event.row_events[0].change_types
        assert event.row_events[0].signals.description_text_added is True
        assert event.row_events[0].signals.description_text_removed is None
        assert event.client_change_set.rows_edited == 1
        assert event.diff_audit.row_id_matches == 1
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_export_request_accepts_camel_case_payload_and_keeps_original_rows():
    payload = {
        "documentId": "doc-camel",
        "templateDetected": "4_resumen_cta_abril_2025",
        "changeSet": {"rowsEdited": 1},
        "rowsOriginal": [
            {
                "rowId": "row-1",
                "fecha": "01/04/2025",
                "descripcion": "ANTES",
                "debito": 10.0,
                "credito": None,
                "saldo": 100.0,
                "pagina": 1,
                "confianza": 0.9,
                "rawPreview": None,
                "issues": [],
            }
        ],
        "rowsFinal": [
            {
                "rowId": "row-1",
                "fecha": "01/04/2025",
                "descripcion": "DESPUES",
                "debito": 10.0,
                "credito": None,
                "saldo": 100.0,
                "pagina": 1,
                "confianza": 0.9,
                "rawPreview": None,
                "issues": [],
            }
        ],
    }

    request = ExportExcelRequest.model_validate(payload)
    assert len(request.rows_original) == 1
    assert len(request.rows_final) == 1
    assert request.rows_original[0].row_id == "row-1"
    assert request.rows_final[0].row_id == "row-1"


def test_learning_logger_fallback_prevents_all_rows_marked_as_added_when_original_missing():
    tmp_path = Path("tests/.test_tmp") / uuid.uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        logger = LearningLogger(logs_dir=tmp_path / "learning")
        request = ExportExcelRequest(
            document_id="doc-fallback",
            change_set=ChangeSetSummary(rows_edited=1),
            rows=[
                MovementRow(
                    row_id="row-1",
                    fecha="01/04/2025",
                    descripcion="UNICA FILA",
                    debito=10.0,
                    credito=None,
                    saldo=100.0,
                    pagina=1,
                    confianza=0.9,
                    raw_preview=None,
                    issues=[],
                )
            ],
        )

        event = logger.log_export_feedback(request)
        assert event.summary_before.total_rows == 1
        assert event.summary_after.total_rows == 1
        assert event.summary_after.updated_rows_count == 0
        assert event.summary_after.deleted_rows_count == 0
        assert event.summary_after.added_rows_count == 0
        assert "original_rows_missing_payload" in event.change_patterns
        assert event.diff_audit.row_id_matches == 1
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)

