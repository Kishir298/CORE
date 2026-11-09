"""
Boot Orchestrator - Decoupled boot sequence with dependency injection.

This module provides a clean separation of concerns for the ASIS boot process,
allowing for easier testing and configuration of individual components.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from asis.ai.manager import AIManager, create_provider
from asis.ai.providers import AIProvider, MockAIProvider
from asis.app.assistant import AssistantApp
from asis.app.boot import BootError
from asis.app.modes import AssistantMode as AppAssistantMode
from asis.app.routers import build_default_tool_router
from asis.configuration import settings
from asis.events import EventBus
from asis.identity import build_identity
from asis.memory import MemoryDatabase, MemoryManager, MemoryStorage
from asis.tui.state import AppState, VoiceState
from asis.tui.widgets import BootLogPanel
from asis.voice.engines.mock import (
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    MockVadDetector,
)
from asis.voice.pipeline import VoicePipeline

logger = logging.getLogger("asis.boot.orchestrator")


class IdentityProvider(Protocol):
    """Protocol for identity providers."""

    def build(self) -> Any:
        ...


class MemoryProvider(Protocol):
    """Protocol for memory providers."""

    def __init__(self, manager: MemoryManager) -> None:
        ...


class ToolRouterProvider(Protocol):
    """Protocol for tool router providers."""

    def build(self) -> Any:
        ...


class AIProviderFactory(Protocol):
    """Protocol for AI provider factories."""

    def create(self, settings_obj: Any) -> AIProvider:
        ...


class VoicePipelineFactory(Protocol):
    """Protocol for voice pipeline factories."""

    def create(self, event_bus: EventBus) -> VoicePipeline:
        ...


@dataclass
class BootComponents:
    """Container for all boot components."""

    identity: Any = None
    memory: MemoryManager | None = None
    tool_router: Any = None
    ai_provider: AIProvider | None = None
    ai_manager: AIManager | None = None
    assistant_app: AssistantApp | None = None
    voice_pipeline: VoicePipeline | None = None
    event_bus: EventBus | None = None


class BootOrchestrator:
    """
    Orchestrates the ASIS boot sequence with dependency injection.

    This class decouples the boot process from the TUI app, allowing
    for easier testing and configuration of individual components.
    """

    def __init__(
        self,
        state: AppState,
        event_bus: EventBus,
        boot_log_panel: BootLogPanel | None = None,
        mock_mode: bool = False,
        # Dependency injection hooks
        identity_provider: IdentityProvider | None = None,
        memory_provider_factory: Callable[[], MemoryManager] | None = None,
        tool_router_provider: ToolRouterProvider | None = None,
        ai_provider_factory: AIProviderFactory | None = None,
        voice_pipeline_factory: VoicePipelineFactory | None = None,
    ) -> None:
        self.state = state
        self.event_bus = event_bus
        self.boot_log_panel = boot_log_panel
        self.mock_mode = mock_mode
        self._components = BootComponents()

        # DI hooks (use defaults if not provided)
        self._identity_provider = identity_provider or DefaultIdentityProvider()
        self._memory_provider_factory = memory_provider_factory or self._default_memory_factory
        self._tool_router_provider = tool_router_provider or DefaultToolRouterProvider()
        self._ai_provider_factory = ai_provider_factory
        self._voice_pipeline_factory = voice_pipeline_factory or DefaultVoicePipelineFactory()

    def _add_boot_log(self, status: str, message: str) -> None:
        """Add a boot log entry."""
        self.state.add_boot_log(status, message)
        if self.boot_log_panel:
            self.boot_log_panel.refresh()
        logger.info("Boot: %s - %s", status, message)

    def _default_memory_factory(self) -> MemoryManager:
        """Default memory factory using SQLite."""
        db_path = settings.paths.memory / settings.memory.database_name
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return MemoryManager(MemoryStorage(MemoryDatabase(db_path)))

    async def run(self) -> BootComponents:
        """Run the complete boot sequence."""
        self._add_boot_log("BOOT", "Starting ASIS boot sequence...")

        # Step 1: Identity
        await self._boot_identity()

        # Step 2: Memory
        await self._boot_memory()

        # Step 3: Tool Router
        await self._boot_tool_router()

        # Step 4: AI Provider
        await self._boot_ai_provider()

        # Step 5: Model Verification
        await self._verify_model()

        # Step 6: AI Manager
        await self._boot_ai_manager()

        # Step 7: Assistant App
        await self._boot_assistant_app()

        # Step 8: Voice Pipeline
        await self._boot_voice_pipeline()

        # Propagate event bus to components
        self._components.event_bus = self.event_bus

        self._add_boot_log("OK", "A.S.I.S. ready.")
        return self._components

    async def _boot_identity(self) -> None:
        """Boot identity system."""
        try:
            identity = self._identity_provider.build()
            self._components.identity = identity
            self._add_boot_log("OK", "Identity loaded")
        except Exception as exc:
            self._add_boot_log("FAIL", f"Identity failed: {exc}")
            raise BootError(f"Identity boot failed: {exc}") from exc

    async def _boot_memory(self) -> None:
        """Boot memory system."""
        try:
            memory = self._memory_provider_factory()
            self._components.memory = memory
            self.state.memory_ready = True
            self._add_boot_log("OK", "Memory initialized")
        except Exception as exc:
            self._add_boot_log("FAIL", f"Memory failed: {exc}")
            raise BootError(f"Memory boot failed: {exc}") from exc

    async def _boot_tool_router(self) -> None:
        """Boot tool router."""
        try:
            tool_router = self._tool_router_provider.build()
            ensure_all_tools = __import__("asis.app.routers", fromlist=["ensure_all_tools"]).ensure_all_tools
            ensure_all_tools(tool_router, None)
            self._components.tool_router = tool_router
            self.state.tools_ready = True
            self._add_boot_log("OK", "Tools initialized")
        except Exception as exc:
            self._add_boot_log("FAIL", f"Tools failed: {exc}")
            raise BootError(f"Tool router boot failed: {exc}") from exc

    async def _boot_ai_provider(self) -> None:
        """Boot AI provider."""
        try:
            if self.mock_mode:
                provider = MockAIProvider(model=settings.ai.model)
                self.state.model_name = settings.ai.model
                self._add_boot_log("OK", "AI provider ready (MOCK)")
            else:
                # Use injected factory if provided, otherwise fall back to default Ollama provider
                if self._ai_provider_factory is not None:
                    # Create a settings object with CLI overrides applied for the factory
                    factory_settings = self._create_factory_settings()
                    provider = self._ai_provider_factory.create(factory_settings)
                    self.state.model_name = getattr(provider, 'model', settings.ai.model)
                    self._add_boot_log("OK", f"AI provider ready ({provider.name})")
                else:
                    # Create provider with CLI overrides if provided
                    from asis.ai.providers import OllamaProvider, resolve_think
                    from asis.configuration import settings as global_settings

                    # Use CLI overrides or fall back to settings
                    model = self.state.ai_model_override if self.state.ai_model_override else global_settings.ai.model
                    host = global_settings.ai.endpoint
                    timeout = global_settings.ai.request_timeout
                    temperature = self.state.ai_temperature if self.state.ai_temperature is not None else global_settings.ai.temperature
                    retries = global_settings.network.retries
                    think = resolve_think(
                        self.state.ai_think if self.state.ai_think is not None else global_settings.ai.think,
                        model
                    )
                    num_predict = self.state.ai_num_predict if self.state.ai_num_predict is not None else (global_settings.ai.num_predict or None)
                    keep_alive = self.state.ai_keep_alive if self.state.ai_keep_alive is not None else (global_settings.ai.keep_alive or None)

                    provider = OllamaProvider(
                        model=model,
                        host=host,
                        timeout=timeout,
                        temperature=temperature,
                        retries=retries,
                        think=think,
                        num_predict=num_predict,
                        keep_alive=keep_alive,
                    )
                    self.state.model_name = model
                    self._add_boot_log("BOOT", f"Connecting to {provider.name} ({provider.model})...")

                    # Check availability in executor to avoid blocking
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
                        self.state.ollama_online = True
                        self._add_boot_log("OK", f"{provider.name.capitalize()} ready")
                    else:
                        self._add_boot_log("FAIL", f"{provider.name.capitalize()} server not reachable")
                        raise BootError(f"{provider.name.capitalize()} server not reachable at {getattr(provider, 'host', global_settings.ai.endpoint)}")

            self._components.ai_provider = provider
        except BootError:
            raise
        except Exception as exc:
            self._add_boot_log("FAIL", f"AI provider failed: {exc}")
            raise BootError(f"AI provider boot failed: {exc}") from exc

    def _create_factory_settings(self):
        """Create a settings-like object with CLI overrides for AI provider factory."""
        from asis.configuration import settings as global_settings
        
        class FactorySettings:
            def __init__(self, base, state):
                self.ai = type('AI', (), {})()
                self.ai.model = state.ai_model_override if state.ai_model_override else global_settings.ai.model
                self.ai.endpoint = global_settings.ai.endpoint
                self.ai.request_timeout = global_settings.ai.request_timeout
                self.ai.temperature = state.ai_temperature if state.ai_temperature is not None else global_settings.ai.temperature
                self.network = type('Network', (), {'retries': global_settings.network.retries})()
                # Add think resolution
                from asis.ai.providers import resolve_think
                think_val = state.ai_think if state.ai_think is not None else global_settings.ai.think
                self.ai.think = resolve_think(think_val, self.ai.model)
                self.ai.num_predict = state.ai_num_predict if state.ai_num_predict is not None else (global_settings.ai.num_predict or None)
                self.ai.keep_alive = state.ai_keep_alive if state.ai_keep_alive is not None else (global_settings.ai.keep_alive or None)
        
        return FactorySettings(global_settings, self.state)

    async def _verify_model(self) -> None:
        """Verify model readiness with a real inference probe using shared policy."""
        self._add_boot_log("BOOT", "Verifying model...")
        try:
            from asis.app.boot import verify_model_readiness, ReadinessPolicy
            provider = self._components.ai_provider
            if not provider:
                raise BootError("AI provider not initialized")

            # Apply probe-specific settings (disable thinking, bound num_predict, set timeout)
            policy = ReadinessPolicy.from_settings()

            # Run chat in executor to avoid blocking the event loop
            # The verify_model_readiness function handles think/num_predict/timeout patching
            # and the provider's timeout will handle the overall deadline
            loop = asyncio.get_event_loop()
            
            def probe_call():
                return verify_model_readiness(provider, policy)
            
            # Use run_in_executor but without wait_for - provider timeout handles it
            response = await loop.run_in_executor(None, probe_call)
            chars, probe_ms = response

            if chars > 0:
                self.state.model_ready = True
                self._add_boot_log("OK", "Model ready")
            else:
                raise BootError("Model readiness probe returned empty response")
        except BootError:
            raise
        except asyncio.TimeoutError:
            self._add_boot_log("FAIL", f"Model readiness probe timed out after {int(policy.overall_timeout_s)}s")
            raise BootError(f"Model readiness probe timed out after {int(policy.overall_timeout_s)}s")
        except Exception as exc:
            self._add_boot_log("FAIL", f"Model readiness check failed: {exc}")
            raise BootError(f"Model readiness check failed: {exc}") from exc

    async def _boot_ai_manager(self) -> None:
        """Boot AI manager."""
        try:
            provider = self._components.ai_provider
            if not provider:
                raise BootError("AI provider not initialized")

            ai = AIManager(provider=provider, event_bus=self.event_bus)
            self._components.ai_manager = ai
            self._add_boot_log("OK", "AI Manager initialized")
        except Exception as exc:
            self._add_boot_log("FAIL", f"AI Manager failed: {exc}")
            raise BootError(f"AI Manager boot failed: {exc}") from exc

    async def _boot_assistant_app(self) -> None:
        """Boot assistant app."""
        try:
            identity = self._components.identity
            ai = self._components.ai_manager
            memory = self._components.memory
            tool_router = self._components.tool_router

            if not all([identity, ai, memory, tool_router]):
                raise BootError("Missing required components for AssistantApp")

            assistant_app = AssistantApp(
                identity=identity,
                ai=ai,
                memory=memory,
                tools_router=tool_router,
                event_bus=self.event_bus,
                mode=AppAssistantMode.GENERAL,
            )

            self._components.assistant_app = assistant_app
            self._add_boot_log("OK", "Assistant App initialized")
        except Exception as exc:
            self._add_boot_log("FAIL", f"Assistant App failed: {exc}")
            raise BootError(f"Assistant App boot failed: {exc}") from exc

    async def _boot_voice_pipeline(self) -> None:
        """Boot voice pipeline (mock for now)."""
        try:
            voice_pipeline = self._voice_pipeline_factory.create(self.event_bus)
            self._components.voice_pipeline = voice_pipeline
            self.state.voice_state = VoiceState.READY
            # Check if using mock engines and label honestly
            # Explicit parentheses for clarity: check if ANY component is a mock
            has_mock_audio = (
                getattr(voice_pipeline, 'audio_input', None)
                and type(voice_pipeline.audio_input).__name__.startswith('Mock')
            )
            has_mock_stt = (
                getattr(voice_pipeline, 'speech_recognizer', None)
                and type(voice_pipeline.speech_recognizer).__name__.startswith('Mock')
            )
            has_mock_tts = (
                getattr(voice_pipeline, 'tts', None)
                and type(voice_pipeline.tts).__name__.startswith('Mock')
            )
            is_mock = has_mock_audio or has_mock_stt or has_mock_tts
            label = "Voice pipeline initialized (MOCK)" if is_mock else "Voice pipeline initialized"
            self._add_boot_log("OK", label)
        except Exception as exc:
            self.state.voice_state = VoiceState.ERROR
            self._add_boot_log("WARN", f"Voice pipeline unavailable: {exc}")


# Default implementations for DI hooks

class DefaultIdentityProvider:
    """Default identity provider using the built-in build_identity."""

    def build(self) -> Any:
        return build_identity()


class DefaultToolRouterProvider:
    """Default tool router provider."""

    def build(self) -> Any:
        return build_default_tool_router()


class DefaultVoicePipelineFactory:
    """Default voice pipeline factory (mock)."""

    def create(self, event_bus: EventBus) -> VoicePipeline:
        return VoicePipeline(
            audio_input=MockAudioInput([]),
            speech_recognizer=MockSpeechRecognizer(),
            speaker_identifier=MockSpeakerIdentifier(),
            tts=MockTextToSpeech(),
            audio_output=MockAudioOutput(),
            event_bus=event_bus,
            vad=MockVadDetector(),
        )


# Backward compatibility function
async def run_boot_sequence_legacy(
    state: AppState,
    event_bus: EventBus,
    boot_log_panel: BootLogPanel | None = None,
    mock_mode: bool = False,
    ai_provider: str | None = None,
    ai_model: str | None = None,
) -> dict[str, Any]:
    """
    Legacy compatibility wrapper for the old boot sequence.

    This function maintains backward compatibility with the existing
    TUI app code while using the new BootOrchestrator internally.
    """
    orchestrator = BootOrchestrator(
        state=state,
        event_bus=event_bus,
        boot_log_panel=boot_log_panel,
        mock_mode=mock_mode,
    )
    # Pass provider/model through state for the orchestrator to use
    if ai_provider:
        state.ai_provider_override = ai_provider
    if ai_model:
        state.ai_model_override = ai_model
    components = await orchestrator.run()
    return {
        "identity": components.identity,
        "memory": components.memory,
        "tool_router": components.tool_router,
        "ai_provider": components.ai_provider,
        "ai_manager": components.ai_manager,
        "assistant_app": components.assistant_app,
        "voice_pipeline": components.voice_pipeline,
        "event_bus": components.event_bus,
        "ollama_owned": False,  # TUI doesn't own Ollama; launcher handles lifecycle
    }
