from __future__ import annotations

from functools import lru_cache

from app.application.use_cases import (
    ExportExcelUseCase,
    ExtractPreviewUseCase,
    SubmitExtractSupportUseCase,
)
from app.core.config import get_settings
from app.exporters.excel_exporter import ExcelBytesExporter
from app.services.export_service import ExportService
from app.services.learning_logger import LearningLogger
from app.services.parser_service import ParserService
from app.services.preview_service import PreviewService
from app.services.support_service import SupportEmailConfig, SupportService


@lru_cache
def get_parser_service() -> ParserService:
    settings = get_settings()
    return ParserService(settings=settings)


@lru_cache
def get_preview_service() -> PreviewService:
    settings = get_settings()
    return PreviewService(
        parser_service=get_parser_service(),
        working_temp_dir=settings.working_temp_dir,
    )


@lru_cache
def get_learning_logger() -> LearningLogger:
    settings = get_settings()
    return LearningLogger(logs_dir=settings.learning_logs_dir)


@lru_cache
def get_export_service() -> ExportService:
    settings = get_settings()
    exporter = ExcelBytesExporter(working_temp_dir=settings.working_temp_dir)
    logger = get_learning_logger()
    return ExportService(exporter=exporter, learning_logger=logger)


@lru_cache
def get_support_service() -> SupportService:
    settings = get_settings()
    email_config = SupportEmailConfig(
        enabled=settings.support_email_enabled,
        to_address=settings.support_email_to,
        from_address=settings.support_email_from,
        smtp_host=settings.support_smtp_host,
        smtp_port=settings.support_smtp_port,
        smtp_username=settings.support_smtp_username,
        smtp_password=settings.support_smtp_password,
        smtp_use_tls=settings.support_smtp_use_tls,
    )
    return SupportService(
        logs_dir=settings.support_logs_dir,
        email_config=email_config,
    )


def get_extract_preview_use_case() -> ExtractPreviewUseCase:
    return ExtractPreviewUseCase(preview_service=get_preview_service())


def get_export_excel_use_case() -> ExportExcelUseCase:
    return ExportExcelUseCase(export_service=get_export_service())


def get_submit_extract_support_use_case() -> SubmitExtractSupportUseCase:
    return SubmitExtractSupportUseCase(support_service=get_support_service())

