from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field
from pydantic import field_validator, model_validator

from app.domain.export.naming import DEFAULT_EXPORT_BASENAME, MAX_EXPORT_BASENAME_LENGTH
from app.schemas.learning import SummaryBefore
from app.schemas.row import MovementRow


class ChangeSetSummary(BaseModel):
    rows_edited: int = Field(default=0, validation_alias=AliasChoices("rows_edited", "rowsEdited"))
    rows_added: int = Field(default=0, validation_alias=AliasChoices("rows_added", "rowsAdded"))
    rows_deleted: int = Field(default=0, validation_alias=AliasChoices("rows_deleted", "rowsDeleted"))
    fields_corrected: dict[str, int] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("fields_corrected", "fieldsCorrected"),
    )
    error_patterns: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("error_patterns", "errorPatterns"),
    )


class ExportExcelRequest(BaseModel):
    document_id: str = Field(validation_alias=AliasChoices("document_id", "documentId"))
    session_id: str | None = Field(default=None, validation_alias=AliasChoices("session_id", "sessionId"))
    filename: str | None = None
    download_filename: str | None = Field(
        default=None,
        validation_alias=AliasChoices("download_filename", "downloadFilename"),
    )
    bank_detected: str | None = Field(default=None, validation_alias=AliasChoices("bank_detected", "bankDetected"))
    template_detected: str | None = Field(
        default=None,
        validation_alias=AliasChoices("template_detected", "templateDetected"),
    )
    template_confidence: float | None = Field(
        default=None,
        validation_alias=AliasChoices("template_confidence", "templateConfidence"),
    )
    parse_status: str | None = Field(default=None, validation_alias=AliasChoices("parse_status", "parseStatus"))
    summary_before: SummaryBefore | None = Field(
        default=None,
        validation_alias=AliasChoices("summary_before", "summaryBefore"),
    )
    rows_original: list[MovementRow] = Field(
        default_factory=list,
        validation_alias=AliasChoices("rows_original", "rowsOriginal"),
    )
    rows_final: list[MovementRow] = Field(
        default_factory=list,
        validation_alias=AliasChoices("rows_final", "rowsFinal"),
    )
    # Compatibilidad temporal con clientes que aun envian "rows".
    rows: list[MovementRow] = Field(default_factory=list, validation_alias=AliasChoices("rows"))
    change_set: ChangeSetSummary = Field(validation_alias=AliasChoices("change_set", "changeSet"))

    @field_validator("download_filename")
    @classmethod
    def validate_download_filename_max_length(cls, value: str | None) -> str | None:
        if value is None:
            return value
        raw = value.strip()
        base = Path(raw).stem if raw else DEFAULT_EXPORT_BASENAME
        normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in base)
        normalized = normalized.strip("_-") or DEFAULT_EXPORT_BASENAME
        if len(normalized) > MAX_EXPORT_BASENAME_LENGTH:
            raise ValueError(
                f"download_filename no puede superar {MAX_EXPORT_BASENAME_LENGTH} caracteres.",
            )
        return value

    @model_validator(mode="after")
    def ensure_rows_final(self) -> "ExportExcelRequest":
        if not self.rows_final and self.rows:
            self.rows_final = list(self.rows)
        if not self.rows_final:
            raise ValueError("rows_final no puede estar vacio.")
        return self

