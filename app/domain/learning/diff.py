from __future__ import annotations

from dataclasses import dataclass

from app.schemas.row import MovementRow

EDITABLE_FIELDS = ("fecha", "descripcion", "debito", "credito", "saldo")


def is_empty(value: str | float | int | None) -> bool:
    return value is None or str(value).strip() == ""


def text_shortened(before: str | None, after: str | None) -> bool:
    if not before or not after:
        return False
    before_clean = before.strip()
    after_clean = after.strip()
    return len(after_clean) < len(before_clean) and before_clean.startswith(after_clean)


def text_changed_meaningfully(before: str | None, after: str | None) -> bool:
    before_value = (before or "").strip()
    after_value = (after or "").strip()
    return before_value != after_value


def numeric_changed(a: float | None, b: float | None) -> bool:
    return a != b


def amount_side_swapped(original_row: MovementRow, final_row: MovementRow) -> bool:
    return (
        original_row.debito is not None
        and final_row.credito == original_row.debito
        and final_row.debito in (None, 0)
    ) or (
        original_row.credito is not None
        and final_row.debito == original_row.credito
        and final_row.credito in (None, 0)
    )


@dataclass(slots=True)
class RowDiff:
    row_id: str
    original_row: MovementRow | None
    final_row: MovementRow | None
    changed_fields: list[str]
    is_added: bool
    is_deleted: bool
    page: int | None
    confidence_before: float | None
    issues_before: list[str]
    is_last_row_of_page_before: bool


def compute_row_diffs(rows_original: list[MovementRow], rows_final: list[MovementRow]) -> list[RowDiff]:
    original_by_id = {row.row_id: row for row in rows_original}
    final_by_id = {row.row_id: row for row in rows_final}
    last_rows_of_page = _find_last_rows_per_page(rows_original)

    diffs: list[RowDiff] = []
    all_row_ids = sorted(set(original_by_id.keys()) | set(final_by_id.keys()))
    for row_id in all_row_ids:
        original_row = original_by_id.get(row_id)
        final_row = final_by_id.get(row_id)

        is_added = original_row is None and final_row is not None
        is_deleted = original_row is not None and final_row is None

        changed_fields: list[str] = []
        if original_row is not None and final_row is not None:
            for field in EDITABLE_FIELDS:
                if getattr(original_row, field) != getattr(final_row, field):
                    changed_fields.append(field)

        if not changed_fields and not is_added and not is_deleted:
            continue

        page = (original_row.pagina if original_row is not None else None) or (
            final_row.pagina if final_row is not None else None
        )
        confidence_before = original_row.confianza if original_row is not None else None
        issues_before = list(original_row.issues) if original_row is not None else []

        diffs.append(
            RowDiff(
                row_id=row_id,
                original_row=original_row,
                final_row=final_row,
                changed_fields=changed_fields,
                is_added=is_added,
                is_deleted=is_deleted,
                page=page,
                confidence_before=confidence_before,
                issues_before=issues_before,
                is_last_row_of_page_before=row_id in last_rows_of_page,
            )
        )
    return diffs


def _find_last_rows_per_page(rows: list[MovementRow]) -> set[str]:
    last_by_page: dict[int, str] = {}
    for row in rows:
        if row.pagina is None:
            continue
        last_by_page[row.pagina] = row.row_id
    return set(last_by_page.values())


