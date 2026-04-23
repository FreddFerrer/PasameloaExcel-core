from __future__ import annotations

from pathlib import Path

from app.parsing.templates.credicoop1 import Credicoop1Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[],
        file_stem="resumen_credicoop_08_2025",
        first_page_text=(
            "Fecha Concepto Nro.Cpbte. Débito Crédito Saldo Cód.\n"
            "https://bancainternet.bancocredicoop.coop"
        ),
    )


def test_credicoop1_cleans_single_line_description_with_columns_suffix() -> None:
    template = Credicoop1Template()
    rows = [
        ParsedMovement(
            fecha="01/09/2025",
            descripcion="Impuesto Ley 25.413 Ali Gral s/Debitos 0 143.69 0.00 4793296.54 IDCC3",
            debito=143.69,
            credito=None,
            saldo=4793296.54,
            pagina=1,
            confianza=0.97,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview="01/09/2025 Impuesto Ley 25.413 Ali Gral s/Debitos 0 143.69 0.00 4793296.54 IDCC3",
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())
    assert rows[0].descripcion == "Impuesto Ley 25.413 Ali Gral s/Debitos"


def test_credicoop1_joins_multiline_origin_block() -> None:
    template = Credicoop1Template()
    rows = [
        ParsedMovement(
            fecha="01/09/2025",
            descripcion="Credito Inmediato (DEBIN) dist titular 27454076562-VAR- 430802 0.00 10220.00 2306129.02 01874",
            debito=None,
            credito=10220.0,
            saldo=2306129.02,
            pagina=1,
            confianza=0.83,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "01/09/2025 Credito Inmediato (DEBIN) dist titular 27454076562-VAR- 430802 0.00 10220.00 2306129.02 01874 | "
                "CAMILA AGOSTINA BARNADA"
            ),
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == (
        "Credito Inmediato (DEBIN) dist titular 27454076562-VAR-CAMILA AGOSTINA BARNADA"
    )


def test_credicoop1_maps_debit_credit_from_structured_line() -> None:
    template = Credicoop1Template()
    row = ParsedMovement(
        fecha="01/09/2025",
        descripcion="dummy",
        debito=None,
        credito=143.69,
        saldo=0.0,
        pagina=1,
        confianza=0.97,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview="01/09/2025 Impuesto Ley 25.413 Ali Gral s/Debitos 0 143.69 0.00 4793296.54 IDCC3",
        issues=[],
    )

    template.postprocess_rows([row], [trace], _context())

    assert row.debito == 143.69
    assert row.credito is None
    assert row.saldo == 4793296.54


def test_credicoop1_skips_numeric_continuation_equal_to_cpbte() -> None:
    template = Credicoop1Template()
    row = ParsedMovement(
        fecha="28/08/2025",
        descripcion="Comision por Transferencia B. INTERNET COM. USO- 000382354",
        debito=1800.0,
        credito=None,
        saldo=424724.84,
        pagina=3,
        confianza=0.90,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview=(
            "28/08/2025 Comision por Transferencia B. INTERNET COM. USO- 382354 1800.00 0.00 424724.84 00211 | "
            "000382354"
        ),
        issues=["descripcion_multilinea"],
    )

    template.postprocess_rows([row], [trace], _context())

    assert row.descripcion == "Comision por Transferencia B. INTERNET COM. USO-"


def test_credicoop1_confidence_not_penalized_for_ley_25413_token() -> None:
    template = Credicoop1Template()
    row = ParsedMovement(
        fecha="01/09/2025",
        descripcion="Impuesto Ley 25.413 Ali Gral s/Debitos",
        debito=143.69,
        credito=None,
        saldo=4793296.54,
        pagina=1,
        confianza=0.90,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview="01/09/2025 Impuesto Ley 25.413 Ali Gral s/Debitos 0 143.69 0.00 4793296.54 IDCC3",
        issues=[],
    )

    delta = template.adjust_row_confidence(row=row, trace=trace, context=_context())

    assert delta >= 0.07


def test_credicoop1_removes_footer_url_from_multiline_description() -> None:
    template = Credicoop1Template()
    row = ParsedMovement(
        fecha="27/08/2025",
        descripcion="dummy",
        debito=None,
        credito=24000.0,
        saldo=173845.80,
        pagina=3,
        confianza=0.90,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview=(
            "27/08/2025 Transf. Inmediata e/Ctas. Dist. Titular 27267308042-VAR- 191033 0.00 24000.00 173845.80 01872 | "
            "VELAZCO, AURORA BEATRI | "
            "https://bancainternet.bancocredicoop.coop/bcclbe/export.do 3/17"
        ),
        issues=["descripcion_multilinea"],
    )

    template.postprocess_rows([row], [trace], _context())

    assert row.descripcion == "Transf. Inmediata e/Ctas. Dist. Titular 27267308042-VAR-VELAZCO, AURORA BEATRI"


def test_credicoop1_compute_confidence_high_for_clean_structured_row() -> None:
    template = Credicoop1Template()
    row = ParsedMovement(
        fecha="01/09/2025",
        descripcion="Impuesto Ley 25.413 Ali Gral s/Debitos",
        debito=143.69,
        credito=None,
        saldo=4793296.54,
        pagina=1,
        confianza=0.83,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview="01/09/2025 Impuesto Ley 25.413 Ali Gral s/Debitos 0 143.69 0.00 4793296.54 IDCC3",
        issues=[],
    )

    confidence = template.compute_row_confidence(row=row, trace=trace, context=_context())

    assert confidence is not None
    assert confidence >= 0.9

