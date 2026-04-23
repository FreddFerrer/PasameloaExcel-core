from __future__ import annotations

from datetime import datetime
from pathlib import Path

DEFAULT_EXPORT_BASENAME = "movimientos"
MAX_EXPORT_BASENAME_LENGTH = 80


def _normalize_export_basename(raw_name: str | None) -> str:
    base = DEFAULT_EXPORT_BASENAME
    if raw_name and raw_name.strip():
        base = Path(raw_name.strip()).stem or DEFAULT_EXPORT_BASENAME
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in base)
    normalized = normalized.strip("_-")
    if not normalized:
        normalized = DEFAULT_EXPORT_BASENAME
    return normalized[:MAX_EXPORT_BASENAME_LENGTH]


def build_export_filename(raw_name: str | None, *, now: datetime, append_timestamp: bool = True) -> str:
    normalized = _normalize_export_basename(raw_name)
    if not append_timestamp:
        return f"{normalized}.xlsx"
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    return f"{normalized}_{timestamp}.xlsx"
