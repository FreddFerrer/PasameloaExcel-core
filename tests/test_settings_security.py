from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_rejects_non_positive_rate_limit_requests() -> None:
    with pytest.raises(ValidationError):
        Settings(rate_limit_requests=0)


def test_settings_rejects_non_positive_rate_limit_window() -> None:
    with pytest.raises(ValidationError):
        Settings(rate_limit_window_seconds=0)
