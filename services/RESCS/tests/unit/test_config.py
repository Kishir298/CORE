"""Configuration tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rescs.config import Settings


def test_defaults_and_env_mapping(settings: Settings):
    assert settings.app_name == "RESCS"
    assert settings.environment == "test"
    assert settings.api_key == "test-api-key-0123456789abcdef"
    assert settings.database_url == "sqlite+pysqlite:///:memory:"
    assert settings.storage_dir == "rescs_test_storage"
    assert settings.log_level == "WARNING"


def test_api_key_is_required(monkeypatch):
    monkeypatch.delenv("RESCS_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_api_key_minimum_length(monkeypatch):
    monkeypatch.setenv("RESCS_API_KEY", "short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_unknown_environment_rejected(monkeypatch):
    monkeypatch.setenv("RESCS_ENV", "staging")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_log_level_rejected(monkeypatch):
    monkeypatch.setenv("RESCS_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_explicit_values_win(monkeypatch):
    monkeypatch.setenv("RESCS_ENV", "production")
    settings = Settings(_env_file=None)
    assert settings.environment == "production"
