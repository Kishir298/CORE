"""Native LLM function calling: schemas, providers, normalization, loop.

Proves the model REQUESTS through structured definitions while A.S.I.S.
validates, authorizes, and executes through the EXISTING
ToolRegistry/Router/PermissionManager/Executor path — no second tool
framework. Heuristic intents remain the fallback.
"""

from __future__ import annotations

import pytest

from asis.ai import AIManager
from asis.ai.models import AIMessage, MessageRole, NativeToolCall
from asis.ai.providers import MockAIProvider, OllamaProvider
from asis.ai.tool_schemas import (
    ToolDefinition,
    ollama_tools,
    select_tool_definitions,
    tool_definition_for,
    tool_definitions_for,
    validate_call_arguments,
)
from asis.app import AssistantApp
from asis.app.actions import ToolRequest
from asis.app.native_tools import (
    NativeToolError,
    max_tool_calls,
    native_tools_enabled,
    normalize_native_call,
    normalize_native_calls,
)
from asis.configuration.settings import load_settings
from asis.errors import ConfigurationError, InferenceError
from asis.identity import build_identity
from asis.tools.base import Tool, ToolMetadata
from asis.tools.executor import ToolExecutor
from asis.tools.provided import (
    CurrentTimeTool,
    EchoTool,
    build_core_tools,
    register_core_tools,
)
from asis.tools.registry import ToolRegistry
from asis.tools.result import ToolResult
from asis.tools.router import ToolRouter


def _registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _user(content="hi"):
    return AIMessage(role=MessageRole.USER, content=content)


def _app(memory_manager, provider, router=None, core=None, **kw):
    return AssistantApp(
        identity=build_identity(),
        ai=AIManager(provider=provider),
        memory=memory_manager,
        tools_router=router,
        core=core,
        **kw,
    )


# -- schemas ------------------------------------------------------------


def test_definitions_deterministic_and_sorted():
    registry = _registry(EchoTool(), CurrentTimeTool())
    first = tool_definitions_for(registry)
    second = tool_definitions_for(
        _registry(CurrentTimeTool(), EchoTool())
    )
    assert [d.name for d in first] == ["current_time", "echo"]
    assert [(d.name, d.parameters) for d in first] == [
        (d.name, d.parameters) for d in second
    ]


def test_echo_schema_requires_text():
    definition = tool_definition_for(EchoTool())
    assert definition.parameters["required"] == ["text"]
    assert definition.parameters["properties"]["text"] == {"type": "string"}


def test_core_and_coding_schemas_present():
    registry = _registry(EchoTool())
    for tool in build_core_tools(None):
        registry.register(tool)
    from asis.coding.tools import build_coding_registry
    from asis.coding.workspace import resolve_workspace

    names = {d.name for d in tool_definitions_for(registry)}
    assert "core_send_to_device" in names
    assert "core_status" in names
    coding = build_coding_registry(resolve_workspace("."))
    coding_names = {d.name for d in tool_definitions_for(coding)}
    assert {"read_file", "run_command", "git_commit"} <= coding_names


def test_secret_vocabulary_rejected_from_schema():
    class SneakyTool(Tool):
        metadata = ToolMetadata(
            name="sneaky",
            description="Exfiltrate data.",
            category="evil",
            parameters={
                "type": "object",
                "properties": {"session_token": {"type": "string"}},
            },
        )

        def execute(self, **kwargs):
            return ToolResult.ok(data={}, tool_name=self.name)

    with pytest.raises(ValueError):
        tool_definition_for(SneakyTool())


def test_ollama_wire_shape():
    rendered = ollama_tools(
        [ToolDefinition(name="echo", description="Repeat text.", parameters={})]
    )
    assert rendered[0]["type"] == "function"
    assert rendered[0]["function"]["name"] == "echo"


# -- normalization --------------------------------------------------------


def test_normalize_valid_call():
    registry = _registry(EchoTool())
    result = normalize_native_call(
        NativeToolCall(name="echo", arguments={"text": "hi"}), registry
    )
    assert isinstance(result, ToolRequest)
    assert result.tool_name == "echo"
    assert result.arguments == {"text": "hi"}


def test_normalize_unknown_tool():
    result = normalize_native_call(
        NativeToolCall(name="rm_rf", arguments={}), _registry(EchoTool())
    )
    assert isinstance(result, NativeToolError)
    assert result.kind == "unknown_tool"


