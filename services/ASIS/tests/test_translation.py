"""Offline Translation Engine: registry, detection, provider, engine,
tool, native calling, modes, voice, offline isolation, configuration.

All deterministic and offline: the scripted mock provider backs
translation tests; the real MADLAD backend is covered by missing-model
errors plus the opt-in live file (test_translation_live.py).
"""

from __future__ import annotations

import socket

import pytest

from asis.ai import AIManager
from asis.ai.providers import MockAIProvider
from asis.ai.tool_schemas import tool_definitions_for
from asis.app import AssistantApp
from asis.app.assistant import build_coding_tool_router, build_default_tool_router
from asis.app.modes import AssistantMode, parse_mode
from asis.app.profiles import get_profile
from asis.configuration.settings import load_settings
from asis.errors import ConfigurationError
from asis.identity import build_identity
from asis.permissions.manager import PermissionManager
from asis.tools.executor import ToolExecutor
from asis.tools.provided.translation_tools import (
    TranslateTextTool,
    register_translation_tools,
)
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter
from asis.translation import (
    TranslationCache,
    TranslationEngine,
    TranslationError,
    build_provider,
)
from asis.translation.detection import detect_language
from asis.translation.languages import (
    get_language,
    is_speech_input_supported,
    is_speech_output_supported,
    is_supported,
    normalize_code,
    supported_languages,
)
from asis.translation.provider import (
    MockTranslationProvider,
    TranslationProviderError,
)


def _app(memory_manager, provider, router=None, **kw):
    return AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=provider),
        memory=memory_manager,
        tools_router=router,
        **kw,
    )


def _translation_router(engine=None, authorizer=None):
    registry = ToolRegistry()
    registry.register(TranslateTextTool(engine))
    return ToolRouter(
        registry,
        ToolExecutor(
            authorizer=authorizer if authorizer is not None else (lambda t: True)
        ),
    )


# -- registry ---------------------------------------------------------------


def test_registry_has_100_plus_languages():
    languages = supported_languages()
    assert len(languages) >= 100


def test_registry_codes_valid_and_unique():
    codes = [lang.code for lang in supported_languages()]
    assert len(codes) == len(set(codes))
    for code in codes:
        assert code == code.strip().lower()
        assert code.replace("-", "").replace("_", "").isalnum()


def test_registry_required_languages():
    hindi = get_language("hi")
    assert hindi is not None and hindi.script == "Deva"
    assert "हिन्दी" in hindi.native_name
    french = get_language("fr")
    assert french is not None and french.script == "Latn"
    arabic = get_language("ar")
    assert arabic is not None and arabic.script == "Arab"
    assert all(is_supported(code) for code in ("en", "hi", "fr", "ar"))


def test_registry_normalizes_and_rejects():
    assert normalize_code(" HI ") == "hi"
    assert normalize_code("xx") is None
    assert is_supported("zu") is True
    assert is_supported("xx") is False


def test_registry_madlad_tags():
    assert get_language("en").madlad_tag == "<2en>"
    assert get_language("hi").madlad_tag == "<2hi>"
    assert get_language("nb").madlad_tag == "<2no>"


def test_registry_speech_capabilities_are_separate():
    assert is_speech_input_supported("hi") is True
    assert is_speech_output_supported("hi") is True
    # Text-only languages must not claim speech support.
    assert is_speech_input_supported("qu") is False
    assert is_speech_output_supported("zu") is False
    assert is_speech_input_supported("xx") is False
    assert is_speech_output_supported("xx") is False


# -- required pairs ------------------------------------------------------------


