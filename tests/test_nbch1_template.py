from __future__ import annotations

from pathlib import Path

from app.parsing.templates.nbch1 import Nbch1Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[],
        file_stem="extracto_nbch_chaco",
        first_page_text="NUEVO BANCO DEL CHACO COMPROBANTE",
    )


def test_nbch1_removes_trailing_comprobante_from_description() -> None:
    template = Nbch1Template()
    rows = [
        ParsedMovement(
            fecha="01/04/2026",
            descripcion="Pago a Comercio Tarjeta de Cre 996007840",
            debito=None,
            credito=1000.0,
            saldo=5000.0,
            pagina=1,
            confianza=0.95,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview="01/04/2026 Pago a Comercio Tarjeta de Cre 996007840 0,00 1.000,00 5.000,00",
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == "Pago a Comercio Tarjeta de Cre"


def test_nbch1_appends_convenio_continuation_to_description() -> None:
    template = Nbch1Template()
    rows = [
        ParsedMovement(
            fecha="02/04/2026",
            descripcion="Convenios - Debito Automatico 996072313 128.988,46 0,00 8.668.473,12",
            debito=128988.46,
            credito=None,
            saldo=8668473.12,
            pagina=2,
            confianza=0.95,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "02/04/2026 Convenios - Debito Automatico 996072313 128.988,46 0,00 8.668.473,12 | "
                "Convenio: WEB FDO INV Y ASIST PROD L842 - 30709332321"
            ),
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == (
        "Convenios - Debito Automatico Convenio: WEB FDO INV Y ASIST PROD L842 - 30709332321"
    )


def test_nbch1_appends_origen_continuation_and_removes_amount_noise() -> None:
    template = Nbch1Template()
    rows = [
        ParsedMovement(
            fecha="03/04/2026",
            descripcion="Transferencia debin Distinto T 901004647 0,00 297.000,00 8.513.077,78",
            debito=None,
            credito=297000.0,
            saldo=8513077.78,
            pagina=2,
            confianza=0.95,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "03/04/2026 Transferencia debin Distinto T 901004647 0,00 297.000,00 8.513.077,78 | "
                "Origen: Doc.:30716759713- Denom.:LS SAS- Ref.: 201961"
            ),
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == (
        "Transferencia debin Distinto T Origen: Doc.:30716759713- Denom.:LS SAS- Ref.: 201961"
    )


def test_nbch1_confidence_adjustment_boosts_clean_multiline_rows() -> None:
    template = Nbch1Template()
    row = ParsedMovement(
        fecha="03/04/2026",
        descripcion="Transferencia debin Distinto T Origen: Doc.:30716759713- Denom.:LS SAS- Ref.: 201961",
        debito=None,
        credito=297000.0,
        saldo=8513077.78,
        pagina=2,
        confianza=0.83,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview=None,
        issues=["descripcion_multilinea"],
    )

    delta = template.adjust_row_confidence(row=row, trace=trace, context=_context())
    assert delta > 0


def test_nbch1_confidence_adjustment_does_not_boost_noisy_description() -> None:
    template = Nbch1Template()
    row = ParsedMovement(
        fecha="03/04/2026",
        descripcion="Transferencia debin Distinto T 0,00 297.000,00",
        debito=None,
        credito=297000.0,
        saldo=8513077.78,
        pagina=2,
        confianza=0.83,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview=None,
        issues=["descripcion_multilinea"],
    )

    delta = template.adjust_row_confidence(row=row, trace=trace, context=_context())
    assert delta == 0.0


def test_nbch1_compute_confidence_high_for_clean_row() -> None:
    template = Nbch1Template()
    row = ParsedMovement(
        fecha="03/04/2026",
        descripcion="Transferencia debin Distinto T Origen: Doc.:30716759713- Denom.:LS SAS- Ref.: 201961",
        debito=None,
        credito=297000.0,
        saldo=8513077.78,
        pagina=2,
        confianza=0.83,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview=(
            "03/04/2026 Transferencia debin Distinto T 901004647 0,00 297.000,00 8.513.077,78 | "
            "Origen: Doc.:30716759713- Denom.:LS SAS- Ref.: 201961"
        ),
        issues=["descripcion_multilinea"],
    )

    confidence = template.compute_row_confidence(row=row, trace=trace, context=_context())

    assert confidence is not None
    assert confidence >= 0.9

