from __future__ import annotations

from dataclasses import dataclass

from app.domain.learning.diff import (
    RowDiff,
    amount_side_swapped,
    is_empty,
    numeric_changed,
    text_changed_meaningfully,
    text_shortened,
)
from app.schemas.learning import FieldCorrections, RowEvent, RowSignals, SummaryAfter


@dataclass(slots=True)
class ClassificationResult:
    summary_after: SummaryAfter
    field_corrections: FieldCorrections
    row_events: list[RowEvent]
    change_patterns: list[str]


def classify_feedback(
    *,
    diffs: list[RowDiff],
    rows_final_count: int,
    template_detected: str | None,
) -> ClassificationResult:
    row_events = [_classify_row(diff) for diff in diffs]
    field_corrections = _field_corrections(diffs)
    summary_after = _summary_after(diffs, rows_final_count)
    change_patterns = _document_patterns(row_events, template_detected=template_detected)

    return ClassificationResult(
        summary_after=summary_after,
        field_corrections=field_corrections,
        row_events=row_events,
        change_patterns=change_patterns,
    )


def _classify_row(diff: RowDiff) -> RowEvent:
    change_types: list[str] = []
    signals = RowSignals(
        row_added=diff.is_added or None,
        row_deleted=diff.is_deleted or None,
    )

    if diff.is_added:
        change_types.append("row_added")
        change_types.append("manual_row_added")
    elif diff.is_deleted:
        change_types.append("row_deleted")
    else:
        original = diff.original_row
        final = diff.final_row
        if original is None or final is None:
            return _build_row_event(diff, change_types, signals)

        if "descripcion" in diff.changed_fields:
            before_desc = original.descripcion
            after_desc = final.descripcion
            before_empty = is_empty(before_desc)
            after_empty = is_empty(after_desc)
            before_len = len((before_desc or "").strip())
            after_len = len((after_desc or "").strip())
            signals.description_before_empty = before_empty
            signals.description_after_empty = after_empty
            signals.description_shortened = text_shortened(before_desc, after_desc) or None
            signals.description_text_added = (after_len > before_len) or None
            signals.description_text_removed = (after_len < before_len) or None

            if before_empty and not after_empty:
                change_types.append("descripcion_filled_when_empty")
            elif not before_empty and after_empty:
                change_types.append("descripcion_cleared")
            elif text_shortened(before_desc, after_desc):
                change_types.append("descripcion_trimmed")
            elif after_len > before_len and text_changed_meaningfully(before_desc, after_desc):
                change_types.append("descripcion_extended")
                change_types.append("descripcion_rewritten")
            elif text_changed_meaningfully(before_desc, after_desc):
                change_types.append("descripcion_rewritten")

            footer_issues = {"footer_like_text_detected", "footer", "footer_marker_detected"}
            footer_removed = any(issue in footer_issues for issue in diff.issues_before) and not any(
                issue in (final.issues or []) for issue in footer_issues
            )
            signals.footer_marker_removed = footer_removed or None

        if "fecha" in diff.changed_fields:
            if is_empty(original.fecha) and not is_empty(final.fecha):
                change_types.append("fecha_filled_when_empty")
            elif text_changed_meaningfully(original.fecha, final.fecha):
                change_types.append("fecha_corrected")

        debit_changed = numeric_changed(original.debito, final.debito)
        credit_changed = numeric_changed(original.credito, final.credito)
        saldo_changed = numeric_changed(original.saldo, final.saldo)
        signals.debit_changed = debit_changed or None
        signals.credit_changed = credit_changed or None
        signals.saldo_changed = saldo_changed or None

        if amount_side_swapped(original, final):
            change_types.append("amount_side_swapped")

        if "debito" in diff.changed_fields and is_empty(original.debito) and not is_empty(final.debito):
            change_types.append("debito_filled_when_empty")

        if "credito" in diff.changed_fields and is_empty(original.credito) and not is_empty(final.credito):
            change_types.append("credito_filled_when_empty")

        if (
            ("debito" in diff.changed_fields or "credito" in diff.changed_fields)
            and "amount_side_swapped" not in change_types
            and (debit_changed or credit_changed)
        ):
            change_types.append("amount_value_corrected")

        if "saldo" in diff.changed_fields:
            if is_empty(original.saldo) and not is_empty(final.saldo):
                change_types.append("saldo_filled_when_empty")
            elif saldo_changed:
                change_types.append("saldo_corrected")

    change_types = sorted(set(change_types))
    return _build_row_event(diff, change_types, signals)


def _build_row_event(diff: RowDiff, change_types: list[str], signals: RowSignals) -> RowEvent:
    return RowEvent(
        row_id=diff.row_id,
        page=diff.page,
        confidence_before=diff.confidence_before,
        issues_before=diff.issues_before,
        changed_fields=diff.changed_fields,
        change_types=change_types,
        signals=signals,
    )


def _field_corrections(diffs: list[RowDiff]) -> FieldCorrections:
    values = FieldCorrections()
    for diff in diffs:
        for field in diff.changed_fields:
            if field in {"fecha", "descripcion", "debito", "credito", "saldo"}:
                setattr(values, field, getattr(values, field) + 1)
    return values


def _summary_after(diffs: list[RowDiff], rows_final_count: int) -> SummaryAfter:
    deleted_rows = sum(1 for diff in diffs if diff.is_deleted)
    added_rows = sum(1 for diff in diffs if diff.is_added)
    updated_rows = sum(1 for diff in diffs if diff.changed_fields)
    return SummaryAfter(
        total_rows=rows_final_count,
        updated_rows_count=updated_rows,
        deleted_rows_count=deleted_rows,
        added_rows_count=added_rows,
    )


def _document_patterns(row_events: list[RowEvent], template_detected: str | None) -> list[str]:
    patterns: set[str] = set()
    template_is_comprobante_like = bool(
        template_detected
        and any(marker in template_detected.lower() for marker in ("resumen", "cta", "mensual", "nbch", "nacion"))
    )

    for event in row_events:
        change_types = set(event.change_types)
        issues_before = set(event.issues_before)
        signals = event.signals

        if "descripcion_filled_when_empty" in change_types and "descripcion_vacia" in issues_before:
            if template_is_comprobante_like:
                patterns.add("missing_description_when_comprobante_nonzero")

        if "descripcion_trimmed" in change_types:
            footer_markers = {
                "footer_like_text_detected",
                "footer",
                "footer_marker_detected",
            }
            if issues_before & footer_markers or signals.footer_marker_removed:
                patterns.add("footer_absorbed_into_description")

            next_page_header_markers = {
                "next_page_header_detected",
                "next_page_header_like_text",
                "header_like_text_detected",
            }
            if issues_before & next_page_header_markers:
                patterns.add("next_page_header_absorbed_into_description")

        if "saldo_filled_when_empty" in change_types:
            patterns.add("saldo_missing")

        if "amount_side_swapped" in change_types:
            patterns.add("debit_credit_swapped")

        if "row_added" in change_types:
            patterns.add("parser_missed_row")

        if "row_deleted" in change_types:
            low_confidence = event.confidence_before is not None and event.confidence_before < 0.75
            noisy_row = len(event.issues_before) >= 2
            if low_confidence or noisy_row:
                patterns.add("false_positive_row")

    return sorted(patterns)


