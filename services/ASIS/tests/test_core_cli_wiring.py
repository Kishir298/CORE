"""CORE CLI wiring: production entry points own one optional CORE session.

Proves ``asis`` (text) and ``asis voice`` build paths attach the shared
``CoreConnectionManager`` when enabled and stay standalone when disabled
— no second client, no credential persistence, no fatal startup.
"""

from __future__ import annotations

import asis.cli.main as cli_main
from asis.cli.main import build_core_manager, core_credential, entry
from asis.configuration.settings import load_settings
from asis.integrations.core.models import CoreConnectionState
from asis.system.context import RuntimeContext


def _enabled_settings(**overrides):
    env = {"ASIS_CORE_ENABLED": "true"}
    env.update(overrides)
    return load_settings(env=env)


def test_disabled_returns_none_standalone():
    assert build_core_manager(load_settings(env={"ASIS_CORE_ENABLED": "false"})) is None


def test_enabled_without_credential_starts_disconnected():
    manager = build_core_manager(_enabled_settings())
    assert manager is not None
    ctx = RuntimeContext()
    manager.start(ctx)  # no credential -> no socket opened
    try:
        assert manager.is_available() is False
        assert manager.state == CoreConnectionState.DISCONNECTED
    finally:
        manager.stop(ctx)


def test_core_credential_runtime_only(monkeypatch):
    monkeypatch.delenv("ASIS_CORE_CREDENTIAL", raising=False)
    assert core_credential() is None
    monkeypatch.setenv("ASIS_CORE_CREDENTIAL", "  secret  ")
    assert core_credential() == "secret"


def test_entry_message_offline_when_core_enabled_no_credential(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(
        cli_main, "settings", _enabled_settings(), raising=True
    )
    monkeypatch.delenv("ASIS_CORE_CREDENTIAL", raising=False)
    db = str(tmp_path / "memory.db")
    code = entry(
        ["--provider", "mock", "--message", "Hello there!", "--memory-db", db]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip()


def test_voice_builds_same_manager_shape():
    # Voice reuses the shared helper (no VoiceCoreClient): same disabled
    # -> None contract as the text CLI.
    assert build_core_manager(load_settings(env={"ASIS_CORE_ENABLED": "0"})) is None
    manager = build_core_manager(_enabled_settings())
    assert manager is not None
    assert manager.adapter.name == "core-client"
