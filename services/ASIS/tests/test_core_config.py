"""C.O.R.E. configuration: centralized, validated, standalone by default.

Uses the canonical ``load_settings(env=...)`` API: present-but-invalid
values raise ``ConfigurationError`` (never silent); empty counts as unset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from asis.configuration.settings import load_settings
from asis.errors import ConfigurationError

CORE_KEYS = (
    "ASIS_CORE_ENABLED",
    "ASIS_CORE_HOST",
    "ASIS_CORE_PORT",
    "ASIS_CORE_DEVICE_FILE",
    "ASIS_CORE_CA_FILE",
    "ASIS_CORE_INSECURE",
    "ASIS_CORE_CONNECT_TIMEOUT",
    "ASIS_CORE_REQUEST_TIMEOUT",
    "ASIS_CORE_RECONNECT_ENABLED",
    "ASIS_CORE_RECONNECT_DELAY",
)


def test_core_defaults_standalone(monkeypatch):
    for key in CORE_KEYS:
        monkeypatch.delenv(key, raising=False)
    core = load_settings().core
    assert core.enabled is False
    assert core.host == "127.0.0.1"
    assert core.port == 5000
    assert core.device_file == ""
    assert core.ca_file == ""
    assert core.insecure is False
    assert core.connect_timeout == 10
    assert core.request_timeout == 30
    assert core.reconnect_enabled is True
    assert core.reconnect_delay == 5


def test_core_env_overrides():
    core = load_settings(
        env={
            "ASIS_CORE_ENABLED": "true",
            "ASIS_CORE_HOST": "192.168.1.10",
            "ASIS_CORE_PORT": "5001",
            "ASIS_CORE_INSECURE": "yes",
            "ASIS_CORE_CONNECT_TIMEOUT": "7",
            "ASIS_CORE_REQUEST_TIMEOUT": "45",
            "ASIS_CORE_RECONNECT_ENABLED": "0",
            "ASIS_CORE_RECONNECT_DELAY": "2",
        }
    ).core
    assert core.enabled is True
    assert core.host == "192.168.1.10"
    assert core.port == 5001
    assert core.insecure is True
    assert core.connect_timeout == 7
    assert core.request_timeout == 45
    assert core.reconnect_enabled is False
    assert core.reconnect_delay == 2


def test_invalid_port_raises():
    for bad in ("abc", "0", "-1", "99999"):
        with pytest.raises(ConfigurationError):
            load_settings(env={"ASIS_CORE_PORT": bad})


def test_invalid_timeouts_raise():
    with pytest.raises(ConfigurationError):
        load_settings(env={"ASIS_CORE_CONNECT_TIMEOUT": "0"})
    with pytest.raises(ConfigurationError):
        load_settings(env={"ASIS_CORE_REQUEST_TIMEOUT": "never"})
    with pytest.raises(ConfigurationError):
        load_settings(env={"ASIS_CORE_RECONNECT_DELAY": "9999"})
    with pytest.raises(ConfigurationError):
        load_settings(env={"ASIS_CORE_ENABLED": "maybe"})


def test_empty_values_count_as_unset():
    core = load_settings(env={"ASIS_CORE_HOST": "   ", "ASIS_CORE_PORT": ""}).core
    assert core.host == "127.0.0.1"
    assert core.port == 5000


def test_invalid_host_and_paths_raise():
    with pytest.raises(ConfigurationError):
        load_settings(env={"ASIS_CORE_HOST": "bad\x00host"})
    with pytest.raises(ConfigurationError):
        load_settings(env={"ASIS_CORE_CA_FILE": "ca\x00.pem"})
    with pytest.raises(ConfigurationError):
        load_settings(env={"ASIS_CORE_DEVICE_FILE": "dev\x00.json"})


def test_env_example_documents_core_keys():
    example = Path(__file__).resolve().parents[1] / ".env.example"
    assert example.exists()
    text = example.read_text()
    for key in (
        "ASIS_CORE_ENABLED",
        "ASIS_CORE_HOST",
        "ASIS_CORE_PORT",
        "ASIS_CORE_REQUEST_TIMEOUT",
    ):
        assert key in text
    assert "credential" not in text.lower() or "runtime-only" in text.lower()
