"""Configuration subsystem tests: defaults, overrides, precedence,
strict parsing, validation, paths, voice sections, isolation.

No Ollama, audio hardware, GPU, internet, CORE, or RESCS required.
"""

import dataclasses
import os
from pathlib import Path

import pytest

from asis.configuration import environment as env_module
from asis.configuration import load_settings, settings
from asis.configuration import paths as paths_module
from asis.errors import ConfigurationError


def _clean(*names):
    for name in names:
        os.environ.pop(name, None)


@pytest.fixture(autouse=True)
def _isolated_env():
    # NOTE: must NOT request `monkeypatch` here, or this teardown would run
    # before monkeypatch.undo() and falsely report leaks.
    yield
    # Guard: no test may leak ASIS_* variables.
    leaked = [k for k in os.environ if k.startswith("ASIS_")]
    assert leaked == [], f"leaked environment variables: {leaked}"


# ---- defaults ----


def test_defaults_load_without_environment(monkeypatch):
    for key in list(os.environ):
        if key.startswith("ASIS_"):
            monkeypatch.delenv(key, raising=False)
    config = load_settings()
    assert config.ai.provider == "ollama"
    assert config.ai.model == "qwen3:14b"
    assert config.ai.endpoint == "http://127.0.0.1:11434"
    assert config.ai.request_timeout == 120
    assert config.ai.temperature == 0.7
    assert config.ai.max_context_messages == 20
    assert config.ai.context_char_limit == 12_000
    assert config.conversation.max_history == 20
    assert config.network.timeout == 10
    assert config.network.retries == 3
    assert config.tools.timeout == 30
    assert config.security.require_confirmation_for_dangerous is True
    assert config.memory.provider == "local"
    assert config.memory.database_name == "memory.db"
    assert config.voice.sample_rate == 16_000
    assert config.voice.channels == 1
    assert config.voice.block_size == 1_024
    assert config.voice.input_engine == "mock"
    assert config.voice.output_engine == "mock"
    assert config.voice.wake_word == "hey asis"
    assert config.voice.stt.engine == "mock"
    assert config.voice.stt.model == "small"
    assert config.voice.tts.engine == "mock"
    assert config.voice.speaker.engine == "mock"
    assert config.voice.speaker.model == "speechbrain/spkrec-ecapa-voxceleb"
    assert config.voice.speaker.device == "cpu"
    assert config.voice.wake.engine == "mock"
    assert config.voice.vad.engine == "mock"
    assert config.runtime.shutdown_timeout == 10
    assert config.runtime.log_level == "INFO"
    assert config.app_name == "A.S.I.S."
    assert config.app_version == "0.1.0"


def test_global_singleton_matches_default_load():
    assert settings.ai.model == load_settings().ai.model
    assert settings.voice.wake_word == "hey asis"


# ---- environment overrides per category ----


def test_ai_overrides(monkeypatch):
    monkeypatch.setenv("ASIS_AI_PROVIDER", "mock")
    monkeypatch.setenv("ASIS_AI_MODEL", "test-model")
    monkeypatch.setenv("ASIS_AI_ENDPOINT", "http://localhost:9999")
    monkeypatch.setenv("ASIS_AI_REQUEST_TIMEOUT", "30")
    monkeypatch.setenv("ASIS_AI_TEMPERATURE", "0.1")
    monkeypatch.setenv("ASIS_AI_MAX_CONTEXT_MESSAGES", "5")
    monkeypatch.setenv("ASIS_AI_CONTEXT_CHAR_LIMIT", "500")
    config = load_settings()
    assert config.ai.provider == "mock"
    assert config.ai.model == "test-model"
    assert config.ai.endpoint == "http://localhost:9999"
    assert config.ai.request_timeout == 30
    assert config.ai.temperature == 0.1
    assert config.ai.max_context_messages == 5
    assert config.ai.context_char_limit == 500


def test_conversation_network_tools_security_overrides(monkeypatch):
    monkeypatch.setenv("ASIS_CONVERSATION_MAX_HISTORY", "7")
    monkeypatch.setenv("ASIS_NETWORK_TIMEOUT", "3")
    monkeypatch.setenv("ASIS_NETWORK_RETRIES", "2")
    monkeypatch.setenv("ASIS_TOOL_TIMEOUT", "9")
    monkeypatch.setenv("ASIS_CONFIRM_DANGEROUS_TOOLS", "no")
    config = load_settings()
    assert config.conversation.max_history == 7
    assert config.network.timeout == 3
    assert config.network.retries == 2
    assert config.tools.timeout == 9
    assert config.security.require_confirmation_for_dangerous is False


