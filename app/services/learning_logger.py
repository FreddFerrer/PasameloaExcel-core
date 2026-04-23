from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.export import ExportExcelRequest
from app.schemas.learning import ClientChangeSet, DiffAudit, LearningEvent, SummaryBefore
from app.schemas.row import MovementRow
from app.services.feedback_classifier import FeedbackClassifier
from app.services.feedback_diff_service import FeedbackDiffService

logger = logging.getLogger(__name__)


class LearningLogger:
    """
    Captura evidencia estructurada de correcciones.

    Importante: no modifica templates ni reglas automaticamente.
    Cada exportacion se registra como observacion independiente para analisis manual posterior.
    """

    def __init__(
        self,
        logs_dir: Path,
        diff_service: FeedbackDiffService | None = None,
        classifier: FeedbackClassifier | None = None,
    ) -> None:
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.diff_service = diff_service or FeedbackDiffService()
        self.classifier = classifier or FeedbackClassifier()

    def log_export_feedback(self, request: ExportExcelRequest) -> LearningEvent:
        rows_original = request.rows_original
        rows_final = request.rows_final
        fallback_used = False

        if not rows_original and rows_final:
            # Fallback defensivo para evitar que toda la muestra quede marcada como "row_added"
            # cuando el cliente envia solo el snapshot final.
            rows_original = [row.model_copy(deep=True) for row in rows_final]
            fallback_used = True
            logger.warning(
                "learning_feedback: rows_original ausente para document_id=%s; usando fallback con snapshot final",
                request.document_id,
            )

        diff_audit = self._build_diff_audit(
            document_id=request.document_id,
            rows_original=rows_original,
            rows_final=rows_final,
        )

        diffs = self.diff_service.compute_diff(rows_original=rows_original, rows_final=rows_final)
        classified = self.classifier.classify(
            diffs=diffs,
            rows_final_count=len(rows_final),
            template_detected=request.template_detected,
        )
        logger.info(
            "learning_feedback_diff document_id=%s updated=%d deleted=%d added=%d",
            request.document_id,
            classified.summary_after.updated_rows_count,
            classified.summary_after.deleted_rows_count,
            classified.summary_after.added_rows_count,
        )

        event = LearningEvent(
            timestamp_utc=datetime.now(timezone.utc).replace(microsecond=0),
            document_id=request.document_id,
            session_id=request.session_id,
            template_detected=request.template_detected,
            template_confidence=request.template_confidence,
            bank_detected=request.bank_detected,
            parse_status=request.parse_status,
            summary_before=request.summary_before or self._build_summary_before(rows_original),
            summary_after=classified.summary_after,
            field_corrections=classified.field_corrections,
            change_patterns=classified.change_patterns,
            row_events=classified.row_events,
            client_change_set=ClientChangeSet(
                rows_edited=request.change_set.rows_edited,
                rows_added=request.change_set.rows_added,
                rows_deleted=request.change_set.rows_deleted,
                fields_corrected=dict(request.change_set.fields_corrected),
                error_patterns=list(request.change_set.error_patterns),
            ),
            diff_audit=diff_audit,
        )
        if fallback_used and "original_rows_missing_payload" not in event.change_patterns:
            event.change_patterns.append("original_rows_missing_payload")

        self._write_event(event)
        return event

    def _build_diff_audit(
        self,
        *,
        document_id: str,
        rows_original: list[MovementRow],
        rows_final: list[MovementRow],
    ) -> DiffAudit:
        original_ids = {row.row_id for row in rows_original}
        final_ids = {row.row_id for row in rows_final}
        matched_ids = original_ids & final_ids
        audit = DiffAudit(
            rows_original_count=len(rows_original),
            rows_final_count=len(rows_final),
            row_id_matches=len(matched_ids),
        )
        logger.info(
            "learning_feedback_trace document_id=%s rows_original=%d rows_final=%d row_id_matches=%d",
            document_id,
            audit.rows_original_count,
            audit.rows_final_count,
            audit.row_id_matches,
        )
        return audit

    def _build_summary_before(self, rows_original: list[MovementRow]) -> SummaryBefore:
        total_rows = len(rows_original)
        if not rows_original:
            return SummaryBefore(
                total_rows=0,
                low_confidence_rows=0,
                rows_with_issues=0,
                total_debito=0.0,
                total_credito=0.0,
                global_confidence=None,
            )

        low_confidence = sum(1 for row in rows_original if row.confianza is not None and row.confianza < 0.8)
        rows_with_issues = sum(1 for row in rows_original if row.issues)
        total_debito = round(sum((row.debito or 0.0) for row in rows_original), 2)
        total_credito = round(sum((row.credito or 0.0) for row in rows_original), 2)
        confidences = [row.confianza for row in rows_original if row.confianza is not None]
        global_confidence = round(sum(confidences) / len(confidences), 3) if confidences else None

        return SummaryBefore(
            total_rows=total_rows,
            low_confidence_rows=low_confidence,
            rows_with_issues=rows_with_issues,
            total_debito=total_debito,
            total_credito=total_credito,
            global_confidence=global_confidence,
        )

    def _write_event(self, event: LearningEvent) -> None:
        timestamp = event.timestamp_utc
        file_path = self.logs_dir / f"feedback-{timestamp:%Y%m%d}.jsonl"
        payload = event.model_dump(mode="json")
        payload["timestamp_utc"] = self._to_zulu_iso(event.timestamp_utc)
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _to_zulu_iso(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