def test_normalize_malformed_calls():
    registry = _registry(EchoTool())
    assert normalize_native_call(None, registry).kind == "malformed_call"
    assert normalize_native_call("echo", registry).kind == "malformed_call"
    with pytest.raises(TypeError):
        NativeToolCall(name="  ", arguments={})


def test_normalize_missing_required_and_wrong_types():
    registry = _registry(EchoTool())
    missing = normalize_native_call(
        NativeToolCall(name="echo", arguments={}), registry
    )
    assert missing.kind == "schema_validation_failed"
    assert "text" in missing.message
    wrong = normalize_native_call(
        NativeToolCall(name="echo", arguments={"text": 42}), registry
    )
    assert wrong.kind == "schema_validation_failed"


def test_normalize_rejects_unknown_parameters():
    registry = _registry(EchoTool())
    injected = normalize_native_call(
        NativeToolCall(
            name="echo", arguments={"text": "hi", "credential": "x"}
        ),
        registry,
    )
    assert injected.kind == "schema_validation_failed"
    assert "credential" in injected.message


def test_normalize_batch_splits_valid_and_errors():
    registry = _registry(EchoTool())
    requests, errors = normalize_native_calls(
        [
            NativeToolCall(name="echo", arguments={"text": "a"}),
            NativeToolCall(name="nope", arguments={}),
        ],
        registry,
    )
    assert len(requests) == 1 and len(errors) == 1


def test_validate_argument_scalar_types():
    definition = ToolDefinition(
        name="t",
        description="typed.",
        parameters={
            "type": "object",
            "properties": {
                "s": {"type": "string"},
                "i": {"type": "integer"},
                "b": {"type": "boolean"},
                "a": {"type": "array"},
                "o": {"type": "object"},
            },
            "required": ["s"],
        },
    )
    ok, _ = validate_call_arguments(
        definition, {"s": "x", "i": 1, "b": True, "a": [], "o": {}}
    )
    assert ok is True
    # bool is not an integer; int is not a string
    assert validate_call_arguments(definition, {"s": "x", "i": True})[0] is False
    assert validate_call_arguments(definition, {"s": 1})[0] is False
    assert validate_call_arguments(definition, "nope")[0] is False


# -- providers ------------------------------------------------------------


def test_base_provider_denies_native_by_default():
    assert MockAIProvider().supports_native_tools is False
    assert OllamaProvider().supports_native_tools is True
    with pytest.raises(InferenceError):
        MockAIProvider().chat_with_tools([_user()], [])


def test_ollama_capability_and_parsing():
    provider = OllamaProvider()
    assert provider.supports_native_tools is True
    message = {
        "content": "",
        "tool_calls": [
            {"function": {"name": "echo", "arguments": {"text": "hi"}}},
            {"function": {"name": "", "arguments": {}}},
            {"function": {"name": "x", "arguments": "not-a-dict"}},
            {"nope": True},
            "junk",
        ],
    }
    parsed = OllamaProvider.parse_tool_calls(message)
    assert parsed == (NativeToolCall(name="echo", arguments={"text": "hi"}),)
    assert OllamaProvider.parse_tool_calls({}) == ()
    assert OllamaProvider.parse_tool_calls({"tool_calls": "bad"}) == ()


def test_ollama_chat_with_tools_sends_definitions(monkeypatch):
    seen: dict = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "current_time",
                                "arguments": {},
                            }
                        }
                    ],
                },
                "done": True,
            }

    def _fake_post(url, json=None, timeout=None):
        seen.update(json or {})
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)
    provider = OllamaProvider()
    response = provider.chat_with_tools(
        [_user("hi")],
        [
            ToolDefinition(
                name="current_time",
                description="Return the current UTC date and time.",
                parameters={"type": "object", "properties": {}},
            )
        ],
    )
    assert [t["function"]["name"] for t in seen["tools"]] == ["current_time"]
    assert response.tool_calls[0].name == "current_time"
    assert response.metadata.get("native_tools") is True


def test_mock_scripted_tool_sequences():
    provider = MockAIProvider(
        responses=("final",),
        tool_sequences=[[("echo", {"text": "hi"})], None],
    )
    # Tuple entries are ignored (only dict/NativeToolCall accepted).
    first = provider.chat_with_tools([_user()], [])
    assert first.tool_calls == ()
    provider2 = MockAIProvider(
        responses=("x",),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "hi"}}]],
    )
    second = provider2.chat_with_tools(
        [_user()],
        [ToolDefinition(name="echo", description="e.", parameters={})],
    )
    assert provider2.last_tools[0].name == "echo"
    assert second.tool_calls[0].arguments == {"text": "hi"}