@pytest.mark.parametrize(
    "source,target,text,expected",
    [
        ("en", "hi", "Hello", "नमस्ते"),
        ("hi", "en", "नमस्ते", "Hello"),
        ("en", "fr", "Hello", "Bonjour"),
        ("fr", "en", "Bonjour", "Hello"),
        ("en", "ar", "Hello", "مرحبا"),
        ("ar", "en", "مرحبا", "Hello"),
        ("hi", "fr", "नमस्ते", "Bonjour"),
        ("fr", "hi", "Bonjour", "नमस्ते"),
        ("hi", "ar", "धन्यवाद", "شكرا"),
        ("ar", "hi", "شكرا", "धन्यवाद"),
        ("fr", "ar", "Merci", "شكرا"),
        ("ar", "fr", "شكرا", "Merci"),
        ("en", "hi", "Where is the nearest airport?", "निकटतम हवाई अड्डा कहाँ है?"),
        (
            "en",
            "fr",
            "Where is the nearest airport?",
            "Où est l'aéroport le plus proche ?",
        ),
        ("en", "ar", "Where is the nearest airport?", "أين يقع أقرب مطار؟"),
    ],
)
def test_required_pairs_both_directions(source, target, text, expected):
    engine = TranslationEngine()
    result = engine.translate_text(text, target, source)
    assert result.translated_text == expected
    assert result.source_language == source
    assert result.target_language == target
    assert result.detected_source is False


def test_translation_preserves_metadata():
    result = TranslationEngine().translate_text("Thank you", "hi", "en")
    assert result.translated_text == "धन्यवाद"
    assert result.source_text == "Thank you"
    assert result.provider == "mock"
    assert result.model == "mock-phrase-table"
    assert result.cached is False


def test_translation_unicode_and_scripts():
    engine = TranslationEngine()
    assert engine.translate_text("नमस्ते", "en", "hi").translated_text == "Hello"
    assert engine.translate_text("مرحبا", "en", "ar").translated_text == "Hello"


def test_translation_empty_and_oversized_rejected():
    engine = TranslationEngine(max_chars=10)
    with pytest.raises(TranslationError) as exc:
        engine.translate_text("   ", "fr", "en")
    assert exc.value.code == "TRANSLATION_INVALID_INPUT"
    with pytest.raises(TranslationError) as exc:
        engine.translate_text("Hello world, this is long", "fr", "en")
    assert exc.value.code == "TRANSLATION_TOO_LARGE"


def test_translation_unsupported_language():
    engine = TranslationEngine()
    with pytest.raises(TranslationError) as exc:
        engine.translate_text("Hello", "xx", "en")
    assert exc.value.code == "TRANSLATION_UNSUPPORTED_LANGUAGE"
    with pytest.raises(TranslationError) as exc:
        engine.translate_text("Hello", "fr", "xx")
    assert exc.value.code == "TRANSLATION_UNSUPPORTED_LANGUAGE"


def test_translation_same_language_passthrough():
    result = TranslationEngine().translate_text("Hello", "en", "en")
    assert result.translated_text == "Hello"


# -- detection ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Where is the nearest airport?", "en"),
        ("Où est l'aéroport le plus proche ?", "fr"),
        ("नमस्ते, आप कैसे हैं? धन्यवाद", "hi"),
        ("أين يقع أقرب مطار؟ شكرا", "ar"),
        ("Hola, ¿dónde está el aeropuerto? Gracias", "es"),
        ("Wo ist der nächste Flughafen? Danke", "de"),
    ],
)
def test_detection_required_languages(text, expected):
    result = detect_language(text)
    assert result.language == expected
    assert result.uncertain is False


def test_detection_short_text_is_uncertain():
    result = detect_language("Hello")
    assert result.uncertain is True


def test_detection_unknown_input_returns_no_language():
    assert detect_language("").language is None
    assert detect_language("12345 !!!").language is None
    assert detect_language("xyzzy qwert").language is None


def test_engine_auto_detect_and_uncertain_refusal():
    engine = TranslationEngine()
    auto = engine.translate_text("Où est l'aéroport le plus proche ?", "en")
    assert auto.source_language == "fr"
    assert auto.detected_source is True
    with pytest.raises(TranslationError) as exc:
        engine.translate_text("Hi", "fr")
    assert exc.value.code == "LANGUAGE_DETECTION_FAILED"


