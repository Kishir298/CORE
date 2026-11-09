import tempfile
from pathlib import Path

import pytest

from tiviss.configuration import ConfigValidationError, TIVISSConfig
from tiviss.identity import AgentIdentity
from tiviss.memory import LocalMemory
from tiviss.models import MockProvider
from tiviss.permissions import DefaultDenyPolicy


def test_defaults_are_valid():
    config = TIVISSConfig.defaults()
    assert config.validate() == []


def test_default_values():
    config = TIVISSConfig.defaults()
    assert config.agent.name == "tiviss"
    assert config.agent.version
    assert config.model.provider_id == "mock"
    assert config.model.model_id == "tiviss-mock-1"
    assert config.memory.backend == "local"
    assert config.core.enabled is False
    assert config.rescs.enabled is False
    assert config.permissions.allow == []


def test_load_from_mapping():
    config = TIVISSConfig.load(
        {
            "agent": {"name": "tiv", "owner_id": "kishir", "agent_id": "tiv-1"},
            "model": {"model_id": "local-model"},
            "permissions": {"allow": ["conversation.generate"]},
            "core": {"enabled": True},
        }
    )
    assert config.agent.agent_id == "tiv-1"
    assert config.model.model_id == "local-model"
    assert config.permissions.allow == ["conversation.generate"]
    assert config.core.enabled is True


def test_load_invalid_provider_rejected():
    with pytest.raises(ConfigValidationError):
        TIVISSConfig.load({"model": {"provider_id": "openai", "model_id": "x"}})


def test_load_invalid_backend_rejected():
    with pytest.raises(ConfigValidationError):
        TIVISSConfig.load({"memory": {"backend": "tape"}})


def test_load_invalid_permission_rejected():
    with pytest.raises(ConfigValidationError):
        TIVISSConfig.load({"permissions": {"allow": ["not a valid permission!!"]}})


def test_load_env_overrides():
    env = {
        "TIVISS_AGENT_NAME": "env-agent",
        "TIVISS_AGENT_ID": "env-id",
        "TIVISS_OWNER_ID": "env-owner",
        "TIVISS_MODEL_ID": "env-model",
        "TIVISS_PERMISSION_ALLOW": "conversation.generate, memory.store",
        "TIVISS_CORE_ENABLED": "1",
        "TIVISS_RESCS_ENABLED": "true",
    }
    config = TIVISSConfig.load_env(env)
    assert config.agent.name == "env-agent"
    assert config.agent.agent_id == "env-id"
    assert config.agent.owner_id == "env-owner"
    assert config.model.model_id == "env-model"
    assert config.permissions.allow == ["conversation.generate", "memory.store"]
    assert config.core.enabled is True
    assert config.rescs.enabled is True


def test_load_env_without_overrides_uses_defaults(monkeypatch):
    monkeypatch.delenv("TIVISS_AGENT_NAME", raising=False)
    config = TIVISSConfig.load_env({})
    assert config.agent.name == "tiviss"


def test_build_identity():
    config = TIVISSConfig.load(
        {"agent": {"name": "tiv", "owner_id": "kishir", "agent_id": "tiv-1"}}
    )
    identity = config.build_identity()
    assert isinstance(identity, AgentIdentity)
    assert identity.agent_id == "tiv-1"
    assert identity.owner_id == "kishir"


def test_build_provider():
    config = TIVISSConfig.defaults()
    provider = config.build_provider()
    assert isinstance(provider, MockProvider)
    assert provider.model_id == "tiviss-mock-1"


def test_build_policy():
    config = TIVISSConfig.load({"permissions": {"allow": ["memory.store"]}})
    policy = config.build_policy()
    assert isinstance(policy, DefaultDenyPolicy)
    ctx_policy = policy
    from tiviss.permissions import Permission, PermissionContext

    assert (
        ctx_policy.check(
            PermissionContext(source="owner"), Permission.of("memory.store")
        )
        is True
    )
    assert (
        ctx_policy.check(PermissionContext(source="owner"), Permission.of("tools.run"))
        is False
    )


