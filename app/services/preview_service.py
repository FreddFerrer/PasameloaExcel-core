from __future__ import annotations

import logging
import uuid
from pathlib import Path
from time import perf_counter

from app.domain.preview import build_preview_projection
from app.schemas.preview import ExtractPreviewResponse
from app.services.parser_service import ParserService

logger = logging.getLogger(__name__)


class PreviewService:
    SUPPORT_CONFIDENCE_THRESHOLD = 0.96
    SUPPORT_LOW_CONF_RATIO_TRIGGER = 0.30

    def __init__(self, parser_service: ParserService, working_temp_dir: Path) -> None:
        self.parser_service = parser_service
        self.working_temp_dir = working_temp_dir

    def extract_preview(self, *, pdf_bytes: bytes, filename: str) -> ExtractPreviewResponse:
        if not pdf_bytes:
            raise ValueError("El PDF recibido esta vacio.")

        started_at = perf_counter()
        temp_path = self._write_temp_pdf(pdf_bytes)
        try:
            execution = self.parser_service.parse_pdf(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        projection = build_preview_projection(
            execution,
            support_confidence_threshold=self.SUPPORT_CONFIDENCE_THRESHOLD,
            support_low_conf_ratio_trigger=self.SUPPORT_LOW_CONF_RATIO_TRIGGER,
        )

        elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.info(
            "extract_preview completed filename=%s parser_mode=%s template_matched=%s "
            "template_confidence=%.3f bank=%s status=%s rows=%d low_conf=%d issues=%d elapsed_ms=%s",
            filename,
            execution.parser_mode,
            execution.template_detected or "unknown",
            execution.template_confidence,
            execution.bank_detected or "unknown",
            execution.parse_status,
            len(projection.rows),
            projection.summary.low_confidence_rows,
            projection.summary.rows_with_issues,
            elapsed_ms,
        )
        if projection.support_recommended:
            logger.warning(
                "extract_preview support_recommended filename=%s template=%s low_confidence_ratio=%.4f "
                "threshold_ratio=%.2f confidence_threshold=%.2f",
                filename,
                execution.template_detected or "unknown",
                projection.low_confidence_ratio,
                self.SUPPORT_LOW_CONF_RATIO_TRIGGER,
                self.SUPPORT_CONFIDENCE_THRESHOLD,
            )

        return ExtractPreviewResponse(
            document_id=str(uuid.uuid4()),
            filename=filename,
            bank_detected=execution.bank_detected,
            template_detected=execution.template_detected,
            template_confidence=execution.template_confidence,
            parse_status=execution.parse_status,
            quality_flag=projection.quality_flag,
            support_recommended=projection.support_recommended,
            quality_message=projection.quality_message,
            low_confidence_ratio=projection.low_confidence_ratio,
            summary=projection.summary,
            rows=projection.rows,
        )

    def _write_temp_pdf(self, payload: bytes) -> Path:
        self.working_temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.working_temp_dir / f"upload_{uuid.uuid4().hex}.pdf"
        file_path.write_bytes(payload)
        return file_path

