from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

from app.parsing.templates import TemplateSelector, build_default_templates
from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import CandidateRow, ParseExecution, ParsedMovement, RowTrace, TemplateContext


DATE_PREFIX_RE = re.compile(r"^\s*(\d{2}/\d{2}(?:\s*/\s*\d{2,4})?)\b")
logger = logging.getLogger(__name__)


class ContaAppParsingAdapter:
    """Adapter local basado en pdfplumber con aislamiento por template."""

    def __init__(
        self,
        *,
        issue_row_confidence_threshold: float = 0.8,
        template_selector: TemplateSelector | None = None,
    ) -> None:
        self.issue_row_confidence_threshold = issue_row_confidence_threshold
        self.template_selector = template_selector or TemplateSelector(build_default_templates())

    def parse(self, pdf_path: Path) -> ParseExecution:
        pages = self._extract_page_lines(pdf_path)
        context = self._build_context(pdf_path=pdf_path, pages=pages)
        selection = self.template_selector.select(context)
        template = selection.template
        logger.info(
            "template_match filename=%s template=%s score=%.3f bank_hint=%s pages=%d",
            pdf_path.name,
            template.template_id,
            selection.score,
            template.bank_hint or "unknown",
            len(pages),
        )

        candidates = self._collect_candidates(pages, template=template, context=context)
        rows: list[ParsedMovement] = []
        traces: list[RowTrace] = []
        for candidate in candidates:
            parsed = self._candidate_to_row(candidate)
            if parsed is None:
                continue
            row, trace = parsed
            rows.append(row)
            traces.append(trace)

        template.postprocess_rows(rows, traces, context)
        self._apply_template_confidence_adjustments(rows=rows, traces=traces, template=template, context=context)

        parse_status = "ok_auto" if rows else "no_rows"
        global_conf = round(sum(row.confianza for row in rows) / len(rows), 3) if rows else 0.0
        field_confidence = {
            "fecha": global_conf,
            "descripcion": global_conf,
            "debito": global_conf,
            "credito": global_conf,
            "saldo": global_conf,
        }

        return ParseExecution(
            rows=rows,
            bank_detected=template.bank_hint,
            template_detected=template.template_id,
            template_confidence=selection.score,
            parser_mode="pdfplumber_local",
            parse_status=parse_status,
            global_confidence=global_conf,
            field_confidence=field_confidence,
            row_traces=traces,
        )

    def _build_context(self, *, pdf_path: Path, pages: list[dict]) -> TemplateContext:
        first_lines = pages[0]["lines"] if pages else []
        first_page_text = "\n".join(first_lines[:80])
        return TemplateContext(
            pdf_path=pdf_path,
            pages=pages,
            file_stem=pdf_path.stem,
            first_page_text=first_page_text,
        )

    def _extract_page_lines(self, pdf_path: Path) -> list[dict]:
        pages: list[dict] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                words = page.extract_words(
                    keep_blank_chars=False,
                    use_text_flow=True,
                    x_tolerance=2,
                    y_tolerance=3,
                )
                lines = self._words_to_lines(words)
                pages.append({"page_num": page_num, "lines": lines})
        return pages

    def _words_to_lines(self, words: list[dict]) -> list[str]:
        if not words:
            return []
        buckets: dict[int, list[dict]] = defaultdict(list)
        for word in words:
            top = float(word.get("top", 0.0))
            bucket = int(round(top / 2.0))
            buckets[bucket].append(word)

        lines: list[str] = []
        for key in sorted(buckets):
            ordered = sorted(buckets[key], key=lambda item: float(item.get("x0", 0.0)))
            text = " ".join(str(item.get("text", "")).strip() for item in ordered if str(item.get("text", "")).strip())
            compact = self._compact_space(text)
            if compact:
                lines.append(compact)
        return lines

    def _collect_candidates(
        self,
        pages: list[dict],
        *,
        template: ParsingTemplate,
        context: TemplateContext,
    ) -> list[CandidateRow]:
        custom_candidates = template.collect_candidates(pages, context)
        if custom_candidates is not None:
            return custom_candidates

        out: list[CandidateRow] = []
        for page in pages:
            page_num = int(page.get("page_num") or 1)
            lines = [self._compact_space(line) for line in page.get("lines", []) if self._compact_space(line)]
            i = 0
            while i < len(lines):
                line = lines[i]
                if not DATE_PREFIX_RE.match(line):
                    i += 1
                    continue

                parts = [line]
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if DATE_PREFIX_RE.match(nxt):
                        if template.should_attach_continuation(parts[0], nxt):
                            parts.append(nxt)
                            j += 1
                            continue
                        break
                    if template.is_footer_line(nxt):
                        break
                    if template.should_attach_continuation(parts[0], nxt):
                        parts.append(nxt)
                        j += 1
                        continue
                    break

                out.append(CandidateRow(page=page_num, raw_text=" | ".join(parts), line_count=len(parts)))
                i = j
        return out

    def _candidate_to_row(self, candidate: CandidateRow) -> tuple[ParsedMovement, RowTrace] | None:
        raw_text = candidate.raw_text
        match = DATE_PREFIX_RE.match(raw_text)
        if not match:
            return None
        fecha = match.group(1)

        amount_tokens = self._extract_tail_amount_tokens(raw_text)
        values = [self._parse_amount_token(tok) for tok in amount_tokens]
        values = [val for val in values if val is not None]
        debito, credito, saldo = self._map_amounts(values)

        description = DATE_PREFIX_RE.sub("", raw_text, count=1).strip()
        description = re.sub(r"^\s*\d{3,8}\s+", "", description, count=1)
        description = self._remove_amount_suffix(description, amount_tokens)
        description = self._compact_space(description.replace("|", " "))
        if not description:
            description = "(sin descripcion)"

        confidence_has_amount_noise = self._description_contains_amount_noise(description)
        description_looks_truncated = self._description_looks_truncated(description)
        confianza = self._estimate_confidence(
            fecha=fecha,
            description=description,
            amount_count=len(values),
            line_count=candidate.line_count,
            description_has_amount_noise=confidence_has_amount_noise,
            description_looks_truncated=description_looks_truncated,
        )
        issues: list[str] = []
        if candidate.line_count > 1:
            issues.append("descripcion_multilinea")
        if description_looks_truncated:
            issues.append("descripcion_truncada_probable")
        if confianza < self.issue_row_confidence_threshold:
            issues.append("low_confidence")

        row = ParsedMovement(
            fecha=fecha,
            descripcion=description,
            debito=debito,
            credito=credito,
            saldo=saldo,
            pagina=candidate.page,
            confianza=confianza,
            confianza_campos={},
        )
        trace = RowTrace(raw_preview=raw_text, issues=issues)
        return row, trace

    def _apply_template_confidence_adjustments(
        self,
        *,
        rows: list[ParsedMovement],
        traces: list[RowTrace],
        template: ParsingTemplate,
        context: TemplateContext,
    ) -> None:
        for idx, row in enumerate(rows):
            trace = traces[idx] if idx < len(traces) else RowTrace(raw_preview=None, issues=[])
            override_confidence = template.compute_row_confidence(row=row, trace=trace, context=context)
            if override_confidence is not None:
                row.confianza = round(max(0.0, min(1.0, float(override_confidence))), 3)
            else:
                delta = template.adjust_row_confidence(row=row, trace=trace, context=context)
                if abs(delta) > 1e-9:
                    row.confianza = round(max(0.0, min(1.0, row.confianza + delta)), 3)

            if row.confianza < self.issue_row_confidence_threshold:
                if "low_confidence" not in trace.issues:
                    trace.issues.append("low_confidence")
            else:
                trace.issues = [issue for issue in trace.issues if issue != "low_confidence"]

            if self._description_looks_truncated(row.descripcion):
                if "descripcion_truncada_probable" not in trace.issues:
                    trace.issues.append("descripcion_truncada_probable")
            else:
                trace.issues = [issue for issue in trace.issues if issue != "descripcion_truncada_probable"]

    def _extract_tail_amount_tokens(self, text: str) -> list[str]:
        tokens = text.split()
        collected: list[str] = []
        for token in reversed(tokens):
            if self._looks_like_amount(token):
                collected.append(token)
                continue
            if collected:
                break
        return list(reversed(collected))

    def _remove_amount_suffix(self, text: str, amount_tokens: list[str]) -> str:
        trimmed = text
        for token in reversed(amount_tokens):
            if trimmed.endswith(token):
                trimmed = trimmed[: -len(token)].rstrip()
        return trimmed

    def _map_amounts(self, values: list[float]) -> tuple[float | None, float | None, float | None]:
        if not values:
            return None, None, None
        if len(values) >= 3:
            deb = self._positive_or_none(values[-3])
            cred = self._positive_or_none(values[-2])
            return deb, cred, values[-1]
        if len(values) == 2:
            movement, saldo = values
            if movement < 0:
                return abs(movement), None, saldo
            if movement > 0:
                return None, movement, saldo
            return None, None, saldo
        movement = values[0]
        if movement < 0:
            return abs(movement), None, None
        if movement > 0:
            return None, movement, None
        return None, None, None

    def _estimate_confidence(
        self,
        *,
        fecha: str | None,
        description: str,
        amount_count: int,
        line_count: int,
        description_has_amount_noise: bool,
        description_looks_truncated: bool,
    ) -> float:
        score = 0.58
        if fecha:
            score += 0.15
        if description and description != "(sin descripcion)":
            score += 0.12
        if amount_count >= 1:
            score += 0.08
        if amount_count >= 2:
            score += 0.04
        if amount_count >= 3:
            score += 0.03
        if line_count > 1:
            score -= 0.07
        if description_has_amount_noise:
            score -= 0.10
        if description_looks_truncated:
            score -= 0.14
        return round(max(0.0, min(score, 1.0)), 3)

    def _description_contains_amount_noise(self, description: str) -> bool:
        if not description:
            return False
        return any(self._looks_like_amount(token) for token in description.split())

    def _description_looks_truncated(self, description: str) -> bool:
        if not description:
            return False
        tokens = description.strip().split()
        if not tokens:
            return False
        last = tokens[-1]
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", last):
            return True
        if description.strip().endswith(("-", "/", ":")):
            return True
        return False

    def _parse_amount_token(self, token: str) -> float | None:
        normalized = token.strip().replace("$", "").replace("−", "-")
        if not normalized:
            return None
        sign = 1.0
        if normalized.endswith("-"):
            sign = -1.0
            normalized = normalized[:-1]
        if normalized.startswith("-"):
            sign = -1.0
            normalized = normalized[1:]
        normalized = normalized.replace(".", "").replace(",", ".")
        try:
            return sign * float(normalized)
        except ValueError:
            return None

    def _looks_like_amount(self, token: str) -> bool:
        value = token.strip().replace("−", "-").replace("$", "")
        if not value or "/" in value:
            return False
        if "," not in value and "." not in value:
            return False
        return re.fullmatch(r"-?\d[\d\.,]*-?", value) is not None

    def _positive_or_none(self, value: float) -> float | None:
        if abs(value) < 1e-9:
            return None
        return abs(value)

    def _compact_space(self, text: str) -> str:
        return " ".join(str(text).split())

