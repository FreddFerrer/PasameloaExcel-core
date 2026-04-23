from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import CandidateRow, ParsedMovement, RowTrace, TemplateContext


class Santander1Template(ParsingTemplate):
    template_id = "santander1"
    bank_hint = "SANTANDER"
    priority = 970

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            self.config = {}

        self._date_line_re = re.compile(r"^\s*(\d{2}/\d{2}/\d{2,4})(?:\s+(.*))?$")
        self._table_header_markers = (
            "FECHA COMPROBANTE MOVIMIENTO DEBITO CREDITO SALDO EN CUENTA",
            "MOVIMIENTOS EN PESOS",
            "CUENTA CORRIENTE N",
        )
        self._footer_markers = (
            "SALVO ERROR U OMISION",
            "BANCO SANTANDER ARGENTINA S.A.",
            "CUIT 30-50000845-4",
            "NINGUN ACCIONISTA MAYORITARIO",
            "PAGINA",
        )
        self._credit_keywords = (
            "TRANSFERENCIA RECIBIDA",
            "CREDITO",
            "PAGO COMERCIOS",
            "PAGOS CTAS",
            "SALDO INICIAL",
        )
        self._debit_keywords = (
            "COMPRA CON TARJETA DE DEBITO",
            "ECHEQ CLEARING RECIBIDO",
            "PAGO DE SERVICIOS",
            "RETIRO EN EFECTIVO",
            "RETIRO EN EFVO",
            "IMPUESTO LEY 25.413 DEBITO",
            "REGIMEN DE RECAUDACION",
            "DEBITO",
            "DEBITO AUTOMATCO",
            "COMISION",
            "MANTENIMIENTO",
        )

    def match_score(self, context: TemplateContext) -> float:
        first_page = self._normalize_text(context.first_page_text)
        score = 0.0
        if "BANCO SANTANDER ARGENTINA S.A. ES UNA SOCIEDAD ANONIMA SEGUN LA LEY ARGENTINA" in first_page:
            score += 0.7
        if "CUIT 30-50000845-4" in first_page:
            score += 0.3

        for page in context.pages[:3]:
            page_text = self._normalize_text("\n".join(page.get("lines", [])[:120]))
            if "FECHA COMPROBANTE MOVIMIENTO DEBITO CREDITO SALDO EN CUENTA" in page_text:
                score += 0.55
            if "MOVIMIENTOS EN PESOS" in page_text:
                score += 0.2
                break
        return min(score, 1.0)

    def is_footer_line(self, line: str) -> bool:
        if super().is_footer_line(line):
            return True
        upper = self._normalize_text(line)
        return any(marker in upper for marker in self._footer_markers)

    def collect_candidates(self, pages: list[dict], context: TemplateContext) -> list[CandidateRow] | None:
        candidates: list[CandidateRow] = []

        for page in pages:
            page_num = int(page.get("page_num") or 1)
            lines = [" ".join(str(line).split()) for line in page.get("lines", []) if str(line).strip()]
            if not lines:
                continue

            in_table = False
            active_date: str | None = None
            i = 0

            while i < len(lines):
                line = lines[i]

                if not in_table:
                    if self._is_table_header_line(line):
                        in_table = True
                    i += 1
                    continue

                if self.is_footer_line(line):
                    i += 1
                    continue

                date_match = self._date_line_re.match(line)
                row_date: str | None = active_date
                row_payload: str | None = None

                if date_match:
                    row_date = self._normalize_date(date_match.group(1))
                    active_date = row_date
                    tail = (date_match.group(2) or "").strip()
                    if not tail:
                        i += 1
                        continue
                    if self._is_row_payload(tail):
                        row_payload = tail
                    else:
                        i += 1
                        continue
                else:
                    if active_date and self._is_row_payload(line):
                        row_date = active_date
                        row_payload = line

                if not row_payload or not row_date:
                    i += 1
                    continue

                parts = [f"{row_date} {row_payload}"]
                first_line = parts[0]
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if self._is_table_header_line(nxt) or self.is_footer_line(nxt):
                        break

                    m2 = self._date_line_re.match(nxt)
                    if m2:
                        date2 = self._normalize_date(m2.group(1))
                        tail2 = (m2.group(2) or "").strip()
                        active_date = date2
                        if tail2 and self._is_row_payload(tail2):
                            break
                        if not tail2:
                            if j + 1 < len(lines):
                                look = lines[j + 1]
                                if self.should_attach_continuation(first_line, look):
                                    parts.append(look.strip())
                                    j += 2
                                    continue
                            j += 1
                            continue
                        if self.should_attach_continuation(first_line, tail2):
                            parts.append(tail2)
                            j += 1
                            continue
                        j += 1
                        continue

                    if self._is_row_payload(nxt):
                        break
                    if self.should_attach_continuation(first_line, nxt):
                        parts.append(nxt.strip())
                        j += 1
                        continue
                    break

                candidates.append(CandidateRow(page=page_num, raw_text=" | ".join(parts), line_count=len(parts)))
                i = j

        return candidates

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
            descripcion = parsed["description"]
            saldo = parsed["saldo"]
            movement_amount = parsed["movement_amount"]
            explicit_debito = parsed["explicit_debito"]
            explicit_credito = parsed["explicit_credito"]

            debito, credito = self._resolve_sides(
                movement_amount=movement_amount,
                explicit_debito=explicit_debito,
                explicit_credito=explicit_credito,
                saldo=saldo,
                prev_saldo=prev_saldo,
                description=descripcion,
            )

            row.fecha = fecha
            row.descripcion = descripcion
            row.debito = debito
            row.credito = credito
            row.saldo = saldo

            if self._is_opening_balance_row(row):
                continue

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
            score += 0.05
        if row.saldo is not None:
            score += 0.05
        else:
            score -= 0.14

        has_debito = row.debito is not None
        has_credito = row.credito is not None
        if has_debito ^ has_credito:
            score += 0.04
        elif has_debito and has_credito:
            score -= 0.06
        else:
            score -= 0.14

        if len(desc.split()) >= 2:
            score += 0.02
        if "descripcion_multilinea" in trace.issues:
            score += 0.01

        if self._contains_amount_token(desc) and not self._amounts_are_contextual(desc):
            score -= 0.12
        elif self._contains_amount_token(desc):
            score += 0.01
        if self._description_looks_truncated(desc):
            score -= 0.12

        return round(max(0.0, min(1.0, score)), 3)

    def _parse_trace(self, trace: RowTrace) -> dict | None:
        raw = trace.raw_preview or ""
        parts = [part.strip() for part in raw.split("|") if part.strip()]
        if not parts:
            return None

        m = self._date_line_re.match(parts[0])
        if not m:
            return None
        fecha = self._normalize_date(m.group(1))
        payload = (m.group(2) or "").strip()
        if not payload:
            return None

        payload_tokens = payload.split()
        amount_indices: list[int] = []
        amount_values: list[float] = []
        for idx, token in enumerate(payload_tokens):
            parsed = self._parse_amount_token(token)
            if parsed is None:
                continue
            if self._has_explicit_negative_prefix(payload_tokens, idx):
                parsed = -abs(parsed)
            amount_indices.append(idx)
            amount_values.append(parsed)

        if not amount_values:
            return None

        saldo: float | None = None
        explicit_debito: float | None = None
        explicit_credito: float | None = None
        movement_amount: float | None = None

        if len(amount_values) >= 3:
            explicit_debito = self._to_positive_or_none(amount_values[-3])
            explicit_credito = self._to_positive_or_none(amount_values[-2])
            saldo = amount_values[-1]
        elif len(amount_values) == 2:
            movement_amount = abs(amount_values[-2])
            saldo = amount_values[-1]
        else:
            saldo = amount_values[0]

        first_amount_idx = amount_indices[0]
        head_tokens = payload_tokens[:first_amount_idx]
        head_tokens = [token for token in head_tokens if token != "$"]
        if head_tokens and re.fullmatch(r"\d{1,12}", head_tokens[0]):
            head_tokens = head_tokens[1:]
        description = " ".join(head_tokens).strip()

        continuations: list[str] = []
        for part in parts[1:]:
            cont = part.strip()
            if not cont or self.is_footer_line(cont):
                continue
            if self._is_row_payload(cont):
                continue
            if self.should_attach_continuation(parts[0], cont):
                continuations.append(cont)

        if continuations:
            description = f"{description} {' '.join(continuations)}".strip()
        description = " ".join(description.split())
        if not description:
            description = "(sin descripcion)"

        return {
            "fecha": fecha,
            "description": description,
            "saldo": saldo,
            "movement_amount": movement_amount,
            "explicit_debito": explicit_debito,
            "explicit_credito": explicit_credito,
        }

    def _resolve_sides(
        self,
        *,
        movement_amount: float | None,
        explicit_debito: float | None,
        explicit_credito: float | None,
        saldo: float | None,
        prev_saldo: float | None,
        description: str,
    ) -> tuple[float | None, float | None]:
        upper = self._normalize_text(description)
        if self._must_force_debit(upper):
            forced = self._to_positive_or_none(explicit_debito)
            if forced is None:
                forced = self._to_positive_or_none(explicit_credito)
            if forced is None:
                forced = self._to_positive_or_none(movement_amount)
            if forced is None:
                return None, None
            return forced, None
        if self._must_force_credit(upper):
            forced = self._to_positive_or_none(explicit_credito)
            if forced is None:
                forced = self._to_positive_or_none(explicit_debito)
            if forced is None:
                forced = self._to_positive_or_none(movement_amount)
            if forced is None:
                return None, None
            return None, forced

        if explicit_debito is not None or explicit_credito is not None:
            return explicit_debito, explicit_credito
        if movement_amount is None or movement_amount <= 0:
            return None, None

        if prev_saldo is not None and saldo is not None:
            delta = saldo - prev_saldo
            if abs(delta - movement_amount) <= 0.02:
                return None, movement_amount
            if abs(delta + movement_amount) <= 0.02:
                return movement_amount, None

        if any(k in upper for k in self._debit_keywords):
            return movement_amount, None
        if any(k in upper for k in self._credit_keywords):
            return None, movement_amount
        return None, movement_amount

    def _must_force_debit(self, normalized_description: str) -> bool:
        debit_only_markers = (
            "ECHEQ CLEARING RECIBIDO 48HS",
            "ECHEQ CLEARING RECIBIDO",
            "RETIRO EN EFVO POR CAJA",
            "RETIRO EN EFECTIVO POR CAJA",
            "IMPUESTO LEY 25.413 DEBITO",
            "CHEQUE DEBITADO",
            "DEBITO AUTOMATICO",
        )
        return any(marker in normalized_description for marker in debit_only_markers)

    def _must_force_credit(self, normalized_description: str) -> bool:
        credit_only_markers = (
            "PAGOS CTAS PROPIAS INTERBANKING IN",
        )
        return any(marker in normalized_description for marker in credit_only_markers)

    def _has_explicit_negative_prefix(self, tokens: list[str], index: int) -> bool:
        if index <= 0:
            return False

        prev = tokens[index - 1].strip()
        if prev in {"-", "−", "-$", "−$"}:
            return True

        if index >= 2:
            prev2 = tokens[index - 2].strip()
            if prev2 in {"-", "−"} and prev == "$":
                return True
        return False

    def _is_table_header_line(self, line: str) -> bool:
        upper = self._normalize_text(line)
        return any(marker in upper for marker in self._table_header_markers)

    def _is_row_payload(self, text: str) -> bool:
        if not text:
            return False
        if self._is_table_header_line(text) or self.is_footer_line(text):
            return False
        amount_count = self._amount_token_count(text)
        upper = self._normalize_text(text)
        if amount_count >= 2:
            return True
        if "SALDO INICIAL" in upper and amount_count >= 1:
            return True
        return False

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        clean = candidate_line.strip()
        if not clean:
            return False
        if self._is_table_header_line(clean) or self.is_footer_line(clean):
            return False
        if self._looks_like_noise_line(clean):
            return False
        if re.match(r"^\s*\d{2}/\d{2}/\d{2,4}\b", clean):
            return False
        if self._is_row_payload(clean):
            return False
        if re.fullmatch(r"\d{8,12}", clean):
            return True
        if re.fullmatch(r"\d{5,}/\d{5,}", clean):
            return True
        upper = self._normalize_text(clean)
        if re.search(r"[A-Z]", upper) is not None:
            return True
        return not self._contains_amount_token(clean)

    def _is_continuation_line(self, text: str) -> bool:
        return self.should_attach_continuation("", text)

    def _looks_like_noise_line(self, text: str) -> bool:
        upper = self._normalize_text(text)
        if "HTTP://" in upper or "HTTPS://" in upper or "WWW." in upper:
            return True
        return re.fullmatch(r"\d+/\d+", text.strip()) is not None

    def _amount_token_count(self, text: str) -> int:
        return sum(1 for token in text.split() if self._parse_amount_token(token) is not None)

    def _contains_amount_token(self, text: str) -> bool:
        return any(self._parse_amount_token(token) is not None for token in text.split())

    def _description_looks_truncated(self, description: str) -> bool:
        tokens = description.split()
        if not tokens:
            return False
        last = tokens[-1]
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", last):
            return True
        return description.endswith(("-", "/", ":"))

    def _amounts_are_contextual(self, description: str) -> bool:
        upper = self._normalize_text(description)
        if "SOBRE $" in upper:
            return True
        if re.search(r"\d+,\d+%\s+SOBRE\s+\$", upper):
            return True
        return False

    def _is_opening_balance_row(self, row: ParsedMovement) -> bool:
        if self._normalize_text(row.descripcion or "") != "SALDO INICIAL":
            return False
        if row.debito is not None or row.credito is not None:
            return False
        return True

    def _normalize_date(self, value: str) -> str:
        clean = value.strip()
        m = re.fullmatch(r"(\d{2}/\d{2})/(\d{2})", clean)
        if m:
            return f"{m.group(1)}/20{m.group(2)}"
        return clean

    def _parse_amount_token(self, token: str) -> float | None:
        candidate = token.strip().replace("$", "").replace("−", "-")
        if not candidate:
            return None
        if re.fullmatch(r"-?\d+(?:[.,]\d{2})-?", candidate) is None and re.fullmatch(
            r"-?\d{1,3}(?:[.,]\d{3})+[.,]\d{2}-?", candidate
        ) is None:
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

    def _to_positive_or_none(self, value: float | None) -> float | None:
        if value is None or abs(value) < 1e-9:
            return None
        return abs(value)

    def _normalize_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        return ascii_only.upper()

