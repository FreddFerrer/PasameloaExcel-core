from __future__ import annotations

from dataclasses import dataclass

from app.schemas.export import ExportExcelRequest
from app.services.export_service import ExportService

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(slots=True)
class ExportExcelResult:
    content: bytes
    filename: str
    media_type: str = XLSX_MEDIA_TYPE


class ExportExcelUseCase:
    def __init__(self, export_service: ExportService) -> None:
        self.export_service = export_service

    def execute(self, request: ExportExcelRequest) -> ExportExcelResult:
        content, filename = self.export_service.export_excel(request)
        return ExportExcelResult(content=content, filename=filename)


