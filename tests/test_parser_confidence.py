from __future__ import annotations

from app.parsing.contaapp_adapter import ContaAppParsingAdapter


def test_confidence_not_flat_when_row_is_clean() -> None:
    adapter = ContaAppParsingAdapter()
    score = adapter._estimate_confidence(
        fecha="01/04/2026",
        description="Pago proveedor",
        amount_count=3,
        line_count=1,
        description_has_amount_noise=False,
        description_looks_truncated=False,
    )
    assert score == 1.0


def test_confidence_penalizes_multiline_and_amount_noise() -> None:
    adapter = ContaAppParsingAdapter()
    score = adapter._estimate_confidence(
        fecha="01/04/2026",
        description="Convenios 128.988,46",
        amount_count=3,
        line_count=2,
        description_has_amount_noise=True,
        description_looks_truncated=False,
    )
    assert score < 0.95


def test_confidence_penalizes_probable_truncated_description() -> None:
    adapter = ContaAppParsingAdapter()
    score = adapter._estimate_confidence(
        fecha="01/04/2026",
        description="Transferencia debin Distinto T",
        amount_count=3,
        line_count=1,
        description_has_amount_noise=False,
        description_looks_truncated=True,
    )
    assert score < 0.95