# -- span protection ---------------------------------------------------------------


def test_protect_spans_round_trip():
    text = "See https://example.com/a and /usr/bin/x plus `code()` today"
    masked, spans = TranslationEngine.protect_spans(text)
    assert "https://example.com/a" not in masked
    assert "/usr/bin/x" not in masked
    assert "`code()`" not in masked
    assert TranslationEngine.restore_spans(masked, spans) == text


def test_protected_spans_survive_translation():
    masked, spans = TranslationEngine.protect_spans("Visit https://example.com today")
    assert spans == ["https://example.com"]
    phrases = {("en", "fr"): {masked: f"Visitez {masked.split()[1]} aujourd'hui"}}
    engine = TranslationEngine(provider=MockTranslationProvider(phrases))
    result = engine.translate_text("Visit https://example.com today", "fr", "en")
    assert result.translated_text == "Visitez https://example.com aujourd'hui"


# -- provider ------------------------------------------------------------------------


def test_mock_provider_records_and_pivots():
    provider = MockTranslationProvider()
    assert provider.translate("Hello", "en", "hi") == "नमस्ते"
    assert provider.calls == [("Hello", "en", "hi")]
    assert provider.is_pair_supported("hi", "fr") is True
    with pytest.raises(TranslationProviderError) as exc:
        provider.translate("No such entry anywhere", "en", "hi")
    assert exc.value.code == "TRANSLATION_PROVIDER_ERROR"


def test_provider_factory_and_model_errors():
    assert build_provider("mock").name == "mock"
    with pytest.raises(TranslationProviderError) as exc:
        build_provider("google")
    assert exc.value.code == "TRANSLATION_PROVIDER_ERROR"
    with pytest.raises(TranslationProviderError) as exc:
        build_provider("madlad", model_path="")
    assert exc.value.code == "TRANSLATION_MODEL_NOT_INSTALLED"
    with pytest.raises(TranslationProviderError) as exc:
        build_provider("madlad", model_path="/nonexistent/weights")
    assert exc.value.code == "TRANSLATION_MODEL_NOT_INSTALLED"


class _FailingProvider(MockTranslationProvider):
    def translate(self, text, source, target):
        raise TranslationProviderError(
            "TRANSLATION_MODEL_NOT_INSTALLED",
            "TRANSLATION_MODEL_NOT_INSTALLED: gone",
        )


def test_engine_maps_model_not_installed():
    engine = TranslationEngine(provider=_FailingProvider())
    with pytest.raises(TranslationError) as exc:
        engine.translate_text("Hello", "fr", "en")
    assert exc.value.code == "TRANSLATION_MODEL_NOT_INSTALLED"


# -- cache -----------------------------------------------------------------------------


def test_cache_hit_and_bound():
    cache = TranslationCache(max_size=2)
    engine = TranslationEngine(cache=cache)
    first = engine.translate_text("Hello", "hi", "en")
    assert first.cached is False
    second = engine.translate_text("Hello", "hi", "en")
    assert second.cached is True
    assert second.translated_text == first.translated_text
    engine.translate_text("Thank you", "hi", "en")
    engine.translate_text("Good morning", "hi", "en")
    assert len(cache) == 2


def test_cache_disabled_never_hits():
    engine = TranslationEngine(cache=TranslationCache(enabled=False))
    assert engine.translate_text("Hello", "hi", "en").cached is False
    assert engine.translate_text("Hello", "hi", "en").cached is False


# -- tool -------------------------------------------------------------------


def test_translate_tool_registered_in_both_routers(tmp_path):
    from asis.coding.workspace import CodingWorkspace

    assert "translate_text" in build_default_tool_router().registry.list_names()
    coding = build_coding_tool_router(CodingWorkspace(tmp_path.resolve()))
    assert "translate_text" in coding.registry.list_names()


