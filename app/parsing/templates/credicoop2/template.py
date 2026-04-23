from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import ParsedMovement, RowTrace, TemplateContext


class Credicoop2Template(ParsingTemplate):
    template_id = "credicoop2"
    bank_hint = "CREDICOOP"
    priority = 982

    def __init__(self) -> None:
        config_path = Path(__file__).with_name("template.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            self.config = {}

        self._date_prefix_re = re.compile(r"^\s*(\d{2}/\d{2}/\d{2,4})\b")
        self._date_time_detail_re = re.compile(r"^\s*\d{2}/\d{2}\s+\d{2}:\d{2}\b")
        self._header_markers = (
            "FECHA COMBTE DESCRIPCION DEBITO CREDITO SALDO",
            "CUENTA CORRIENTE - MOD. PYMES PJ",
            "RESUMEN:",
        )
        self._footer_markers = (
            "BANCO CREDICOOP COOPERATIVO LIMITADO",
            "CCT@BANCOCREDICOOP.COOP",
            "CREDICOOP RESPONDE: 0810-888-4500",
            "CALIDAD DE SERVICIOS:",
            "SITIO DE INTERNET: WWW.BANCOCREDICOOP.COOP",
            "CONTINUA EN PAGINA SIGUIENTE",
            "VIENE DE PAGINA ANTERIOR",
            "PAGINA ",
        )
        self._credit_keywords = (
            "ACREDITACION DE VALORES",
            "TRANSF. INTERBANKING - DISTINTO TITULAR",
            "TRANSF. INTERBANKING",
            "TRANSFER. E/CUENTAS DE DISTINTO TITULAR",
            "TRANSF. INMEDIATA E/CTAS. DIST. TITULAR",
            "CHEQUE RECHAZADO",
        )
        self._debit_keywords = (
            "SERVICIO ACREDITACIONES AUTOMATICAS",
            "PAGO DE SERVICIOS",
            "TRANSF.INMEDIATA E/CTAS.DIST TIT.O/BCO",
            "TRANSF. INMEDIATA E/CTAS. DIST. TITULAR",
            "RETIRO DE CAJERO AUTOMATICO",
            "COMPRA LOCAL CON TARJETA DE DEBITO",
            "IMPUESTO LEY 25.413",
            "ALI GRAL S/CREDITOS",
            "I.V.A.",
            "COMISION",
            "DEBITO",
            "ECHEQ - PAGO CHEQUE DE CAMARA",
            "TRANSFERENCIA POR PAGO DE HABERES",
        )

    def match_score(self, context: TemplateContext) -> float:
        first_page = self._normalize_text(context.first_page_text)
        score = 0.0
        if "BANCO CREDICOOP COOPERATIVO LIMITADO" in first_page:
            score += 0.55
        if "CCT@BANCOCREDICOOP.COOP" in first_page:
            score += 0.35
        if "CREDICOOP RESPONDE: 0810-888-4500" in first_page:
            score += 0.2

        for page in context.pages[:3]:
            text = self._normalize_text("\n".join(page.get("lines", [])[:120]))
            if "FECHA COMBTE DESCRIPCION DEBITO CREDITO SALDO" in text:
                score += 0.45
                break
        return min(score, 1.0)

    def is_footer_line(self, line: str) -> bool:
        if super().is_footer_line(line):
            return True
        upper = self._normalize_text(line)
        return any(marker in upper for marker in self._footer_markers)

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        candidate = candidate_line.strip()
        if not candidate:
            return False

        # Detalle de cajero: "04/04 14:26 Tarj:..."
        if self._date_time_detail_re.match(candidate):
            return True

        # Nueva fecha de fila real: dd/mm/yy ...
        if self._date_prefix_re.match(candidate):
            if re.fullmatch(r"\d{2}/\d{2}/\d{2,4}", candidate):
                return False
            return False

        upper = self._normalize_text(candidate)
        if any(marker in upper for marker in self._header_markers):
            return False

        if re.fullmatch(r"\d{8,14}", candidate):
            return True
        if re.fullmatch(r"\d{5,}/\d{5,}", candidate):
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
        filtered_rows: list[ParsedMovement] = []
        filtered_traces: list[RowTrace] = []
        prev_saldo: float | None = None

        for idx, row in enumerate(rows):
            trace = traces[idx] if idx < len(traces) else RowTrace(raw_preview=None, issues=[])
            parsed = self._parse_trace(trace)
            if parsed is None:
                continue

            row.fecha = parsed["fecha"]
            row.descripcion = parsed["descripcion"]
            row.saldo = parsed["saldo"]
            row.debito, row.credito = self._resolve_sides(
                movement=parsed["movement"],
                explicit_debito=parsed["explicit_debito"],
                explicit_credito=parsed["explicit_credito"],
                saldo=parsed["saldo"],
                prev_saldo=prev_saldo,
                descripcion=parsed["descripcion"],
            )

            if row.saldo is not None:
                prev_saldo = row.saldo

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

        # En este layout el saldo es opcional en la mayoria de filas validas.
        score = 0.86
        if row.fecha:
            score += 0.05
        if row.saldo is not None:
            score += 0.03
        if row.debito is not None or row.credito is not None:
            score += 0.04
        else:
            score -= 0.12
        if len(desc.split()) >= 2:
            score += 0.01
        if "descripcion_multilinea" in trace.issues:
            score += 0.02
        if self._description_looks_truncated(desc):
            score -= 0.1
        return round(max(0.0, min(1.0, score)), 3)

    def _parse_trace(self, trace: RowTrace) -> dict | None:
        raw = trace.raw_preview or ""
        segments = [segment.strip() for segment in raw.split("|") if segment.strip()]
        if not segments:
            return None

        first = segments[0]
        m_date = self._date_prefix_re.match(first)
        if not m_date:
            return None
        fecha = self._normalize_date(m_date.group(1))

        after_date = first[m_date.end() :].strip()
        if not after_date:
            return None

        tokens = [tok for tok in after_date.split() if tok != "$"]
        if not tokens:
            return None

        amount_indices: list[int] = []
        amount_values: list[float] = []
        for idx, token in enumerate(tokens):
            parsed = self._parse_amount_token(token)
            if parsed is None:
                continue
            amount_indices.append(idx)
            amount_values.append(parsed)

        if not amount_values:
            return None

        first_amount_idx = amount_indices[0]
        head_tokens = tokens[:first_amount_idx]
        if head_tokens and re.fullmatch(r"\d{2,12}", head_tokens[0]):
            head_tokens = head_tokens[1:]
        descripcion = " ".join(head_tokens).strip()

        continuation_chunks: list[str] = []
        for segment in segments[1:]:
            clean = segment.strip()
            if not clean or self.is_footer_line(clean):
                continue
            if re.fullmatch(r"\d{2}/\d{2}/\d{2,4}", clean):
                continue
            continuation_chunks.append(clean)
        if continuation_chunks:
            descripcion = f"{descripcion} {' '.join(continuation_chunks)}".strip()
        descripcion = " ".join(descripcion.split())
        if not descripcion:
            descripcion = "(sin descripcion)"

        movement: float | None = None
        explicit_debito: float | None = None
        explicit_credito: float | None = None
        saldo: float | None = None

        if len(amount_values) >= 3:
            explicit_debito = self._to_positive_or_none(amount_values[-3])
            explicit_credito = self._to_positive_or_none(amount_values[-2])
            saldo = amount_values[-1]
        elif len(amount_values) == 2:
            movement = abs(amount_values[-2])
            saldo = amount_values[-1]
        elif len(amount_values) == 1:
            movement = abs(amount_values[-1])

        return {
            "fecha": fecha,
            "descripcion": descripcion,
            "movement": movement,
            "explicit_debito": explicit_debito,
            "explicit_credito": explicit_credito,
            "saldo": saldo,
        }

    def _resolve_sides(
        self,
        *,
        movement: float | None,
        explicit_debito: float | None,
        explicit_credito: float | None,
        saldo: float | None,
        prev_saldo: float | None,
        descripcion: str,
    ) -> tuple[float | None, float | None]:
        if explicit_debito is not None or explicit_credito is not None:
            return explicit_debito, explicit_credito
        if movement is None:
            return None, None

        if prev_saldo is not None and saldo is not None:
            delta = saldo - prev_saldo
            if abs(delta - movement) <= 0.05:
                return None, movement
            if abs(delta + movement) <= 0.05:
                return movement, None

        upper = self._normalize_text(descripcion)
        if any(keyword in upper for keyword in self._credit_keywords):
            return None, movement
        if any(keyword in upper for keyword in self._debit_keywords):
            return movement, None
        return movement, None

    def _description_looks_truncated(self, description: str) -> bool:
        if not description:
            return False
        # En credicoop2 abundan abreviaciones validas al final (ej: "S A", "DE J").
        return description.endswith(("-", "/", ":"))

    def _normalize_date(self, value: str) -> str:
        clean = value.strip()
        m = re.fullmatch(r"(\d{2}/\d{2})/(\d{2})", clean)
        if m:
            return f"{m.group(1)}/20{m.group(2)}"
        return clean

    def _parse_amount_token(self, token: str) -> float | None:
        candidate = token.strip().replace("$", "").replace("−", "-").replace("âˆ’", "-")
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


