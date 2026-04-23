from __future__ import annotations

from abc import ABC, abstractmethod

from app.parsing.types import CandidateRow, ParsedMovement, RowTrace, TemplateContext


class ParsingTemplate(ABC):
    template_id: str
    bank_hint: str | None = None
    priority: int = 100

    @abstractmethod
    def match_score(self, context: TemplateContext) -> float:
        """Return score in [0,1]. 0 means no match."""

    def is_footer_line(self, line: str) -> bool:
        markers = (
            "TOTAL ",
            "PERIODO COMPRENDIDO",
            "RETENCION",
            "COMPUTABLE",
            "SALDO AL ",
            "RESUMEN",
        )
        upper = line.upper()
        return any(marker in upper for marker in markers)

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        """Hook for template-specific multiline grouping."""
        return False

    def collect_candidates(self, pages: list[dict], context: TemplateContext) -> list[CandidateRow] | None:
        """
        Hook opcional para templates con layouts no compatibles con la
        agrupacion default (fecha al inicio de cada fila).
        Si retorna None, el adapter usa el colector generico.
        """
        return None

    def postprocess_rows(
        self,
        rows: list[ParsedMovement],
        traces: list[RowTrace],
        context: TemplateContext,
    ) -> None:
        """Template-specific cleanup after generic row parsing."""
        return None

    def adjust_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float:
        """
        Retorna un delta de confianza para la fila (puede ser positivo o negativo).
        El adapter aplica el delta despues del postproceso y limita el resultado a [0, 1].
        """
        return 0.0

    def compute_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float | None:
        """
        Override opcional de confianza final por template.
        Si devuelve None, el adapter mantiene el mecanismo legacy por delta.
        """
        return None

