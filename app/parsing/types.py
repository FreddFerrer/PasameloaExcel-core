from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ParsedMovement:
    fecha: str | None
    descripcion: str
    debito: float | None
    credito: float | None
    saldo: float | None
    pagina: int | None
    confianza: float
    confianza_campos: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RowTrace:
    raw_preview: str | None
    issues: list[str]


@dataclass(slots=True)
class ParseExecution:
    rows: list[ParsedMovement]
    bank_detected: str | None
    template_detected: str | None
    template_confidence: float
    parser_mode: str
    parse_status: str
    global_confidence: float
    field_confidence: dict[str, float]
    row_traces: list[RowTrace]


@dataclass(slots=True)
class CandidateRow:
    page: int
    raw_text: str
    line_count: int


@dataclass(slots=True)
class TemplateContext:
    pdf_path: Path
    pages: list[dict]
    file_stem: str
    first_page_text: str
