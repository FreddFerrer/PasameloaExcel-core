from __future__ import annotations

from dataclasses import dataclass

from app.parsing.templates.base_template import ParsingTemplate
from app.parsing.templates.credicoop1 import Credicoop1Template
from app.parsing.templates.credicoop2 import Credicoop2Template
from app.parsing.templates.formosa1 import Formosa1Template
from app.parsing.templates.galicia1 import Galicia1Template
from app.parsing.templates.generic_template import GenericTemplate
from app.parsing.templates.nacion1 import Nacion1Template
from app.parsing.templates.nacion2 import Nacion2Template
from app.parsing.templates.nbch1 import Nbch1Template
from app.parsing.templates.nbch2 import Nbch2Template
from app.parsing.templates.santander1 import Santander1Template
from app.parsing.types import TemplateContext


@dataclass(slots=True)
class TemplateSelection:
    template: ParsingTemplate
    score: float


class TemplateSelector:
    def __init__(self, templates: list[ParsingTemplate]) -> None:
        self.templates = sorted(templates, key=lambda template: template.priority, reverse=True)

    def select(self, context: TemplateContext) -> TemplateSelection:
        best_template = None
        best_score = -1.0
        for template in self.templates:
            score = template.match_score(context)
            if score > best_score:
                best_template = template
                best_score = score
        if best_template is None:
            fallback = GenericTemplate()
            return TemplateSelection(template=fallback, score=0.0)
        return TemplateSelection(template=best_template, score=max(best_score, 0.0))


def build_default_templates() -> list[ParsingTemplate]:
    return [
        Credicoop2Template(),
        Santander1Template(),
        Credicoop1Template(),
        Nbch2Template(),
        Nacion2Template(),
        Nacion1Template(),
        Formosa1Template(),
        Galicia1Template(),
        Nbch1Template(),
        GenericTemplate(),
    ]