# -- config ---------------------------------------------------------------


def test_native_tools_config_defaults_and_validation():
    fresh = load_settings(env={})
    assert fresh.ai.native_tools == "auto"
    assert fresh.tools.max_calls_per_turn == 3
    assert native_tools_enabled(fresh) is True
    assert max_tool_calls(fresh) == 3
    disabled = load_settings(env={"ASIS_AI_NATIVE_TOOLS": "FALSE"})
    assert disabled.ai.native_tools == "FALSE"
    assert native_tools_enabled(
        load_settings(env={"ASIS_AI_NATIVE_TOOLS": "false"})
    ) is False
    for bad in ("maybe", "yes", "on", "1"):
        with pytest.raises(ConfigurationError):
            load_settings(env={"ASIS_AI_NATIVE_TOOLS": bad})
    for bad in ("0", "11", "many"):
        with pytest.raises(ConfigurationError):
            load_settings(env={"ASIS_TOOL_MAX_CALLS_PER_TURN": bad})


# -- runtime loop ---------------------------------------------------------


def test_native_call_allowed_executes_and_finalizes(memory_manager):
    provider = MockAIProvider(
        responses=("mid", "The time is now."),
        tool_sequences=[[{"name": "current_time", "arguments": {}}], None],
    )
    app = _app(memory_manager, provider)
    reply = app.chat("what time is it")
    assert reply == "The time is now."
    assert provider.last_tools is not None
    assert "current_time" in [t.name for t in provider.last_tools]
    blob = " ".join(m.content for m in app.session.messages)
    assert "current_time result" in blob


def test_native_call_denied_never_executes(memory_manager):
    from asis.tools.provided import EchoTool as _Echo

    registry = ToolRegistry()
    registry.register(_Echo())
    denied_router = ToolRouter(
        registry, ToolExecutor(authorizer=lambda tool: False)
    )
    provider = MockAIProvider(
        responses=("fallback final",),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "hi"}}], None],
    )
    app = _app(memory_manager, provider, router=denied_router)
    reply = app.chat("run echo hi")
    assert reply == "fallback final"
    blob = " ".join(m.content for m in app.session.messages)
    assert "echo result" not in blob  # denied: no execution


def test_heuristic_fallback_when_native_unsupported(memory_manager):
    provider = MockAIProvider(responses=("it is noon",))
    assert provider.supports_native_tools is False
    app = _app(memory_manager, provider)
    reply = app.chat("what time is it")
    # Heuristic current_time intent still fires, then final inference.
    assert reply == "it is noon"


def test_fallback_when_model_answers_without_calls(memory_manager):
    provider = MockAIProvider(
        responses=("",),
        tool_sequences=[None],
    )
    app = _app(memory_manager, provider)
    # Empty native content -> heuristic fallback finds no intent either.
    assert app.chat("hello there") == ""


def test_unknown_native_tool_is_rejected_safely(memory_manager):
    provider = MockAIProvider(
        responses=("", "I cannot do that."),
        tool_sequences=[[{"name": "rm_rf", "arguments": {}}], None],
    )
    app = _app(memory_manager, provider)
    assert app.chat("delete everything") == "I cannot do that."
    blob = " ".join(m.content for m in app.session.messages)
    assert "Unknown tool" in blob


def test_malformed_native_arguments_rejected(memory_manager):
    provider = MockAIProvider(
        responses=("", "need valid args."),
        tool_sequences=[[{"name": "echo", "arguments": {}}], None],
    )
    app = _app(memory_manager, provider)
    assert app.chat("run echo hi") == "need valid args."
    blob = " ".join(m.content for m in app.session.messages)
    assert "Invalid arguments" in blob


def test_multi_step_loop_is_bounded(memory_manager):
    provider = MockAIProvider(
        responses=("f",),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "x"}}]] * 6,
    )
    app = _app(memory_manager, provider)
    app.chat("run loop please")
    blob = " ".join(m.content for m in app.session.messages)
    assert blob.count("echo result") == max_tool_calls()


# -- CORE / ASCS / voice share the path ------------------------------------


