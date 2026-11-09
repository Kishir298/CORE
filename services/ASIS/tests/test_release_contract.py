"""Command-release regressions; protocol servers are simulations, not real models."""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
from dataclasses import replace
from unittest.mock import Mock

import pytest

from asis.configuration.settings import load_settings


PARTS = ("DATA", "CONFIG", "CACHE", "LOG", "MEMORY", "RUNTIME")


def test_all_profile_paths_and_direct_helpers(tmp_path, monkeypatch):
    from asis.configuration import paths
    for part in PARTS:
        monkeypatch.setenv(f"ASIS_{part}_DIRECTORY", str(tmp_path / part))
    s = load_settings()
    for name, part in zip(("data", "config", "cache", "logs", "memory", "runtime"), PARTS):
        assert getattr(s.paths, name) == tmp_path / part
    assert paths.get_config_directory() == tmp_path / "CONFIG"
    assert paths.get_memory_directory() == tmp_path / "MEMORY"
    from asis.tui.config import get_tui_config_path
    assert get_tui_config_path().parent == tmp_path / "CONFIG"


def test_data_root_derives_unset_paths(tmp_path, monkeypatch):
    for part in PARTS:
        monkeypatch.delenv(f"ASIS_{part}_DIRECTORY", raising=False)
    s = load_settings({"ASIS_DATA_DIRECTORY": str(tmp_path)})
    assert s.paths.config == tmp_path / "config"
    assert s.paths.memory == tmp_path / "memory"
    assert s.paths.runtime == tmp_path / "runtime"


def test_profile_does_not_load_shared_dotenv(tmp_path, monkeypatch):
    from asis.configuration import environment
    shared = tmp_path / "shared.env"
    shared.write_text("ASIS_AI_MODEL=shared-owner-model\n")
    config = tmp_path / "profile"
    config.mkdir()
    (config / ".env").write_text("ASIS_AI_MODEL=profile-model\n")
    monkeypatch.setattr(environment, "_PROJECT_ROOT_ENV_FILE", shared)
    monkeypatch.setenv("ASIS_CONFIG_DIRECTORY", str(config))
    monkeypatch.delenv("ASIS_AI_MODEL", raising=False)
    environment._load_env_files()
    assert os.environ["ASIS_AI_MODEL"] == "profile-model"


def test_unwritable_explicit_memory_never_falls_back(tmp_path):
    from asis.cli.main import build_memory
    marker = tmp_path / "file"
    marker.write_text("not a directory")
    with pytest.raises(OSError):
        build_memory(marker / "memory.db")
    assert marker.read_text() == "not a directory"


def test_general_mode_has_no_coding_capabilities(memory_manager):
    from asis.ai import AIManager
    from asis.ai.providers import MockAIProvider
    from asis.app.assistant import AssistantApp
    from asis.identity import build_identity
    app = AssistantApp(build_identity(), AIManager(MockAIProvider()), memory_manager, mode="general")
    assert not ({"run_command", "run_tests", "write_file", "ascs_run"} & set(app.tools_router.registry.list_names()))
    result = app.tools_router.execute("run_command", argv=["python", "-c", "raise Exception"])
    assert not result.success


