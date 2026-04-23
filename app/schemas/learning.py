from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field


class SummaryBefore(BaseModel):
    total_rows: int = Field(validation_alias=AliasChoices("total_rows", "totalRows"))
    low_confidence_rows: int = Field(
        validation_alias=AliasChoices("low_confidence_rows", "lowConfidenceRows")
    )
    rows_with_issues: int = Field(validation_alias=AliasChoices("rows_with_issues", "rowsWithIssues"))
    total_debito: float | None = Field(default=None, validation_alias=AliasChoices("total_debito", "totalDebito"))
    total_credito: float | None = Field(default=None, validation_alias=AliasChoices("total_credito", "totalCredito"))
    global_confidence: float | None = Field(
        default=None,
        validation_alias=AliasChoices("global_confidence", "globalConfidence"),
    )


class SummaryAfter(BaseModel):
    total_rows: int
    updated_rows_count: int
    deleted_rows_count: int
    added_rows_count: int


class FieldCorrections(BaseModel):
    fecha: int = 0
    descripcion: int = 0
    debito: int = 0
    credito: int = 0
    saldo: int = 0


class RowSignals(BaseModel):
    description_before_empty: bool | None = None
    description_after_empty: bool | None = None
    description_shortened: bool | None = None
    description_text_added: bool | None = None
    description_text_removed: bool | None = None
    footer_marker_removed: bool | None = None
    debit_changed: bool | None = None
    credit_changed: bool | None = None
    saldo_changed: bool | None = None
    row_deleted: bool | None = None
    row_added: bool | None = None


class RowEvent(BaseModel):
    row_id: str
    page: int | None = None
    confidence_before: float | None = None
    issues_before: list[str] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
    change_types: list[str] = Field(default_factory=list)
    signals: RowSignals = Field(default_factory=RowSignals)


class PrivacyInfo(BaseModel):
    raw_pdf_stored: bool = False
    raw_rows_stored: bool = False
    full_cell_values_stored: bool = False


class ClientChangeSet(BaseModel):
    rows_edited: int = 0
    rows_added: int = 0
    rows_deleted: int = 0
    fields_corrected: dict[str, int] = Field(default_factory=dict)
    error_patterns: list[str] = Field(default_factory=list)


class DiffAudit(BaseModel):
    rows_original_count: int = 0
    rows_final_count: int = 0
    row_id_matches: int = 0


class LearningEvent(BaseModel):
    event_type: Literal["export_confirmed"] = "export_confirmed"
    event_version: int = 1
    timestamp_utc: datetime
    document_id: str
    session_id: str | None = None
    template_detected: str | None = None
    template_confidence: float | None = None
    bank_detected: str | None = None
    parse_status: str | None = None
    summary_before: SummaryBefore
    summary_after: SummaryAfter
    field_corrections: FieldCorrections
    change_patterns: list[str] = Field(default_factory=list)
    row_events: list[RowEvent] = Field(default_factory=list)
    client_change_set: ClientChangeSet = Field(default_factory=ClientChangeSet)
    diff_audit: DiffAudit = Field(default_factory=DiffAudit)
    privacy: PrivacyInfo = Field(default_factory=PrivacyInfo)
