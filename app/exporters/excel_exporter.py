from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font


class ExcelBytesExporter:
    """Exporta movimientos a XLSX en memoria (sin dependencias externas al backend)."""

    def __init__(self, working_temp_dir: Path) -> None:
        self.working_temp_dir = working_temp_dir

    def export(self, rows: list[object]) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "movimientos"

        headers = ["Fecha", "Descripcion", "Debito", "Credito", "Saldo", "Pagina", "Confianza"]
        sheet.append(headers)

        for col_idx, _ in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=col_idx)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for row in rows:
            sheet.append(
                [
                    getattr(row, "fecha", None),
                    getattr(row, "descripcion", None),
                    getattr(row, "debito", None),
                    getattr(row, "credito", None),
                    getattr(row, "saldo", None),
                    getattr(row, "pagina", None),
                    getattr(row, "confianza", None),
                ]
            )

        numeric_cols = ["C", "D", "E", "G"]
        for col in numeric_cols:
            for cell in sheet[col][1:]:
                if cell.value is not None:
                    cell.number_format = "#,##0.00"
                    cell.alignment = Alignment(horizontal="right")

        widths = {"A": 14, "B": 64, "C": 14, "D": 14, "E": 14, "F": 10, "G": 12}
        for col, width in widths.items():
            sheet.column_dimensions[col].width = width

        output = BytesIO()
        workbook.save(output)
        return output.getvalue()