def test_memory_overrides(monkeypatch):
    monkeypatch.setenv("ASIS_MEMORY_DATABASE_NAME", "test-mem.db")
    config = load_settings()
    assert config.memory.database_name == "test-mem.db"


def test_voice_overrides(monkeypatch):
    monkeypatch.setenv("ASIS_VOICE_SAMPLE_RATE", "8000")
    monkeypatch.setenv("ASIS_VOICE_CHANNELS", "2")
    monkeypatch.setenv("ASIS_VOICE_BLOCK_SIZE", "512")
    monkeypatch.setenv("ASIS_VOICE_INPUT_ENGINE", "sounddevice")
    monkeypatch.setenv("ASIS_VOICE_OUTPUT_ENGINE", "sounddevice")
    monkeypatch.setenv("ASIS_VOICE_WAKE_WORD", "hello asis")
    monkeypatch.setenv("ASIS_VOICE_STT_ENGINE", "faster-whisper")
    monkeypatch.setenv("ASIS_VOICE_STT_MODEL", "tiny")
    monkeypatch.setenv("ASIS_VOICE_TTS_ENGINE", "pyttsx3")
    monkeypatch.setenv("ASIS_VOICE_TTS_VOICE", "test-voice")
    monkeypatch.setenv("ASIS_VOICE_SPEAKER_ENGINE", "embedding")
    monkeypatch.setenv("ASIS_VOICE_SPEAKER_THRESHOLD", "0.8")
    monkeypatch.setenv("ASIS_VOICE_WAKE_ENGINE", "openwakeword")
    monkeypatch.setenv("ASIS_VOICE_WAKE_THRESHOLD", "0.7")
    monkeypatch.setenv("ASIS_VOICE_VAD_ENGINE", "silero")
    monkeypatch.setenv("ASIS_VOICE_VAD_THRESHOLD", "0.6")
    config = load_settings()
    assert config.voice.sample_rate == 8000
    assert config.voice.channels == 2
    assert config.voice.block_size == 512
    assert config.voice.input_engine == "sounddevice"
    assert config.voice.output_engine == "sounddevice"
    assert config.voice.wake_word == "hello asis"
    assert config.voice.stt.engine == "faster-whisper"
    assert config.voice.stt.model == "tiny"
    assert config.voice.tts.engine == "pyttsx3"
    assert config.voice.tts.voice == "test-voice"
    assert config.voice.speaker.engine == "embedding"
    assert config.voice.speaker.threshold == 0.8
    assert config.voice.wake.engine == "openwakeword"
    assert config.voice.wake.threshold == 0.7
    assert config.voice.vad.engine == "silero"
    assert config.voice.vad.threshold == 0.6


def test_explicit_mapping_beats_process_environment(monkeypatch):
    monkeypatch.setenv("ASIS_AI_MODEL", "from-env")
    config = load_settings({"ASIS_AI_MODEL": "from-explicit"})
    assert config.ai.model == "from-explicit"
    # Process env still wins over defaults on the next plain load.
    assert load_settings().ai.model == "from-env"


# ---- precedence: env > .env > defaults ----


def test_dotenv_does_not_override_process_env(tmp_path):
    # Managed manually (no monkeypatch): finally-pop would fight
    # monkeypatch.undo() and resurrect the dotenv value.
    previous = os.environ.get("ASIS_AI_MODEL")
    dotenv = tmp_path / "precedence.env"
    dotenv.write_text("ASIS_AI_MODEL=from-dotenv\n", encoding="utf-8")
    try:
        assert env_module.load_env_file(dotenv, override=False) is True
        assert load_settings().ai.model == "from-dotenv"
        os.environ["ASIS_AI_MODEL"] = "from-process"
        assert load_settings().ai.model == "from-process"
    finally:
        if previous is None:
            os.environ.pop("ASIS_AI_MODEL", None)
        else:
            os.environ["ASIS_AI_MODEL"] = previous


