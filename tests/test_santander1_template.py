from __future__ import annotations

from pathlib import Path

from app.parsing.templates.santander1 import Santander1Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[
            {
                "page_num": 1,
                "lines": [
                    "Resumen de cuenta",
                    "Banco Santander Argentina S.A. es una sociedad anónima según la ley argentina",
                    "CUIT 30-50000845-4",
                ],
            },
            {
                "page_num": 2,
                "lines": [
                    "Movimientos en pesos",
                    "Fecha Comprobante Movimiento Débito Crédito Saldo en cuenta",
                ],
            },
        ],
        file_stem="resumen_mensual_noviembre_2025",
        first_page_text=(
            "Resumen de cuenta\n"
            "Banco Santander Argentina S.A. es una sociedad anónima según la ley argentina\n"
            "CUIT 30-50000845-4"
        ),
    )


def test_santander1_match_score_is_high_with_legal_footer_and_header() -> None:
    template = Santander1Template()
    score = template.match_score(_context())
    assert score >= 0.9


def test_santander1_collects_grouped_rows_with_shared_date() -> None:
    template = Santander1Template()
    context = _context()
    pages = [
        {
            "page_num": 2,
            "lines": [
                "Movimientos en pesos",
                "Fecha Comprobante Movimiento Débito Crédito Saldo en cuenta",
                "01/11/25 Saldo Inicial $ 2.776.041,45",
                "03/11/25 286 Echeq clearing recibido 48hs $ 443.745,37 $ 2.332.296,08",
                "15819574 Compra con tarjeta de debito $ 478.426,54 $ 1.853.869,54",
                "03/11/25",
                "Jetsmart airlines sa - tarj nro. 1041",
                "30107036 Pago haberes $ 1.025.249,00 $ 5.729.968,72",
                "03/11/25",
                "2511055072",
                "* Salvo error u omisión 2 - 13",
            ],
        }
    ]

    candidates = template.collect_candidates(pages, context)
    assert candidates is not None
    assert len(candidates) == 4
    assert "Saldo Inicial" in candidates[0].raw_text
    assert "15819574 Compra con tarjeta de debito" in candidates[2].raw_text
    assert "Jetsmart airlines sa - tarj nro. 1041" in candidates[2].raw_text
    assert "Pago haberes" in candidates[3].raw_text
    assert "2511055072" in candidates[3].raw_text


def test_santander1_postprocess_parses_multiline_and_infers_debit() -> None:
    template = Santander1Template()
    rows = [
        ParsedMovement(
            fecha="01/11/25",
            descripcion="Saldo Inicial",
            debito=None,
            credito=None,
            saldo=None,
            pagina=2,
            confianza=0.5,
            confianza_campos={},
        ),
        ParsedMovement(
            fecha="03/11/25",
            descripcion="Compra con tarjeta de debito",
            debito=None,
            credito=None,
            saldo=None,
            pagina=2,
            confianza=0.5,
            confianza_campos={},
        ),
    ]
    traces = [
        RowTrace(
            raw_preview="01/11/2025 Saldo Inicial $ 2.776.041,45",
            issues=[],
        ),
        RowTrace(
            raw_preview=(
                "03/11/2025 15819574 Compra con tarjeta de debito $ 478.426,54 $ 1.853.869,54 | "
                "Jetsmart airlines sa - tarj nro. 1041"
            ),
            issues=["descripcion_multilinea"],
        ),
    ]

    template.postprocess_rows(rows, traces, _context())

    assert len(rows) == 1
    assert rows[0].descripcion == "Compra con tarjeta de debito Jetsmart airlines sa - tarj nro. 1041"
    assert rows[0].debito == 478426.54
    assert rows[0].credito is None
    assert rows[0].saldo == 1853869.54


def test_santander1_confidence_boosts_contextual_amount_in_description() -> None:
    template = Santander1Template()
    row = ParsedMovement(
        fecha="03/11/2025",
        descripcion="Regimen de recaudacion sircreb v Resp:30718080963 / 3,00% sobre $59.004,32",
        debito=1770.13,
        credito=None,
        saldo=5700656.20,
        pagina=2,
        confianza=0.0,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview=(
            "03/11/2025 Regimen de recaudacion sircreb v $ 1.770,13 $ 5.700.656,20 | "
            "Resp:30718080963 / 3,00% sobre $59.004,32"
        ),
        issues=["descripcion_multilinea"],
    )

    confidence = template.compute_row_confidence(row=row, trace=trace, context=_context())

    assert confidence is not None
    assert confidence >= 0.95


def test_santander1_allows_generic_multiline_continuation_and_ignores_noise() -> None:
    template = Santander1Template()
    first_line = "03/11/2025 30107036 Pago haberes $ 1.025.249,00 $ 5.729.968,72"

    assert template.should_attach_continuation(first_line, "Detalle adicional del pago")
    assert template.should_attach_continuation(first_line, "2511055072")
    assert not template.should_attach_continuation(first_line, "https://bank.example/export 3/17")
    assert not template.should_attach_continuation(
        first_line,
        "04/11/2025 48150071 Pago comercios first data visa nro.liq. $ 3.567,32 $ 5.726.401,40",
    )


def test_santander1_forces_echeq_to_debit_even_if_detected_in_credit_column() -> None:
    template = Santander1Template()
    rows = [
        ParsedMovement(
            fecha="12/01/2026",
            descripcion="Echeq clearing recibido 48hs",
            debito=None,
            credito=None,
            saldo=None,
            pagina=4,
            confianza=0.5,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview="12/01/2026 999 Echeq clearing recibido 48hs $ 0,00 $ 152.213,27 $ 4.000.000,00",
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].debito == 152213.27
    assert rows[0].credito is None


def test_santander1_forces_retiro_por_caja_to_debit() -> None:
    template = Santander1Template()
    rows = [
        ParsedMovement(
            fecha="08/01/2026",
            descripcion="Retiro en efvo por caja suc resistencia",
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
            raw_preview="08/01/2026 777 Retiro en efvo por caja suc resistencia $ 0,00 $ 30.000.000,00 $ 5.500.000,00",
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].debito == 30000000.0
    assert rows[0].credito is None


def test_santander1_negative_saldo_with_split_minus_keeps_debito_automatico_as_debit() -> None:
    template = Santander1Template()
    rows = [
        ParsedMovement(
            fecha="12/01/2026",
            descripcion="Debito automatico",
            debito=None,
            credito=None,
            saldo=None,
            pagina=6,
            confianza=0.5,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "12/01/2026 4988 Debito automatico $ 1.979.246,03 -$ 21.538.034,25 | "
                "La segunda segur-0000000000040066798359"
            ),
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].debito == 1979246.03
    assert rows[0].credito is None
    assert rows[0].saldo == -21538034.25


def test_santander1_forces_pagos_ctas_propias_interbanking_as_credit() -> None:
    template = Santander1Template()
    rows = [
        ParsedMovement(
            fecha="12/01/2026",
            descripcion="Pagos ctas propias interbanking in Serman nea s r l",
            debito=None,
            credito=None,
            saldo=None,
            pagina=7,
            confianza=0.5,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "12/01/2026 3136688 Pagos ctas propias interbanking in $ 5.000.000,00 -$ 17.872.240,23 | "
                "Serman nea s r l 30716759403 01 3136688"
            ),
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].credito == 5000000.0
    assert rows[0].debito is None


