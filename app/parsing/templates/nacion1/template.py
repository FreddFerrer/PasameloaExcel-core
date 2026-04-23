from __future__ import annotations

import json
import re
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


class Nacion1Template(ParsingTemplate):
    template_id = "nacion1"
    bank_hint = "BNA"
    priority = 945

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            self.config = {}

        self._date_prefix_re = re.compile(r"^\s*\d{2}/\d{2}/\d{2,4}\s+")
        self._comprob_re = re.compile(r"^\d{3,10}$")
        self._secondary_or_footer_markers = (
            "TOTAL GRAV. LEY 25413",
            "SALDO FINAL",
            "SALDO ANTERIOR",
            "CUENTA CORRIENTE - PESOS",
            "NRO. CUENTA SUCURSAL",
            "CANTIDAD TOTAL DE INTEGRANTES",
            "BANCO DE LA NACION ARGENTINA",
            "CUIT 30-50001091-2",
            "IVA RESPONSABLE INSCRIPTO",
        )
        self._credit_keywords = (
            "DEBIN",
            "CRED",
            "ACRED",
            "DEPOSITO",
            "DEP.",
            "DEP ",
            "TRANSFERENCIA RECIB",
            "BCA.E.TR.",
        )
        self._debit_keywords = (
            "DEB.",
            "COMISION",
            "I.V.A.",
            "RETEN.",
            "GRAVAMEN",
            "REG.REC.",
            "INTERESES",
            "PAGO",
        )

    def match_score(self, context: TemplateContext) -> float:
        first_page = self._normalize_match_text(context.first_page_text)

        score = 0.0
        if "BANCODELANACIONARGENTINA" in first_page:
            score += 0.65
        if "CUIT30500010912IVARESPONSABLEINSCRIPTO" in first_page:
            score += 0.35
        if "FECHAMOVIMIENTOSCOMPROBDEBITOSCREDITOSSALDO" in first_page:
            score += 0.55
        return min(score, 1.0)

    def is_footer_line(self, line: str) -> bool:
        upper = self._normalize_text(line)
        if super().is_footer_line(line):
            return True
        return any(marker in upper for marker in self._secondary_or_footer_markers)

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        if re.match(r"^\s*\d{2}/\d{2}/\d{2,4}\b", candidate_line):
            return False
        # BNA suele venir en una sola linea, pero dejamos soporte para conceptos largos.
        clean = candidate_line.strip()
        if not clean:
            return False
        if self._is_standalone_amount_line(clean):
            return True
        return self._contains_letters(clean)

    def postprocess_rows(
        self,
        rows: list[ParsedMovement],
        traces: list[RowTrace],
        context: TemplateContext,
    ) -> None:
        filtered_rows: list[ParsedMovement] = []
        filtered_traces: list[RowTrace] = []
        prev_saldo = self._extract_initial_balance(context.first_page_text)

        for idx, row in enumerate(rows):
            trace = traces[idx] if idx < len(traces) else RowTrace(raw_preview=None, issues=[])
            parsed = self._parse_trace(trace)
            if parsed is None:
                continue

            description = parsed["description"]
            movement = parsed["movement"]
            saldo = parsed["saldo"]
            debito, credito = self._resolve_sides(
                movement=movement,
                saldo=saldo,
                prev_saldo=prev_saldo,
                description=description,
            )

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

        score = 0.8
        if row.fecha:
            score += 0.04
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

        first = segments[0]
        if self._looks_like_non_main_line(first):
            return None

        line_wo_date = self._date_prefix_re.sub("", first).strip()
        if not line_wo_date:
            return None

        tokens = line_wo_date.split()
        amount_tokens: list[str] = []
        while tokens and self._is_amount_token(tokens[-1]):
            amount_tokens.insert(0, tokens.pop())

        if len(amount_tokens) < 2:
            return None

        # COMPROB suele ir inmediatamente antes del importe de movimiento.
        if tokens and self._comprob_re.fullmatch(tokens[-1]):
            tokens.pop()

        description = " ".join(tokens).strip()
        if not description or self._looks_like_non_main_line(description):
            return None

        continuation_saldo: float | None = None
        continuation_desc: list[str] = []
        for segment in segments[1:]:
            clean = segment.strip()
            if not clean or self._looks_like_non_main_line(clean):
                continue
            if self._is_standalone_amount_line(clean):
                parsed = self._parse_amount_token(clean)
                if parsed is not None:
                    continuation_saldo = parsed
                continue
            if self._contains_letters(clean):
                continuation_desc.append(clean)

        if continuation_desc:
            description = f"{description} {' '.join(continuation_desc)}".strip()

        movement = self._parse_amount_token(amount_tokens[-2])
        saldo = self._parse_amount_token(amount_tokens[-1])
        if continuation_saldo is not None:
            saldo = continuation_saldo

        if movement is None or saldo is None:
            return None

        return {
            "description": " ".join(description.split()),
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

    def _extract_initial_balance(self, first_page_text: str) -> float | None:
        for line in (first_page_text or "").splitlines():
            upper = self._normalize_text(line)
            if "SALDO ANTERIOR" not in upper:
                continue
            token = line.split()[-1] if line.split() else ""
            value = self._parse_amount_token(token)
            if value is not None:
                return value
        return None

    def _looks_like_non_main_line(self, text: str) -> bool:
        upper = self._normalize_text(text)
        return any(marker in upper for marker in self._secondary_or_footer_markers)

    def _contains_letters(self, text: str) -> bool:
        return re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", text) is not None

    def _is_standalone_amount_line(self, text: str) -> bool:
        return self._parse_amount_token(text.strip()) is not None

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

