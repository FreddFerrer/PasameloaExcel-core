from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


class MovementRow(BaseModel):
    row_id: str = Field(validation_alias=AliasChoices("row_id", "rowId"))
    fecha: str | None = None
    descripcion: str
    debito: float | None = None
    credito: float | None = None
    saldo: float | None = None
    pagina: int | None = None
    confianza: float | None = None
    raw_preview: str | None = Field(default=None, validation_alias=AliasChoices("raw_preview", "rawPreview"))
    issues: list[str] = Field(default_factory=list)
