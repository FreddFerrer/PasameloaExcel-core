from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


class Nbch2Template(ParsingTemplate):
    template_id = "nbch2"
    bank_hint = "NBCH"
    priority = 947

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            self.config = {}

        self._date_prefix_re = re.compile(r"^\s*\d{2}/\d{2}/\d{4}\s+")
        self._comprob_re = re.compile(r"^\d{5,12}$")
        self._secondary_markers = (
            "ULTIMOS MOVIMIENTOS",
            "ARCHIVO GENERADO",
            "BUSQUEDA POR:",
            "FECHA MONTO N DE COMPROBANTE DESCRIPCION SALDO",
            "PAGINA ",
        )

    def match_score(self, context: TemplateContext) -> float:
        first_page = self._normalize_match_text(context.first_page_text)
        file_stem = self._normalize_match_text(context.file_stem)
        score = 0.0
        if "ULTIMOSMOVIMIENTOS" in first_page:
            score += 0.4
        if "FECHAMONTO" in first_page and "NDECOMPROBANTE" in first_page and "DESCRIPCION" in first_page:
            score += 0.55
        if "FECHAMONTONDECOMPROBANTEDESCRIPCIONSALDO" in first_page:
            score += 0.2
        if "DEBITOSYCREDITOS" in first_page:
            score += 0.12
        if "NBCH" in file_stem:
            score += 0.08
        if "NUEVOBANCODELCHACO" in first_page:
            score += 0.2
        return min(score, 1.0)

    def is_footer_line(self, line: str) -> bool:
        if super().is_footer_line(line):
            return True
        upper = self._normalize_match_text(line)
        return any(marker in upper for marker in self._secondary_markers)

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        if re.match(r"^\s*\d{2}/\d{2}/\d{4}\b", candidate_line):
            return False
        return bool(candidate_line.strip())

    def postprocess_rows(
        self,
        rows: list[ParsedMovement],
        traces: list[RowTrace],
        context: TemplateContext,
    ) -> None:
        filtered_rows: list[ParsedMovement] = []
        filtered_traces: list[RowTrace] = []

        for idx, row in enumerate(rows):
            trace = traces[idx] if idx < len(traces) else RowTrace(raw_preview=None, issues=[])
            parsed = self._parse_trace(trace)
            if parsed is None:
                continue

            row.fecha = parsed["fecha"]
            row.descripcion = parsed["description"]
            row.debito = parsed["debito"]
            row.credito = parsed["credito"]
            row.saldo = parsed["saldo"]

            filtered_rows.append(row)
            filtered_traces.append(trace)

        rows[:] = filtered_rows
        traces[:] = filtered_traces

    def compute_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float | None:
        desc = (row.descripcion or "").strip()
        if not desc:
            return 0.45

        # Calibracion para que filas limpias de este layout queden altas,
        # manteniendo penalizaciones fuertes ante ruido real.
        score = 0.84
        if row.fecha:
            score += 0.05
        if row.saldo is not None:
            score += 0.02
        else:
            score -= 0.16

        has_debito = row.debito is not None
        has_credito = row.credito is not None
        if has_debito ^ has_credito:
            score += 0.02
        elif has_debito and has_credito:
            score -= 0.08
        else:
            score -= 0.16

        if desc != "(sin descripcion)":
            score += 0.02
        if len(desc.split()) >= 2:
            score += 0.02
        if "descripcion_multilinea" in trace.issues:
            score += 0.01

        if not self._contains_amount_token(desc):
            score += 0.01
        else:
            score -= 0.14

        if self._description_looks_truncated(desc):
            score -= 0.14
        else:
            score += 0.01

        return round(max(0.0, min(1.0, score)), 3)

    def _parse_trace(self, trace: RowTrace) -> dict | None:
        raw = trace.raw_preview or ""
        segments = [segment.strip() for segment in raw.split("|") if segment.strip()]
        if not segments:
            return None

        usable = [seg for seg in segments if not self._looks_like_secondary_line(seg)]
        if not usable:
            return None

        full_text = " ".join(usable).strip()
        if not full_text:
            return None

        m_date = re.match(r"^\s*(\d{2}/\d{2}/\d{4})\b", full_text)
        if not m_date:
            return None
        fecha = m_date.group(1)

        content = self._date_prefix_re.sub("", full_text).strip()
        tokens = [token for token in content.split() if token != "$"]
        if not tokens:
            return None

        amount_indices: list[int] = []
        amount_values: list[float] = []
        for idx, token in enumerate(tokens):
            if not self._is_amount_token(token):
                continue
            parsed = self._parse_amount_token(token)
            if parsed is None:
                continue
            amount_indices.append(idx)
            amount_values.append(parsed)

        if len(amount_values) < 2:
            return None

        movement_idx = amount_indices[0]
        saldo_idx = amount_indices[-1]
        movement = amount_values[0]
        saldo = amount_values[-1]

        comprob_idx: int | None = None
        comprob_candidate_idx = movement_idx + 1
        if comprob_candidate_idx < saldo_idx and self._comprob_re.fullmatch(tokens[comprob_candidate_idx]):
            comprob_idx = comprob_candidate_idx

        description_tokens: list[str] = []
        for idx, token in enumerate(tokens):
            if idx <= movement_idx:
                continue
            if idx >= saldo_idx:
                continue
            if comprob_idx is not None and idx == comprob_idx:
                continue
            description_tokens.append(token)

        description = " ".join(description_tokens).strip()
        if not description:
            description = "(sin descripcion)"

        amount = abs(movement)
        debito: float | None
        credito: float | None
        if movement < 0:
            debito, credito = amount, None
        elif movement > 0:
            debito, credito = None, amount
        else:
            debito, credito = None, None

        return {
            "fecha": fecha,
            "description": description,
            "debito": debito,
            "credito": credito,
            "saldo": saldo,
        }

    def _looks_like_secondary_line(self, text: str) -> bool:
        upper = self._normalize_match_text(text)
        return any(marker in upper for marker in self._secondary_markers)

    def _contains_amount_token(self, text: str) -> bool:
        return any(self._is_amount_token(token) for token in text.split())

    def _description_looks_truncated(self, description: str) -> bool:
        tokens = description.split()
        if not tokens:
            return False
        last = tokens[-1]
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", last):
            return True
        return description.endswith(("-", "/", ":"))

    def _is_amount_token(self, token: str) -> bool:
        candidate = token.strip().replace("$", "").replace("−", "-")
        if not candidate:
            return False
        return (
            re.fullmatch(r"-?\d+(?:[.,]\d{2})-?", candidate) is not None
            or re.fullmatch(r"-?\d{1,3}(?:[.,]\d{3})+[.,]\d{2}-?", candidate) is not None
        )

    def _parse_amount_token(self, token: str) -> float | None:
        candidate = token.strip().replace("$", "").replace("−", "-")
        if not candidate or not self._is_amount_token(candidate):
            return None

        sign = 1.0
        if candidate.endswith("-"):
            sign = -1.0
            candidate = candidate[:-1]
        if candidate.startswith("-"):
            sign = -1.0
            candidate = candidate[1:]

        candidate = self._normalize_numeric_token(candidate)
        try:
            return sign * float(candidate)
        except ValueError:
            return None

    def _normalize_numeric_token(self, candidate: str) -> str:
        raw = candidate.strip()
        if "," in raw and "." in raw:
            if raw.rfind(",") > raw.rfind("."):
                return raw.replace(".", "").replace(",", ".")
            return raw.replace(",", "")
        if "," in raw:
            return raw.replace(".", "").replace(",", ".")
        if "." in raw:
            parts = raw.split(".")
            if len(parts) > 2:
                return "".join(parts)
            decimals = parts[-1]
            if len(decimals) in (1, 2):
                return raw
            return raw.replace(".", "")
        return raw

    def _normalize_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        return ascii_only.upper()

    def _normalize_match_text(self, value: str) -> str:
        normalized = self._normalize_text(value)
        return re.sub(r"[^A-Z0-9]+", "", normalized)


