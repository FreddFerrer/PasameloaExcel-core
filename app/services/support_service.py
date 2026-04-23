from __future__ import annotations

import hashlib
import json
import logging
import smtplib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from app.schemas.preview import ExtractPreviewResponse
from app.schemas.support import SupportSubmissionResponse

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SupportEmailConfig:
    enabled: bool
    to_address: str | None
    from_address: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool = True


class SupportService:
    """Recibe extractos reportados y captura evidencia para mejora manual de templates."""

    def __init__(self, logs_dir: Path, email_config: SupportEmailConfig) -> None:
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.email_config = email_config

    def submit_extract_support(
        self,
        *,
        pdf_bytes: bytes,
        filename: str,
        preview_payload: dict,
        user_note: str | None = None,
        session_id: str | None = None,
    ) -> SupportSubmissionResponse:
        if not pdf_bytes:
            raise ValueError("El PDF recibido esta vacio.")

        preview = ExtractPreviewResponse.model_validate(preview_payload)
        ticket_id = f"supp_{uuid.uuid4().hex[:10]}"
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
        pdf_hash_prefix = hashlib.sha256(pdf_bytes).hexdigest()[:16]

        event = {
            "event_type": "support_submission",
            "event_version": 1,
            "timestamp_utc": self._to_zulu_iso(timestamp),
            "ticket_id": ticket_id,
            "session_id": session_id,
            "document_id": preview.document_id,
            "filename": filename,
            "pdf_bytes": len(pdf_bytes),
            "pdf_sha256_prefix": pdf_hash_prefix,
            "template_detected": preview.template_detected,
            "template_confidence": preview.template_confidence,
            "bank_detected": preview.bank_detected,
            "parse_status": preview.parse_status,
            "quality_flag": preview.quality_flag,
            "support_recommended": preview.support_recommended,
            "low_confidence_ratio": preview.low_confidence_ratio,
            "summary": preview.summary.model_dump(mode="json"),
            "user_note": (user_note or "").strip() or None,
            "privacy": {
                "raw_pdf_stored": False,
                "raw_rows_stored": False,
                "full_cell_values_stored": False,
            },
        }

        forwarded_channel = "backend_log_only"
        if self._can_send_email():
            forwarded_channel = self._send_support_email(
                ticket_id=ticket_id,
                filename=filename,
                pdf_bytes=pdf_bytes,
                preview=preview,
                user_note=user_note,
                event=event,
            )

        event["forwarded_channel"] = forwarded_channel
        self._write_event(event)

        logger.info(
            "support_submission ticket_id=%s filename=%s template=%s support_recommended=%s channel=%s",
            ticket_id,
            filename,
            preview.template_detected or "unknown",
            preview.support_recommended,
            forwarded_channel,
        )

        return SupportSubmissionResponse(
            ticket_id=ticket_id,
            status="received",
            message="Soporte recibio tu extracto. Gracias por ayudar a mejorar PasameloaExcel.",
            forwarded_channel=forwarded_channel,
        )

    def _can_send_email(self) -> bool:
        cfg = self.email_config
        return bool(
            cfg.enabled
            and cfg.to_address
            and cfg.from_address
            and cfg.smtp_host
        )

    def _send_support_email(
        self,
        *,
        ticket_id: str,
        filename: str,
        pdf_bytes: bytes,
        preview: ExtractPreviewResponse,
        user_note: str | None,
        event: dict,
    ) -> str:
        cfg = self.email_config
        assert cfg.to_address and cfg.from_address and cfg.smtp_host

        message = EmailMessage()
        message["Subject"] = f"[PasameloaExcel][Support] {ticket_id} - {filename}"
        message["From"] = cfg.from_address
        message["To"] = cfg.to_address
        message.set_content(
            "Se recibio un extracto para mejorar templates.\n\n"
            f"ticket_id: {ticket_id}\n"
            f"document_id: {preview.document_id}\n"
            f"template_detected: {preview.template_detected}\n"
            f"support_recommended: {preview.support_recommended}\n"
            f"low_confidence_ratio: {preview.low_confidence_ratio}\n"
            f"user_note: {(user_note or '').strip() or 'N/A'}\n"
        )

        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=filename,
        )
        preview_json = json.dumps(preview.model_dump(mode="json"), ensure_ascii=False, indent=2).encode("utf-8")
        message.add_attachment(
            preview_json,
            maintype="application",
            subtype="json",
            filename=f"{ticket_id}_preview.json",
        )
        event_json = json.dumps(event, ensure_ascii=False, indent=2).encode("utf-8")
        message.add_attachment(
            event_json,
            maintype="application",
            subtype="json",
            filename=f"{ticket_id}_event.json",
        )

        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as smtp:
                if cfg.smtp_use_tls:
                    smtp.starttls()
                if cfg.smtp_username and cfg.smtp_password:
                    smtp.login(cfg.smtp_username, cfg.smtp_password)
                smtp.send_message(message)
            return "email"
        except Exception:
            logger.exception("support_submission email_forward_failed ticket_id=%s", ticket_id)
            return "backend_log_only"

    def _write_event(self, event: dict) -> None:
        timestamp = datetime.now(timezone.utc)
        file_path = self.logs_dir / f"support-submissions-{timestamp:%Y%m%d}.jsonl"
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _to_zulu_iso(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

