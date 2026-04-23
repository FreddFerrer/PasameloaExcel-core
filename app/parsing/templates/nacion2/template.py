from __future__ import annotations

import json
import re
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


class Nacion2Template(ParsingTemplate):
    template_id = "nacion2"
    bank_hint = "BNA"
    priority = 944

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            self.config = {}

        self._secondary_markers = (
            "ULTIMOS MOVIMIENTOS",
            "FECHA COMPROBANTE CONCEPTO IMPORTE SALDO",
            "FECHA:",
            "SALDO ANTERIOR",
            "SALDO FINAL",
            "TOTAL GRAV. LEY 25413",
            "BANCO DE LA NACION ARGENTINA",
            "CUIT 30-50001091-2",
            "IVA RESPONSABLE INSCRIPTO",
        )
        self._day_month_re = re.compile(r"^\s*(\d{2}/\d{2})\b")
        self._year_re = re.compile(r"/\s*(\d{4})\b")
        self._comprob_re = re.compile(r"^\d{1,10}$")
        self._credit_keywords = (
            "CRED ",
            "CREDITO",
            "CR.",
            "DEBIN",
            "DEPOS",
            "ACRED",
            "LIQ",
            "TRF",
            "TRANSF",
        )
        self._debit_keywords = (
            "DEB.",
            "COMIS",
            "IVA",
            "RETEN",
            "GRAVAMEN",
            "REG. REC",
            "INTERES",
            "CANCEL",
            "PAGO",
        )

    def match_score(self, context: TemplateContext) -> float:
        first_page = self._normalize_match_text(context.first_page_text)
        score = 0.0
        if "ULTIMOSMOVIMIENTOS" in first_page:
            score += 0.65
        if "FECHACOMPROBANTECONCEPTOIMPORTESALDO" in first_page:
            score += 0.75
        if "BANCODELANACIONARGENTINA" in first_page:
            score += 0.1
        return min(score, 1.0)

    def is_footer_line(self, line: str) -> bool:
        upper = self._normalize_text(line)
        if super().is_footer_line(line):
            return True
        return any(marker in upper for marker in self._secondary_markers)

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        # Si ya viene una nueva fecha (incluso dd/mm sin año) arranca nueva fila.
        if self._day_month_re.match(candidate_line):
            return False
        clean = candidate_line.strip()
        if not clean:
            return False
        # En este layout casi todo lo que no sea nueva fecha/footers pertenece a la fila actual.
        return True

    def postprocess_rows(
        self,
        rows: list[ParsedMovement],
        traces: list[RowTrace],
        context: TemplateContext,
    ) -> None:
        filtered_rows: list[ParsedMovement] = []
        filtered_traces: list[RowTrace] = []
        prev_saldo: float | None = None

        for idx, row in enumerate(rows):
            trace = traces[idx] if idx < len(traces) else RowTrace(raw_preview=None, issues=[])
            parsed = self._parse_trace(trace)
            if parsed is None:
                continue

            fecha = parsed["fecha"]
            description = parsed["description"]
            movement = parsed["movement"]
            saldo = parsed["saldo"]

            debito, credito = self._resolve_sides(
                movement=movement,
                saldo=saldo,
                prev_saldo=prev_saldo,
                description=description,
            )

            row.fecha = fecha
            row.descripcion = description
            row.debito = debito
            row.credito = credito
            row.saldo = saldo

            if saldo is not None:
                prev_saldo = saldo

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

        score = 0.79
        if row.fecha and len(row.fecha) >= 8:
            score += 0.05
        if desc != "(sin descripcion)":
            score += 0.05
        else:
            score -= 0.25

        has_debito = row.debito is not None
        has_credito = row.credito is not None
        if has_debito and has_credito:
            score -= 0.06
        elif has_debito or has_credito:
            score += 0.04
        else:
            score -= 0.12

        if row.saldo is not None:
            score += 0.05
        else:
            score -= 0.12

        if "descripcion_multilinea" in trace.issues and len(desc.split()) >= 3:
            score += 0.02
        if self._contains_amount_token(desc):
            score -= 0.08
        if self._description_looks_truncated(desc):
            score -= 0.12

        return round(max(0.0, min(1.0, score)), 3)

    def _parse_trace(self, trace: RowTrace) -> dict | None:
        raw = trace.raw_preview or ""
        segments = [segment.strip() for segment in raw.split("|") if segment.strip()]
        if not segments:
            return None

        if any(self._looks_like_secondary_line(seg) for seg in segments):
            return None

        day_month: str | None = None
        year: str | None = None
        merged_text_parts: list[str] = []

        for seg in segments:
            if day_month is None:
                m_dm = self._day_month_re.match(seg)
                if m_dm:
                    day_month = m_dm.group(1)
            if year is None:
                m_y = self._year_re.search(seg)
                if m_y:
                    year = m_y.group(1)
            clean = self._strip_date_fragments(seg)
            if clean:
                merged_text_parts.append(clean)

        if not day_month:
            return None
        if not year:
            year = "2025"
        fecha = f"{day_month}/{year}"

        full_text = " ".join(merged_text_parts).strip()
        if not full_text:
            return None

        tokens = [token for token in full_text.split() if token != "$"]
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

        movement = amount_values[-2]
        saldo = amount_values[-1]

        first_amount_idx = amount_indices[0]
        comprob_idx: int | None = None
        if tokens and first_amount_idx > 0 and self._comprob_re.fullmatch(tokens[0]):
            # Caso habitual: COMPROB al inicio del registro.
            comprob_idx = 0
        else:
            # Caso alternativo: concepto parte en linea 1 y el COMPROB aparece
            # al comienzo de la linea 2 justo antes del importe.
            for idx in range(first_amount_idx - 1, -1, -1):
                token = tokens[idx]
                if not self._comprob_re.fullmatch(token):
                    continue
                comprob_idx = idx
                break

        description_tokens: list[str] = []
        amount_idx_set = set(amount_indices)
        for idx, token in enumerate(tokens):
            if idx in amount_idx_set:
                continue
            if comprob_idx is not None and idx == comprob_idx:
                continue
            description_tokens.append(token)

        description = " ".join(description_tokens).strip()
        if not description:
            description = "(sin descripcion)"
        if self._looks_like_secondary_line(description):
            return None

        return {
            "fecha": fecha,
            "description": description,
            "movement": movement,
            "saldo": saldo,
        }

    def _resolve_sides(
        self,
        *,
        movement: float,
        saldo: float,
        prev_saldo: float | None,
        description: str,
    ) -> tuple[float | None, float | None]:
        amount = abs(movement)
        if amount < 1e-9:
            return None, None
        if movement < 0:
            return amount, None

        if prev_saldo is not None:
            delta = saldo - prev_saldo
            if delta < -0.005:
                return amount, None
            if delta > 0.005:
                return None, amount

        side = self._infer_side_from_description(description)
        if side == "debito":
            return amount, None
        return None, amount

    def _infer_side_from_description(self, description: str) -> str:
        upper = self._normalize_text(description)
        if any(keyword in upper for keyword in self._debit_keywords):
            return "debito"
        if any(keyword in upper for keyword in self._credit_keywords):
            return "credito"
        return "debito"

    def _strip_date_fragments(self, text: str) -> str:
        out = text
        out = self._day_month_re.sub("", out, count=1).strip()
        out = re.sub(r"^/\s*\d{4}\b", "", out).strip()
        return out

    def _looks_like_secondary_line(self, text: str) -> bool:
        upper = self._normalize_text(text)
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
        upper = value.upper()
        replacements = str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN")
        return upper.translate(replacements)

    def _normalize_match_text(self, value: str) -> str:
        normalized = self._normalize_text(value)
        return re.sub(r"[^A-Z0-9]+", "", normalized)