def test_dotenv_missing_file_returns_false(tmp_path):
    assert env_module.load_env_file(tmp_path / "nope.env") is False


# ---- strict type parsing ----


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("enabled", True),
        ("TRUE", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("disabled", False),
    ],
)
def test_bool_vocabulary(monkeypatch, value, expected):
    monkeypatch.setenv("ASIS_DEBUG", value)
    assert load_settings().runtime.debug is expected


@pytest.mark.parametrize("value", ["maybe", "2", "yep", "nope", ""])
def test_bool_invalid_or_empty(monkeypatch, value):
    # Empty counts as unset -> default; anything else unrecognized -> error.
    monkeypatch.setenv("ASIS_DEBUG", value)
    if value == "":
        assert load_settings().runtime.debug is False
    else:
        with pytest.raises(ConfigurationError) as exc:
            load_settings()
        assert "ASIS_DEBUG" in str(exc.value)


@pytest.mark.parametrize(
    "variable",
    [
        "ASIS_AI_REQUEST_TIMEOUT",
        "ASIS_VOICE_SAMPLE_RATE",
        "ASIS_VOICE_CHANNELS",
        "ASIS_VOICE_BLOCK_SIZE",
        "ASIS_TOOL_TIMEOUT",
        "ASIS_NETWORK_TIMEOUT",
        "ASIS_SHUTDOWN_TIMEOUT",
    ],
)
def test_invalid_integers_raise(monkeypatch, variable):
    monkeypatch.setenv(variable, "abc")
    with pytest.raises(ConfigurationError) as exc:
        load_settings()
    assert variable in str(exc.value)
    assert "abc" in str(exc.value)


@pytest.mark.parametrize(
    "variable", ["ASIS_AI_TEMPERATURE", "ASIS_VOICE_WAKE_THRESHOLD"]
)
def test_invalid_floats_raise(monkeypatch, variable):
    monkeypatch.setenv(variable, "not-a-number")
    with pytest.raises(ConfigurationError):
        load_settings()


def test_empty_values_count_as_unset(monkeypatch):
    monkeypatch.setenv("ASIS_AI_MODEL", "   ")
    monkeypatch.setenv("ASIS_VOICE_WAKE_WORD", "")
    config = load_settings()
    assert config.ai.model == "qwen3:14b"
    assert config.voice.wake_word == "hey asis"


# ---- validation ----


def test_blank_provider_falls_back_to_default():
    # Empty counts as unset, so a blank provider yields the default.
    import dataclasses

    from asis.configuration.validation import validate_settings

    config = load_settings({"ASIS_AI_PROVIDER": "   "})
    assert config.ai.provider == "ollama"
    # ...while a programmatically blanked provider is still rejected.
    blanked = dataclasses.replace(
        config, ai=dataclasses.replace(config.ai, provider="  ")
    )
    with pytest.raises(ConfigurationError):
        validate_settings(blanked)


def test_bad_endpoint_rejected(monkeypatch):
    for bad in ["notaurl", "ftp://host", "http://", ""]:
        if bad == "":
            continue  # empty counts as unset, covered elsewhere
        monkeypatch.setenv("ASIS_AI_ENDPOINT", bad)
        with pytest.raises(ConfigurationError):
            load_settings()
    monkeypatch.setenv("ASIS_AI_ENDPOINT", "https://example.com:11434")
    assert load_settings().ai.endpoint == "https://example.com:11434"


def test_temperature_range(monkeypatch):
    monkeypatch.setenv("ASIS_AI_TEMPERATURE", "2.0")
    assert load_settings().ai.temperature == 2.0
    monkeypatch.setenv("ASIS_AI_TEMPERATURE", "2.1")
    with pytest.raises(ConfigurationError):
        load_settings()
    monkeypatch.setenv("ASIS_AI_TEMPERATURE", "-0.1")
    with pytest.raises(ConfigurationError):
        load_settings()


def test_zero_and_negative_numerics_rejected(monkeypatch):
    monkeypatch.setenv("ASIS_AI_REQUEST_TIMEOUT", "0")
    with pytest.raises(ConfigurationError):
        load_settings()
    monkeypatch.setenv("ASIS_AI_REQUEST_TIMEOUT", "120")
    monkeypatch.setenv("ASIS_NETWORK_RETRIES", "-1")
    with pytest.raises(ConfigurationError):
        load_settings()
    monkeypatch.setenv("ASIS_NETWORK_RETRIES", "0")
    assert load_settings().network.retries == 0


