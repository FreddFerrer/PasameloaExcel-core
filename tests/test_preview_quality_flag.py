from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.parsing.types import ParseExecution, ParsedMovement, RowTrace
from app.services.preview_service import PreviewService


class _FakeParserService:
    def __init__(self, execution: ParseExecution) -> None:
        self._execution = execution

    def parse_pdf(self, pdf_path: Path) -> ParseExecution:
        return self._execution


def _build_execution(template_detected: str, confidences: list[float]) -> ParseExecution:
    rows = [
        ParsedMovement(
            fecha="01/01/2026",
            descripcion=f"MOV-{idx}",
            debito=10.0,
            credito=None,
            saldo=100.0,
            pagina=1,
            confianza=conf,
            confianza_campos={},
        )
        for idx, conf in enumerate(confidences, start=1)
    ]
    traces = [RowTrace(raw_preview=None, issues=[]) for _ in rows]
    return ParseExecution(
        rows=rows,
        bank_detected=None,
        template_detected=template_detected,
        template_confidence=0.1,
        parser_mode="pdfplumber_local",
        parse_status="ok_auto",
        global_confidence=0.9,
        field_confidence={},
        row_traces=traces,
    )


def test_quality_flag_enabled_only_for_generic_auto_and_low_confidence_ratio() -> None:
    tmp_path = Path("tests/.test_tmp") / uuid.uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        execution = _build_execution("generic_auto", [0.95, 0.95, 0.97, 0.97, 0.97])
        service = PreviewService(parser_service=_FakeParserService(execution), working_temp_dir=tmp_path)

        response = service.extract_preview(pdf_bytes=b"%PDF-1.4 fake", filename="nuevo.pdf")

        assert response.support_recommended is True
        assert response.quality_flag == "needs_template_support"
        assert response.low_confidence_ratio == 0.4
        assert response.quality_message is not None
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_quality_flag_disabled_for_non_generic_template() -> None:
    tmp_path = Path("tests/.test_tmp") / uuid.uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        execution = _build_execution("manual_template_x", [0.90, 0.91, 0.92, 0.93])
        service = PreviewService(parser_service=_FakeParserService(execution), working_temp_dir=tmp_path)

        response = service.extract_preview(pdf_bytes=b"%PDF-1.4 fake", filename="manual.pdf")

        assert response.support_recommended is False
        assert response.quality_flag is None
        assert response.quality_message is None
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)

