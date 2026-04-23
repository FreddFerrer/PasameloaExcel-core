from __future__ import annotations

from pathlib import Path

from app.parsing.templates.nbch2 import Nbch2Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[],
        file_stem="nbch2",
        first_page_text=(
            "Ultimos movimientos\n"
            "Fecha Monto N° de Comprobante Descripción Saldo\n"
            "Debitos y Creditos"
        ),
    )


def test_nbch2_match_score_for_modern_header() -> None:
    template = Nbch2Template()
    score = template.match_score(_context())
    assert score >= 0.9


def test_nbch2_removes_comprobante_from_description_and_maps_credit() -> None:
    template = Nbch2Template()
    rows = [
        ParsedMovement(
            fecha="12/09/2025",
            descripcion="996025869 Percepción IVA sobre comisiones (R.G. 2408/08)",
            debito=None,
            credito=970.0,
            saldo=106779.84,
            pagina=2,
            confianza=0.95,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "12/09/2025 $ 970,00 996025869 "
                "Percepción IVA sobre comisiones (R.G. 2408/08) "
                "$ 106.779,84"
            ),
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == "Percepción IVA sobre comisiones (R.G. 2408/08)"
    assert rows[0].debito is None
    assert rows[0].credito == 970.0
    assert rows[0].saldo == 106779.84


def test_nbch2_maps_negative_movement_to_debit() -> None:
    template = Nbch2Template()
    rows = [
        ParsedMovement(
            fecha="12/09/2025",
            descripcion="996025870 COMISION MANTENIMIENTO",
            debito=None,
            credito=None,
            saldo=106209.84,
            pagina=2,
            confianza=0.95,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "12/09/2025 $ -570,00 996025870 COMISION MANTENIMIENTO $ 106.209,84"
            ),
            issues=[],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == "COMISION MANTENIMIENTO"
    assert rows[0].debito == 570.0
    assert rows[0].credito is None


def test_nbch2_confidence_is_high_for_clean_rows() -> None:
    template = Nbch2Template()
    row = ParsedMovement(
        fecha="12/09/2025",
        descripcion="Percepcion IVA sobre comisiones (R.G. 2408/08)",
        debito=1200.0,
        credito=None,
        saldo=106779.84,
        pagina=2,
        confianza=0.0,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview="12/09/2025 $ -1200,00 996025869 Percepcion IVA sobre comisiones (R.G. 2408/08) $ 106.779,84",
        issues=[],
    )

    confidence = template.compute_row_confidence(row=row, trace=trace, context=_context())

    assert confidence is not None
    assert confidence >= 0.97


