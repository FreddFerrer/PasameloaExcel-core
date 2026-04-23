from __future__ import annotations

from app.domain.learning import classify_feedback, compute_row_diffs
from app.schemas.row import MovementRow


def test_learning_domain_diff_and_classification_detects_rewrite_and_swap() -> None:
    rows_original = [
        MovementRow(
            row_id="row-1",
            fecha="01/04/2025",
            descripcion="PAGO",
            debito=100.0,
            credito=None,
            saldo=900.0,
            pagina=1,
            confianza=0.9,
            raw_preview=None,
            issues=[],
        )
    ]
    rows_final = [
        MovementRow(
            row_id="row-1",
            fecha="01/04/2025",
            descripcion="PAGO EDITADO",
            debito=None,
            credito=100.0,
            saldo=900.0,
            pagina=1,
            confianza=0.9,
            raw_preview=None,
            issues=[],
        )
    ]

    diffs = compute_row_diffs(rows_original=rows_original, rows_final=rows_final)
    result = classify_feedback(diffs=diffs, rows_final_count=len(rows_final), template_detected="nbch1")

    assert result.summary_after.updated_rows_count == 1
    assert result.field_corrections.descripcion == 1
    assert result.field_corrections.debito == 1
    assert result.field_corrections.credito == 1
    assert len(result.row_events) == 1
    assert "descripcion_extended" in result.row_events[0].change_types
    assert "amount_side_swapped" in result.row_events[0].change_types
    assert "debit_credit_swapped" in result.change_patterns


