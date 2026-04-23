from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.parsing.contaapp_adapter import ContaAppParsingAdapter
from app.parsing.types import ParseExecution


class ParserService:
    def __init__(self, settings: Settings) -> None:
        self.adapter = ContaAppParsingAdapter(
            issue_row_confidence_threshold=settings.issue_row_confidence_threshold,
        )

    def parse_pdf(self, pdf_path: Path) -> ParseExecution:
        return self.adapter.parse(pdf_path)

