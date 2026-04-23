from __future__ import annotations

from app.core.config import Settings


def test_settings_parse_cors_origins_from_csv() -> None:
    settings = Settings(
        cors_allowed_origins="https://a.example.com, https://b.example.com",
    )
    assert settings.cors_allowed_origins == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_settings_parse_cors_origins_from_json_array() -> None:
    settings = Settings(
        cors_allowed_origins='["https://a.example.com", "https://b.example.com"]',
    )
    assert settings.cors_allowed_origins == [
        "https://a.example.com",
        "https://b.example.com",
    ]
