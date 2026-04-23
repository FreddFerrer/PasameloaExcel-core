from __future__ import annotations

from pathlib import Path

from app.parsing.templates.nacion2 import Nacion2Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[],
        file_stem="nacion2",
        first_page_text=(
            "Últimos movimientos\n"
            "Fecha Comprobante Concepto Importe Saldo\n"
            "Fecha: 2025-09-09 15:13:04"
        ),
    )


def test_nacion2_match_score_from_modern_header() -> None:
    template = Nacion2Template()
    score = template.match_score(_context())
    assert score >= 0.9


def test_nacion2_parses_split_date_and_removes_comprobante() -> None:
    template = Nacion2Template()
    rows = [
        ParsedMovement(
            fecha="29/08",
            descripcion="GRAVAMEN LEY 25413/DEB 0",
            debito=None,
            credito=72.0,
            saldo=143670.25,
            pagina=1,
            confianza=0.9,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview="29/08 | 0 GRAVAMEN LEY 25413/DEB $ -72,00 $ 143.670,25 | /2025",
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].fecha == "29/08/2025"
    assert rows[0].descripcion == "GRAVAMEN LEY 25413/DEB"
    assert rows[0].debito == 72.0
    assert rows[0].credito is None
    assert rows[0].saldo == 143670.25


def test_nacion2_joins_multiline_concept_with_cuit() -> None:
    template = Nacion2Template()
    rows = [
        ParsedMovement(
            fecha="28/08",
            descripcion="CR.TRANF.INTER. MISMO TIT",
            debito=None,
            credito=300000.0,
            saldo=-222052.88,
            pagina=1,
            confianza=0.9,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "28/08 CR.TRANF.INTER. MISMO TIT - | "
                "685 $ 300.000,00 $ -222.052,88 | "
                "/2025 CUIT/CUIL: 30707095136"
            ),
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].fecha == "28/08/2025"
    assert rows[0].descripcion == "CR.TRANF.INTER. MISMO TIT - CUIT/CUIL: 30707095136"
    assert rows[0].debito is None
    assert rows[0].credito == 300000.0
    assert rows[0].saldo == -222052.88


def test_nacion2_keeps_numeric_token_that_belongs_to_concept() -> None:
    template = Nacion2Template()
    rows = [
        ParsedMovement(
            fecha="29/08",
            descripcion="CRED LIQ NATIV 24 H",
            debito=None,
            credito=79393.85,
            saldo=77152.11,
            pagina=1,
            confianza=0.9,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview="29/08 | 5172840 CRED LIQ NATIV 24 H $ 79.393,85 $ 77.152,11 | /2025",
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == "CRED LIQ NATIV 24 H"

