from __future__ import annotations

from pathlib import Path

from app.parsing.templates.formosa1 import Formosa1Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[],
        file_stem="4_resumen_abril_formosa",
        first_page_text=(
            "FECHA CONCEPTO REFERENCIA CHEQUE DEBITOS CREDITOS SALDO\n"
            "Banco de Formosa S.A.\n"
            "DETALLE POR PRODUCTO"
        ),
    )


def test_formosa1_match_score_uses_footer_and_main_header() -> None:
    template = Formosa1Template()
    score = template.match_score(_context())
    assert score >= 0.9


def test_formosa1_strips_reference_and_assigns_credit_from_keywords() -> None:
    template = Formosa1Template()
    rows = [
        ParsedMovement(
            fecha="01/04/25",
            descripcion="Dep en Efectivo 27349606475",
            debito=None,
            credito=207400.0,
            saldo=-31732183.02,
            pagina=1,
            confianza=0.93,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview="01/04/25 Dep en Efectivo 27349606475 207,400.00 -31,732,183.02",
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == "Dep en Efectivo"
    assert rows[0].debito is None
    assert rows[0].credito == 207400.0
    assert rows[0].saldo == -31732183.02


def test_formosa1_uses_continuation_balance_line_for_debit() -> None:
    template = Formosa1Template()
    rows = [
        ParsedMovement(
            fecha="01/04/25",
            descripcion="DB Interés",
            debito=None,
            credito=72470.76,
            saldo=None,
            pagina=1,
            confianza=0.93,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview="01/04/25 DB Interés 72,470.76 | -30,191,805.13",
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].debito == 72470.76
    assert rows[0].credito is None
    assert rows[0].saldo == -30191805.13


def test_formosa1_filters_secondary_table_rows() -> None:
    template = Formosa1Template()
    rows = [
        ParsedMovement(
            fecha="01/04/25",
            descripcion="",
            debito=None,
            credito=None,
            saldo=None,
            pagina=6,
            confianza=0.85,
            confianza_campos={},
        ),
        ParsedMovement(
            fecha="01/04/25",
            descripcion="Impto DyC S/Cred 1,244.40",
            debito=None,
            credito=1244.4,
            saldo=-31733427.42,
            pagina=1,
            confianza=0.93,
            confianza_campos={},
        ),
    ]
    traces = [
        RowTrace(raw_preview="01/04/25 1,600,000.00", issues=[]),
        RowTrace(raw_preview="01/04/25 Impto DyC S/Cred 1,244.40 -31,733,427.42", issues=[]),
    ]

    template.postprocess_rows(rows, traces, _context())

    assert len(rows) == 1
    assert rows[0].descripcion == "Impto DyC S/Cred"
    assert rows[0].credito is None
    assert rows[0].debito == 1244.4


def test_formosa1_compute_confidence_high_for_clean_rows() -> None:
    template = Formosa1Template()
    row = ParsedMovement(
        fecha="01/04/25",
        descripcion="IVA Débito Fiscal",
        debito=15218.86,
        credito=None,
        saldo=-30207023.99,
        pagina=1,
        confianza=0.68,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview="01/04/25 IVA Débito Fiscal 15,218.86 | -30,207,023.99",
        issues=["descripcion_multilinea", "low_confidence"],
    )

    confidence = template.compute_row_confidence(row=row, trace=trace, context=_context())

    assert confidence is not None
    assert confidence >= 0.9