def test_unsafe_database_name_rejected(monkeypatch):
    for bad in ["../evil.db", "a/b.db", "we*ird.db"]:
        monkeypatch.setenv("ASIS_MEMORY_DATABASE_NAME", bad)
        with pytest.raises(ConfigurationError):
            load_settings()


def test_voice_ranges(monkeypatch):
    monkeypatch.setenv("ASIS_VOICE_SAMPLE_RATE", "0")
    with pytest.raises(ConfigurationError):
        load_settings()
    monkeypatch.setenv("ASIS_VOICE_SAMPLE_RATE", "16000")
    monkeypatch.setenv("ASIS_VOICE_SPEAKER_CONFIDENCE", "1.5")
    with pytest.raises(ConfigurationError):
        load_settings()
    monkeypatch.setenv("ASIS_VOICE_SPEAKER_CONFIDENCE", "0.6")
    monkeypatch.setenv("ASIS_VOICE_WAKE_ENGINE", "openwakeword")
    # A blank wake word arrives as the default ("hey asis"), which is valid;
    # the enabled-mode requirement is enforced on programmatic settings.
    import dataclasses

    from asis.configuration.validation import validate_settings

    assert load_settings().voice.wake_word == "hey asis"
    blanked = dataclasses.replace(
        load_settings(),
        voice=dataclasses.replace(load_settings().voice, wake_word="  "),
    )
    with pytest.raises(ConfigurationError):
        validate_settings(blanked)


def test_bad_log_level_rejected(monkeypatch):
    monkeypatch.setenv("ASIS_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ConfigurationError):
        load_settings()
    monkeypatch.setenv("ASIS_LOG_LEVEL", "debug")
    assert load_settings().runtime.log_level == "debug"


def test_error_names_variable_and_value():
    with pytest.raises(ConfigurationError) as exc:
        load_settings({"ASIS_AI_REQUEST_TIMEOUT": "abc"})
    message = str(exc.value)
    assert "ASIS_AI_REQUEST_TIMEOUT" in message
    assert "abc" in message


# ---- immutability ----


def test_settings_are_frozen():
    config = load_settings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.ai.model = "mutated"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.voice.sample_rate = 1  # type: ignore[misc]


def test_loads_are_independent():
    first = load_settings({"ASIS_AI_MODEL": "one"})
    second = load_settings({"ASIS_AI_MODEL": "two"})
    assert first.ai.model == "one"
    assert second.ai.model == "two"


# ---- paths ----


def test_path_overrides(monkeypatch, tmp_path):
    target = tmp_path / "custom-data"
    monkeypatch.setenv("ASIS_DATA_DIRECTORY", str(target))
    config = load_settings()
    assert config.paths.data == target.absolute()
    # Other directories still use platform defaults.
    assert config.paths.cache != config.paths.data


def test_path_override_tilde_expands(monkeypatch):
    monkeypatch.setenv("ASIS_CACHE_DIRECTORY", "~/asis-cache-test")
    config = load_settings()
    assert str(config.paths.cache).startswith(str(Path.home()))
    assert "~" not in str(config.paths.cache)


def test_platformdirs_used_not_repo(monkeypatch):
    calls = []

    def fake_user_data_dir(appname):
        calls.append(appname)
        return "/platform/data"

    monkeypatch.setattr(paths_module, "user_data_dir", fake_user_data_dir)
    config = load_settings()
    assert calls and calls[0] == "A.S.I.S."
    # Separator-agnostic: Windows Path() renders "/" as "\".
    assert str(config.paths.data).replace("\\", "/").startswith("/platform/data")
    assert ".git" not in str(config.paths.data)
    repo = Path.cwd().resolve()
    for field in ("data", "config", "cache", "logs", "memory"):
        assert repo not in Path(getattr(config.paths, field)).parents


def test_distinct_directories():
    config = load_settings()
    values = {
        str(getattr(config.paths, f))
        for f in ("data", "config", "cache", "logs", "memory", "runtime")
    }
    assert len(values) == 6