def test_translate_tool_schema():
    registry = ToolRegistry()
    register_translation_tools(registry, MockTranslationProvider())
    definitions = {d.name: d for d in tool_definitions_for(registry)}
    schema = definitions["translate_text"].parameters
    assert schema["required"] == ["text", "target_language"]
    assert set(schema["properties"]) == {"text", "target_language", "source_language"}


def test_translate_tool_executes_and_validates():
    tool = TranslateTextTool(TranslationEngine())
    ok = tool.execute(text="Hello", target_language="hi", source_language="en")
    assert ok.success is True
    assert ok.data["translated_text"] == "नमस्ते"
    assert ok.data["source_language"] == "en"
    assert tool.execute(text="   ", target_language="hi").success is False
    assert tool.execute(text="Hello", target_language="").success is False
    bad = tool.execute(text="Hello", target_language="xx", source_language="en")
    assert bad.success is False
    assert "TRANSLATION_UNSUPPORTED_LANGUAGE" in bad.error


def test_translate_tool_uses_configured_default_source(monkeypatch):
    import sys as _sys

    module = _sys.modules["asis.configuration.settings"]
    monkeypatch.setattr(
        module, "settings", load_settings({"ASIS_TRANSLATION_DEFAULT_SOURCE": "en"})
    )
    tool = TranslateTextTool(TranslationEngine())
    ok = tool.execute(text="Hello", target_language="fr")
    assert ok.success is True
    assert ok.data["translated_text"] == "Bonjour"


def test_translate_tool_disabled_returns_clean_error(monkeypatch):
    import sys as _sys

    module = _sys.modules["asis.configuration.settings"]
    monkeypatch.setattr(
        module, "settings", load_settings({"ASIS_TRANSLATION_ENABLED": "false"})
    )
    tool = TranslateTextTool(TranslationEngine())
    result = tool.execute(text="Hello", target_language="hi", source_language="en")
    assert result.success is False
    assert result.error.startswith("TRANSLATION_DISABLED")


def test_translate_denied_never_executes():
    engine = TranslationEngine(provider=MockTranslationProvider())
    router = _translation_router(engine, authorizer=lambda tool: False)
    result = router.execute("translate_text", text="Hello", target_language="hi")
    assert result.success is False
    assert engine.provider.calls == []


def test_native_translate_call_executes(memory_manager):
    ai = MockAIProvider(
        responses=("", "Voici la traduction."),
        tool_sequences=[
            [{"name": "translate_text",
              "arguments": {"text": "Hello", "target_language": "fr",
                            "source_language": "en"}}],
            None,
        ],
    )
    app = _app(
        memory_manager, ai,
        router=_translation_router(TranslationEngine()),
    )
    assert app.chat("translate hello to french") == "Voici la traduction."
    blob = " ".join(m.content for m in app.session.messages)
    assert "translate_text result" in blob
    assert "Bonjour" in blob


def test_native_translate_unknown_language_rejected(memory_manager):
    engine = TranslationEngine(provider=MockTranslationProvider())
    ai = MockAIProvider(
        responses=("", "can't do that."),
        tool_sequences=[
            [{"name": "translate_text",
              "arguments": {"text": "Hello", "target_language": "xx"}}],
            None,
        ],
    )
    app = _app(memory_manager, ai, router=_translation_router(engine))
    assert app.chat("translate to xx") == "can't do that."
    assert engine.provider.calls == []


