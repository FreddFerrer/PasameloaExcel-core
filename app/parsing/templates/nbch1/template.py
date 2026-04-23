from __future__ import annotations

import json
import re
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


class Nbch1Template(ParsingTemplate):
    template_id = "nbch1"
    bank_hint = "NBCH"
    priority = 900

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            self.config = {}

        rules = self.config.get("description_rules", {})
        min_digits = int(rules.get("comprobante_digits_min", 8))
        max_digits = int(rules.get("comprobante_digits_max", 10))
        self._trailing_comprobante_re = re.compile(rf"\s+\d{{{min_digits},{max_digits}}}$")
        configured_prefixes = rules.get("continuation_prefixes") or ["CONVENIO:", "ORIGEN:"]
        self._continuation_prefixes = [str(prefix).strip().upper() for prefix in configured_prefixes if str(prefix).strip()]

    def match_score(self, context: TemplateContext) -> float:
        file_stem = self._normalize_match_text(context.file_stem)
        first_page = self._normalize_match_text(context.first_page_text)

        score = 0.0
        # Firma fuerte del banco en encabezado / footer.
        if "NUEVOBANCODELCHACOSA" in first_page:
            score += 0.7
        if "CASACENTRALGUEMES102RESISTENCIACHACOARGENTINA" in first_page:
            score += 0.2
        if "CUIT30670157799" in first_page:
            score += 0.2
        if "RESPONSABLEINSCRIPTO" in first_page:
            score += 0.1

        # Via secundaria controlada: evita false positives por solo contener "CHACO".
        if "NUEVOBANCODELCHACO" in first_page and "COMPROBANTE" in first_page:
            score += 0.25
        if "NBCH" in file_stem:
            score += 0.25
        if "NUEVOBANCODELCHACO" in file_stem:
            score += 0.2
        return min(score, 1.0)

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        if re.match(r"^\s*\d{2}/\d{2}/\d{2,4}\b", candidate_line):
            return False

        upper = candidate_line.strip().upper()
        return any(upper.startswith(prefix) for prefix in self._continuation_prefixes)

    def postprocess_rows(
        self,
        rows: list[ParsedMovement],
        traces: list[RowTrace],
        context: TemplateContext,
    ) -> None:
        for idx, row in enumerate(rows):
            trace = traces[idx] if idx < len(traces) else RowTrace(raw_preview=None, issues=[])
            row.descripcion = self._normalize_description(row.descripcion, trace)

    def adjust_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float:
        description = (row.descripcion or "").strip()
        if not description:
            return -0.15

        if self._description_has_amount_noise(description) or self._description_looks_truncated(description):
            return 0.0

        delta = 0.0
        if "descripcion_multilinea" in trace.issues:
            delta += 0.12
        if self._contains_continuation_marker(description):
            delta += 0.05
        return min(delta, 0.2)

    def compute_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float | None:
        description = (row.descripcion or "").strip()
        if not description:
            return 0.45

        score = 0.77
        if row.fecha:
            score += 0.05
        if description != "(sin descripcion)":
            score += 0.04
        else:
            score -= 0.25

        has_debito = row.debito is not None
        has_credito = row.credito is not None
        if has_debito and has_credito:
            score -= 0.04
        elif has_debito or has_credito:
            score += 0.04
        else:
            score -= 0.12

        if row.saldo is not None:
            score += 0.05
        else:
            score -= 0.07

        if "descripcion_multilinea" in trace.issues and len(description.split()) >= 3:
            score += 0.02
        if self._contains_continuation_marker(description):
            score += 0.03

        if self._description_has_amount_noise(description):
            score -= 0.08
        if self._description_looks_truncated(description):
            score -= 0.12

        return round(max(0.0, min(1.0, score)), 3)

    def _normalize_description(self, description: str, trace: RowTrace) -> str:
        desc = self._extract_primary_description_from_raw(trace.raw_preview) or " ".join((description or "").split())
        if not desc:
            return desc

        desc = self._strip_trailing_amounts(desc)
        desc = self._strip_trailing_comprobante(desc)
        continuation_lines = self._extract_continuation_lines(trace.raw_preview)
        for continuation in continuation_lines:
            if continuation.lower() not in desc.lower():
                desc = f"{desc} {continuation}".strip()

        return " ".join(desc.split())

    def _strip_trailing_comprobante(self, description: str) -> str:
        return self._trailing_comprobante_re.sub("", description).strip()

    def _extract_continuation_lines(self, raw_preview: str | None) -> list[str]:
        if not raw_preview:
            return []
        segments = [segment.strip() for segment in raw_preview.split("|") if segment.strip()]
        out: list[str] = []
        for segment in segments[1:]:
            upper = segment.upper()
            if any(upper.startswith(prefix) for prefix in self._continuation_prefixes):
                out.append(segment)
        return out

    def _extract_primary_description_from_raw(self, raw_preview: str | None) -> str | None:
        if not raw_preview:
            return None
        segments = [segment.strip() for segment in raw_preview.split("|") if segment.strip()]
        if not segments:
            return None

        primary = segments[0]
        primary = re.sub(r"^\s*\d{2}/\d{2}/\d{2,4}\s+", "", primary)
        return " ".join(primary.split()) if primary else None

    def _strip_trailing_amounts(self, description: str) -> str:
        tokens = description.split()
        while tokens and self._is_amount_token(tokens[-1]):
            tokens.pop()
        return " ".join(tokens).strip()

    def _is_amount_token(self, token: str) -> bool:
        candidate = token.strip().replace("$", "").replace("−", "-")
        if not candidate:
            return False
        if "," not in candidate and "." not in candidate:
            return False
        return re.fullmatch(r"-?\d[\d\.,]*-?", candidate) is not None

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

    def _contains_continuation_marker(self, description: str) -> bool:
        upper = description.upper()
        return any(prefix in upper for prefix in self._continuation_prefixes)

    def _normalize_match_text(self, value: str) -> str:
        upper = value.upper()
        replacements = str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN")
        normalized = upper.translate(replacements)
        return re.sub(r"[^A-Z0-9]+", "", normalized)