def test_native_core_tool_through_adapter(memory_manager):
    from asis.integrations.core.connection import CoreConnectionManager
    from asis.integrations.core.mock import MockCoreAdapter
    from asis.system.context import RuntimeContext

    mock = MockCoreAdapter()
    manager = CoreConnectionManager(
        mock, enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=False,
    )
    registry = ToolRegistry()
    register_core_tools(registry, manager)
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    provider = MockAIProvider(
        responses=("", "core is up."),
        tool_sequences=[[{"name": "core_status", "arguments": {}}], None],
    )
    ctx = RuntimeContext()
    manager.start(ctx)
    try:
        # HIGH CORE tools need an approving authorizer (console
        # confirmation would block under test capture).
        auto_router = ToolRouter(
            router.registry, ToolExecutor(authorizer=lambda tool: True)
        )
        app = _app(memory_manager, provider, router=auto_router, core=manager)
        assert app.chat("core status?") == "core is up."
        names = [t.name for t in provider.last_tools]
        assert "core_status" in names
    finally:
        manager.stop(ctx)


def test_native_core_offline_reports_unavailable(memory_manager):
    from asis.integrations.core.connection import CoreConnectionManager
    from asis.integrations.core.mock import MockCoreAdapter

    manager = CoreConnectionManager(
        MockCoreAdapter(), enabled=True, credential_provider=lambda: "cred",
        reconnect_enabled=False,
    )  # never started -> offline
    registry = ToolRegistry()
    register_core_tools(registry, manager)
    router = ToolRouter(registry, ToolExecutor(authorizer=lambda tool: True))
    provider = MockAIProvider(
        responses=("", "core is down."),
        tool_sequences=[[{"name": "core_discover_devices", "arguments": {}}], None],
    )
    auto_router = ToolRouter(
        router.registry, ToolExecutor(authorizer=lambda tool: True)
    )
    app = _app(memory_manager, provider, router=auto_router, core=manager)
    assert app.chat("list devices") == "core is down."
    blob = " ".join(m.content for m in app.session.messages)
    assert "CORE_UNAVAILABLE" in blob


def test_native_coding_tool_same_pipeline(memory_manager, tmp_path):
    from asis.app.modes import AssistantMode
    from asis.coding.workspace import resolve_workspace

    target = tmp_path / "note.txt"
    target.write_text("ascs-native")
    provider = MockAIProvider(
        responses=("", "file read."),
        tool_sequences=[
            [{"name": "read_file", "arguments": {"path": "note.txt"}}],
            None,
        ],
    )
    app = _app(
        memory_manager,
        provider,
        mode=AssistantMode.CODING,
        workspace=resolve_workspace(str(tmp_path)),
    )
    assert app.chat("read the note") == "file read."
    blob = " ".join(m.content for m in app.session.messages)
    assert "ascs-native" in blob


def test_voice_native_tool_same_application_path(memory_manager):
    from asis.voice import (
        MockAudioInput,
        MockAudioOutput,
        MockSpeakerIdentifier,
        MockSpeechRecognizer,
        MockTextToSpeech,
        VoicePipeline,
        VoiceRunner,
        VoiceRunnerConfig,
    )
    from asis.voice.models import AudioData

    provider = MockAIProvider(
        responses=("", "echo spoken."),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "hi"}}], None],
    )
    app = _app(memory_manager, provider)
    tts = MockTextToSpeech()
    pipe = VoicePipeline(
        MockAudioInput([AudioData(samples=[0], sample_rate=16000)]),
        MockSpeechRecognizer(text="run echo hi"),
        MockSpeakerIdentifier(),
        tts,
        MockAudioOutput(),
    )
    summary = VoiceRunner(
        pipe,
        app,
        config=VoiceRunnerConfig(require_wake_word=False, max_turns=1),
    ).run()
    assert summary["turns"] == 1
    assert tts.synthesized == ["echo spoken."]


# -- security boundaries ----------------------------------------------------


def test_native_shell_string_cannot_execute(memory_manager):
    provider = MockAIProvider(
        responses=("", "refused."),
        tool_sequences=[
            [{"name": "run_command", "arguments": {"argv": ["rm", "-rf", "/"]}}],
            None,
        ],
    )
    from asis.app.modes import AssistantMode
    from asis.coding.workspace import resolve_workspace

    auto_router = ToolRouter(
        _registry(EchoTool(), CurrentTimeTool()),
        ToolExecutor(authorizer=lambda tool: True),
    )
    app = _app(
        memory_manager,
        provider,
        router=auto_router,
        mode=AssistantMode.CODING,
        workspace=resolve_workspace("."),
    )
    assert app.chat("wipe the disk") == "refused."
    blob = " ".join(m.content for m in app.session.messages)
    assert "Command not allowed" in blob


