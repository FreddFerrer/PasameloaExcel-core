from __future__ import annotations

from app.schemas.preview import ExtractPreviewResponse
from app.services.preview_service import PreviewService


class ExtractPreviewUseCase:
    def __init__(self, preview_service: PreviewService) -> None:
        self.preview_service = preview_service

    def execute(self, *, pdf_bytes: bytes, filename: str) -> ExtractPreviewResponse:
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Solo se admiten archivos PDF.")
        return self.preview_service.extract_preview(pdf_bytes=pdf_bytes, filename=filename)