def test_translated_instruction_stays_data(memory_manager, tmp_path):
    """'delete all my files' in another language must not touch the FS."""
    from asis.coding.workspace import CodingWorkspace

    workspace = CodingWorkspace(tmp_path.resolve())
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("keep me")
    ai = MockAIProvider(
        responses=("", "Translated only."),
        tool_sequences=[
            [{"name": "translate_text",
              "arguments": {"text": "delete all my files",
                            "target_language": "hi", "source_language": "en"}}],
            None,
        ],
    )
    coding = build_coding_tool_router(workspace)
    router = ToolRouter(coding.registry, ToolExecutor(authorizer=lambda t: True))
    app = _app(memory_manager, ai, router=router, mode="coding", workspace=workspace)
    # Translation-only app path: exercise the general router with fakes.
    simple = _app(
        memory_manager,
        MockAIProvider(
            responses=("", "Translated only."),
            tool_sequences=[
                [{"name": "translate_text",
                  "arguments": {"text": "delete all my files",
                                "target_language": "hi", "source_language": "en"}}],
                None,
            ],
        ),
        router=_translation_router(TranslationEngine()),
    )
    assert simple.chat("translate that") == "Translated only."
    blob = " ".join(m.content for m in simple.session.messages)
    assert "मेरी सभी फ़ाइलें हटा दें" in blob
    assert sentinel.read_text() == "keep me"
    assert app.chat("list files") is not None  # coding path unaffected


# -- modes / CLI ------------------------------------------------------------


def test_translation_mode_parse_and_profile():
    assert parse_mode("translation") is AssistantMode.TRANSLATION
    assert parse_mode(" TRANSLATION ") is AssistantMode.TRANSLATION
    profile = get_profile(AssistantMode.TRANSLATION)
    assert "translat" in profile.instructions.lower()


def test_translation_mode_direct_turn(memory_manager):
    app = _app(
        memory_manager, MockAIProvider(responses=("unused",)), mode="translation"
    )
    app.set_translation_languages(source="en", target="fr")
    assert app.chat("Hello") == "Bonjour"
    assert app.translation_target == "fr"
    assert app.translation_source == "en"


def test_translation_mode_auto_detect_turn(memory_manager):
    app = _app(
        memory_manager, MockAIProvider(responses=("unused",)), mode="translation"
    )
    app.set_translation_languages(target="en")
    assert app.translation_source == "auto"
    reply = app.chat("Où est l'aéroport le plus proche ?")
    assert reply == "[fr] Where is the nearest airport?"


def test_translation_mode_uncertain_source_reports_error(memory_manager):
    app = _app(
        memory_manager, MockAIProvider(responses=("unused",)), mode="translation"
    )
    reply = app.chat("Hi")
    assert "LANGUAGE_DETECTION_FAILED" in reply


def test_translation_language_setters(memory_manager):
    app = _app(memory_manager, MockAIProvider(responses=("x",)))
    assert app.set_translation_languages(source="en", target="hi") == ("en", "hi")
    assert app.set_translation_languages(source="auto") == ("auto", "hi")
    with pytest.raises(ValueError):
        app.set_translation_languages(source="xx")
    with pytest.raises(ValueError):
        app.set_translation_languages(target="xx")


def test_mode_commands_translate_and_languages(memory_manager):
    from asis.cli.main import handle_mode_command

    app = _app(memory_manager, MockAIProvider(responses=("x",)))
    assert "Translation mode" in handle_mode_command(app, "/translate")
    assert app.mode is AssistantMode.TRANSLATION
    assert "fr" in handle_mode_command(app, "/tr-to fr")
    assert "auto" in handle_mode_command(app, "/tr-from auto")
    assert "Unsupported" in handle_mode_command(app, "/tr-to xx")
    assert "translation" in handle_mode_command(app, "/mode translation").lower()
    assert handle_mode_command(app, "/mode general") == "A.S.I.S. general mode enabled."


def test_voice_mode_phrases_include_translation():
    from asis.voice.commands import parse_voice_mode_command

    assert (
        parse_voice_mode_command("enable translation mode")
        is AssistantMode.TRANSLATION
    )
    assert parse_voice_mode_command("translation mode") is AssistantMode.TRANSLATION
    assert parse_voice_mode_command("exit translation mode") is AssistantMode.GENERAL


