from __future__ import annotations

from app.domain.learning.diff import (
    RowDiff,
    compute_row_diffs,
)
from app.schemas.row import MovementRow


class FeedbackDiffService:
    """
    Adapter de aplicación para el motor de diff de dominio.
    Mantiene el contrato actual del servicio para evitar romper integraciones.
    """

    def compute_diff(self, rows_original: list[MovementRow], rows_final: list[MovementRow]) -> list[RowDiff]:
        return compute_row_diffs(rows_original=rows_original, rows_final=rows_final)


