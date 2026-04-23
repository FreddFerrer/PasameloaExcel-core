from __future__ import annotations

from pathlib import Path

from app.parsing.templates.credicoop2 import Credicoop2Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[],
        file_stem="resumen_abril_2025",
        first_page_text=(
            "FECHA COMBTE DESCRIPCION DEBITO CREDITO SALDO\n"
            "Banco Credicoop Cooperativo Limitado - Reconquista 484\n"
            "Ctro. de Contacto Telefonico: cct@bancocredicoop.coop\n"
            "Credicoop Responde: 0810-888-4500"
        ),
    )


def test_credicoop2_match_score_high_for_footer_and_header() -> None:
    template = Credicoop2Template()
    score = template.match_score(_context())
    assert score >= 0.9


def test_credicoop2_should_attach_date_time_detail_line() -> None:
    template = Credicoop2Template()
    assert template.should_attach_continuation(
        "07/04/25 6755 Retiro de Cajero Automatico 80.000,00",
        "04/04 14:26 Tarj:4339 Term:837551âˆ’CREDI",
    )


def test_credicoop2_postprocess_appends_ente_and_ord_continuations() -> None:
    template = Credicoop2Template()
    rows = [
        ParsedMovement(
            fecha="03/04/25",
            descripcion="Pago de Servicios",
            debito=None,
            credito=None,
            saldo=None,
            pagina=1,
            confianza=0.5,
            confianza_campos={},
        ),
        ParsedMovement(
            fecha="03/04/25",
            descripcion="Transf. Interbanking - Distinto Titular",
            debito=None,
            credito=None,
            saldo=None,
            pagina=1,
            confianza=0.5,
            confianza_campos={},
        ),
    ]
    traces = [
        RowTrace(
            raw_preview="03/04/25 350242 Pago de Servicios 393.568,81 | Ente: SERVICIOS ENERGET DEL CHACO",
            issues=["descripcion_multilinea"],
        ),
        RowTrace(
            raw_preview=(
                "03/04/25 680340 Transf. Interbanking âˆ’ Distinto Titular 1.516.688,30 | "
                "Ord.:30584374817âˆ’ECOM CHACO SA"
            ),
            issues=["descripcion_multilinea"],
        ),
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == "Pago de Servicios Ente: SERVICIOS ENERGET DEL CHACO"
    assert rows[1].descripcion == "Transf. Interbanking âˆ’ Distinto Titular Ord.:30584374817âˆ’ECOM CHACO SA"


def test_credicoop2_postprocess_merges_retiro_date_time_detail() -> None:
    template = Credicoop2Template()
    rows = [
        ParsedMovement(
            fecha="07/04/25",
            descripcion="Retiro de Cajero Automatico",
            debito=None,
            credito=None,
            saldo=None,
            pagina=2,
            confianza=0.5,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "07/04/25 6755 Retiro de Cajero Automatico 80.000,00 | "
                "04/04 14:26 Tarj:4339 Term:837551âˆ’CREDI"
            ),
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == "Retiro de Cajero Automatico 04/04 14:26 Tarj:4339 Term:837551âˆ’CREDI"
    assert rows[0].debito == 80000.0
    assert rows[0].credito is None


def test_credicoop2_side_rules_for_debit_and_credit_keywords() -> None:
    template = Credicoop2Template()
    rows = [
        ParsedMovement(
            fecha="01/04/25",
            descripcion="Servicio acreditaciones automaticas",
            debito=None,
            credito=None,
            saldo=None,
            pagina=1,
            confianza=0.5,
            confianza_campos={},
        ),
        ParsedMovement(
            fecha="01/04/25",
            descripcion="Transf. Inmediata e/Ctas. Dist. Titular",
            debito=None,
            credito=None,
            saldo=None,
            pagina=1,
            confianza=0.5,
            confianza_campos={},
        ),
        ParsedMovement(
            fecha="01/04/25",
            descripcion="Impuesto Ley 25.413 Ali Gral s/Creditos",
            debito=None,
            credito=None,
            saldo=None,
            pagina=1,
            confianza=0.5,
            confianza_campos={},
        ),
    ]
    traces = [
        RowTrace(
            raw_preview="01/04/25 478100 Servicio acreditaciones automaticas 1,00",
            issues=[],
        ),
        RowTrace(
            raw_preview="01/04/25 904542 Transf. Inmediata e/Ctas. Dist. Titular 2.926.450,00",
            issues=[],
        ),
        RowTrace(
            raw_preview="01/04/25 Impuesto Ley 25.413 Ali Gral s/Creditos 17.558,70",
            issues=[],
        ),
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].debito == 1.0 and rows[0].credito is None
    assert rows[1].credito == 2926450.0 and rows[1].debito is None
    assert rows[2].debito == 17558.7 and rows[2].credito is None