def test_translate_cli_single_shot(capsys):
    from asis.cli.translate import run_translate

    assert (
        run_translate(
            ["--message", "Hello", "--from", "en", "--to", "hi", "--provider", "mock"]
        )
        == 0
    )
    assert "नमस्ते" in capsys.readouterr().out


def test_translate_cli_rejects_unknown_language(capsys):
    from asis.cli.translate import run_translate

    assert (
        run_translate(["--message", "Hello", "--to", "xx", "--provider", "mock"]) == 2
    )
    assert "Unsupported target language" in capsys.readouterr().out


def test_coding_mode_shares_translate_tool(memory_manager, tmp_path):
    from asis.coding.workspace import CodingWorkspace

    workspace = CodingWorkspace(tmp_path.resolve())
    ai = MockAIProvider(
        responses=("", "translated in coding mode."),
        tool_sequences=[
            [{"name": "translate_text",
              "arguments": {"text": "Hello", "target_language": "hi",
                            "source_language": "en"}}],
            None,
        ],
    )
    import asis.translation.engine as engine_module

    real_builder = engine_module.build_engine_from_settings
    fake = TranslationEngine()
    engine_module.build_engine_from_settings = lambda settings_obj=None: fake
    try:
        app = _app(memory_manager, ai, mode="coding", workspace=workspace)
        assert app.chat("translate hello") == "translated in coding mode."
        assert fake.provider.calls
    finally:
        engine_module.build_engine_from_settings = real_builder


# -- voice --------------------------------------------------------------------


def test_voice_speech_to_text_translation():
    from asis.translation.voice import speech_to_text_translation

    result = speech_to_text_translation(
        "Hello", "hi", stt_language="en", engine=TranslationEngine()
    )
    assert result.translated_text == "नमस्ते"


def test_voice_speech_to_speech_translation():
    from asis.translation.voice import speech_to_speech_translation
    from asis.voice.engines.mock import MockTextToSpeech

    tts = MockTextToSpeech()
    result, audio = speech_to_speech_translation(
        "Hello", "fr", tts, stt_language="en", engine=TranslationEngine()
    )
    assert result.translated_text == "Bonjour"
    assert tts.synthesized == ["Bonjour"]
    assert audio is not None


def test_voice_text_to_speech_translation():
    from asis.translation.voice import text_to_speech_translation
    from asis.voice.engines.mock import MockTextToSpeech

    tts = MockTextToSpeech()
    result, _audio = text_to_speech_translation(
        "Thank you", "ar", tts, source="en", engine=TranslationEngine()
    )
    assert result.translated_text == "شكرا"
    assert tts.synthesized == ["شكرا"]


def test_voice_stt_language_gate():
    from asis.translation.voice import translate_speech

    with pytest.raises(TranslationError) as exc:
        translate_speech("Hello", "hi", stt_language="xx", engine=TranslationEngine())
    assert exc.value.code == "STT_LANGUAGE_UNSUPPORTED"


def test_voice_tts_language_gate():
    from asis.translation.voice import text_to_speech_translation
    from asis.voice.engines.mock import MockTextToSpeech

    phrases = {("en", "zu"): {"Hello": "Sawubona"}}
    engine = TranslationEngine(provider=MockTranslationProvider(phrases))
    with pytest.raises(TranslationError) as exc:
        text_to_speech_translation(
            "Hello", "zu", MockTextToSpeech(), source="en", engine=engine
        )
    assert exc.value.code == "TTS_LANGUAGE_UNSUPPORTED"


