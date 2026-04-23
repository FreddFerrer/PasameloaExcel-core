from __future__ import annotations

from dataclasses import dataclass

from app.parsing.types import ParseExecution
from app.schemas.preview import PreviewSummary
from app.schemas.row import MovementRow


LOW_CONFIDENCE_SUMMARY_THRESHOLD = 0.8
GENERIC_TEMPLATE_ID = "generic_auto"
QUALITY_FLAG_NEEDS_TEMPLATE_SUPPORT = "needs_template_support"
QUALITY_MESSAGE_LOW_QUALITY = (
    "La extraccion parece de baja calidad. "
    "Te recomendamos enviar este extracto a soporte para mejorar el template."
)


@dataclass(slots=True)
class PreviewProjection:
    rows: list[MovementRow]
    summary: PreviewSummary
    low_confidence_ratio: float
    support_recommended: bool
    quality_flag: str | None
    quality_message: str | None


def build_preview_projection(
    execution: ParseExecution,
    *,
    support_confidence_threshold: float,
    support_low_conf_ratio_trigger: float,
) -> PreviewProjection:
    rows = _map_rows(execution)
    low_confidence_096_count = sum(
        1 for row in rows if row.confianza is not None and row.confianza < support_confidence_threshold
    )
    low_confidence_ratio = round((low_confidence_096_count / len(rows)), 4) if rows else 0.0
    support_recommended = (
        execution.template_detected == GENERIC_TEMPLATE_ID
        and low_confidence_ratio >= support_low_conf_ratio_trigger
    )
    quality_flag = QUALITY_FLAG_NEEDS_TEMPLATE_SUPPORT if support_recommended else None
    quality_message = QUALITY_MESSAGE_LOW_QUALITY if support_recommended else None

    return PreviewProjection(
        rows=rows,
        summary=_build_summary(rows),
        low_confidence_ratio=low_confidence_ratio,
        support_recommended=support_recommended,
        quality_flag=quality_flag,
        quality_message=quality_message,
    )


def _map_rows(execution: ParseExecution) -> list[MovementRow]:
    rows: list[MovementRow] = []
    for idx, row in enumerate(execution.rows, start=1):
        trace = execution.row_traces[idx - 1] if idx - 1 < len(execution.row_traces) else None
        rows.append(
            MovementRow(
                row_id=f"row-{idx}",
                fecha=row.fecha,
                descripcion=row.descripcion,
                debito=row.debito,
                credito=row.credito,
                saldo=row.saldo,
                pagina=row.pagina,
                confianza=row.confianza,
                raw_preview=trace.raw_preview if trace else None,
                issues=trace.issues if trace else [],
            )
        )
    return rows


def _build_summary(rows: list[MovementRow]) -> PreviewSummary:
    low_conf = sum(1 for row in rows if (row.confianza or 0.0) < LOW_CONFIDENCE_SUMMARY_THRESHOLD)
    rows_with_issues = sum(1 for row in rows if row.issues)
    return PreviewSummary(
        total_rows=len(rows),
        low_confidence_rows=low_conf,
        rows_with_issues=rows_with_issues,
        total_debito=round(sum((row.debito or 0.0) for row in rows), 2),
        total_credito=round(sum((row.credito or 0.0) for row in rows), 2),
    )