def test_native_path_escape_rejected_by_sandbox(memory_manager, tmp_path):
    from asis.app.modes import AssistantMode
    from asis.coding.workspace import resolve_workspace

    provider = MockAIProvider(
        responses=("", "blocked."),
        tool_sequences=[
            [{"name": "read_file", "arguments": {"path": "../outside.txt"}}],
            None,
        ],
    )
    auto_router = ToolRouter(
        _registry(EchoTool(), CurrentTimeTool()),
        ToolExecutor(authorizer=lambda tool: True),
    )
    app = _app(
        memory_manager,
        provider,
        router=auto_router,
        mode=AssistantMode.CODING,
        workspace=resolve_workspace(str(tmp_path)),
    )
    assert app.chat("read outside") == "blocked."
    blob = " ".join(m.content for m in app.session.messages)
    assert "error" in blob


def test_native_call_cannot_confirm_itself(memory_manager):
    # A model-generated "confirmed"/"yes" argument is not authorization:
    # unknown params are rejected before the permission layer is reached.
    provider = MockAIProvider(
        responses=("", "still gated."),
        tool_sequences=[
            [{"name": "echo", "arguments": {"text": "hi", "confirmed": "yes"}}],
            None,
        ],
    )
    app = _app(memory_manager, provider)
    assert app.chat("run echo hi") == "still gated."
    blob = " ".join(m.content for m in app.session.messages)
    assert "echo result" not in blob
    assert "unknown parameter" in blob


def test_no_host_imports_still_hold():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "asis"
    offenders = [
        str(path)
        for path in root.rglob("*.py")
        if "from core.communication" in path.read_text(errors="ignore")
        or "from core.tcp" in path.read_text(errors="ignore")
    ]
    assert offenders == []
    import sys

    assert not any(
        name == "core" or name.startswith("core.") for name in sys.modules
    )


def test_schemas_and_results_never_carry_secrets(memory_manager):
    import json

    registry = ToolRegistry()
    registry.register(EchoTool())
    for tool in build_core_tools(None):
        registry.register(tool)
    blob = json.dumps([d.__dict__ for d in tool_definitions_for(registry)])
    for secret in ("token", "credential", "password", "secret", "private_key"):
        assert secret not in blob.lower()
    provider = MockAIProvider(
        responses=("", "ok."),
        tool_sequences=[[{"name": "core_status", "arguments": {}}], None],
    )
    app = _app(memory_manager, provider)
    app.chat("status")
    history = json.dumps([m.content for m in app.session.messages])
    assert "session_token" not in history


# -- intent-aware tool selection ----------------------------------------


def _default_definitions():
    from asis.app.assistant import build_default_tool_router

    return tool_definitions_for(build_default_tool_router().registry)


def test_filter_calculator_request_sends_only_calculate():
    selected = select_tool_definitions(_default_definitions(), "calculate")
    assert [d.name for d in selected] == ["calculate"]


def test_filter_web_request_sends_only_web_tools():
    selected = select_tool_definitions(_default_definitions(), "web")
    assert {d.name for d in selected} == {"web_search", "web_fetch"}


def test_filter_time_echo_translate_singletons():
    assert [
        d.name for d in select_tool_definitions(_default_definitions(), "time")
    ] == ["current_time"]
    assert [
        d.name for d in select_tool_definitions(_default_definitions(), "echo")
    ] == ["echo"]
    assert [
        d.name for d in select_tool_definitions(_default_definitions(), "translate")
    ] == ["translate_text"]


def test_filter_unknown_hint_and_coding_keep_full_set():
    full = _default_definitions()
    assert select_tool_definitions(full, None) == full
    assert select_tool_definitions(full, "coding-tools") == full
    assert select_tool_definitions(full, "nonsense-hint") == full


def test_filter_none_hint_returns_explicit_empty():
    assert select_tool_definitions(_default_definitions(), "none") == []


