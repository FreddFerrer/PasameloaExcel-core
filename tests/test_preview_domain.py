from __future__ import annotations

from app.domain.preview import build_preview_projection
from app.parsing.types import ParseExecution, ParsedMovement, RowTrace


def _execution(template_detected: str, confidences: list[float]) -> ParseExecution:
    rows = [
        ParsedMovement(
            fecha="01/01/2026",
            descripcion=f"MOV-{idx}",
            debito=10.0,
            credito=None,
            saldo=100.0,
            pagina=1,
            confianza=confidence,
            confianza_campos={},
        )
        for idx, confidence in enumerate(confidences, start=1)
    ]
    traces = [RowTrace(raw_preview=f"raw-{idx}", issues=[]) for idx in range(1, len(rows) + 1)]
    return ParseExecution(
        rows=rows,
        bank_detected="bank",
        template_detected=template_detected,
        template_confidence=0.8,
        parser_mode="pdfplumber_local",
        parse_status="ok_auto",
        global_confidence=0.9,
        field_confidence={},
        row_traces=traces,
    )


def test_build_preview_projection_marks_support_recommended_when_generic_is_low_conf() -> None:
    execution = _execution("generic_auto", [0.95, 0.95, 0.99, 0.99, 0.99])
    projection = build_preview_projection(
        execution,
        support_confidence_threshold=0.96,
        support_low_conf_ratio_trigger=0.30,
    )

    assert projection.support_recommended is True
    assert projection.quality_flag == "needs_template_support"
    assert projection.low_confidence_ratio == 0.4
    assert projection.summary.total_rows == 5
    assert projection.summary.total_debito == 50.0


def test_build_preview_projection_keeps_row_mapping_and_summary() -> None:
    execution = _execution("santander1", [1.0, 0.92])
    projection = build_preview_projection(
        execution,
        support_confidence_threshold=0.96,
        support_low_conf_ratio_trigger=0.30,
    )

    assert projection.support_recommended is False
    assert projection.quality_flag is None
    assert len(projection.rows) == 2
    assert projection.rows[0].row_id == "row-1"
    assert projection.rows[0].raw_preview == "raw-1"
    assert projection.summary.low_confidence_rows == 0


