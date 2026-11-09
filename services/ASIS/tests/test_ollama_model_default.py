"""Ollama default-model correction: A.S.I.S. must default to qwen3:14b.

Deterministic and offline: HTTP is mocked, no live Ollama required.

Covers:
1. Default Ollama provider configuration resolves to qwen3:14b.
2. Explicit model override still works.
3. The Ollama request uses the configured model.
4. Tool-enabled requests use the configured model.
5. Normal (fallback/plain) requests use the configured model.
"""

from __future__ import annotations

import os

from asis.ai import AIManager
from asis.ai.models import AIMessage, MessageRole
from asis.ai.tool_schemas import ToolDefinition
from asis.configuration import defaults, load_settings

DEFAULT_MODEL = "qwen3:14b"
OVERRIDE_MODEL = "custom-override-model"


def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("ASIS_"):
            monkeypatch.delenv(key, raising=False)


def _user(content="hi"):
    return AIMessage(role=MessageRole.USER, content=content)


def _tool_defs():
    return [
        ToolDefinition(
            name="echo",
            description="Repeat text.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
    ]


# 1. Default resolves to qwen3:14b ------------------------------------------


def test_authoritative_default_is_qwen3_14b():
    assert defaults.AI_MODEL == DEFAULT_MODEL


def test_default_settings_resolve_to_qwen3_14b(monkeypatch):
    _clean_env(monkeypatch)
    config = load_settings()
    assert config.ai.provider == "ollama"
    assert config.ai.model == DEFAULT_MODEL


def test_default_ollama_provider_resolves_to_qwen3_14b(monkeypatch):
    _clean_env(monkeypatch)
    from asis.ai.providers.ollama import OllamaProvider

    assert OllamaProvider().model == DEFAULT_MODEL
    # Single-sourced: provider default tracks the authoritative default.
    assert OllamaProvider().model == defaults.AI_MODEL
    assert OllamaProvider().model == load_settings().ai.model


def test_cli_default_model_is_qwen3_14b(monkeypatch):
    _clean_env(monkeypatch)
    # Re-read settings after cleaning so the CLI default reflects built-ins.
    from asis.cli.main import build_parser

    args = build_parser().parse_args([])
    # CLI defaults come from settings; with a clean env that is the new default.
    # (If the developer shell exports ASIS_AI_MODEL, the CLI correctly
    # honors the environment instead — covered by the override test.)
    if "ASIS_AI_MODEL" not in os.environ:
        assert args.model == DEFAULT_MODEL
    assert load_settings().ai.model == DEFAULT_MODEL


# 2. Explicit override still works --------------------------------------------


def test_explicit_model_override(monkeypatch):
    _clean_env(monkeypatch)
    from asis.ai.providers.ollama import OllamaProvider

    assert load_settings({"ASIS_AI_MODEL": OVERRIDE_MODEL}).ai.model == OVERRIDE_MODEL
    monkeypatch.setenv("ASIS_AI_MODEL", OVERRIDE_MODEL)
    assert load_settings().ai.model == OVERRIDE_MODEL
    assert OllamaProvider(model=OVERRIDE_MODEL).model == OVERRIDE_MODEL


def test_cli_model_override(monkeypatch):
    _clean_env(monkeypatch)
    from asis.cli.main import _provider, build_parser

    args = build_parser().parse_args(["--model", OVERRIDE_MODEL])
    assert args.model == OVERRIDE_MODEL
    provider = _provider(args.provider, args.model)
    assert provider.model == OVERRIDE_MODEL

    voice_parser_args = None
    translate_parser_args = None
    try:
        from asis.cli.translate import build_translate_parser
        from asis.cli.voice import build_voice_parser

        voice_parser_args = build_voice_parser().parse_args(["--model", OVERRIDE_MODEL])
        translate_parser_args = build_translate_parser().parse_args(
            ["--model", OVERRIDE_MODEL]
        )
    except Exception:
        pass
    if voice_parser_args is not None:
        assert voice_parser_args.model == OVERRIDE_MODEL
    if translate_parser_args is not None:
        assert translate_parser_args.model == OVERRIDE_MODEL


def test_manager_create_provider_uses_configured_model(monkeypatch):
    _clean_env(monkeypatch)
    import asis.ai.manager as manager_module
    from asis.configuration.settings import reset_settings

    # Use environment variables to configure settings (reset_settings reads from env)
    monkeypatch.setenv("ASIS_AI_MODEL", OVERRIDE_MODEL)
    reset_settings()
    
    provider = manager_module.create_provider("ollama")
    assert provider.name == "ollama"
    assert provider.model == OVERRIDE_MODEL

    # Reset to defaults
    monkeypatch.delenv("ASIS_AI_MODEL", raising=False)
    reset_settings()
    default_provider = manager_module.create_provider("ollama")
    assert default_provider.model == DEFAULT_MODEL


# 3. Ollama request uses the configured model ---------------------------------


def test_ollama_chat_request_uses_configured_model(monkeypatch):
    from asis.ai.providers.ollama import OllamaProvider

    seen: dict = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "ok"}, "done": True}

    def _fake_post(url, json=None, timeout=None, **kwargs):
        seen.update(json or {})
        seen["url"] = url
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    default_response = OllamaProvider().chat([_user("hi")])
    assert seen["model"] == DEFAULT_MODEL
    assert default_response.model == DEFAULT_MODEL
    assert "/api/chat" in seen["url"]

    override_response = OllamaProvider(model=OVERRIDE_MODEL).chat([_user("hi")])
    assert seen["model"] == OVERRIDE_MODEL
    assert override_response.model == OVERRIDE_MODEL


