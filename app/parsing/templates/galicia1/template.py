from __future__ import annotations

import json
import re
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


class Galicia1Template(ParsingTemplate):
    template_id = "galicia1"
    bank_hint = "GALICIA"
    priority = 950

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            self.config = {}

        rules = self.config.get("description_rules", {})
        self._trailing_code_re = re.compile(rules.get("strip_trailing_code_pattern", r"\s+[0-9]{2}[A-Z0-9]{2,}$"))
        min_digits = int(rules.get("comprobante_digits_min", 8))
        max_digits = int(rules.get("comprobante_digits_max", 10))
        self._trailing_comprobante_re = re.compile(rf"\s+\d{{{min_digits},{max_digits}}}$")
        prefixes = rules.get("continuation_prefixes") or ["ORIGEN:"]
        self._continuation_prefixes = [str(prefix).strip().upper() for prefix in prefixes if str(prefix).strip()]
        static_tokens = rules.get("continuation_static_tokens") or ["VARIOS", "CUOTA"]
        self._continuation_static_tokens = {str(token).strip().upper() for token in static_tokens if str(token).strip()}

    def match_score(self, context: TemplateContext) -> float:
        file_stem = self._normalize_text(context.file_stem)
        first_page = self._normalize_text(context.first_page_text)

        score = 0.0
        if "GALICIA" in file_stem:
            score += 0.6
        if "BANCO GALICIA" in first_page:
            score += 0.5
        if "FECHA DESCRIPCION ORIGEN CREDITO DEBITO SALDO" in first_page:
            score += 0.7
        if "RESUMEN DE CUENTA CORRIENTE EN PESOS" in first_page:
            score += 0.2
        return min(score, 1.0)

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        if re.match(r"^\s*\d{2}/\d{2}/\d{2,4}\b", candidate_line):
            return False

        candidate = candidate_line.strip()
        if not candidate:
            return False
        upper = candidate.upper()
        if any(upper.startswith(prefix) for prefix in self._continuation_prefixes):
            return True
        if upper in self._continuation_static_tokens:
            return True
        if re.fullmatch(r"\d{8,}", candidate):
            return True
        # Regla flexible: cualquier linea textual sin montos se considera
        # continuacion valida para descripcion en galicia1.
        if re.search(r"[A-Z]", upper) and not self._contains_amount_token(candidate):
            return True
        return False

    def postprocess_rows(
        self,
        rows: list[ParsedMovement],
        traces: list[RowTrace],
        context: TemplateContext,
    ) -> None:
        for idx, row in enumerate(rows):
            trace = traces[idx] if idx < len(traces) else RowTrace(raw_preview=None, issues=[])
            row.descripcion = self._normalize_description(row.descripcion, trace)
            self._fix_amount_columns(row, trace)

    def adjust_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float:
        desc = (row.descripcion or "").strip()
        if not desc:
            return -0.15

        if self._description_has_amount_noise(desc) or self._description_looks_truncated(desc):
            return 0.0

        delta = 0.0
        if "descripcion_multilinea" in trace.issues:
            delta += 0.12
        if "TRANSFERENCIA DE TERCEROS" in desc.upper() and len(desc.split()) >= 8:
            delta += 0.05
        return min(delta, 0.2)

    def compute_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float | None:
        desc = (row.descripcion or "").strip()
        if not desc:
            return 0.45

        score = 0.78
        if row.fecha:
            score += 0.05
        if desc != "(sin descripcion)":
            score += 0.05
        else:
            score -= 0.25

        has_debito = row.debito is not None
        has_credito = row.credito is not None
        if has_debito and has_credito:
            score -= 0.05
        elif has_debito or has_credito:
            score += 0.04
        else:
            score -= 0.12

        if row.saldo is not None:
            score += 0.05
        else:
            score -= 0.07

        if "descripcion_multilinea" in trace.issues and len(desc.split()) >= 3:
            score += 0.03
        if "TRANSFERENCIA DE TERCEROS" in desc.upper() and len(desc.split()) >= 8:
            score += 0.03

        if self._description_has_amount_noise(desc):
            score -= 0.08
        if self._description_looks_truncated(desc):
            score -= 0.12

        return round(max(0.0, min(1.0, score)), 3)

    def _normalize_description(self, description: str, trace: RowTrace) -> str:
        desc = self._extract_primary_description_from_raw(trace.raw_preview) or " ".join((description or "").split())
        if not desc:
            return desc

        desc = self._strip_trailing_amounts(desc)
        desc = self._strip_trailing_code(desc)
        desc = self._strip_trailing_comprobante(desc)

        continuation_lines = self._extract_continuation_lines(trace.raw_preview)
        for continuation in continuation_lines:
            if continuation.lower() not in desc.lower():
                desc = f"{desc} {continuation}".strip()

        return " ".join(desc.split())

    def _fix_amount_columns(self, row: ParsedMovement, trace: RowTrace) -> None:
        first_line = self._first_line(trace.raw_preview)
        if not first_line:
            return

        values = self._extract_tail_amounts_from_line(first_line)
        if len(values) < 3:
            return

        credito_col, debito_col, saldo_col = values[-3], values[-2], values[-1]
        row.credito = self._to_credito(credito_col)
        row.debito = self._to_debito(debito_col)
        row.saldo = saldo_col

    def _first_line(self, raw_preview: str | None) -> str | None:
        if not raw_preview:
            return None
        segments = [segment.strip() for segment in raw_preview.split("|") if segment.strip()]
        return segments[0] if segments else None

    def _extract_primary_description_from_raw(self, raw_preview: str | None) -> str | None:
        first_line = self._first_line(raw_preview)
        if not first_line:
            return None

        line = re.sub(r"^\s*\d{2}/\d{2}/\d{2,4}\s+", "", first_line)
        return " ".join(line.split()) if line else None

    def _extract_continuation_lines(self, raw_preview: str | None) -> list[str]:
        if not raw_preview:
            return []
        segments = [segment.strip() for segment in raw_preview.split("|") if segment.strip()]
        out: list[str] = []
        for segment in segments[1:]:
            candidate = segment.strip()
            upper = candidate.upper()
            if any(upper.startswith(prefix) for prefix in self._continuation_prefixes):
                out.append(candidate)
                continue
            if upper in self._continuation_static_tokens:
                out.append(candidate)
                continue
            if re.fullmatch(r"\d{8,}", candidate):
                out.append(candidate)
                continue
            if re.search(r"[A-Z]", upper) and not self._contains_amount_token(candidate):
                out.append(candidate)
        return out

    def _strip_trailing_code(self, description: str) -> str:
        match = self._trailing_code_re.search(description)
        if not match:
            return description.strip()

        tail = match.group(0).strip()
        # Solo removemos códigos de "origen" alfanuméricos (ej. 00C4).
        # Si el sufijo es numérico puro (ej. ticket 0072), se conserva.
        if re.search(r"[A-Z]", tail):
            return self._trailing_code_re.sub("", description).strip()
        return description.strip()

    def _strip_trailing_comprobante(self, description: str) -> str:
        return self._trailing_comprobante_re.sub("", description).strip()

    def _strip_trailing_amounts(self, description: str) -> str:
        tokens = description.split()
        while tokens and self._is_amount_token(tokens[-1]):
            tokens.pop()
        return " ".join(tokens).strip()

    def _extract_tail_amounts_from_line(self, line: str) -> list[float]:
        tokens = line.split()
        collected: list[float] = []
        for token in reversed(tokens):
            value = self._parse_amount_token(token)
            if value is not None:
                collected.append(value)
                continue
            if collected:
                break
        return list(reversed(collected))

    def _contains_amount_token(self, text: str) -> bool:
        return any(self._is_amount_token(token) for token in text.split())

    def _is_amount_token(self, token: str) -> bool:
        candidate = token.strip().replace("$", "").replace("−", "-")
        if not candidate:
            return False
        if "," not in candidate and "." not in candidate:
            return False
        return re.fullmatch(r"-?\d[\d\.,]*-?", candidate) is not None

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

        candidate = candidate.replace(".", "").replace(",", ".")
        try:
            return sign * float(candidate)
        except ValueError:
            return None

    def _to_credito(self, value: float) -> float | None:
        if abs(value) < 1e-9:
            return None
        return abs(value)

    def _to_debito(self, value: float) -> float | None:
        if abs(value) < 1e-9:
            return None
        return abs(value)

    def _description_has_amount_noise(self, description: str) -> bool:
        return any(self._is_amount_token(token) for token in description.split())

    def _description_looks_truncated(self, description: str) -> bool:
        tokens = description.split()
        if not tokens:
            return False
        last = tokens[-1]
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", last):
            return True
        return description.endswith(("-", "/", ":"))

    def _normalize_text(self, value: str) -> str:
        upper = value.upper()
        replacements = str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN")
        return upper.translate(replacements)

