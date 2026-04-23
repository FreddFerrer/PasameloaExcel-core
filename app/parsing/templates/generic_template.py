from __future__ import annotations

import re

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.types import TemplateContext


class GenericTemplate(ParsingTemplate):
    template_id = "generic_auto"
    bank_hint = None
    priority = 1

    def match_score(self, context: TemplateContext) -> float:
        return 0.01

    def should_attach_continuation(self, first_line: str, candidate_line: str) -> bool:
        if self.is_footer_line(candidate_line):
            return False
        if re.match(r"^\s*\d{2}/\d{2}/\d{2,4}\b", candidate_line):
            return False

        upper = candidate_line.upper()
        if re.search(r"\b(TARJ:|TERM:|CUIT|CUIL)\b", upper):
            return True
        if re.match(r"^\d{8,}[\-−][A-Z]", upper):
            return True
        return False