def test_doctor_is_offline_and_reports_local_persistence(monkeypatch, capsys):
    from asis.cli.maintenance import run_maintenance
    monkeypatch.setattr(socket, "create_connection", Mock(side_effect=AssertionError("network forbidden")))
    assert run_maintenance(["doctor", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["model_check"] == "not requested"
    assert "local SQLite" in data["persistence"]
    socket.create_connection.assert_not_called()


def test_setup_preserves_existing_config_and_never_downloads(tmp_path, monkeypatch):
    from asis.cli import maintenance
    s = replace(maintenance.settings, paths=replace(maintenance.settings.paths,
        **{name: tmp_path / name for name in ("data", "config", "cache", "logs", "memory", "runtime")}))
    monkeypatch.setattr(maintenance, "settings", s)
    monkeypatch.setattr(socket, "create_connection", Mock(side_effect=AssertionError("network forbidden")))
    assert maintenance.run_maintenance(["setup", "--model", "local:installed"]) == 0
    config = s.paths.config / ".env"
    original = config.read_bytes()
    assert b"ASIS_CORE_ENABLED=false" in original
    assert maintenance.run_maintenance(["setup", "--model", "different"]) == 0
    assert config.read_bytes() == original


@pytest.mark.parametrize("target", ["win32", "darwin", "linux"])
def test_ollama_process_os_adapters(target, monkeypatch):
    from asis.ai import ollama_lifecycle as life
    monkeypatch.setattr(sys, "platform", target)
    monkeypatch.setattr(life.shutil, "which", lambda name: "/tools/ollama")
    popen = Mock()
    monkeypatch.setattr(life.subprocess, "Popen", popen)
    life._launch_serve("127.0.0.1:11434")
    args, kwargs = popen.call_args
    assert args[0] == ["/tools/ollama", "serve"]
    assert kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
    if target == "win32":
        assert "creationflags" in kwargs and "start_new_session" not in kwargs
    else:
        assert kwargs["start_new_session"] is True


@pytest.mark.parametrize("endpoint,bind", [("https://remote.example:11434", "127.0.0.1:11434"),
                                             ("http://127.0.0.1:11434", "0.0.0.0:11434")])
def test_no_remote_substitution_or_automatic_public_bind(endpoint, bind):
    from asis.ai.ollama_lifecycle import ensure_ollama, OllamaLifecycleError
    spawn = Mock()
    with pytest.raises(OllamaLifecycleError):
        ensure_ollama(endpoint, bind_host=bind, available_fn=lambda: False, popen_factory=spawn)
    spawn.assert_not_called()


def test_stream_error_never_restarts_as_success(memory_manager):
    from asis.ai import AIManager
    from asis.ai.providers import MockAIProvider
    from asis.app.assistant import AssistantApp
    from asis.identity import build_identity
    app = AssistantApp(build_identity(), AIManager(MockAIProvider()), memory_manager)
    app.engine.generate_streamed = Mock(side_effect=RuntimeError("broken stream"))
    app.engine.generate = Mock()
    with pytest.raises(RuntimeError, match="broken stream"):
        app._generate_text([], on_chunk=lambda x: None)
    app.engine.generate.assert_not_called()


def test_termination_handler_returns_cancelled_and_restores(monkeypatch):
    from asis.cli import main
    before = signal.getsignal(signal.SIGTERM)
    def task(argv):
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    monkeypatch.setattr(main, "_entry", task)
    assert main.entry([]) == 130
    assert signal.getsignal(signal.SIGTERM) == before


def test_core_disabled_never_constructs_adapter(monkeypatch):
    from asis.cli.main import build_core_manager
    from asis.integrations.core import adapter
    spy = Mock(side_effect=AssertionError("recursive CORE connection"))
    monkeypatch.setattr(adapter, "RealCoreAdapter", spy)
    s = load_settings({"ASIS_CORE_ENABLED": "false"})
    assert build_core_manager(s) is None
    spy.assert_not_called()


def test_real_voice_failure_is_not_replaced_by_mock(monkeypatch, capsys):
    from asis.cli.main import _build_interactive_pipeline
    from asis.voice import factory
    monkeypatch.setattr(factory, "create_audio_input", Mock(side_effect=RuntimeError("missing microphone")))
    assert _build_interactive_pipeline() is None
    assert "Voice unavailable: missing microphone" in capsys.readouterr().err


def test_stt_runtime_uses_installed_weights_only(monkeypatch):
    from types import SimpleNamespace
    factory = Mock()
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=factory))
    from asis.voice.speech.speech_to_text import SpeechTranscriber
    SpeechTranscriber(model_size="small")
    assert factory.call_args.kwargs["local_files_only"] is True


def test_speaker_requires_prepared_local_source(monkeypatch):
    from types import ModuleType
    package = ModuleType("speechbrain")
    inference = ModuleType("speechbrain.inference")
    speaker = ModuleType("speechbrain.inference.speaker")
    factory = Mock()
    speaker.EncoderClassifier = type("Encoder", (), {"from_hparams": factory})
    for name, module in (("speechbrain", package), ("speechbrain.inference", inference),
                         ("speechbrain.inference.speaker", speaker)):
        monkeypatch.setitem(sys.modules, name, module)
    from asis.voice.speaker.embeddings import SpeechBrainEmbeddingProvider
    with pytest.raises(Exception, match="MODEL_NOT_INSTALLED"):
        SpeechBrainEmbeddingProvider(model="not-an-installed-directory")
    factory.assert_not_called()
