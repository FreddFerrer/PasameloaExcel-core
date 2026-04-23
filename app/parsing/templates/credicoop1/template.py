from __future__ import annotations

import json
import re
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


class Credicoop1Template(ParsingTemplate):
    template_id = "credicoop1"
    bank_hint = "CREDICOOP"
    priority = 980

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            self.config = {}

        rules = self.config.get("description_rules", {})
        pattern = rules.get(
            "line_regex",
            r"^\s*(?P<fecha>\d{2}/\d{2}/\d{4})\s+(?P<concepto>.+?)\s+(?P<cpbte>\d+)\s+(?P<debito>-?\d[\d.,]*)\s+(?P<credito>-?\d[\d.,]*)\s+(?P<saldo>-?\d[\d.,]*)\s+(?P<cod>[A-Z0-9]+)\s*$",
        )
        self._line_re = re.compile(pattern)
        static_tokens = rules.get("continuation_static_tokens") or ["CUOTA"]
        self._continuation_static_tokens = {str(token).strip().upper() for token in static_tokens if str(token).strip()}
        skip_prefixes = rules.get("skip_prefixes") or []
        self._skip_prefixes = [str(prefix).strip().upper() for prefix in skip_prefixes if str(prefix).strip()]

    def match_score(self, context: TemplateContext) -> float:
        first_page = self._normalize_text(context.first_page_text)
        score = 0.0
        if "FECHA CONCEPTO NRO.CPBTE. DEBITO CREDITO SALDO COD." in first_page:
            score += 0.75
        if "BANCAINTERNET.BANCOCREDICOOP.COOP" in first_page:
            score += 0.45
        if "ADHERENTE:" in first_page and "NRO. DE CUENTA:" in first_page:
            score += 0.2
        return min(score, 1.0)

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        if re.match(r"^\s*\d{2}/\d{2}/\d{2,4}\b", candidate_line):
            return False

        candidate = candidate_line.strip()
        upper = self._normalize_text(candidate)
        if not candidate:
            return False
        if self._is_skip_line(upper):
            return False
        if self._contains_amount_token(candidate):
            return False
        if upper in self._continuation_static_tokens:
            return True
        if re.fullmatch(r"\d{8,}", candidate):
            return True
        if re.search(r"[A-Z]", upper):
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

        delta = 0.0
        first_line = self._first_line(trace.raw_preview)
        if first_line and self._parse_line_structured(first_line):
            delta += 0.07
        if "descripcion_multilinea" in trace.issues and len(desc.split()) >= 6:
            delta += 0.1
        if "CREDITO INMEDIATO (DEBIN)" in self._normalize_text(desc):
            delta += 0.03
        return min(delta, 0.15)

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
        if row.fecha:
            score += 0.05
        if desc != "(sin descripcion)":
            score += 0.05
        else:
            score -= 0.25

        first_line = self._first_line(trace.raw_preview)
        if first_line and self._parse_line_structured(first_line):
            score += 0.06

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
            score -= 0.08

        if "descripcion_multilinea" in trace.issues and len(desc.split()) >= 6:
            score += 0.03
        if "CREDITO INMEDIATO (DEBIN)" in self._normalize_text(desc):
            score += 0.02

        if self._contains_amount_token(desc):
            score -= 0.08
        if self._description_looks_truncated(desc):
            score -= 0.12

        return round(max(0.0, min(1.0, score)), 3)

    def _normalize_description(self, description: str, trace: RowTrace) -> str:
        first_line = self._first_line(trace.raw_preview)
        desc = self._extract_concept_from_first_line(first_line) or " ".join((description or "").split())

        continuation_lines = self._extract_continuation_lines(trace.raw_preview)
        for continuation in continuation_lines:
            if continuation.lower() not in desc.lower():
                desc = f"{desc} {continuation}".strip()

        desc = self._strip_footer_noise(desc)
        desc = self._tighten_var_separator(desc)
        return " ".join(desc.split())

    def _fix_amount_columns(self, row: ParsedMovement, trace: RowTrace) -> None:
        first_line = self._first_line(trace.raw_preview)
        if not first_line:
            return

        parsed = self._parse_line_structured(first_line)
        if not parsed:
            return

        debito = parsed.get("debito")
        credito = parsed.get("credito")
        saldo = parsed.get("saldo")

        row.debito = self._to_debito(self._parse_amount_token(debito or ""))
        row.credito = self._to_credito(self._parse_amount_token(credito or ""))
        parsed_saldo = self._parse_amount_token(saldo or "")
        if parsed_saldo is not None:
            row.saldo = parsed_saldo

    def _extract_concept_from_first_line(self, first_line: str | None) -> str | None:
        if not first_line:
            return None
        parsed = self._parse_line_structured(first_line)
        if parsed:
            return " ".join((parsed.get("concepto") or "").split())

        fallback = re.sub(r"^\s*\d{2}/\d{2}/\d{2,4}\s+", "", first_line)
        fallback = self._strip_trailing_amounts_and_code(fallback)
        return " ".join(fallback.split()) if fallback else None

    def _extract_continuation_lines(self, raw_preview: str | None) -> list[str]:
        if not raw_preview:
            return []
        segments = [segment.strip() for segment in raw_preview.split("|") if segment.strip()]
        first_line = segments[0] if segments else ""
        parsed_first = self._parse_line_structured(first_line)
        cpbte = (parsed_first or {}).get("cpbte")
        out: list[str] = []
        for segment in segments[1:]:
            upper = self._normalize_text(segment)
            if self._is_skip_line(upper):
                continue
            if self._contains_amount_token(segment):
                continue
            if upper in self._continuation_static_tokens:
                out.append(segment)
                continue
            if re.fullmatch(r"\d{8,}", segment):
                if cpbte and segment.lstrip("0") == cpbte.lstrip("0"):
                    continue
                if len(segment) <= 9:
                    continue
                out.append(segment)
                continue
            if re.search(r"[A-Z]", upper):
                out.append(segment)
        return out

    def _first_line(self, raw_preview: str | None) -> str | None:
        if not raw_preview:
            return None
        parts = [part.strip() for part in raw_preview.split("|") if part.strip()]
        return parts[0] if parts else None

    def _parse_line_structured(self, line: str) -> dict[str, str] | None:
        match = self._line_re.match(line)
        if not match:
            return None
        return match.groupdict()

    def _strip_trailing_amounts_and_code(self, text: str) -> str:
        candidate = text.strip()
        for _ in range(5):
            tokens = candidate.split()
            if not tokens:
                break
            last = tokens[-1]
            if self._is_amount_token(last) or re.fullmatch(r"[A-Z0-9]{4,}", last):
                tokens.pop()
                candidate = " ".join(tokens)
                continue
            break
        return candidate.strip()

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

    def _to_credito(self, value: float | None) -> float | None:
        if value is None or abs(value) < 1e-9:
            return None
        return abs(value)

    def _to_debito(self, value: float | None) -> float | None:
        if value is None or abs(value) < 1e-9:
            return None
        return abs(value)

    def _is_skip_line(self, upper_line: str) -> bool:
        if not upper_line:
            return True
        if "BANCAINTERNET.BANCOCREDICOOP.COOP" in upper_line:
            return True
        if "EXPORT.DO" in upper_line:
            return True
        if "BANCO CREDICOOP COOPERATIVO LTDO" in upper_line:
            return True
        if "DERECHOS RESERVADOS" in upper_line:
            return True
        if any(upper_line.startswith(prefix) for prefix in self._skip_prefixes):
            return True
        return False

    def _strip_footer_noise(self, description: str) -> str:
        if not description:
            return description

        cleaned = re.sub(
            r"\s+https?://\S+",
            "",
            description,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\s+BANCO\s+CREDICOOP\s+COOPERATIVO\s+LTDO\.\s+DERECHOS\s+RESERVADOS\s+\d{4}",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+\d+/\d+\s*$", "", cleaned)
        return cleaned.strip()

    def _tighten_var_separator(self, description: str) -> str:
        if not description:
            return description
        # Credicoop suele cortar en multilinea con "...-VAR- <NOMBRE>", y queremos "...-VAR-<NOMBRE>".
        return re.sub(r"(-VAR-)\s+", r"\1", description, flags=re.IGNORECASE).strip()

    def _normalize_numeric_token(self, candidate: str) -> str:
        raw = candidate.strip()
        if "," in raw and "." in raw:
            # Formato mixto (ej: 1.234,56) -> decimal con coma.
            if raw.rfind(",") > raw.rfind("."):
                return raw.replace(".", "").replace(",", ".")
            # Caso inverso (raro): coma miles, punto decimal.
            return raw.replace(",", "")

        if "," in raw:
            # 1234,56 -> decimal con coma.
            return raw.replace(".", "").replace(",", ".")

        if "." in raw:
            parts = raw.split(".")
            if len(parts) > 2:
                # Múltiples puntos, probable miles: 1.234.567
                return "".join(parts)
            decimals = parts[-1]
            if len(decimals) in (1, 2):
                # Decimal con punto: 143.69
                return raw
            # Punto como miles: 1.234
            return raw.replace(".", "")

        return raw

    def _normalize_text(self, value: str) -> str:
        upper = value.upper()
        replacements = str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN")
        return upper.translate(replacements)

