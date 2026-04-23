from __future__ import annotations

import json
import re
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


class Formosa1Template(ParsingTemplate):
    template_id = "formosa1"
    bank_hint = "BANCO_FORMOSA"
    priority = 930

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            self.config = {}

        self._secondary_markers = (
            "TRANSFERENCIAS MEP",
            "DEBITOS AUTOMATICOS",
            "REVERSO DE DEBITOS AUTOMATICOS",
            "TOTAL DE TRANSFERENCIAS RECIBIDAS",
            "NO SE HAN REGISTRADO MOVIMIENTOS",
        )
        self._footer_markers = (
            "BANCO DE FORMOSA S.A.",
            "RESUMEN DE CUENTA CORRIENTE EN PESOS",
            "SALDO FINAL",
            "DETALLE POR PRODUCTO",
            "TOTAL RET. IMP. LEY 25.413",
        )
        self._reference_token_re = re.compile(r"^\d{5,14}$")
        self._date_prefix_re = re.compile(r"^\s*\d{2}/\d{2}/\d{2,4}\s+")
        self._credit_keywords = (
            "DEP EN EFECTIVO",
            "DEP ",
            "ACRED",
            "CREDITO",
            "CR.",
            "CR ",
            "TRANSFERENCIA",
            "TRANSF.",
        )
        self._debit_keywords = (
            "DB ",
            "DEBITO",
            "DEB.",
            "INT ",
            "IVA",
            "IMP ",
            "IMPTO",
            "IMPTO ",
            "IMP REC",
            "PERCEPCION",
            "PAGO",
            "MANT.",
            "COMISION",
        )

    def match_score(self, context: TemplateContext) -> float:
        first_page = self._normalize_text(context.first_page_text)
        file_stem = self._normalize_text(context.file_stem)

        score = 0.0
        if "BANCO DE FORMOSA S.A." in first_page:
            score += 0.75
        if "FECHA CONCEPTO REFERENCIA CHEQUE DEBITOS CREDITOS SALDO" in first_page:
            score += 0.7
        if "DETALLE POR PRODUCTO" in first_page:
            score += 0.2
        if "FORMOSA" in file_stem:
            score += 0.25
        return min(score, 1.0)

    def is_footer_line(self, line: str) -> bool:
        upper = self._normalize_text(line)
        if super().is_footer_line(line):
            return True
        if any(marker in upper for marker in self._secondary_markers):
            return True
        if any(marker in upper for marker in self._footer_markers):
            return True
        return False

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        if re.match(r"^\s*\d{2}/\d{2}/\d{2,4}\b", candidate_line):
            return False

        candidate = candidate_line.strip()
        first_upper = self._normalize_text(first_line)
        candidate_upper = self._normalize_text(candidate)

        if self._is_standalone_amount_line(candidate):
            return True
        if "CREDITO TRANSFERENCIA" in first_upper and self._is_non_amount_text_line(candidate):
            return True
        if "ING. BRUTOS S/ CRED" in first_upper and "RG." in candidate_upper:
            return True
        return False

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
            parsed = self._parse_trace(row=row, trace=trace)
            if parsed is None:
                continue

            description = parsed["description"]
            movement = parsed["movement"]
            saldo = parsed["saldo"]
            explicit_debito = parsed["explicit_debito"]
            explicit_credito = parsed["explicit_credito"]

            debito, credito = self._resolve_sides(
                movement=movement,
                saldo=saldo,
                prev_saldo=prev_saldo,
                description=description,
                explicit_debito=explicit_debito,
                explicit_credito=explicit_credito,
            )

            row.descripcion = description
            row.debito = debito
            row.credito = credito
            row.saldo = saldo if saldo is not None else row.saldo

            if row.saldo is not None:
                prev_saldo = row.saldo

            filtered_rows.append(row)
            filtered_traces.append(trace)

        rows[:] = filtered_rows
        traces[:] = filtered_traces

    def adjust_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float:
        desc = (row.descripcion or "").strip()
        if not desc:
            return -0.2
        if row.debito is None and row.credito is None:
            return -0.12
        delta = 0.0
        if row.saldo is not None:
            delta += 0.07
        if "descripcion_multilinea" in trace.issues and len(desc.split()) >= 4:
            delta += 0.05
        return min(delta, 0.15)

    def compute_row_confidence(
        self,
        row: ParsedMovement,
        trace: RowTrace,
        context: TemplateContext,
    ) -> float | None:
        """
        Recalculo template-aware sobre la fila ya normalizada.
        Evita castigar movimientos validos solo por multilinea del layout.
        """
        desc = (row.descripcion or "").strip()
        if not desc:
            return 0.45

        score = 0.78
        if row.fecha:
            score += 0.04
        if desc and desc != "(sin descripcion)":
            score += 0.05
        else:
            score -= 0.25

        if row.saldo is not None:
            score += 0.06
        else:
            score -= 0.1

        has_debito = row.debito is not None
        has_credito = row.credito is not None
        if has_debito and has_credito:
            score -= 0.06
        elif has_debito or has_credito:
            score += 0.04
        else:
            score -= 0.12

        if "descripcion_multilinea" in trace.issues and len(desc.split()) >= 2:
            score += 0.02

        if self._contains_amount_token(desc):
            score -= 0.08
        if self._description_looks_truncated(desc):
            score -= 0.12
        if self._looks_like_non_main_table_description(desc):
            score -= 0.2

        return round(max(0.0, min(1.0, score)), 3)

    def _parse_trace(self, *, row: ParsedMovement, trace: RowTrace) -> dict | None:
        raw = trace.raw_preview or ""
        segments = [segment.strip() for segment in raw.split("|") if segment.strip()]
        if not segments:
            return None

        first = segments[0]
        first_without_date = self._date_prefix_re.sub("", first).strip()
        if not first_without_date:
            return None

        tokens = first_without_date.split()
        amount_tokens: list[str] = []
        while tokens and self._is_amount_token(tokens[-1]):
            amount_tokens.insert(0, tokens.pop())

        reference_tokens_removed = 0
        while tokens and self._reference_token_re.fullmatch(tokens[-1]) and reference_tokens_removed < 2:
            tokens.pop()
            reference_tokens_removed += 1

        description = " ".join(tokens).strip()
        if not description:
            return None

        continuation_texts: list[str] = []
        continuation_saldo: float | None = None
        for segment in segments[1:]:
            clean = segment.strip()
            if not clean or self._is_secondary_or_footer_line(clean):
                continue
            if self._is_standalone_amount_line(clean):
                parsed_amount = self._parse_amount_token(clean)
                if parsed_amount is not None:
                    continuation_saldo = parsed_amount
                continue
            if self._is_non_amount_text_line(clean):
                continuation_texts.append(clean)

        if continuation_texts:
            description = f"{description} {' '.join(continuation_texts)}".strip()

        movement: float | None = None
        saldo: float | None = None
        explicit_debito: float | None = None
        explicit_credito: float | None = None
        parsed_amounts = [self._parse_amount_token(token) for token in amount_tokens]
        parsed_amounts = [value for value in parsed_amounts if value is not None]

        if len(parsed_amounts) >= 3:
            debito_val, credito_val, saldo_val = parsed_amounts[-3], parsed_amounts[-2], parsed_amounts[-1]
            explicit_debito = abs(debito_val) if abs(debito_val) > 1e-9 else None
            explicit_credito = abs(credito_val) if abs(credito_val) > 1e-9 else None
            saldo = saldo_val
        elif len(parsed_amounts) == 2:
            movement = parsed_amounts[-2]
            saldo = parsed_amounts[-1]
        elif len(parsed_amounts) == 1:
            movement = parsed_amounts[-1]

        if continuation_saldo is not None:
            saldo = continuation_saldo

        if movement is None and explicit_debito is None and explicit_credito is None and saldo is None:
            return None

        if self._looks_like_non_main_table_description(description):
            return None

        return {
            "description": " ".join(description.split()),
            "movement": movement,
            "saldo": saldo,
            "explicit_debito": explicit_debito,
            "explicit_credito": explicit_credito,
        }

    def _resolve_sides(
        self,
        *,
        movement: float | None,
        saldo: float | None,
        prev_saldo: float | None,
        description: str,
        explicit_debito: float | None,
        explicit_credito: float | None,
    ) -> tuple[float | None, float | None]:
        if explicit_debito is not None or explicit_credito is not None:
            return explicit_debito, explicit_credito
        if movement is None:
            return None, None

        amount = abs(movement)
        if amount < 1e-9:
            return None, None
        if movement < 0:
            return amount, None

        side = self._infer_side(description=description, saldo=saldo, prev_saldo=prev_saldo)
        if side == "debito":
            return amount, None
        return None, amount

    def _infer_side(self, *, description: str, saldo: float | None, prev_saldo: float | None) -> str:
        if saldo is not None and prev_saldo is not None:
            if saldo < prev_saldo - 0.005:
                return "debito"
            if saldo > prev_saldo + 0.005:
                return "credito"

        upper = self._normalize_text(description)
        if any(keyword in upper for keyword in self._debit_keywords):
            return "debito"
        if any(keyword in upper for keyword in self._credit_keywords):
            return "credito"
        return "debito"

    def _is_secondary_or_footer_line(self, line: str) -> bool:
        upper = self._normalize_text(line)
        if any(marker in upper for marker in self._secondary_markers):
            return True
        if any(marker in upper for marker in self._footer_markers):
            return True
        if "PAGINA " in upper and " / " in upper:
            return True
        return False

    def _looks_like_non_main_table_description(self, description: str) -> bool:
        upper = self._normalize_text(description)
        disallowed_prefixes = (
            "TOTAL RET.",
            "IMPUESTO AL VALOR AGREGADO",
            "CAJA DE AHORRO",
            "LES PERIODOS",
            "Y A PARTIR DEL",
        )
        return any(upper.startswith(prefix) for prefix in disallowed_prefixes)

    def _description_looks_truncated(self, description: str) -> bool:
        tokens = description.split()
        if not tokens:
            return False
        last = tokens[-1]
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", last):
            return True
        return description.endswith(("-", "/", ":"))

    def _is_non_amount_text_line(self, line: str) -> bool:
        if self._contains_amount_token(line):
            return False
        return re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", line) is not None

    def _is_standalone_amount_line(self, line: str) -> bool:
        token = line.strip()
        return self._parse_amount_token(token) is not None

    def _contains_amount_token(self, text: str) -> bool:
        return any(self._is_amount_token(token) for token in text.split())

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

