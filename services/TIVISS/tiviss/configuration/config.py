"""T.I.V.I.S.S. configuration.

Configuration controls real agent behavior (identity, model, memory, and
permissions) with validation and sensible defaults. Secrets are never read
from source; settings can be supplied explicitly or via ``TIVISS_*``
environment variables. No secrets are hard-coded here.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .. import __version__ as _package_version


class ConfigValidationError(ValueError):
    """Raised when a configuration is invalid."""


@dataclass
class AgentSettings:
    name: str = "tiviss"
    version: str = _package_version
    agent_id: str | None = None
    owner_id: str = "unassigned"


@dataclass
class ModelSettings:
    provider_id: str = "mock"
    model_id: str = "tiviss-mock-1"
    prefix: str = "ack"
    # Ollama-specific settings
    endpoint: str = "http://127.0.0.1:11434"
    timeout_s: float = 60.0
    temperature: float = 0.7
    num_predict: int = 0
    keep_alive: str = "30m"
    strip_thinking: bool = True


@dataclass
class MemorySettings:
    backend: str = "local"
    # SQLite dual-database paths (conversation_logs + semantic_memory)
    conversation_db: str | None = None
    semantic_db: str | None = None
    # Legacy single-path for backward compatibility
    storage_path: str | None = None


@dataclass
class WebSettings:
    enabled: bool = False
    search_provider: str = "duckduckgo"
    timeout: int = 10
    max_results: int = 5
    max_chars: int = 8000
    max_query_length: int = 500
    max_url_length: int = 2048


@dataclass
class CalculatorSettings:
    enabled: bool = True
    max_expression_chars: int = 2000
    max_matrix_size: int = 10
    timeout: int = 30
    precision: int = 10
    angle_mode: str = "radians"


@dataclass
class TranslationSettings:
    enabled: bool = True
    provider: str = "mock"
    model: str = "google/madlad400-3b-mt"
    model_path: str = ""
    device: str = "cpu"
    cache_enabled: bool = True
    cache_size: int = 200
    default_source: str = "auto"
    default_target: str = "en"
    max_chars: int = 5000


@dataclass
class VoiceSettings:
    enabled: bool = False
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 1024
    stt_engine: str = "mock"
    stt_model: str = "small"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_language: str = ""
    tts_engine: str = "mock"
    tts_voice: str = "male-default"
    tts_sample_rate: int = 16000
    speaker_engine: str = "mock"
    speaker_model: str = "speechbrain/spkrec-ecapa-voxceleb"
    speaker_device: str = "cpu"
    speaker_confidence: float = 0.6
    speaker_threshold: float = 0.6
    speaker_metric: str = "cosine"
    wake_engine: str = "mock"
    wake_threshold: float = 0.5
    wake_model: str = ""
    vad_engine: str = "mock"
    vad_threshold: float = 0.5
    max_utterance_s: float = 15.0
    silence_s: float = 0.8


@dataclass
class PermissionSettings:
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)


@dataclass
class RuntimeSettings:
    enabled: bool = True


@dataclass
class CoreSettings:
    enabled: bool = False
    endpoint: str | None = None


@dataclass
class RescsSettings:
    enabled: bool = False
    endpoint: str | None = None


@dataclass
class TIVISSConfig:
    """Validated, environment-overridable configuration."""

    agent: AgentSettings = field(default_factory=AgentSettings)
    model: ModelSettings = field(default_factory=ModelSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    permissions: PermissionSettings = field(default_factory=PermissionSettings)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    core: CoreSettings = field(default_factory=CoreSettings)
    rescs: RescsSettings = field(default_factory=RescsSettings)
    web: WebSettings = field(default_factory=WebSettings)
    calculator: CalculatorSettings = field(default_factory=CalculatorSettings)
    translation: TranslationSettings = field(default_factory=TranslationSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)

    @classmethod
    def defaults(cls) -> TIVISSConfig:
        return cls()

    def validate(self) -> list[str]:
        """Return a list of configuration problems (empty when valid)."""
        errors: list[str] = []
        if not self.agent.name.strip():
            errors.append("agent.name must be a non-empty string")
        if not self.agent.version.strip():
            errors.append("agent.version must be a non-empty string")
        if not self.agent.owner_id.strip():
            errors.append("agent.owner_id must be a non-empty string")
        if self.agent.agent_id is not None and not self.agent.agent_id.strip():
            errors.append("agent.agent_id must be a non-empty string when provided")

        if self.model.provider_id not in {"mock", "ollama"}:
            errors.append(
                "model.provider_id must be one of 'mock', 'ollama'; "
                f"got {self.model.provider_id!r}"
            )
        if not self.model.model_id.strip():
            errors.append("model.model_id must be a non-empty string")

        if self.memory.backend not in {"local", "rescs", "sqlite"}:
            errors.append(
                "memory.backend must be one of 'local', 'rescs', 'sqlite'; got "
                f"{self.memory.backend!r}"
            )

        for permission in [*self.permissions.allow, *self.permissions.deny]:
            if not self._valid_permission(permission):
                errors.append(f"permission is malformed: {permission!r}")

        # Validate dual SQLite paths
        if self.memory.backend == "sqlite":
            if not self.memory.conversation_db:
                errors.append("memory.conversation_db must be set when backend is 'sqlite'")
            if not self.memory.semantic_db:
                errors.append("memory.semantic_db must be set when backend is 'sqlite'")
            import pathlib
            for path in (self.memory.conversation_db, self.memory.semantic_db):
                if path:
                    parent = pathlib.Path(path).parent
                    if not pathlib.Path(parent).exists():
                        errors.append(f"memory database parent does not exist: {parent}")
        elif self.memory.storage_path:
            import pathlib

            parent = pathlib.Path(self.memory.storage_path).parent
            if not pathlib.Path(parent).exists():
                errors.append(f"memory.storage_path parent does not exist: {parent}")
        return errors

    @staticmethod
    def _valid_permission(name: str) -> bool:
        from ..permissions.permissions import Permission

        try:
            Permission.of(name)
        except ValueError:
            return False
        return True

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise ConfigValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        """Return a detached snapshot; mutating it never affects config."""
        return {
            "agent": dict(self.agent.__dict__),
            "model": dict(self.model.__dict__),
            "memory": dict(self.memory.__dict__),
            "permissions": {
                "allow": list(self.permissions.allow),
                "deny": list(self.permissions.deny),
            },
            "runtime": dict(self.runtime.__dict__),
            "core": dict(self.core.__dict__),
            "rescs": dict(self.rescs.__dict__),
            "web": dict(self.web.__dict__),
            "calculator": dict(self.calculator.__dict__),
            "translation": dict(self.translation.__dict__),
            "voice": dict(self.voice.__dict__),
        }

    # --- building agents -------------------------------------------------

    def build_identity(self):
        from ..identity.identity import AgentIdentity

        return AgentIdentity.create(
            agent_id=self.agent.agent_id,
            name=self.agent.name,
            version=self.agent.version,
            owner_id=self.agent.owner_id,
        )

    def build_provider(self):
        if self.model.provider_id == "mock":
            from ..models.mock import MockProvider

            return MockProvider(model_id=self.model.model_id, prefix=self.model.prefix)
        if self.model.provider_id == "ollama":
            from ..models.ollama import OllamaProvider

            return OllamaProvider(
                endpoint=self.model.endpoint,
                model_id=self.model.model_id,
                timeout_s=self.model.timeout_s,
                temperature=self.model.temperature,
                num_predict=self.model.num_predict,
                keep_alive=self.model.keep_alive,
                strip_thinking=self.model.strip_thinking,
            )
        raise ConfigValidationError(
            f"provider {self.model.provider_id!r} is not implemented yet"
        )

    def build_policy(self):
        from ..permissions.permissions import Permission
        from ..permissions.policy import DefaultDenyPolicy

        return DefaultDenyPolicy(
            allow={Permission.of(p) for p in self.permissions.allow},
            deny={Permission.of(p) for p in self.permissions.deny},
        )

    def build_memory(self):
        if self.memory.backend == "local":
            from ..memory.local import LocalMemory

            return LocalMemory(storage_path=self.memory.storage_path)
        if self.memory.backend == "sqlite":
            from ..memory.sqlite import SQLiteMemoryStore

            return SQLiteMemoryStore(
                conversation_db=self.memory.conversation_db,
                semantic_db=self.memory.semantic_db,
            )
        return None  # 'rescs' backend resolved via the RESCS adapter

    # --- loading ---------------------------------------------------------

    @staticmethod
    def _to_bool(raw: Any, default: bool) -> bool:
        """Parse booleans the same way for mappings and environment."""
        if isinstance(raw, bool):
            return raw
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def _to_float(cls, raw: Any, default: float, field_name: str) -> float:
        """Parse float with validation."""
        if raw is None:
            return default
        if isinstance(raw, (int, float)):
            return float(raw)
        try:
            return float(str(raw).strip())
        except ValueError:
            raise ConfigValidationError(f"{field_name} must be a valid number, got {raw!r}")

    @classmethod
    def _to_int(cls, raw: Any, default: int, field_name: str) -> int:
        """Parse int with validation."""
        if raw is None:
            return default
        if isinstance(raw, int):
            return raw
        try:
            return int(str(raw).strip())
        except ValueError:
            raise ConfigValidationError(f"{field_name} must be a valid integer, got {raw!r}")

    @classmethod
    def load(cls, data: Mapping[str, Any]) -> TIVISSConfig:
        """Load from a mapping, then normalise and validate."""
        config = cls.defaults()
        agent = data.get("agent") or {}
        model = data.get("model") or {}
        memory = data.get("memory") or {}
        permissions = data.get("permissions") or {}
        runtime = data.get("runtime") or {}
        core = data.get("core") or {}
        rescs = data.get("rescs") or {}
        web = data.get("web") or {}
        calculator = data.get("calculator") or {}
        translation = data.get("translation") or {}
        voice = data.get("voice") or {}

        config.agent = AgentSettings(
            name=str(agent.get("name", config.agent.name)),
            version=str(agent.get("version", config.agent.version)),
            agent_id=str(agent["agent_id"])
            if agent.get("agent_id") is not None
            else None,
            owner_id=str(agent.get("owner_id", config.agent.owner_id)),
        )
        config.model = ModelSettings(
            provider_id=str(model.get("provider_id", "mock")),
            model_id=str(model.get("model_id", config.model.model_id)),
            prefix=str(model.get("prefix", config.model.prefix)),
            endpoint=str(model.get("endpoint", config.model.endpoint)),
            timeout_s=cls._to_float(model.get("timeout_s"), config.model.timeout_s, "model.timeout_s"),
            temperature=cls._to_float(model.get("temperature"), config.model.temperature, "model.temperature"),
            num_predict=cls._to_int(model.get("num_predict"), config.model.num_predict, "model.num_predict"),
            keep_alive=str(model.get("keep_alive", config.model.keep_alive)),
            strip_thinking=cls._to_bool(model.get("strip_thinking"), config.model.strip_thinking),
        )
        config.memory = MemorySettings(
            backend=str(memory.get("backend", config.memory.backend)),
            conversation_db=str(memory["conversation_db"])
            if memory.get("conversation_db")
            else None,
            semantic_db=str(memory["semantic_db"])
            if memory.get("semantic_db")
            else None,
            storage_path=str(memory["storage_path"])
            if memory.get("storage_path")
            else None,
        )
        config.permissions = PermissionSettings(
            allow=[str(p) for p in (permissions.get("allow") or [])],
            deny=[str(p) for p in (permissions.get("deny") or [])],
        )
        config.runtime = RuntimeSettings(
            enabled=cls._to_bool(runtime.get("enabled"), config.runtime.enabled)
        )
        config.core = CoreSettings(
            enabled=cls._to_bool(core.get("enabled"), False),
            endpoint=core.get("endpoint"),
        )
        config.rescs = RescsSettings(
            enabled=cls._to_bool(rescs.get("enabled"), False),
            endpoint=rescs.get("endpoint"),
        )
        config.web = WebSettings(
            enabled=cls._to_bool(web.get("enabled"), config.web.enabled),
            search_provider=str(web.get("search_provider", config.web.search_provider)),
            timeout=cls._to_int(web.get("timeout"), config.web.timeout, "web.timeout"),
            max_results=cls._to_int(web.get("max_results"), config.web.max_results, "web.max_results"),
            max_chars=cls._to_int(web.get("max_chars"), config.web.max_chars, "web.max_chars"),
            max_query_length=cls._to_int(web.get("max_query_length"), config.web.max_query_length, "web.max_query_length"),
            max_url_length=cls._to_int(web.get("max_url_length"), config.web.max_url_length, "web.max_url_length"),
        )
        config.calculator = CalculatorSettings(
            enabled=cls._to_bool(calculator.get("enabled"), config.calculator.enabled),
            max_expression_chars=cls._to_int(calculator.get("max_expression_chars"), config.calculator.max_expression_chars, "calculator.max_expression_chars"),
            max_matrix_size=cls._to_int(calculator.get("max_matrix_size"), config.calculator.max_matrix_size, "calculator.max_matrix_size"),
            timeout=cls._to_int(calculator.get("timeout"), config.calculator.timeout, "calculator.timeout"),
            precision=cls._to_int(calculator.get("precision"), config.calculator.precision, "calculator.precision"),
            angle_mode=str(calculator.get("angle_mode", config.calculator.angle_mode)),
        )
        config.translation = TranslationSettings(
            enabled=cls._to_bool(translation.get("enabled"), config.translation.enabled),
            provider=str(translation.get("provider", config.translation.provider)),
            model=str(translation.get("model", config.translation.model)),
            model_path=str(translation.get("model_path", config.translation.model_path)),
            device=str(translation.get("device", config.translation.device)),
            cache_enabled=cls._to_bool(translation.get("cache_enabled"), config.translation.cache_enabled),
            cache_size=cls._to_int(translation.get("cache_size"), config.translation.cache_size, "translation.cache_size"),
            default_source=str(translation.get("default_source", config.translation.default_source)),
            default_target=str(translation.get("default_target", config.translation.default_target)),
            max_chars=cls._to_int(translation.get("max_chars"), config.translation.max_chars, "translation.max_chars"),
        )
        config.voice = VoiceSettings(
            enabled=cls._to_bool(voice.get("enabled"), config.voice.enabled),
            sample_rate=cls._to_int(voice.get("sample_rate"), config.voice.sample_rate, "voice.sample_rate"),
            channels=cls._to_int(voice.get("channels"), config.voice.channels, "voice.channels"),
            block_size=cls._to_int(voice.get("block_size"), config.voice.block_size, "voice.block_size"),
            stt_engine=str(voice.get("stt_engine", config.voice.stt_engine)),
            stt_model=str(voice.get("stt_model", config.voice.stt_model)),
            stt_device=str(voice.get("stt_device", config.voice.stt_device)),
            stt_compute_type=str(voice.get("stt_compute_type", config.voice.stt_compute_type)),
            stt_language=str(voice.get("stt_language", config.voice.stt_language)),
            tts_engine=str(voice.get("tts_engine", config.voice.tts_engine)),
            tts_voice=str(voice.get("tts_voice", config.voice.tts_voice)),
            tts_sample_rate=cls._to_int(voice.get("tts_sample_rate"), config.voice.tts_sample_rate, "voice.tts_sample_rate"),
            speaker_engine=str(voice.get("speaker_engine", config.voice.speaker_engine)),
            speaker_model=str(voice.get("speaker_model", config.voice.speaker_model)),
            speaker_device=str(voice.get("speaker_device", config.voice.speaker_device)),
            speaker_confidence=cls._to_float(voice.get("speaker_confidence"), config.voice.speaker_confidence, "voice.speaker_confidence"),
            speaker_threshold=cls._to_float(voice.get("speaker_threshold"), config.voice.speaker_threshold, "voice.speaker_threshold"),
            speaker_metric=str(voice.get("speaker_metric", config.voice.speaker_metric)),
            wake_engine=str(voice.get("wake_engine", config.voice.wake_engine)),
            wake_threshold=cls._to_float(voice.get("wake_threshold"), config.voice.wake_threshold, "voice.wake_threshold"),
            wake_model=str(voice.get("wake_model", config.voice.wake_model)),
            vad_engine=str(voice.get("vad_engine", config.voice.vad_engine)),
            vad_threshold=cls._to_float(voice.get("vad_threshold"), config.voice.vad_threshold, "voice.vad_threshold"),
            max_utterance_s=cls._to_float(voice.get("max_utterance_s"), config.voice.max_utterance_s, "voice.max_utterance_s"),
            silence_s=cls._to_float(voice.get("silence_s"), config.voice.silence_s, "voice.silence_s"),
        )
        config.assert_valid()
        return config

    @classmethod
    def load_env(cls, environ: Mapping[str, str] | None = None) -> TIVISSConfig:
        """Load configuration from ``TIVISS_*`` environment variables."""
        env = os.environ if environ is None else environ

        def _get(*names: str) -> str | None:
            for name in names:
                value = env.get(name)
                if value:
                    return value
            return None

        def _to_list(value: str | None) -> list[str]:
            return (
                [item.strip() for item in value.split(",") if item.strip()]
                if value
                else []
            )

        config = cls.defaults()
        if name := _get("TIVISS_AGENT_NAME"):
            config.agent.name = name
        if version := _get("TIVISS_AGENT_VERSION"):
            config.agent.version = version
        if agent_id := _get("TIVISS_AGENT_ID"):
            config.agent.agent_id = agent_id
        if owner := _get("TIVISS_OWNER_ID"):
            config.agent.owner_id = owner
        if model_id := _get("TIVISS_MODEL_ID"):
            config.model.model_id = model_id
        if prefix := _get("TIVISS_MODEL_PREFIX"):
            config.model.prefix = prefix
        if backend := _get("TIVISS_MEMORY_BACKEND"):
            config.memory.backend = backend
        if path := _get("TIVISS_MEMORY_STORAGE_PATH"):
            config.memory.storage_path = path
        if raw_allow := _get("TIVISS_PERMISSION_ALLOW"):
            config.permissions.allow = _to_list(raw_allow)
        if raw_deny := _get("TIVISS_PERMISSION_DENY"):
            config.permissions.deny = _to_list(raw_deny)
        if raw_runtime := _get("TIVISS_RUNTIME_ENABLED"):
            config.runtime.enabled = raw_runtime.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if raw_core := _get("TIVISS_CORE_ENABLED"):
            config.core.enabled = raw_core.strip().lower() in {"1", "true", "yes", "on"}
        if raw_rescs := _get("TIVISS_RESCS_ENABLED"):
            config.rescs.enabled = raw_rescs.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        # Model provider settings
        if provider := _get("TIVISS_MODEL_PROVIDER"):
            config.model.provider_id = provider
        if endpoint := _get("TIVISS_OLLAMA_ENDPOINT"):
            config.model.endpoint = endpoint
        if timeout := _get("TIVISS_OLLAMA_TIMEOUT"):
            config.model.timeout_s = float(timeout)
        if temp := _get("TIVISS_OLLAMA_TEMPERATURE"):
            config.model.temperature = float(temp)
        if predict := _get("TIVISS_OLLAMA_NUM_PREDICT"):
            config.model.num_predict = int(predict)
        if keep_alive := _get("TIVISS_OLLAMA_KEEP_ALIVE"):
            config.model.keep_alive = keep_alive
        if strip := _get("TIVISS_OLLAMA_STRIP_THINKING"):
            config.model.strip_thinking = strip.strip().lower() in {"1", "true", "yes", "on"}
        # Memory dual SQLite
        if conv_db := _get("TIVISS_MEMORY_CONVERSATION_DB"):
            config.memory.conversation_db = conv_db
        if sem_db := _get("TIVISS_MEMORY_SEMANTIC_DB"):
            config.memory.semantic_db = sem_db
        # Web settings
        if web_enabled := _get("TIVISS_WEB_ENABLED"):
            config.web.enabled = web_enabled.strip().lower() in {"1", "true", "yes", "on"}
        if max_query := _get("TIVISS_WEB_MAX_QUERY_LENGTH"):
            config.web.max_query_length = int(max_query)
        if max_url := _get("TIVISS_WEB_MAX_URL_LENGTH"):
            config.web.max_url_length = int(max_url)
        # Calculator settings
        if calc_enabled := _get("TIVISS_CALCULATOR_ENABLED"):
            config.calculator.enabled = calc_enabled.strip().lower() in {"1", "true", "yes", "on"}
        # Translation settings
        if trans_enabled := _get("TIVISS_TRANSLATION_ENABLED"):
            config.translation.enabled = trans_enabled.strip().lower() in {"1", "true", "yes", "on"}
        if trans_provider := _get("TIVISS_TRANSLATION_PROVIDER"):
            config.translation.provider = trans_provider
        # Voice settings
        if voice_enabled := _get("TIVISS_VOICE_ENABLED"):
            config.voice.enabled = voice_enabled.strip().lower() in {"1", "true", "yes", "on"}

        config.assert_valid()
        return config