# 4. Tool-enabled requests use the configured model ----------------------------


def test_ollama_tool_enabled_request_uses_configured_model(monkeypatch):
    from asis.ai.providers.ollama import OllamaProvider

    seen: dict = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "done"}, "done": True}

    def _fake_post(url, json=None, timeout=None, **kwargs):
        seen.update(json or {})
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    default_response = OllamaProvider().chat_with_tools([_user("hi")], _tool_defs())
    assert seen["model"] == DEFAULT_MODEL
    assert default_response.model == DEFAULT_MODEL
    assert len(seen["tools"]) == 1
    assert seen["tools"][0]["function"]["name"] == "echo"

    override_response = OllamaProvider(model=OVERRIDE_MODEL).chat_with_tools(
        [_user("hi")], _tool_defs()
    )
    assert seen["model"] == OVERRIDE_MODEL
    assert override_response.model == OVERRIDE_MODEL


# 5. Normal fallback (plain) requests use the configured model -----------------


def test_manager_plain_and_tool_requests_use_configured_model(monkeypatch):
    """AIManager.chat (fallback path) and chat_with_tools both propagate it."""
    from asis.ai.providers.ollama import OllamaProvider

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    calls: list[dict] = []

    def _fake_post(url, json=None, timeout=None, **kwargs):
        calls.append(dict(json or {}))
        if (json or {}).get("tools"):
            return _FakeResponse({"message": {"content": "tooled"}, "done": True})
        return _FakeResponse({"message": {"content": "plain"}, "done": True})

    monkeypatch.setattr("requests.post", _fake_post)

    manager = AIManager(provider=OllamaProvider())
    plain = manager.chat([_user("hello")])
    assert plain.model == DEFAULT_MODEL
    assert calls[-1]["model"] == DEFAULT_MODEL
    assert "tools" not in calls[-1]

    tooled = manager.chat_with_tools([_user("hello")], _tool_defs())
    assert tooled.model == DEFAULT_MODEL
    assert calls[-1]["model"] == DEFAULT_MODEL
    assert len(calls[-1]["tools"]) == 1

    override_manager = AIManager(provider=OllamaProvider(model=OVERRIDE_MODEL))
    plain_override = override_manager.chat([_user("hello")])
    assert plain_override.model == OVERRIDE_MODEL
    assert calls[-1]["model"] == OVERRIDE_MODEL


def test_native_tool_support_and_fallback_preserved():
    from asis.ai.providers import MockAIProvider
    from asis.ai.providers.ollama import OllamaProvider

    provider = OllamaProvider()
    assert provider.supports_native_tools is True
    assert MockAIProvider().supports_native_tools is False
    # Fallback path still exists: plain chat works without tools.
    assert hasattr(provider, "chat")
    assert hasattr(provider, "chat_with_tools")
