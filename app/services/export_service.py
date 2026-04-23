from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.domain.export import build_export_filename
from app.exporters.excel_exporter import ExcelBytesExporter
from app.schemas.export import ExportExcelRequest
from app.services.learning_logger import LearningLogger


class ExportService:
    def __init__(
        self,
        exporter: ExcelBytesExporter,
        learning_logger: LearningLogger,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.exporter = exporter
        self.learning_logger = learning_logger
        self.now_provider = now_provider or datetime.now

    def export_excel(self, request: ExportExcelRequest) -> tuple[bytes, str]:
        file_bytes = self.exporter.export(request.rows_final)
        if request.download_filename:
            output_name = build_export_filename(
                request.download_filename,
                now=self.now_provider(),
                append_timestamp=False,
            )
        else:
            output_name = build_export_filename(request.filename, now=self.now_provider())
        self.learning_logger.log_export_feedback(request)
        return file_bytes, output_name

