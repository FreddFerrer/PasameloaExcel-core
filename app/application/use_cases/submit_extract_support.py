from __future__ import annotations

import json

from app.schemas.support import SupportSubmissionResponse
from app.services.support_service import SupportService


class SubmitExtractSupportUseCase:
    def __init__(self, support_service: SupportService) -> None:
        self.support_service = support_service

    def execute(
        self,
        *,
        pdf_bytes: bytes,
        filename: str,
        preview_json: str,
        session_id: str | None = None,
        user_note: str | None = None,
    ) -> SupportSubmissionResponse:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Solo se admiten archivos PDF.")

        try:
            preview_payload = json.loads(preview_json)
        except json.JSONDecodeError as exc:
            raise ValueError("preview_json no es un JSON valido.") from exc

        return self.support_service.submit_extract_support(
            pdf_bytes=pdf_bytes,
            filename=filename,
            preview_payload=preview_payload,
            user_note=user_note,
            session_id=session_id,
        )


