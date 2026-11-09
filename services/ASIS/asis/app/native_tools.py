"""
Native tool-call normalization for A.S.I.S.

Converts provider-native tool invocations (untrusted model output) into
the EXISTING validated ``ToolRequest`` model. The provider layer never
executes tools; this module never bypasses permissions — it only
decides WHAT was requested. Execution still flows through
``ToolRouter`` → ``PermissionManager`` → ``ToolExecutor``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asis.ai.models import NativeToolCall
from asis.ai.tool_schemas import (
    tool_definition_for,
    validate_call_arguments,
)

from .actions import ToolRequest


@dataclass(frozen=True)
class NativeToolError:
    """A rejected native tool call (safe, deterministic, model-shareable)."""

    kind: str  # unknown_tool | malformed_call | schema_validation_failed
    message: str
    call_name: str = ""


def normalize_native_call(
    call: Any, registry: Any
) -> ToolRequest | NativeToolError:
    """Normalize one native call into a ToolRequest or a structured error."""
    name = call.name if isinstance(call, NativeToolCall) else None
    arguments = call.arguments if isinstance(call, NativeToolCall) else None
    if not isinstance(name, str) or not name.strip():
        return NativeToolError(
            kind="malformed_call",
            message="Tool call is missing a valid tool name.",
        )
    if not isinstance(arguments, dict):
        return NativeToolError(
            kind="malformed_call",
            message=f"Tool call {name.strip()!r} has malformed arguments.",
            call_name=name.strip(),
        )
    tool = registry.get(name.strip())
    if tool is None:
        return NativeToolError(
            kind="unknown_tool",
            message=f"Unknown tool: {name.strip()!r}.",
            call_name=name.strip(),
        )
    try:
        definition = tool_definition_for(tool)
    except ValueError as exc:
        return NativeToolError(
            kind="schema_validation_failed",
            message=str(exc),
            call_name=name.strip(),
        )
    ok, reason = validate_call_arguments(definition, arguments)
    if not ok:
        return NativeToolError(
            kind="schema_validation_failed",
            message=f"Invalid arguments for {name.strip()!r}: {reason}",
            call_name=name.strip(),
        )
    try:
        return ToolRequest(tool_name=name.strip(), arguments=dict(arguments))
    except ValueError as exc:
        return NativeToolError(
            kind="malformed_call",
            message=str(exc),
            call_name=name.strip(),
        )


def normalize_native_calls(
    calls: Any, registry: Any
) -> tuple[list[ToolRequest], list[NativeToolError]]:
    """Split native calls into valid requests and structured errors."""
    requests: list[ToolRequest] = []
    errors: list[NativeToolError] = []
    for call in calls or []:
        result = normalize_native_call(call, registry)
        if isinstance(result, ToolRequest):
            requests.append(result)
        else:
            errors.append(result)
    return requests, errors


def native_tools_enabled(settings_obj: Any = None) -> bool:
    """Return whether native tool calling is enabled (default: auto→on)."""
    if settings_obj is None:
        from asis.configuration.settings import settings as settings_obj
    mode = str(getattr(settings_obj.ai, "native_tools", "auto")).strip().lower()
    return mode in ("auto", "true")


def max_tool_calls(settings_obj: Any = None) -> int:
    """Return the configured bound on native tool calls per turn."""
    if settings_obj is None:
        from asis.configuration.settings import settings as settings_obj
    try:
        value = int(getattr(settings_obj.tools, "max_calls_per_turn", 3))
    except (TypeError, ValueError):
        return 3
    return min(10, max(1, value))
