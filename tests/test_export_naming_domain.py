from __future__ import annotations

from datetime import datetime

from app.domain.export import build_export_filename
from app.domain.export.naming import MAX_EXPORT_BASENAME_LENGTH


def test_build_export_filename_sanitizes_name_and_adds_timestamp() -> None:
    value = build_export_filename("extracto enero 2026.pdf", now=datetime(2026, 1, 3, 4, 5, 6))
    assert value == "extracto_enero_2026_20260103_040506.xlsx"


def test_build_export_filename_uses_default_base_when_name_is_missing() -> None:
    value = build_export_filename(None, now=datetime(2026, 1, 3, 4, 5, 6))
    assert value == "movimientos_20260103_040506.xlsx"


def test_build_export_filename_can_skip_timestamp_for_custom_download_name() -> None:
    value = build_export_filename(
        "mi descarga personalizada.pdf",
        now=datetime(2026, 1, 3, 4, 5, 6),
        append_timestamp=False,
    )
    assert value == "mi_descarga_personalizada.xlsx"


def test_build_export_filename_enforces_max_length_and_fixed_extension() -> None:
    raw_name = ("A" * 200) + ".pdf"
    value = build_export_filename(raw_name, now=datetime(2026, 1, 3, 4, 5, 6))
    expected_base = "A" * MAX_EXPORT_BASENAME_LENGTH
    assert value == f"{expected_base}_20260103_040506.xlsx"


