from __future__ import annotations

from pathlib import Path

from app.parsing.templates.galicia1 import Galicia1Template
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


def _context() -> TemplateContext:
    return TemplateContext(
        pdf_path=Path("dummy.pdf"),
        pages=[],
        file_stem="1_julio",
        first_page_text="Resumen de Cuenta Corriente en Pesos\nFecha Descripción Origen Crédito Débito Saldo",
    )


def test_galicia1_appends_multiline_origin_block() -> None:
    template = Galicia1Template()
    rows = [
        ParsedMovement(
            fecha="01/07/24",
            descripcion="TRANSFERENCIA DE TERCEROS 00C4 0,00 297.000,00 8.513.077,78",
            debito=None,
            credito=297000.0,
            saldo=8513077.78,
            pagina=2,
            confianza=0.97,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "01/07/24 TRANSFERENCIA DE TERCEROS 00C4 0,00 297.000,00 8.513.077,78 | "
                "ESPINDOLA, JUAN RAM | "
                "20180958011 | "
                "00000000000000000000 | "
                "272040790548 | "
                "5537715642979003 | "
                "CUOTA"
            ),
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == (
        "TRANSFERENCIA DE TERCEROS ESPINDOLA, JUAN RAM 20180958011 "
        "00000000000000000000 272040790548 5537715642979003 CUOTA"
    )


def test_galicia1_swaps_credit_debit_columns_from_three_amount_layout() -> None:
    template = Galicia1Template()
    row = ParsedMovement(
        fecha="01/07/24",
        descripcion="ECHEQ 48 HS. NRO. 935",
        debito=None,
        credito=573766.0,
        saldo=5423269.74,
        pagina=1,
        confianza=0.97,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview="01/07/24 ECHEQ 48 HS. NRO. 935 0,00 -573.766,00 5.423.269,74",
        issues=[],
    )

    template.postprocess_rows([row], [trace], _context())

    assert row.debito == 573766.0
    assert row.credito is None
    assert row.saldo == 5423269.74


def test_galicia1_appends_multiline_for_credito_transferencia() -> None:
    template = Galicia1Template()
    first_line = "31/07/24 CREDITO TRANSFERENCIA 179.505,00 2.780.455,65"

    assert template.should_attach_continuation(first_line, "COELSA")
    assert template.should_attach_continuation(first_line, "Evangelina Alcantara")
    assert template.should_attach_continuation(first_line, "23217235944")
    assert template.should_attach_continuation(first_line, "MERCADO LIBRE SRL")
    assert not template.should_attach_continuation(first_line, "31/07/24 ING. BRUTOS S/ CRED -2.198,94 2.778.256,71")

    rows = [
        ParsedMovement(
            fecha="31/07/24",
            descripcion="CREDITO TRANSFERENCIA",
            debito=None,
            credito=179505.0,
            saldo=2780455.65,
            pagina=76,
            confianza=0.97,
            confianza_campos={},
        )
    ]
    traces = [
        RowTrace(
            raw_preview=(
                "31/07/24 CREDITO TRANSFERENCIA 179.505,00 2.780.455,65 | "
                "COELSA | "
                "Evangelina Alcantara | "
                "23217235944 | "
                "MERCADO LIBRE SRL"
            ),
            issues=["descripcion_multilinea"],
        )
    ]

    template.postprocess_rows(rows, traces, _context())

    assert rows[0].descripcion == (
        "CREDITO TRANSFERENCIA COELSA Evangelina Alcantara 23217235944 MERCADO LIBRE SRL"
    )


def test_galicia1_allows_generic_multiline_continuation() -> None:
    template = Galicia1Template()
    first_line = "31/07/24 PAGO CON TARJETA 20.000,00 3.000.000,00"

    assert template.should_attach_continuation(first_line, "SUPERMERCADO DEL CENTRO")
    assert not template.should_attach_continuation(first_line, "01/08/24 CREDITO TRANSFERENCIA 2.660,00 1.586.850,23")


def test_galicia1_appends_multiline_for_ingresos_brutos() -> None:
    template = Galicia1Template()
    first_line = "01/07/24 ING. BRUTOS S/ CRED -104,24 4.818.089,13"

    assert template.should_attach_continuation(first_line, "RG.19/02-MISIONES")
    assert not template.should_attach_continuation(first_line, "02/07/24 CREDITO TRANSFERENCIA 2.660,00 1.586.850,23")

    row = ParsedMovement(
        fecha="01/07/24",
        descripcion="ING. BRUTOS S/ CRED",
        debito=104.24,
        credito=None,
        saldo=4818089.13,
        pagina=2,
        confianza=0.97,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview="01/07/24 ING. BRUTOS S/ CRED -104,24 4.818.089,13 | RG.19/02-MISIONES",
        issues=["descripcion_multilinea"],
    )

    template.postprocess_rows([row], [trace], _context())

    assert row.descripcion == "ING. BRUTOS S/ CRED RG.19/02-MISIONES"


def test_galicia1_compute_confidence_high_for_clean_multiline_row() -> None:
    template = Galicia1Template()
    row = ParsedMovement(
        fecha="31/07/24",
        descripcion="CREDITO TRANSFERENCIA COELSA Evangelina Alcantara 23217235944 MERCADO LIBRE SRL",
        debito=None,
        credito=179505.0,
        saldo=2780455.65,
        pagina=76,
        confianza=0.83,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview=(
            "31/07/24 CREDITO TRANSFERENCIA 179.505,00 2.780.455,65 | "
            "COELSA | Evangelina Alcantara | 23217235944 | MERCADO LIBRE SRL"
        ),
        issues=["descripcion_multilinea"],
    )

    confidence = template.compute_row_confidence(row=row, trace=trace, context=_context())

    assert confidence is not None
    assert confidence >= 0.9


def test_galicia1_keeps_numeric_ticket_suffix_in_description() -> None:
    template = Galicia1Template()
    row = ParsedMovement(
        fecha="24/07/24",
        descripcion="DEP.EFVO.AUTOSERVICIO TICKET:",
        debito=None,
        credito=300000.0,
        saldo=3371440.98,
        pagina=61,
        confianza=0.85,
        confianza_campos={},
    )
    trace = RowTrace(
        raw_preview="24/07/24 DEP.EFVO.AUTOSERVICIO TICKET: 0071 300.000,00 3.371.440,98-",
        issues=["descripcion_truncada_probable"],
    )

    template.postprocess_rows([row], [trace], _context())

    assert row.descripcion == "DEP.EFVO.AUTOSERVICIO TICKET: 0071"