def test_build_memory(tmp_path):
    config = TIVISSConfig.load(
        {"memory": {"backend": "local", "storage_path": str(tmp_path / "m.json")}}
    )
    memory = config.build_memory()
    assert isinstance(memory, LocalMemory)


def test_secrets_not_in_config_surfaces():
    config = TIVISSConfig.defaults()
    serialized = config.to_dict()
    assert "secret" not in str(serialized).lower()
    assert "token" not in str(serialized).lower()
    assert "password" not in str(serialized).lower()


def test_to_dict_roundtrip_all_sections(tmp_path):
    """Test that to_dict serializes all sections and load() restores them exactly."""
    temp_dir = tempfile.gettempdir()
    original = TIVISSConfig.load({
        "agent": {
            "name": "roundtrip-agent",
            "owner_id": "test-owner",
            "agent_id": "rt-1",
            "version": "1.0.0"
        },
        "model": {
            "provider_id": "ollama",
            "model_id": "llama3",
            "endpoint": "http://localhost:11434",
            "timeout_s": 30.0,
            "temperature": 0.5,
            "num_predict": 100,
            "keep_alive": "10m",
            "strip_thinking": False
        },
        "memory": {
            "backend": "sqlite",
            "conversation_db": str(Path(temp_dir) / "conv.db"),
            "semantic_db": str(Path(temp_dir) / "sem.db")
        },
        "permissions": {
            "allow": ["conversation.generate", "memory.store"],
            "deny": ["tools.dangerous"]
        },
        "runtime": {"enabled": True},
        "core": {"enabled": True, "endpoint": "tcp://localhost:5000"},
        "rescs": {"enabled": False, "endpoint": None},
        "web": {
            "enabled": True,
            "search_provider": "duckduckgo",
            "timeout": 15,
            "max_results": 10,
            "max_chars": 4000,
            "max_query_length": 300,
            "max_url_length": 1024
        },
        "calculator": {
            "enabled": True,
            "max_expression_chars": 1500,
            "max_matrix_size": 8,
            "timeout": 20,
            "precision": 8,
            "angle_mode": "degrees"
        },
        "translation": {
            "enabled": True,
            "provider": "mock",
            "model": "test-model",
            "model_path": "/path/to/model",
            "device": "cpu",
            "cache_enabled": False,
            "cache_size": 100,
            "default_source": "en",
            "default_target": "es",
            "max_chars": 3000
        },
        "voice": {
            "enabled": True,
            "sample_rate": 22050,
            "channels": 2,
            "block_size": 512,
            "stt_engine": "whisper",
            "stt_model": "base",
            "stt_device": "cuda",
            "stt_compute_type": "float16",
            "stt_language": "en",
            "tts_engine": "piper",
            "tts_voice": "female",
            "tts_sample_rate": 22050,
            "speaker_engine": "speechbrain",
            "speaker_model": "ecapa",
            "speaker_device": "cuda",
            "speaker_confidence": 0.8,
            "speaker_threshold": 0.7,
            "speaker_metric": "cosine",
            "wake_engine": "porcupine",
            "wake_threshold": 0.6,
            "wake_model": "/path/to/wake",
            "vad_engine": "silero",
            "vad_threshold": 0.4,
            "max_utterance_s": 20.0,
            "silence_s": 1.0
        },
    })

    # Serialize to dict
    serialized = original.to_dict()

    # Verify all sections present
    expected_sections = [
        "agent", "model", "memory", "permissions", "runtime",
        "core", "rescs", "web", "calculator", "translation", "voice"
    ]
    for section in expected_sections:
        assert section in serialized, f"Missing section: {section}"

    # Load from serialized dict
    restored = TIVISSConfig.load(serialized)

    # Verify roundtrip equality for all fields
    assert restored.agent.name == original.agent.name
    assert restored.agent.owner_id == original.agent.owner_id
    assert restored.agent.agent_id == original.agent.agent_id
    assert restored.agent.version == original.agent.version

    assert restored.model.provider_id == original.model.provider_id
    assert restored.model.model_id == original.model.model_id
    assert restored.model.endpoint == original.model.endpoint
    assert restored.model.timeout_s == original.model.timeout_s
    assert restored.model.temperature == original.model.temperature
    assert restored.model.num_predict == original.model.num_predict
    assert restored.model.keep_alive == original.model.keep_alive
    assert restored.model.strip_thinking == original.model.strip_thinking

    assert restored.memory.backend == original.memory.backend
    assert restored.memory.conversation_db == original.memory.conversation_db
    assert restored.memory.semantic_db == original.memory.semantic_db

    assert restored.permissions.allow == original.permissions.allow
    assert restored.permissions.deny == original.permissions.deny

    assert restored.runtime.enabled == original.runtime.enabled
    assert restored.core.enabled == original.core.enabled
    assert restored.core.endpoint == original.core.endpoint
    assert restored.rescs.enabled == original.rescs.enabled
    assert restored.rescs.endpoint == original.rescs.endpoint

    assert restored.web.enabled == original.web.enabled
    assert restored.web.search_provider == original.web.search_provider
    assert restored.web.timeout == original.web.timeout
    assert restored.web.max_results == original.web.max_results
    assert restored.web.max_chars == original.web.max_chars
    assert restored.web.max_query_length == original.web.max_query_length
    assert restored.web.max_url_length == original.web.max_url_length

    assert restored.calculator.enabled == original.calculator.enabled
    assert restored.calculator.max_expression_chars == original.calculator.max_expression_chars
    assert restored.calculator.max_matrix_size == original.calculator.max_matrix_size
    assert restored.calculator.timeout == original.calculator.timeout
    assert restored.calculator.precision == original.calculator.precision
    assert restored.calculator.angle_mode == original.calculator.angle_mode

    assert restored.translation.enabled == original.translation.enabled
    assert restored.translation.provider == original.translation.provider
    assert restored.translation.model == original.translation.model
    assert restored.translation.model_path == original.translation.model_path
    assert restored.translation.device == original.translation.device
    assert restored.translation.cache_enabled == original.translation.cache_enabled
    assert restored.translation.cache_size == original.translation.cache_size
    assert restored.translation.default_source == original.translation.default_source
    assert restored.translation.default_target == original.translation.default_target
    assert restored.translation.max_chars == original.translation.max_chars

    assert restored.voice.enabled == original.voice.enabled
    assert restored.voice.sample_rate == original.voice.sample_rate
    assert restored.voice.channels == original.voice.channels
    assert restored.voice.block_size == original.voice.block_size
    assert restored.voice.stt_engine == original.voice.stt_engine
    assert restored.voice.stt_model == original.voice.stt_model
    assert restored.voice.stt_device == original.voice.stt_device
    assert restored.voice.stt_compute_type == original.voice.stt_compute_type
    assert restored.voice.stt_language == original.voice.stt_language
    assert restored.voice.tts_engine == original.voice.tts_engine
    assert restored.voice.tts_voice == original.voice.tts_voice
    assert restored.voice.tts_sample_rate == original.voice.tts_sample_rate
    assert restored.voice.speaker_engine == original.voice.speaker_engine
    assert restored.voice.speaker_model == original.voice.speaker_model
    assert restored.voice.speaker_device == original.voice.speaker_device
    assert restored.voice.speaker_confidence == original.voice.speaker_confidence
    assert restored.voice.speaker_threshold == original.voice.speaker_threshold
    assert restored.voice.speaker_metric == original.voice.speaker_metric
    assert restored.voice.wake_engine == original.voice.wake_engine
    assert restored.voice.wake_threshold == original.voice.wake_threshold
    assert restored.voice.wake_model == original.voice.wake_model
    assert restored.voice.vad_engine == original.voice.vad_engine
    assert restored.voice.vad_threshold == original.voice.vad_threshold
    assert restored.voice.max_utterance_s == original.voice.max_utterance_s
    assert restored.voice.silence_s == original.voice.silence_s
