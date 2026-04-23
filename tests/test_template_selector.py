from __future__ import annotations

from pathlib import Path

from app.parsing.templates.registry import TemplateSelector, build_default_templates
from app.parsing.types import TemplateContext


def _context(file_stem: str, first_page_text: str) -> TemplateContext:
    return TemplateContext(
        pdf_path=Path(f"{file_stem}.pdf"),
        pages=[],
        file_stem=file_stem,
        first_page_text=first_page_text,
    )


def test_default_templates_contains_credicoop2_santander_credicoop_nbch2_nacion2_nacion1_formosa_galicia_nbch_and_generic() -> None:
    templates = build_default_templates()
    assert len(templates) == 10
    assert templates[0].template_id == "credicoop2"
    assert templates[1].template_id == "santander1"
    assert templates[2].template_id == "credicoop1"
    assert templates[3].template_id == "nbch2"
    assert templates[4].template_id == "nacion2"
    assert templates[5].template_id == "nacion1"
    assert templates[6].template_id == "formosa1"
    assert templates[7].template_id == "galicia1"
    assert templates[8].template_id == "nbch1"
    assert templates[9].template_id == "generic_auto"


def test_selector_picks_credicoop1_for_credicoop_like_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="resumen_08_2025",
            first_page_text=(
                "Fecha Concepto Nro.Cpbte. Débito Crédito Saldo Cód.\n"
                "https://bancainternet.bancocredicoop.coop"
            ),
        )
    )

    assert selection.template.template_id == "credicoop1"


def test_selector_picks_credicoop2_for_footer_driven_credicoop_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="4_resumen_cta_abril_2025",
            first_page_text=(
                "FECHA COMBTE DESCRIPCION DEBITO CREDITO SALDO\n"
                "Banco Credicoop Cooperativo Limitado - Reconquista 484\n"
                "Ctro. de Contacto Telefonico: cct@bancocredicoop.coop\n"
                "Credicoop Responde: 0810-888-4500"
            ),
        )
    )

    assert selection.template.template_id == "credicoop2"


def test_selector_picks_santander1_for_santander_like_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="resumen_mensual_noviembre_2025",
            first_page_text=(
                "Resumen de cuenta\n"
                "Banco Santander Argentina S.A. es una sociedad anónima según la ley argentina\n"
                "CUIT 30-50000845-4"
            ),
        )
    )

    assert selection.template.template_id == "santander1"


def test_selector_picks_galicia1_for_galicia_like_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="1_julio",
            first_page_text=(
                "Resumen de Cuenta Corriente en Pesos\n"
                "Fecha Descripción Origen Crédito Débito Saldo"
            ),
        )
    )

    assert selection.template.template_id == "galicia1"


def test_selector_picks_formosa1_for_formosa_like_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="resumen_abril_2025",
            first_page_text=(
                "FECHA CONCEPTO REFERENCIA CHEQUE DEBITOS CREDITOS SALDO\n"
                "Banco de Formosa S.A.\n"
                "DETALLE POR PRODUCTO"
            ),
        )
    )

    assert selection.template.template_id == "formosa1"


def test_selector_picks_nacion1_for_bna_like_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="extracto_junio",
            first_page_text=(
                "BANCO DE LA\n"
                "NACION ARGENTINA\n"
                "CUIT 30-50001091-2 IVA RESPONSABLE INSCRIPTO\n"
                "FECHA MOVIMIENTOS COMPROB. DEBITOS CREDITOS SALDO"
            ),
        )
    )

    assert selection.template.template_id == "nacion1"


def test_selector_picks_nacion2_for_modern_bna_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="extracto_septiembre",
            first_page_text=(
                "Fecha: 2025-09-09 15:13:04\n"
                "Últimos movimientos\n"
                "Fecha Comprobante Concepto Importe Saldo"
            ),
        )
    )

    assert selection.template.template_id == "nacion2"


def test_selector_picks_nbch2_for_modern_nbch_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="nbch2_extracto_octubre",
            first_page_text=(
                "ULTIMOS MOVIMIENTOS\n"
                "Fecha Monto N° de Comprobante Descripción Saldo\n"
                "DEBITOS Y CREDITOS"
            ),
        )
    )

    assert selection.template.template_id == "nbch2"


def test_selector_picks_nbch1_for_nbch_like_extract() -> None:
    selector = TemplateSelector(build_default_templates())

    selection_nbch_like = selector.select(
        _context(
            file_stem="nuevo_banco_chaco_abril_2026_nbch",
            first_page_text="NUEVO BANCO DEL CHACO - COMPROBANTE",
        )
    )

    assert selection_nbch_like.template.template_id == "nbch1"


def test_selector_does_not_pick_nbch1_with_generic_chaco_mentions_only() -> None:
    selector = TemplateSelector(build_default_templates())

    selection = selector.select(
        _context(
            file_stem="extracto_banco_x",
            first_page_text=(
                "Sucursal Chaco - Resumen de movimientos\n"
                "Comprobante de operaciones del periodo"
            ),
        )
    )

    assert selection.template.template_id == "generic_auto"


def test_selector_falls_back_to_generic_for_unknown_extract() -> None:
    selector = TemplateSelector(build_default_templates())
    selection = selector.select(
        _context(
            file_stem="extracto_desconocido",
            first_page_text="ENTIDAD FINANCIERA X",
        )
    )

    assert selection.template.template_id == "generic_auto"
    assert selection.score == 0.01

