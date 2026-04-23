from __future__ import annotations

from pathlib import Path

from app.parsing.templates.nacion1 import Nacion1Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[],
        file_stem="nacion1",
        first_page_text=(
            "BANCO DE LA\n"
            "NACION ARGENTINA\n"
            "CUIT 30-50001091-2 IVA RESPONSABLE INSCRIPTO\n"
            "FECHA MOVIMIENTOS COMPROB. DEBITOS CREDITOS SALDO\n"
            "SALDO ANTERIOR 3.687,69"
        ),
    )


def test_nacion1_match_score_from_header_signature() -> None:
    template = Nacion1Template()
    score = template.match_score(_context())
    assert score >= 0.9


def test_nacion1_removes_comprob_from_description() -> None:
    template = Nacion1Template()
    rows = [
        ParsedMovement(
            fecha="02/06/25",
            descripcion="COMISION PAQUETES 2690",
            debito=None,
            credito=27000.0,
            saldo=-23312.31,
            pagina=1,
            confianza=0.95,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview="02/06/25 COMISION PAQUETES 2690 27.000,00 23.312,31-",
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == "COMISION PAQUETES"


def test_nacion1_maps_debit_and_credit_with_balance_delta() -> None:
    template = Nacion1Template()
    rows = [
        ParsedMovement(
            fecha="02/06/25",
            descripcion="COMISION PAQUETES 2690",
            debito=None,
            credito=27000.0,
            saldo=-23312.31,
            pagina=1,
            confianza=0.95,
            confianza_campos={},
        ),
        ParsedMovement(
            fecha="09/06/25",
            descripcion="DEBIN 27350834503 2709",
            debito=None,
            credito=388084.0,
            saldo=358090.81,
            pagina=1,
            confianza=0.95,
            confianza_campos={},
        ),
    ]
    traces = [
        RowTrace(raw_preview="02/06/25 COMISION PAQUETES 2690 27.000,00 23.312,31-", issues=[]),
        RowTrace(raw_preview="09/06/25 DEBIN 27350834503 2709 388.084,00 358.090,81", issues=[]),
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].debito == 27000.0
    assert rows[0].credito is None
    assert rows[1].debito is None
    assert rows[1].credito == 388084.0