def test_filtered_out_tool_call_is_rejected_without_execution(memory_manager):
    provider = MockAIProvider(
        responses=("", "done."),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "hi"}}], None],
    )
    app = _app(memory_manager, provider)
    # Calculator hint exposes only `calculate`; the model's `echo` call
    # must be rejected before permission/execution.
    reply = app._run_native_tool_loop("calculate 1+1", tool_hint="calculate")
    assert reply == "done."
    blob = " ".join(m.content for m in app.session.messages)
    assert "Unknown tool" in blob
    assert "echo result" not in blob


def test_orchestrator_granular_hints():
    from asis.ai.orchestrator import build_plan

    assert build_plan("what time is it").tool_hint == "time"
    assert build_plan("search the web").tool_hint == "web"
    assert build_plan("fetch that page").tool_hint == "web"
    assert build_plan("translate hello to french").tool_hint == "translate"
    assert build_plan("calculate 6*7").tool_hint == "calculate"
    assert build_plan("what is 6 times 7").tool_hint == "calculate"
    # Generic questions keep the full set (conservative: never starve).
    assert build_plan("What should I do today?").tool_hint is None


def test_tool_turn_fallthrough_final_generation_streams(memory_manager):
    # When the loop exhausts without a direct continuation answer, the
    # final plain generation after the loop must stream through on_chunk.
    # (A continuation that already answers returns its buffered text
    # directly — no extra LLM call just to re-stream it; the CLI then
    # displays it via its legacy render fallback.)
    provider = MockAIProvider(
        responses=("", "", "streamed final."),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "x"}}], []],
    )
    app = _app(memory_manager, provider)
    chunks: list[str] = []
    reply = app.chat_streamed("run echo hi", on_chunk=chunks.append)
    assert reply.strip() == "streamed final."
    assert chunks, "fall-through final generation must stream chunks"
    assert "streamed final." in "".join(chunks)


def test_tool_continuation_answer_returns_without_extra_call(memory_manager):
    # A continuation that already answers with tool results in context is
    # the final response: no extra generation call is spent re-streaming
    # it (efficiency over the appearance of streaming).
    provider = MockAIProvider(
        responses=("", "direct answer."),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "x"}}], None],
    )
    app = _app(memory_manager, provider)
    assert app.chat_streamed("run echo hi", on_chunk=lambda c: None) == (
        "direct answer."
    )


def test_tool_decision_calls_stay_buffered(memory_manager):
    # The native tool-decision requests must not go through the
    # streaming path (Ollama chat_with_tools is stream=False by design).
    calls = {"with_tools": 0, "stream": 0}

    class Counting(MockAIProvider):
        def chat_with_tools(self, messages, tools):
            calls["with_tools"] += 1
            return super().chat_with_tools(messages, tools)

        def stream_chat(self, messages):
            calls["stream"] += 1
            yield from super().stream_chat(messages)

    provider = Counting(
        responses=("", "", "final answer."),
        tool_sequences=[[{"name": "echo", "arguments": {"text": "x"}}], []],
    )
    app = _app(memory_manager, provider)
    reply = app.chat_streamed("run echo hi", on_chunk=lambda c: None)
    assert reply.strip() == "final answer."
    assert calls["with_tools"] >= 1
    assert calls["stream"] >= 1


def test_tool_result_small_payloads_untouched():
    from asis.app.actions import format_tool_result_for_context

    ok = format_tool_result_for_context(ToolResult.ok(data={"a": 1}, tool_name="echo"))
    assert ok == "[tool echo result] {'a': 1}"
    err = format_tool_result_for_context(
        ToolResult.failure(error="nope", tool_name="echo")
    )
    assert err == "[tool echo error] nope"


def test_tool_result_large_payload_bounded_with_marker():
    from asis.app.actions import _TOOL_RESULT_MAX_CHARS, format_tool_result_for_context

    assert _TOOL_RESULT_MAX_CHARS == 4000
    big = "x" * 20000
    rendered = format_tool_result_for_context(
        ToolResult.ok(data={"blob": big}, tool_name="read_file")
    )
    assert len(rendered) <= _TOOL_RESULT_MAX_CHARS + 64
    assert "[truncated " in rendered
    assert rendered.startswith("[tool read_file result]")
    big_err = format_tool_result_for_context(
        ToolResult.failure(error="e" * 9000, tool_name="run_command")
    )
    assert "[truncated " in big_err
    assert big_err.startswith("[tool run_command error]")
