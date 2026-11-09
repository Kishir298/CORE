"""
Centralized validation for A.S.I.S. configuration.

Runs after parsing and before settings become active: any invalid value
raises ``ConfigurationError`` naming the field and constraint. Invalid
configuration never silently becomes a default. Provider-specific value
checks belong to the provider/factory layer, not here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from asis.errors import ConfigurationError

if TYPE_CHECKING:  # avoid a runtime cycle with settings.py
    from .settings import Settings

LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_TEMPERATURE_MAX = 2.0


def _require_non_empty(section: str, field: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(
            f"Invalid configuration {section}.{field}: must be a non-empty string."
        )


def _require_positive_int(section: str, field: str, value: int) -> None:
    if not isinstance(value, bool) and isinstance(value, int) and value > 0:
        return
    raise ConfigurationError(
        f"Invalid configuration {section}.{field}: expected a positive "
        f"integer, received {value!r}."
    )


def _require_non_negative_int(section: str, field: str, value: int) -> None:
    if not isinstance(value, bool) and isinstance(value, int) and value >= 0:
        return
    raise ConfigurationError(
        f"Invalid configuration {section}.{field}: expected an integer >= 0, "
        f"received {value!r}."
    )


def _require_unit_interval(section: str, field: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(
            f"Invalid configuration {section}.{field}: expected a number "
            f"between 0 and 1, received {value!r}."
        )
    if not 0.0 <= float(value) <= 1.0:
        raise ConfigurationError(
            f"Invalid configuration {section}.{field}: expected a number "
            f"between 0 and 1, received {value!r}."
        )


def _validate_endpoint(endpoint: str) -> None:
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ConfigurationError(
            "Invalid configuration ai.endpoint: must be a non-empty endpoint URL."
        )
    parsed = urlparse(endpoint.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ConfigurationError(
            f"Invalid configuration ai.endpoint: expected an http(s) URL, "
            f"received {endpoint!r}."
        )


def _validate_database_name(name: str) -> None:
    _require_non_empty("memory", "database_name", name)
    if "/" in name or "\\" in name or ".." in name or "\x00" in name:
        raise ConfigurationError(
            f"Invalid configuration memory.database_name: unsafe database "
            f"name {name!r}."
        )
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(c not in allowed for c in name):
        raise ConfigurationError(
            f"Invalid configuration memory.database_name: unsupported "
            f"characters in {name!r}."
        )


def _validate_ai(settings: Settings) -> None:
    _require_non_empty("ai", "provider", settings.ai.provider)
    _require_non_empty("ai", "model", settings.ai.model)
    _validate_endpoint(settings.ai.endpoint)
    _require_positive_int("ai", "request_timeout", settings.ai.request_timeout)
    temp = settings.ai.temperature
    if (
        isinstance(temp, bool)
        or not isinstance(temp, (int, float))
        or not 0.0 <= float(temp) <= _TEMPERATURE_MAX
    ):
        raise ConfigurationError(
            f"Invalid configuration ai.temperature: expected a number "
            f"between 0 and {_TEMPERATURE_MAX}, received {temp!r}."
        )
    _require_positive_int(
        "ai", "max_context_messages", settings.ai.max_context_messages
    )
    _require_positive_int("ai", "context_char_limit", settings.ai.context_char_limit)
    native_tools = settings.ai.native_tools
    if (
        not isinstance(native_tools, str)
        or native_tools.strip().lower() not in ("auto", "true", "false")
    ):
        raise ConfigurationError(
            "Invalid configuration ai.native_tools: expected one of "
            f"'auto', 'true', 'false', received {native_tools!r}."
        )
    think = settings.ai.think
    if (
        not isinstance(think, str)
        or think.strip().lower() not in ("auto", "true", "false")
    ):
        raise ConfigurationError(
            "Invalid configuration ai.think: expected one of "
            f"'auto', 'true', 'false', received {think!r}."
        )
    _require_non_negative_int("ai", "num_predict", settings.ai.num_predict)
    if not isinstance(settings.ai.keep_alive, str):
        raise ConfigurationError(
            "Invalid configuration ai.keep_alive: expected a string "
            f"(e.g. '30m', '' for server default), received "
            f"{settings.ai.keep_alive!r}."
        )


def _validate_ollama(settings: Settings) -> None:
    managed = settings.ollama.managed
    if (
        not isinstance(managed, str)
        or managed.strip().lower() not in ("auto", "on", "off")
    ):
        raise ConfigurationError(
            "Invalid configuration ollama.managed: expected one of "
            f"'auto', 'on', 'off', received {managed!r}."
        )
    for field_name, low, high in (
        ("serve_timeout", 5, 300),
        ("shutdown_timeout", 1, 120),
    ):
        value = getattr(settings.ollama, field_name)
        bad_type = isinstance(value, bool) or not isinstance(value, int)
        if bad_type or not low <= value <= high:
            raise ConfigurationError(
                f"Invalid configuration ollama.{field_name}: expected an "
                f"integer between {low} and {high}, received {value!r}."
            )


def _validate_conversation(settings: Settings) -> None:
    _require_positive_int(
        "conversation", "max_history", settings.conversation.max_history
    )


def _validate_network(settings: Settings) -> None:
    _require_positive_int("network", "timeout", settings.network.timeout)
    _require_non_negative_int("network", "retries", settings.network.retries)


def _validate_tools(settings: Settings) -> None:
    _require_positive_int("tools", "timeout", settings.tools.timeout)
    calls = settings.tools.max_calls_per_turn
    if isinstance(calls, bool) or not isinstance(calls, int) or not 1 <= calls <= 10:
        raise ConfigurationError(
            "Invalid configuration tools.max_calls_per_turn: expected an "
            f"integer between 1 and 10, received {calls!r}."
        )


def _validate_web(settings: Settings) -> None:
    if not isinstance(settings.web.enabled, bool):
        raise ConfigurationError(
            "Invalid configuration web.enabled: expected a boolean."
        )
    _require_non_empty("web", "search_provider", settings.web.search_provider)
    if settings.web.search_provider.strip().lower() not in ("duckduckgo",):
        raise ConfigurationError(
            "Invalid configuration web.search_provider: expected one of "
            f"'duckduckgo', received {settings.web.search_provider!r}."
        )
    for field_name, low, high in (
        ("timeout", 1, 120),
        ("max_results", 1, 10),
        ("max_chars", 500, 50_000),
        ("max_response_bytes", 10_000, 5_000_000),
        ("max_redirects", 0, 5),
        ("max_query_length", 1, 2_000),
        ("max_url_length", 100, 8_000),
    ):
        value = getattr(settings.web, field_name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not low <= value <= high
        ):
            raise ConfigurationError(
                f"Invalid configuration web.{field_name}: expected an "
                f"integer between {low} and {high}, received {value!r}."
            )


def _validate_translation(settings: Settings) -> None:
    if not isinstance(settings.translation.enabled, bool):
        raise ConfigurationError(
            "Invalid configuration translation.enabled: expected a boolean."
        )
    _require_non_empty("translation", "provider", settings.translation.provider)
    if settings.translation.provider.strip().lower() not in ("mock", "madlad"):
        raise ConfigurationError(
            "Invalid configuration translation.provider: expected one of "
            f"'mock', 'madlad', received {settings.translation.provider!r}."
        )
    _require_non_empty("translation", "model", settings.translation.model)
    _require_non_empty("translation", "device", settings.translation.device)
    for field_name in ("model_path",):
        value = getattr(settings.translation, field_name)
        if not isinstance(value, str):
            raise ConfigurationError(
                f"Invalid configuration translation.{field_name}: "
                "expected a string."
            )
        if "\x00" in value:
            raise ConfigurationError(
                f"Invalid configuration translation.{field_name}: "
                "must not contain NUL bytes."
            )
    if not isinstance(settings.translation.cache_enabled, bool):
        raise ConfigurationError(
            "Invalid configuration translation.cache_enabled: expected a boolean."
        )
    cache_size = settings.translation.cache_size
    if (
        isinstance(cache_size, bool)
        or not isinstance(cache_size, int)
        or not 1 <= cache_size <= 10_000
    ):
        raise ConfigurationError(
            "Invalid configuration translation.cache_size: expected an "
            f"integer between 1 and 10000, received {cache_size!r}."
        )
    from asis.translation.languages import normalize_code as _normalize_code

    default_source = settings.translation.default_source
    if not isinstance(default_source, str) or (
        default_source.strip().lower() != "auto"
        and _normalize_code(default_source) is None
    ):
        raise ConfigurationError(
            "Invalid configuration translation.default_source: expected "
            f"'auto' or a supported language code, received {default_source!r}."
        )
    if _normalize_code(settings.translation.default_target) is None:
        raise ConfigurationError(
            "Invalid configuration translation.default_target: expected a "
            "supported language code, received "
            f"{settings.translation.default_target!r}."
        )
    max_chars = settings.translation.max_chars
    if (
        isinstance(max_chars, bool)
        or not isinstance(max_chars, int)
        or not 1 <= max_chars <= 50_000
    ):
        raise ConfigurationError(
            "Invalid configuration translation.max_chars: expected an "
            f"integer between 1 and 50000, received {max_chars!r}."
        )


def _validate_calculator(settings: Settings) -> None:
    if not isinstance(settings.calculator.enabled, bool):
        raise ConfigurationError(
            "Invalid configuration calculator.enabled: expected a boolean."
        )
    for field_name, low, high in (
        ("max_expression_chars", 100, 20_000),
        ("max_matrix_size", 2, 50),
        ("timeout", 1, 300),
        ("precision", 0, 30),
    ):
        value = getattr(settings.calculator, field_name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not low <= value <= high
        ):
            raise ConfigurationError(
                f"Invalid configuration calculator.{field_name}: expected an "
                f"integer between {low} and {high}, received {value!r}."
            )
    _require_non_empty("calculator", "angle_mode", settings.calculator.angle_mode)
    if settings.calculator.angle_mode.strip().lower() not in (
        "radians",
        "degrees",
        "gradians",
    ):
        raise ConfigurationError(
            "Invalid configuration calculator.angle_mode: expected one of "
            "'radians', 'degrees', 'gradians', received "
            f"{settings.calculator.angle_mode!r}."
        )


def _validate_security(settings: Settings) -> None:
    if not isinstance(settings.security.require_confirmation_for_dangerous, bool):
        raise ConfigurationError(
            "Invalid configuration "
            "security.require_confirmation_for_dangerous: expected a boolean."
        )


def _validate_memory(settings: Settings) -> None:
    _require_non_empty("memory", "provider", settings.memory.provider)
    _validate_database_name(settings.memory.database_name)


def _validate_voice(settings: Settings) -> None:
    _require_non_empty("voice", "input_engine", settings.voice.input_engine)
    _require_non_empty("voice", "output_engine", settings.voice.output_engine)
    _require_positive_int("voice", "sample_rate", settings.voice.sample_rate)
    _require_positive_int("voice", "channels", settings.voice.channels)
    _require_positive_int("voice", "block_size", settings.voice.block_size)

    # STT (language may be empty meaning automatic detection)
    _require_non_empty("voice.stt", "engine", settings.voice.stt.engine)
    _require_non_empty("voice.stt", "model", settings.voice.stt.model)
    _require_non_empty("voice.stt", "device", settings.voice.stt.device)
    _require_non_empty("voice.stt", "compute_type", settings.voice.stt.compute_type)

    # TTS (voice may be empty when the provider auto-selects)
    _require_non_empty("voice.tts", "engine", settings.voice.tts.engine)
    _require_positive_int("voice.tts", "sample_rate", settings.voice.tts.sample_rate)

    # Speaker
    _require_non_empty("voice.speaker", "engine", settings.voice.speaker.engine)
    _require_non_empty("voice.speaker", "model", settings.voice.speaker.model)
    _require_non_empty("voice.speaker", "device", settings.voice.speaker.device)
    _require_unit_interval(
        "voice.speaker", "confidence", settings.voice.speaker.confidence
    )
    _require_unit_interval(
        "voice.speaker", "threshold", settings.voice.speaker.threshold
    )
    _require_non_empty("voice.speaker", "metric", settings.voice.speaker.metric)

    # Wake word required whenever wake-word mode is enabled
    _require_non_empty("voice.wake", "engine", settings.voice.wake.engine)
    _require_unit_interval("voice.wake", "threshold", settings.voice.wake.threshold)
    if settings.voice.wake.engine.strip().lower() not in ("mock", "none", "off", ""):
        _require_non_empty("voice", "wake_word", settings.voice.wake_word)

    # VAD
    _require_non_empty("voice.vad", "engine", settings.voice.vad.engine)
    _require_unit_interval("voice.vad", "threshold", settings.voice.vad.threshold)

    # Utterance bounds (must stay positive to avoid infinite capture)
    for field_name in ("max_utterance_s", "silence_s"):
        value = getattr(settings.voice, field_name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not float(value) > 0
        ):
            raise ConfigurationError(
                f"Invalid configuration voice.{field_name}: expected a "
                f"positive number, received {value!r}."
            )


def _validate_runtime(settings: Settings) -> None:
    _require_positive_int(
        "runtime", "shutdown_timeout", settings.runtime.shutdown_timeout
    )
    if (
        not isinstance(settings.runtime.log_level, str)
        or settings.runtime.log_level.strip().upper() not in LOG_LEVELS
    ):
        raise ConfigurationError(
            f"Invalid configuration runtime.log_level: expected one of "
            f"{sorted(LOG_LEVELS)}, received "
            f"{settings.runtime.log_level!r}."
        )


def _validate_coding(settings: Settings) -> None:
    _require_non_empty("coding", "default_mode", settings.coding.default_mode)
    if settings.coding.default_mode.strip().lower() not in (
        "general",
        "coding",
        "translation",
    ):
        raise ConfigurationError(
            "Invalid configuration coding.default_mode: expected 'general', "
            f"'coding', or 'translation', received {settings.coding.default_mode!r}."
        )
    _require_positive_int("coding", "command_timeout", settings.coding.command_timeout)
    _require_positive_int("coding", "max_file_size", settings.coding.max_file_size)
    _require_positive_int("coding", "max_output_size", settings.coding.max_output_size)


def _validate_update(settings: Settings) -> None:
    if not isinstance(settings.update.enabled, bool):
        raise ConfigurationError(
            "Invalid configuration update.enabled: expected a boolean."
        )
    if not isinstance(settings.update.check_on_startup, bool):
        raise ConfigurationError(
            "Invalid configuration update.check_on_startup: expected a boolean."
        )
    if not isinstance(settings.update.auto_install, bool):
        raise ConfigurationError(
            "Invalid configuration update.auto_install: expected a boolean."
        )
    _require_positive_int(
        "update", "check_interval_hours", settings.update.check_interval_hours
    )
    _require_positive_int("update", "network_timeout", settings.update.network_timeout)
    if not isinstance(settings.update.skip_components, list):
        raise ConfigurationError(
            "Invalid configuration update.skip_components: expected a list."
        )
    allowed_components = {"git", "pip", "ollama_models"}
    for comp in settings.update.skip_components:
        if comp not in allowed_components:
            raise ConfigurationError(
                f"Invalid configuration update.skip_components: unknown component "
                f"'{comp}'. Allowed: {sorted(allowed_components)}"
            )


def _validate_core(settings: Settings) -> None:
    _require_non_empty("core", "host", settings.core.host)
    if "\x00" in settings.core.host:
        raise ConfigurationError(
            "Invalid configuration core.host: must not contain NUL bytes."
        )
    port = settings.core.port
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigurationError(
            f"Invalid configuration core.port: expected an integer "
            f"between 1 and 65535, received {port!r}."
        )
    for field_name in ("connect_timeout", "request_timeout"):
        value = getattr(settings.core, field_name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= 600
        ):
            raise ConfigurationError(
                f"Invalid configuration core.{field_name}: expected an "
                f"integer between 1 and 600, received {value!r}."
            )
    delay = settings.core.reconnect_delay
    if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= 300:
        raise ConfigurationError(
            f"Invalid configuration core.reconnect_delay: expected an "
            f"integer between 0 and 300, received {delay!r}."
        )
    for field_name in ("enabled", "insecure", "reconnect_enabled"):
        if not isinstance(getattr(settings.core, field_name), bool):
            raise ConfigurationError(
                f"Invalid configuration core.{field_name}: expected a boolean."
            )
    for field_name in ("device_file", "ca_file"):
        value = getattr(settings.core, field_name)
        if not isinstance(value, str):
            raise ConfigurationError(
                f"Invalid configuration core.{field_name}: expected a string."
            )
        if "\x00" in value:
            raise ConfigurationError(
                f"Invalid configuration core.{field_name}: "
                "must not contain NUL bytes."
            )


def _validate_paths(settings: Settings) -> None:
    for field_name in ("data", "config", "cache", "logs", "memory", "runtime"):
        value = getattr(settings.paths, field_name)
        if value is None or str(value) == "":
            raise ConfigurationError(
                f"Invalid configuration paths.{field_name}: must be a valid path."
            )


def validate_settings(settings: Settings) -> Settings:
    """Validate a fully built ``Settings`` object, returning it unchanged."""
    _validate_ai(settings)
    _validate_ollama(settings)
    _validate_conversation(settings)
    _validate_network(settings)
    _validate_tools(settings)
    _validate_web(settings)
    _validate_translation(settings)
    _validate_calculator(settings)
    _validate_security(settings)
    _validate_memory(settings)
    _validate_voice(settings)
    _validate_runtime(settings)
    _validate_coding(settings)
    _validate_update(settings)
    _validate_core(settings)
    _validate_paths(settings)
    return settings
