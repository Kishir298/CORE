"""
A.S.I.S. AI subsystem.
"""

from .context import ContextAssembler
from .conversation import ConversationSession
from .inference import InferenceEngine
from .manager import AIManager, create_provider
from .models import AIMessage, AIResponse, MessageRole, NativeToolCall
from .orchestrator import Intent, OrchestratorPlan, build_plan, classify_intent
from .providers import AIProvider, MockAIProvider
from .tool_schemas import (
    ToolDefinition,
    ollama_tools,
    tool_definition_for,
    tool_definitions_for,
    validate_call_arguments,
)


def __getattr__(name: str):
    # Lazy so `import asis.ai` works on a base install without `requests`.
    if name == "OllamaProvider":
        from .providers import OllamaProvider

        globals()[name] = OllamaProvider
        return OllamaProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AIManager",
    "create_provider",
    "AIMessage",
    "AIResponse",
    "MessageRole",
    "NativeToolCall",
    "AIProvider",
    "MockAIProvider",
    "OllamaProvider",
    "ConversationSession",
    "ContextAssembler",
    "InferenceEngine",
    "Intent",
    "OrchestratorPlan",
    "build_plan",
    "classify_intent",
    "ToolDefinition",
    "ollama_tools",
    "tool_definition_for",
    "tool_definitions_for",
    "validate_call_arguments",
]
