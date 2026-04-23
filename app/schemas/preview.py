from __future__ import annotations

from pydantic import BaseModel

from app.schemas.row import MovementRow


class PreviewSummary(BaseModel):
    total_rows: int
    low_confidence_rows: int
    rows_with_issues: int
    total_debito: float
    total_credito: float


class ExtractPreviewResponse(BaseModel):
    document_id: str
    filename: str
    bank_detected: str | None = None
    template_detected: str | None = None
    template_confidence: float = 0.0
    parse_status: str
    quality_flag: str | None = None
    support_recommended: bool = False
    quality_message: str | None = None
    low_confidence_ratio: float = 0.0
    summary: PreviewSummary
    rows: list[MovementRow]

