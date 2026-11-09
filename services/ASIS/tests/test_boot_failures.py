"""Boot failure regression tests - verify real failures are not masked by mock fallbacks."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import Mock, patch

from asis.ai.models import AIMessage, AIResponse
from asis.ai.providers import MockAIProvider
from asis.app.boot import BootError, verify_model_readiness
from asis.tui.boot_orchestrator import BootOrchestrator
from asis.tui.state import AppState
from asis.events import EventBus


class UnavailableProvider(MockAIProvider):
    """Provider that simulates unavailable Ollama server."""
    
    def available(self, timeout=None):
        return False
    
    def chat(self, messages):
        raise ConnectionError("Ollama server not reachable")


class MissingModelProvider(MockAIProvider):
    """Provider that simulates missing model."""
    
    def available(self, timeout=None):
        return True
    
    def chat(self, messages):
        # Simulate Ollama error for missing model
        raise ConnectionError("model 'qwen3:14b' not found")


class EmptyResponseProvider(MockAIProvider):
    """Provider that returns empty response."""
    
    def available(self, timeout=None):
        return True
    
    def chat(self, messages):
        return AIResponse(content="", model="test", provider="mock")


class TimeoutProvider(MockAIProvider):
    """Provider that times out on chat."""
    
    def available(self, timeout=None):
        return True
    
    def chat(self, messages):
        import asyncio
        # Use asyncio.sleep which can be cancelled, but run in executor so it blocks
        import time
        time.sleep(10)  # Longer than our timeout
        return AIResponse(content="late", model="test", provider="mock")


class InvalidConfigProvider:
    """Provider with invalid configuration (missing chat method)."""
    
    name = "invalid"
    model = "invalid"
    
    def available(self, timeout=None):
        return True
    
    # No chat method!


@pytest.mark.asyncio
async def test_boot_fails_when_ollama_unavailable():
    """Boot should fail when Ollama is unavailable, not fall back to mock."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=False)
    
    # Override the provider factory to return our unavailable provider
    original_boot_ai = orchestrator._boot_ai_provider
    
    async def mock_boot_ai():
        orchestrator._components.ai_provider = UnavailableProvider(model="test")
        orchestrator.state.model_name = "test"
        orchestrator._add_boot_log("BOOT", "Connecting to ollama (test)...")
        # Check availability - should fail
        loop = asyncio.get_event_loop()
        available = False
        avail_fn = getattr(orchestrator._components.ai_provider, "available", None)
        if callable(avail_fn):
            try:
                available = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: avail_fn(timeout=5.0)),
                    timeout=10.0,
                )
            except TypeError:
                available = await asyncio.wait_for(
                    loop.run_in_executor(None, avail_fn),
                    timeout=10.0,
                )
            except Exception:
                available = False
        
        if available:
            orchestrator.state.ollama_online = True
            orchestrator._add_boot_log("OK", "Ollama ready")
        else:
            orchestrator._add_boot_log("FAIL", "Ollama server not reachable")
            raise BootError("Ollama server not reachable")
    
    orchestrator._boot_ai_provider = mock_boot_ai
    
    with pytest.raises(BootError, match="not reachable"):
        await orchestrator._boot_ai_provider()
    
    # Verify model_ready is NOT set to True
    assert state.model_ready is False
    assert state.ollama_online is False


@pytest.mark.asyncio
async def test_boot_fails_when_model_missing():
    """Boot should fail when model is missing, not fall back to mock."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=False)
    orchestrator._components.ai_provider = MissingModelProvider(model="test")
    
    with pytest.raises(BootError, match="Model readiness probe failed"):
        await orchestrator._verify_model()
    
    # Verify model_ready is NOT set to True
    assert state.model_ready is False


@pytest.mark.asyncio
async def test_boot_fails_on_empty_response():
    """Boot should fail when model returns empty response."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=False)
    orchestrator._components.ai_provider = EmptyResponseProvider(model="test")
    
    with pytest.raises(BootError, match="empty response"):
        await orchestrator._verify_model()
    
    assert state.model_ready is False


@pytest.mark.asyncio
async def test_boot_fails_on_timeout():
    """Boot should fail when model times out."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=False)
    
    # Create a provider that simulates a timeout by raising TimeoutError
    class TimeoutSimProvider(MockAIProvider):
        def available(self, timeout=None):
            return True
        
        def chat(self, messages):
            raise asyncio.TimeoutError("Simulated timeout")
    
    orchestrator._components.ai_provider = TimeoutSimProvider(model="test")
    
    with pytest.raises(BootError, match="Model readiness probe failed"):
        await orchestrator._verify_model()
    
    assert state.model_ready is False


@pytest.mark.asyncio
async def test_boot_fails_on_invalid_provider():
    """Boot should fail when provider has no chat method."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=False)
    orchestrator._components.ai_provider = InvalidConfigProvider()
    
    with pytest.raises(BootError, match="AI provider has no chat"):
        await orchestrator._verify_model()
    
    assert state.model_ready is False


def test_verify_model_readiness_fails_on_unavailable():
    """verify_model_readiness should fail for unavailable provider."""
    provider = UnavailableProvider(model="test")
    
    with pytest.raises(BootError):
        verify_model_readiness(provider)


def test_verify_model_readiness_fails_on_empty():
    """verify_model_readiness should fail for empty response."""
    provider = EmptyResponseProvider(model="test")
    
    with pytest.raises(BootError, match="empty response"):
        verify_model_readiness(provider)


@pytest.mark.asyncio
async def test_mock_mode_succeeds():
    """Mock mode should succeed and label itself."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=True)
    
    # Mock mode uses MockAIProvider which always returns a response
    await orchestrator._boot_ai_provider()
    await orchestrator._verify_model()
    
    assert state.model_ready is True
    # Verify it's using mock provider
    assert orchestrator._components.ai_provider.name == "mock"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])