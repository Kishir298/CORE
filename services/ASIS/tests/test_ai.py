"""Tests for the AI subsystem: mock provider and AIManager."""

from __future__ import annotations

import pytest

from asis.ai import AIManager, AIMessage, MessageRole, create_provider
from asis.ai.providers import MockAIProvider


def _user(content: str) -> AIMessage:
    return AIMessage(role=MessageRole.USER, content=content)


def test_mock_provider_available():
    assert MockAIProvider().available() is True
    assert MockAIProvider(fail=True).available() is False


def test_mock_provider_chat():
    provider = MockAIProvider(model="m", responses=("Hello!",))
    response = provider.chat([_user("hi")])

    assert response.content == "Hello!"
    assert response.provider == "mock"
    assert response.model == "m"


def test_mock_provider_chat_fails_when_configured():
    provider = MockAIProvider(fail=True)
    with pytest.raises(ConnectionError):
        provider.chat([_user("hi")])


def test_mock_provider_cycles_responses():
    provider = MockAIProvider(responses=("one", "two", "three"))
    texts = [provider.chat([_user("a")]).content for _ in range(4)]
    assert texts == ["one", "two", "three", "one"]


def test_manager_rejects_empty_messages():
    manager = AIManager(provider=MockAIProvider())
    with pytest.raises(ValueError):
        manager.chat([])


def test_manager_chat_returns_response():
    manager = AIManager(provider=MockAIProvider(responses=("Hi there.",)))
    response = manager.chat([_user("hey")])
    assert response.content == "Hi there."


def test_manager_stream_chat():
    manager = AIManager(provider=MockAIProvider(responses=("hello world",)))
    chunks = list(manager.stream_chat([_user("x")]))
    assert "".join(chunks).strip() == "hello world"


def test_create_provider_mock():
    provider = create_provider("mock")
    assert provider.name == "mock"


def test_manager_available_uses_provider():
    assert AIManager(provider=MockAIProvider()).available() is True
    assert AIManager(provider=MockAIProvider(fail=True)).available() is False
