from __future__ import annotations

from app.domain.learning.classification import ClassificationResult, classify_feedback
from app.domain.learning.diff import RowDiff


class FeedbackClassifier:
    """
    Adapter de aplicación para el clasificador de dominio.
    Mantiene la interfaz existente del servicio.
    """

    def classify(
        self,
        *,
        diffs: list[RowDiff],
        rows_final_count: int,
        template_detected: str | None,
    ) -> ClassificationResult:
        return classify_feedback(
            diffs=diffs,
            rows_final_count=rows_final_count,
            template_detected=template_detected,
        )