def test_voice_full_pipeline_mocked(memory_manager):
    from asis.translation.voice import speech_to_text_translation
    from asis.voice import (
        MockAudioInput,
        MockAudioOutput,
        MockSpeakerIdentifier,
        MockSpeechRecognizer,
        MockTextToSpeech,
        VoicePipeline,
    )
    from asis.voice.models import AudioData

    engine = TranslationEngine()
    seen: list[str] = []

    def _process(text, speaker):
        translated = speech_to_text_translation(
            text, "hi", stt_language="en", engine=engine
        ).translated_text
        seen.append(translated)
        return translated

    tts = MockTextToSpeech()
    pipe = VoicePipeline(
        MockAudioInput([AudioData(samples=[0], sample_rate=16000)]),
        MockSpeechRecognizer(text="Hello"),
        MockSpeakerIdentifier(),
        tts,
        MockAudioOutput(),
    )
    # Drive the pipeline with a translation process function instead of chat.
    out = pipe.run_once(process_fn=_process, require_wake_word=False)
    assert out["status"] == "spoken"
    assert seen == ["नमस्ते"]
    assert tts.synthesized == ["नमस्ते"]


# -- offline ------------------------------------------------------------------


def test_offline_translation_works_without_network(monkeypatch):
    def _no_dns(host, port, *args, **kwargs):
        raise socket.gaierror(8, "offline")

    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    engine = TranslationEngine()
    assert engine.translate_text("Hello", "ar", "en").translated_text == "مرحبا"


def test_offline_missing_model_is_deterministic(monkeypatch):
    def _no_dns(host, port, *args, **kwargs):
        raise socket.gaierror(8, "offline")

    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    with pytest.raises(TranslationProviderError) as exc:
        build_provider("madlad", model_path="/nonexistent/weights")
    assert exc.value.code == "TRANSLATION_MODEL_NOT_INSTALLED"


def test_offline_translation_failure_keeps_local_tools(memory_manager):
    router = build_default_tool_router()
    bad = router.execute("translate_text", text="Hello", target_language="xx")
    assert bad.success is False
    assert router.execute("echo", text="ok").success is True


# -- configuration -------------------------------------------------------------


def test_translation_config_defaults(monkeypatch):
    for name in (
        "ASIS_TRANSLATION_ENABLED",
        "ASIS_TRANSLATION_PROVIDER",
        "ASIS_TRANSLATION_MODEL",
        "ASIS_TRANSLATION_MODEL_PATH",
        "ASIS_TRANSLATION_DEVICE",
        "ASIS_TRANSLATION_CACHE_ENABLED",
        "ASIS_TRANSLATION_CACHE_SIZE",
        "ASIS_TRANSLATION_DEFAULT_SOURCE",
        "ASIS_TRANSLATION_DEFAULT_TARGET",
        "ASIS_TRANSLATION_MAX_CHARS",
    ):
        monkeypatch.delenv(name, raising=False)
    config = load_settings()
    assert config.translation.enabled is True
    assert config.translation.provider == "mock"
    assert config.translation.model == "google/madlad400-3b-mt"
    assert config.translation.device == "cpu"
    assert config.translation.cache_size == 200
    assert config.translation.default_source == "auto"
    assert config.translation.default_target == "en"
    assert config.translation.max_chars == 5000


@pytest.mark.parametrize(
    "env",
    [
        {"ASIS_TRANSLATION_PROVIDER": "google"},
        {"ASIS_TRANSLATION_DEFAULT_TARGET": "xx"},
        {"ASIS_TRANSLATION_DEFAULT_SOURCE": "xx"},
        {"ASIS_TRANSLATION_CACHE_SIZE": "0"},
        {"ASIS_TRANSLATION_MAX_CHARS": "0"},
        {"ASIS_TRANSLATION_ENABLED": "maybe"},
        {"ASIS_TRANSLATION_CACHE_ENABLED": "maybe"},
    ],
)
def test_translation_invalid_config_rejected(env):
    with pytest.raises(ConfigurationError):
        load_settings(env)


def test_translation_permission_is_low():
    from asis.permissions.models import PermissionLevel

    tool = TranslateTextTool(TranslationEngine())
    assert tool.permission is PermissionLevel.LOW
    manager = PermissionManager()
    assert manager.needs_confirmation(tool) is False
