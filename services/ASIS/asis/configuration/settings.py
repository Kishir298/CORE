"""
Centralized A.S.I.S. configuration.

Combines built-in defaults, environment overrides and cross-platform
paths. Other A.S.I.S. modules should resolve configuration through
`settings` rather than reading the environment directly.

Precedence (highest wins): explicit ``load_settings(env=...)`` overrides
> process environment > ``.env`` files > built-in defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import defaults, environment
from .paths import (
    get_cache_directory,
    get_config_directory,
    get_data_directory,
    get_log_directory,
    get_memory_directory,
    get_runtime_directory,
)


@dataclass(frozen=True)
class AISettings:
    provider: str
    model: str
    endpoint: str
    request_timeout: int
    temperature: float
    max_context_messages: int
    context_char_limit: int
    native_tools: str
    think: str
    num_predict: int
    keep_alive: str


@dataclass(frozen=True)
class OllamaSettings:
    """Local Ollama server lifecycle (ownership-safe, standalone by default)."""

    managed: str
    serve_timeout: int
    shutdown_timeout: int


@dataclass(frozen=True)
class BootReadinessSettings:
    """Boot-time model readiness probe configuration."""

    timeout: int
    probe_num_predict: int
    disable_think: bool
    require_visible: bool


@dataclass(frozen=True)
class ConversationSettings:
    max_history: int


@dataclass(frozen=True)
class NetworkSettings:
    timeout: int
    retries: int


@dataclass(frozen=True)
class ToolSettings:
    timeout: int
    max_calls_per_turn: int


@dataclass(frozen=True)
class WebSettings:
    """Optional basic web access (search + fetch, standalone capability)."""

    enabled: bool
    search_provider: str
    timeout: int
    max_results: int
    max_chars: int
    max_response_bytes: int
    max_redirects: int
    max_query_length: int
    max_url_length: int


@dataclass(frozen=True)
class TranslationSettings:
    """Optional local translation engine (offline, mock backend default)."""

    enabled: bool
    provider: str
    model: str
    model_path: str
    device: str
    cache_enabled: bool
    cache_size: int
    default_source: str
    default_target: str
    max_chars: int


@dataclass(frozen=True)
class CalculatorSettings:
    """Local deterministic calculator engine (offline, SymPy-backed)."""

    enabled: bool
    max_expression_chars: int
    max_matrix_size: int
    timeout: int
    precision: int
    angle_mode: str


@dataclass(frozen=True)
class SecuritySettings:
    require_confirmation_for_dangerous: bool


@dataclass(frozen=True)
class MemorySettings:
    provider: str
    database_name: str


@dataclass(frozen=True)
class SpeechToTextSettings:
    engine: str
    model: str
    device: str
    compute_type: str
    language: str


@dataclass(frozen=True)
class TTSSettings:
    engine: str
    voice: str
    sample_rate: int = 16_000


@dataclass(frozen=True)
class SpeakerSettings:
    engine: str
    model: str
    device: str
    confidence: float
    threshold: float = 0.6
    metric: str = "cosine"


@dataclass(frozen=True)
class WakeSettings:
    engine: str = "mock"
    threshold: float = 0.5
    model: str = ""


@dataclass(frozen=True)
class VadSettings:
    engine: str = "mock"
    threshold: float = 0.5


@dataclass(frozen=True)
class VoiceSettings:
    sample_rate: int
    channels: int
    block_size: int
    wake_word: str
    max_utterance_s: float = 15.0
    silence_s: float = 0.8
    input_engine: str = "mock"
    output_engine: str = "mock"
    stt: SpeechToTextSettings = field(default_factory=SpeechToTextSettings)
    tts: TTSSettings = field(default_factory=TTSSettings)
    speaker: SpeakerSettings = field(default_factory=SpeakerSettings)
    wake: WakeSettings = field(default_factory=WakeSettings)
    vad: VadSettings = field(default_factory=VadSettings)


@dataclass(frozen=True)
class RuntimeSettings:
    shutdown_timeout: int
    debug: bool
    log_level: str


@dataclass(frozen=True)
class CoreSettings:
    """Optional C.O.R.E. infrastructure connection (standalone by default)."""

    enabled: bool
    host: str
    port: int
    device_file: str
    ca_file: str
    insecure: bool
    connect_timeout: int
    request_timeout: int
    reconnect_enabled: bool
    reconnect_delay: int


@dataclass(frozen=True)
class CodingSettings:
    default_mode: str
    workspace: str
    command_timeout: int
    max_file_size: int
    max_output_size: int


@dataclass(frozen=True)
class AscsSettings:
    """A.S.C.S. integration settings (optional coding agent)."""
    enabled: bool
    invoke_mode: str  # "subprocess" | "api"
    workspace: str
    mode: str
    intelligence: str
    command_timeout: int
    request_timeout: int
    model: str
    fallback_model: str
    max_iterations: int
    handover_enabled: bool


@dataclass(frozen=True)
class TUISettings:
    """TUI-specific persistent user preferences."""
    sidebar_collapsed: bool = False
    theme: str = "dark"
    left_column_width: int = 28


@dataclass(frozen=True)
class UpdateSettings:
    """Auto-update system (offline-first, optional online updates)."""

    enabled: bool
    check_on_startup: bool
    auto_install: bool
    check_interval_hours: int
    network_timeout: int
    skip_components: list[str]


@dataclass(frozen=True)
class IdentitySettings:
    name: str
    title: str
    shutdown_phrase: str


@dataclass(frozen=True)
class PathSettings:
    data: Path
    config: Path
    cache: Path
    logs: Path
    memory: Path
    runtime: Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str

    identity: IdentitySettings
    ai: AISettings
    ollama: OllamaSettings
    boot_readiness: BootReadinessSettings
    conversation: ConversationSettings
    network: NetworkSettings
    tools: ToolSettings
    web: WebSettings
    translation: TranslationSettings
    calculator: CalculatorSettings
    security: SecuritySettings
    memory: MemorySettings
    voice: VoiceSettings
    runtime: RuntimeSettings
    core: CoreSettings
    coding: CodingSettings
    ascs: AscsSettings
    tui: TUISettings
    update: UpdateSettings
    paths: PathSettings


def _build_identity_settings(get_s, d) -> IdentitySettings:
    return IdentitySettings(
        name=get_s("ASIS_IDENTITY_NAME", d.APP_NAME),
        title=get_s("ASIS_IDENTITY_TITLE", d.IDENTITY_TITLE),
        shutdown_phrase=get_s("ASIS_SHUTDOWN_PHRASE", d.SHUTDOWN_PHRASE),
    )


def _build_ai_settings(get_s, get_i, get_f, d) -> AISettings:
    return AISettings(
        provider=get_s("ASIS_AI_PROVIDER", d.AI_PROVIDER),
        model=get_s("ASIS_AI_MODEL", d.AI_MODEL),
        endpoint=get_s("ASIS_AI_ENDPOINT", d.AI_ENDPOINT),
        request_timeout=get_i("ASIS_AI_REQUEST_TIMEOUT", d.AI_REQUEST_TIMEOUT),
        temperature=get_f("ASIS_AI_TEMPERATURE", d.AI_TEMPERATURE),
        max_context_messages=get_i(
            "ASIS_AI_MAX_CONTEXT_MESSAGES", d.AI_MAX_CONTEXT_MESSAGES
        ),
        context_char_limit=get_i(
            "ASIS_AI_CONTEXT_CHAR_LIMIT", d.AI_CONTEXT_CHAR_LIMIT
        ),
        native_tools=get_s("ASIS_AI_NATIVE_TOOLS", d.AI_NATIVE_TOOLS),
        think=get_s("ASIS_AI_THINK", d.AI_THINK),
        num_predict=get_i("ASIS_AI_NUM_PREDICT", d.AI_NUM_PREDICT),
        keep_alive=get_s("ASIS_AI_KEEP_ALIVE", d.AI_KEEP_ALIVE),
    )


def _build_conversation_settings(get_i, d) -> ConversationSettings:
    return ConversationSettings(
        max_history=get_i(
            "ASIS_CONVERSATION_MAX_HISTORY", d.CONVERSATION_MAX_HISTORY
        ),
    )


def _build_ollama_settings(get_s, environment, d) -> OllamaSettings:
    return OllamaSettings(
        managed=get_s("ASIS_OLLAMA_MANAGED", d.OLLAMA_MANAGED),
        serve_timeout=environment.get_bounded_int(
            "ASIS_OLLAMA_SERVE_TIMEOUT", d.OLLAMA_SERVE_TIMEOUT, 5, 300
        ),
        shutdown_timeout=environment.get_bounded_int(
            "ASIS_OLLAMA_SHUTDOWN_TIMEOUT",
            d.OLLAMA_SHUTDOWN_TIMEOUT,
            1,
            120,
        ),
    )


def _build_boot_readiness_settings(get_s, get_b, get_i, d) -> BootReadinessSettings:
    return BootReadinessSettings(
        timeout=environment.get_bounded_int(
            "ASIS_BOOT_READINESS_TIMEOUT", d.BOOT_READINESS_TIMEOUT, 10, 600
        ),
        probe_num_predict=environment.get_bounded_int(
            "ASIS_BOOT_PROBE_NUM_PREDICT", d.BOOT_PROBE_NUM_PREDICT, 1, 1024
        ),
        disable_think=get_b("ASIS_BOOT_PROBE_DISABLE_THINK", d.BOOT_PROBE_DISABLE_THINK),
        require_visible=get_b("ASIS_BOOT_PROBE_REQUIRE_VISIBLE", d.BOOT_PROBE_REQUIRE_VISIBLE),
    )


def _build_core_settings(get_s, get_b, environment, d) -> CoreSettings:
    return CoreSettings(
        enabled=get_b("ASIS_CORE_ENABLED", d.CORE_ENABLED),
        host=get_s("ASIS_CORE_HOST", d.CORE_HOST),
        port=environment.get_port("ASIS_CORE_PORT", d.CORE_PORT),
        device_file=get_s("ASIS_CORE_DEVICE_FILE", d.CORE_DEVICE_FILE),
        ca_file=get_s("ASIS_CORE_CA_FILE", d.CORE_CA_FILE),
        insecure=get_b("ASIS_CORE_INSECURE", d.CORE_INSECURE),
        connect_timeout=environment.get_bounded_int(
            "ASIS_CORE_CONNECT_TIMEOUT", d.CORE_CONNECT_TIMEOUT, 1, 600
        ),
        request_timeout=environment.get_bounded_int(
            "ASIS_CORE_REQUEST_TIMEOUT", d.CORE_REQUEST_TIMEOUT, 1, 600
        ),
        reconnect_enabled=get_b(
            "ASIS_CORE_RECONNECT_ENABLED", d.CORE_RECONNECT_ENABLED
        ),
        reconnect_delay=environment.get_bounded_int(
            "ASIS_CORE_RECONNECT_DELAY", d.CORE_RECONNECT_DELAY, 0, 300
        ),
    )


def _build_network_settings(get_i, d) -> NetworkSettings:
    return NetworkSettings(
        timeout=get_i("ASIS_NETWORK_TIMEOUT", d.NETWORK_TIMEOUT),
        retries=get_i("ASIS_NETWORK_RETRIES", d.NETWORK_RETRIES),
    )


def _build_tool_settings(get_i, environment, d) -> ToolSettings:
    return ToolSettings(
        timeout=get_i("ASIS_TOOL_TIMEOUT", d.TOOL_TIMEOUT),
        max_calls_per_turn=environment.get_bounded_int(
            "ASIS_TOOL_MAX_CALLS_PER_TURN", d.TOOL_MAX_CALLS_PER_TURN, 1, 10
        ),
    )


def _build_web_settings(get_s, get_b, environment, d) -> WebSettings:
    return WebSettings(
        enabled=get_b("ASIS_WEB_ENABLED", d.WEB_ENABLED),
        search_provider=get_s(
            "ASIS_WEB_SEARCH_PROVIDER", d.WEB_SEARCH_PROVIDER
        ),
        timeout=environment.get_bounded_int(
            "ASIS_WEB_TIMEOUT", d.WEB_TIMEOUT, 1, 120
        ),
        max_results=environment.get_bounded_int(
            "ASIS_WEB_MAX_RESULTS", d.WEB_MAX_RESULTS, 1, 10
        ),
        max_chars=environment.get_bounded_int(
            "ASIS_WEB_MAX_CHARS", d.WEB_MAX_CHARS, 500, 50_000
        ),
        max_response_bytes=environment.get_bounded_int(
            "ASIS_WEB_MAX_RESPONSE_BYTES",
            d.WEB_MAX_RESPONSE_BYTES,
            10_000,
            5_000_000,
        ),
        max_redirects=environment.get_bounded_int(
            "ASIS_WEB_MAX_REDIRECTS", d.WEB_MAX_REDIRECTS, 0, 5
        ),
        max_query_length=environment.get_bounded_int(
            "ASIS_WEB_MAX_QUERY_LENGTH",
            d.WEB_MAX_QUERY_LENGTH,
            1,
            2_000,
        ),
        max_url_length=environment.get_bounded_int(
            "ASIS_WEB_MAX_URL_LENGTH", d.WEB_MAX_URL_LENGTH, 100, 8_000
        ),
    )


def _build_translation_settings(get_s, get_b, environment, d) -> TranslationSettings:
    return TranslationSettings(
        enabled=get_b("ASIS_TRANSLATION_ENABLED", d.TRANSLATION_ENABLED),
        provider=get_s("ASIS_TRANSLATION_PROVIDER", d.TRANSLATION_PROVIDER),
        model=get_s("ASIS_TRANSLATION_MODEL", d.TRANSLATION_MODEL),
        model_path=get_s(
            "ASIS_TRANSLATION_MODEL_PATH", d.TRANSLATION_MODEL_PATH
        ),
        device=get_s("ASIS_TRANSLATION_DEVICE", d.TRANSLATION_DEVICE),
        cache_enabled=get_b(
            "ASIS_TRANSLATION_CACHE_ENABLED", d.TRANSLATION_CACHE_ENABLED
        ),
        cache_size=environment.get_bounded_int(
            "ASIS_TRANSLATION_CACHE_SIZE", d.TRANSLATION_CACHE_SIZE, 1, 10_000
        ),
        default_source=get_s(
            "ASIS_TRANSLATION_DEFAULT_SOURCE", d.TRANSLATION_DEFAULT_SOURCE
        ),
        default_target=get_s(
            "ASIS_TRANSLATION_DEFAULT_TARGET", d.TRANSLATION_DEFAULT_TARGET
        ),
        max_chars=environment.get_bounded_int(
            "ASIS_TRANSLATION_MAX_CHARS", d.TRANSLATION_MAX_CHARS, 1, 50_000
        ),
    )


def _build_calculator_settings(get_s, get_b, environment, d) -> CalculatorSettings:
    return CalculatorSettings(
        enabled=get_b("ASIS_CALCULATOR_ENABLED", d.CALCULATOR_ENABLED),
        max_expression_chars=environment.get_bounded_int(
            "ASIS_CALCULATOR_MAX_EXPRESSION_CHARS",
            d.CALCULATOR_MAX_EXPRESSION_CHARS,
            100,
            20_000,
        ),
        max_matrix_size=environment.get_bounded_int(
            "ASIS_CALCULATOR_MAX_MATRIX_SIZE",
            d.CALCULATOR_MAX_MATRIX_SIZE,
            2,
            50,
        ),
        timeout=environment.get_bounded_int(
            "ASIS_CALCULATOR_TIMEOUT", d.CALCULATOR_TIMEOUT, 1, 300
        ),
        precision=environment.get_bounded_int(
            "ASIS_CALCULATOR_PRECISION", d.CALCULATOR_PRECISION, 0, 30
        ),
        angle_mode=get_s("ASIS_CALCULATOR_ANGLE_MODE", d.CALCULATOR_ANGLE_MODE),
    )


def _build_security_settings(get_b, d) -> SecuritySettings:
    return SecuritySettings(
        require_confirmation_for_dangerous=get_b(
            "ASIS_CONFIRM_DANGEROUS_TOOLS",
            d.REQUIRE_CONFIRMATION_FOR_DANGEROUS,
        )
    )


def _build_memory_settings(get_s, d) -> MemorySettings:
    return MemorySettings(
        provider=get_s("ASIS_MEMORY_PROVIDER", d.MEMORY_PROVIDER),
        database_name=get_s(
            "ASIS_MEMORY_DATABASE_NAME", d.MEMORY_DATABASE_NAME
        ),
    )


def _build_voice_settings(get_s, get_i, get_f, d) -> VoiceSettings:
    return VoiceSettings(
        sample_rate=get_i("ASIS_VOICE_SAMPLE_RATE", d.VOICE_SAMPLE_RATE),
        channels=get_i("ASIS_VOICE_CHANNELS", d.VOICE_CHANNELS),
        block_size=get_i("ASIS_VOICE_BLOCK_SIZE", d.VOICE_BLOCK_SIZE),
        wake_word=get_s("ASIS_VOICE_WAKE_WORD", d.VOICE_WAKE_WORD),
        max_utterance_s=get_f(
            "ASIS_VOICE_MAX_UTTERANCE_S", d.VOICE_MAX_UTTERANCE_S
        ),
        silence_s=get_f("ASIS_VOICE_SILENCE_S", d.VOICE_SILENCE_S),
        input_engine=get_s("ASIS_VOICE_INPUT_ENGINE", d.VOICE_INPUT_ENGINE),
        output_engine=get_s("ASIS_VOICE_OUTPUT_ENGINE", d.VOICE_OUTPUT_ENGINE),
        stt=SpeechToTextSettings(
            engine=get_s("ASIS_VOICE_STT_ENGINE", d.VOICE_STT_ENGINE),
            model=get_s("ASIS_VOICE_STT_MODEL", d.VOICE_STT_MODEL),
            device=get_s("ASIS_VOICE_STT_DEVICE", d.VOICE_STT_DEVICE),
            compute_type=get_s(
                "ASIS_VOICE_STT_COMPUTE_TYPE", d.VOICE_STT_COMPUTE_TYPE
            ),
            language=get_s("ASIS_VOICE_STT_LANGUAGE", d.VOICE_STT_LANGUAGE),
        ),
        tts=TTSSettings(
            engine=get_s("ASIS_VOICE_TTS_ENGINE", d.VOICE_TTS_ENGINE),
            voice=get_s("ASIS_VOICE_TTS_VOICE", d.VOICE_TTS_VOICE),
            sample_rate=get_i(
                "ASIS_VOICE_TTS_SAMPLE_RATE", d.VOICE_TTS_SAMPLE_RATE
            ),
        ),
        speaker=SpeakerSettings(
            engine=get_s("ASIS_VOICE_SPEAKER_ENGINE", d.VOICE_SPEAKER_ENGINE),
            model=get_s("ASIS_VOICE_SPEAKER_MODEL", d.VOICE_SPEAKER_MODEL),
            device=get_s("ASIS_VOICE_SPEAKER_DEVICE", d.VOICE_SPEAKER_DEVICE),
            confidence=get_f(
                "ASIS_VOICE_SPEAKER_CONFIDENCE", d.VOICE_SPEAKER_CONFIDENCE
            ),
            threshold=get_f(
                "ASIS_VOICE_SPEAKER_THRESHOLD", d.VOICE_SPEAKER_THRESHOLD
            ),
            metric=get_s("ASIS_VOICE_SPEAKER_METRIC", d.VOICE_SPEAKER_METRIC),
        ),
        wake=WakeSettings(
            engine=get_s("ASIS_VOICE_WAKE_ENGINE", d.VOICE_WAKE_ENGINE),
            threshold=get_f(
                "ASIS_VOICE_WAKE_THRESHOLD", d.VOICE_WAKE_THRESHOLD
            ),
            model=get_s("ASIS_VOICE_WAKE_MODEL", d.VOICE_WAKE_MODEL),
        ),
        vad=VadSettings(
            engine=get_s("ASIS_VOICE_VAD_ENGINE", d.VOICE_VAD_ENGINE),
            threshold=get_f("ASIS_VOICE_VAD_THRESHOLD", d.VOICE_VAD_THRESHOLD),
        ),
    )


def _build_runtime_settings(get_s, get_b, get_i, d) -> RuntimeSettings:
    return RuntimeSettings(
        shutdown_timeout=get_i("ASIS_SHUTDOWN_TIMEOUT", d.SHUTDOWN_TIMEOUT),
        debug=get_b("ASIS_DEBUG", d.DEBUG),
        log_level=get_s("ASIS_LOG_LEVEL", d.LOG_LEVEL),
    )


def _build_coding_settings(get_s, get_i, d) -> CodingSettings:
    return CodingSettings(
        default_mode=get_s("ASIS_DEFAULT_MODE", d.DEFAULT_MODE),
        workspace=get_s("ASIS_CODING_WORKSPACE", d.CODING_WORKSPACE),
        command_timeout=get_i(
            "ASIS_CODING_COMMAND_TIMEOUT", d.CODING_COMMAND_TIMEOUT
        ),
        max_file_size=get_i(
            "ASIS_CODING_MAX_FILE_SIZE", d.CODING_MAX_FILE_SIZE
        ),
        max_output_size=get_i(
            "ASIS_CODING_MAX_OUTPUT_SIZE", d.CODING_MAX_OUTPUT_SIZE
        ),
    )


def _build_ascs_settings(get_s, get_b, get_i, get_list, environment, d) -> AscsSettings:
    return AscsSettings(
        enabled=get_b("ASIS_ASCS_ENABLED", d.ASCS_ENABLED),
        invoke_mode=get_s("ASIS_ASCS_INVOKE_MODE", d.ASCS_INVOKE_MODE),
        workspace=get_s("ASIS_ASCS_WORKSPACE", d.ASCS_WORKSPACE),
        mode=get_s("ASIS_ASCS_MODE", d.ASCS_MODE),
        intelligence=get_s("ASIS_ASCS_INTELLIGENCE", d.ASCS_INTELLIGENCE),
        command_timeout=get_i("ASIS_ASCS_COMMAND_TIMEOUT", d.ASCS_COMMAND_TIMEOUT),
        request_timeout=get_i("ASIS_ASCS_REQUEST_TIMEOUT", d.ASCS_REQUEST_TIMEOUT),
        model=get_s("ASIS_ASCS_MODEL", d.ASCS_MODEL),
        fallback_model=get_s("ASIS_ASCS_FALLBACK_MODEL", d.ASCS_FALLBACK_MODEL),
        max_iterations=get_i("ASIS_ASCS_MAX_ITERATIONS", d.ASCS_MAX_ITERATIONS),
        handover_enabled=get_b("ASIS_ASCS_HANDOVER_ENABLED", d.ASCS_HANDOVER_ENABLED),
    )


def _build_tui_settings(get_s, get_b, get_i, d) -> TUISettings:
    return TUISettings(
        sidebar_collapsed=get_b("ASIS_TUI_SIDEBAR_COLLAPSED", d.TUI_SIDEBAR_COLLAPSED),
        theme=get_s("ASIS_TUI_THEME", d.TUI_THEME),
        left_column_width=get_i("ASIS_TUI_LEFT_COLUMN_WIDTH", d.TUI_LEFT_COLUMN_WIDTH),
    )


def _build_update_settings(get_s, get_b, get_i, get_list, d) -> UpdateSettings:
    return UpdateSettings(
        enabled=get_b("ASIS_UPDATE_ENABLED", d.UPDATE_ENABLED),
        check_on_startup=get_b("ASIS_UPDATE_CHECK_ON_STARTUP", d.UPDATE_CHECK_ON_STARTUP),
        auto_install=get_b("ASIS_UPDATE_AUTO_INSTALL", d.UPDATE_AUTO_INSTALL),
        check_interval_hours=environment.get_bounded_int(
            "ASIS_UPDATE_CHECK_INTERVAL_HOURS", d.UPDATE_CHECK_INTERVAL_HOURS, 1, 168
        ),
        network_timeout=environment.get_bounded_int(
            "ASIS_UPDATE_NETWORK_TIMEOUT", d.UPDATE_NETWORK_TIMEOUT, 1, 30
        ),
        skip_components=get_list("ASIS_UPDATE_SKIP_COMPONENTS", d.UPDATE_SKIP_COMPONENTS),
    )


def _build_path_settings(environment) -> PathSettings:
    return PathSettings(
        data=get_data_directory(environment.get_path("ASIS_DATA_DIRECTORY")),
        config=get_config_directory(
            environment.get_path("ASIS_CONFIG_DIRECTORY")
        ),
        cache=get_cache_directory(environment.get_path("ASIS_CACHE_DIRECTORY")),
        logs=get_log_directory(environment.get_path("ASIS_LOG_DIRECTORY")),
        memory=get_memory_directory(
            environment.get_path("ASIS_MEMORY_DIRECTORY")
        ),
        runtime=get_runtime_directory(
            environment.get_path("ASIS_RUNTIME_DIRECTORY")
        ),
    )


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build and return an independent, validated A.S.I.S. configuration.

    Reads the live process environment on every call (plus optional
    explicit ``env`` overrides, highest precedence), so tests can set
    variables and reload without touching the global ``settings``.
    Raises ``ConfigurationError`` on any present-but-invalid value.
    """
    from .validation import validate_settings

    with environment.override_env(env or {}):
        get_s = environment.get_string
        get_b = environment.get_bool
        get_i = environment.get_int
        get_f = environment.get_float
        get_list = environment.get_list
        d = defaults
        built = Settings(
            app_name=get_s("ASIS_IDENTITY_NAME", d.APP_NAME),
            app_version=get_s("ASIS_APP_VERSION", d.APP_VERSION),
            identity=_build_identity_settings(get_s, d),
            ai=_build_ai_settings(get_s, get_i, get_f, d),
            conversation=_build_conversation_settings(get_i, d),
            ollama=_build_ollama_settings(get_s, environment, d),
            boot_readiness=_build_boot_readiness_settings(get_s, get_b, get_i, d),
            core=_build_core_settings(get_s, get_b, environment, d),
            network=_build_network_settings(get_i, d),
            tools=_build_tool_settings(get_i, environment, d),
            web=_build_web_settings(get_s, get_b, environment, d),
            translation=_build_translation_settings(get_s, get_b, environment, d),
            calculator=_build_calculator_settings(get_s, get_b, environment, d),
            security=_build_security_settings(get_b, d),
            memory=_build_memory_settings(get_s, d),
            voice=_build_voice_settings(get_s, get_i, get_f, d),
            runtime=_build_runtime_settings(get_s, get_b, get_i, d),
            coding=_build_coding_settings(get_s, get_i, d),
            ascs=_build_ascs_settings(get_s, get_b, get_i, get_list, environment, d),
            tui=_build_tui_settings(get_s, get_b, get_i, d),
            update=_build_update_settings(get_s, get_b, get_i, get_list, d),
            paths=_build_path_settings(environment),
        )
    return validate_settings(built)


# Global read-only configuration instance.
settings = load_settings()


def reset_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Reload settings with optional environment overrides (for tests)."""
    global settings
    settings = load_settings(env=env)
    return settings
