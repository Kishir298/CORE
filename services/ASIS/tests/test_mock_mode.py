"""Mock mode regression tests - verify explicit --mock works and labels itself."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from asis.tui.app import ASISTUI
from asis.tui.boot_orchestrator import BootOrchestrator
from asis.tui.state import AppState
from asis.events import EventBus
from asis.ai.providers import MockAIProvider


def test_mock_mode_tui_mount():
    """Test that TUI mounts in mock mode."""
    app = ASISTUI(mock_mode=True)
    app.run(headless=True, inline=True)
    # If we get here, mount succeeded


def test_mock_mode_boot_orchestrator():
    """Test that BootOrchestrator works in mock mode."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=True)
    
    # Verify mock mode is set
    assert orchestrator.mock_mode is True
    
    # Run boot sequence
    import asyncio
    components = asyncio.run(orchestrator.run())
    
    # Verify provider is mock
    assert components.ai_provider is not None
    assert components.ai_provider.name == "mock"
    
    # Verify state shows model ready
    assert state.model_ready is True
    assert state.ollama_online is False  # Mock mode doesn't check Ollama
    
    # Verify boot log shows (MOCK) label
    mock_logs = [entry for entry in state.boot_log if "(MOCK)" in entry.message]
    assert len(mock_logs) > 0


def test_mock_mode_provider_is_mock():
    """Test that mock mode uses MockAIProvider."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=True)
    
    import asyncio
    components = asyncio.run(orchestrator.run())
    
    assert isinstance(components.ai_provider, MockAIProvider)
    assert components.ai_provider.name == "mock"


def test_mock_mode_boot_log_labels():
    """Test that mock mode boot logs are labeled."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=True)
    
    import asyncio
    asyncio.run(orchestrator.run())
    
    # Check that boot logs contain (MOCK) labels
    log_messages = [entry.message for entry in state.boot_log]
    
    # AI provider should be labeled as MOCK
    ai_provider_logs = [msg for msg in log_messages if "AI provider" in msg]
    assert any("(MOCK)" in msg for msg in ai_provider_logs)
    
    # Model ready should work in mock mode
    model_ready_logs = [msg for msg in log_messages if "Model ready" in msg]
    assert len(model_ready_logs) > 0


def test_mock_mode_cli_args():
    """Test that TUI accepts mock mode CLI args."""
    app = ASISTUI(
        mock_mode=True,
        ai_temperature=0.5,
        ai_think="false",
        ai_num_predict=100,
        ai_keep_alive="10m",
    )
    
    assert app.mock_mode is True
    assert app.state.ai_temperature == 0.5
    assert app.state.ai_think == "false"
    assert app.state.ai_num_predict == 100
    assert app.state.ai_keep_alive == "10m"


def test_non_mock_mode_requires_ollama():
    """Test that non-mock mode fails when Ollama is unavailable."""
    state = AppState()
    event_bus = EventBus()
    
    orchestrator = BootOrchestrator(state=state, event_bus=event_bus, mock_mode=False)
    
    # Mock the provider to simulate unavailable Ollama
    from asis.ai.providers import MockAIProvider
    class UnavailableProvider(MockAIProvider):
        def available(self, timeout=None):
            return False
    
    # Replace the provider creation
    original_boot_ai = orchestrator._boot_ai_provider
    
    async def mock_boot_ai():
        provider = UnavailableProvider(model="test")
        orchestrator._components.ai_provider = provider
        orchestrator.state.model_name = "test"
        orchestrator._add_boot_log("BOOT", "Connecting to ollama (test)...")
        # Check availability - should fail
        loop = asyncio.get_event_loop()
        available = False
        avail_fn = getattr(provider, "available", None)
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
            raise Exception("Ollama server not reachable")
    
    orchestrator._boot_ai_provider = mock_boot_ai
    
    import asyncio
    with pytest.raises(Exception, match="Ollama server not reachable"):
        asyncio.run(orchestrator.run())


def test_mock_mode_vs_real_mode_difference():
    """Test that mock mode and real mode behave differently."""
    state_mock = AppState()
    state_real = AppState()
    event_bus = EventBus()
    
    orchestrator_mock = BootOrchestrator(state=state_mock, event_bus=event_bus, mock_mode=True)
    orchestrator_real = BootOrchestrator(state=state_real, event_bus=event_bus, mock_mode=False)
    
    import asyncio
    
    # Mock mode should succeed
    components_mock = asyncio.run(orchestrator_mock.run())
    assert state_mock.model_ready is True
    assert components_mock.ai_provider.name == "mock"
    
    # Real mode with mocked unavailable Ollama should fail
    from asis.ai.providers import MockAIProvider
    class UnavailableProvider(MockAIProvider):
        def available(self, timeout=None):
            return False
    
    # Replace the provider creation for real mode
    original_boot_ai = orchestrator_real._boot_ai_provider
    
    async def mock_boot_ai():
        provider = UnavailableProvider(model="test")
        orchestrator_real._components.ai_provider = provider
        orchestrator_real.state.model_name = "test"
        orchestrator_real._add_boot_log("BOOT", "Connecting to ollama (test)...")
        loop = asyncio.get_event_loop()
        available = False
        avail_fn = getattr(provider, "available", None)
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
            orchestrator_real.state.ollama_online = True
            orchestrator_real._add_boot_log("OK", "Ollama ready")
        else:
            orchestrator_real._add_boot_log("FAIL", "Ollama server not reachable")
            raise Exception("Ollama server not reachable")
    
    orchestrator_real._boot_ai_provider = mock_boot_ai
    
    with pytest.raises(Exception, match="Ollama server not reachable"):
        asyncio.run(orchestrator_real.run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])