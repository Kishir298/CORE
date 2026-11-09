"""
Provider-neutral tool definitions for native LLM function calling.

Derives structured ``ToolDefinition`` records from the EXISTING
``ToolRegistry`` — no second tool framework. The provider layer converts
these into the wire format of the underlying model API (e.g. Ollama
``tools``). Schemas are deterministic: same registry → same definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Keys that must never appear in a tool schema (names or descriptions).
_FORBIDDEN_SCHEMA_KEYS = frozenset(
    {
        "token",
        "credential",
        "password",
        "api_key",
        "secret",
        "session_token",
        "private_key",
        "connection_id",
    }
)

_SCALAR_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object"})


@dataclass(frozen=True)
class ToolDefinition:
    """Provider-neutral description of one callable tool."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ToolDefinition.name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("ToolDefinition.description must be a non-empty string.")
        if not isinstance(self.parameters, dict):
            raise ValueError("ToolDefinition.parameters must be a dict.")


def _schema_is_safe(name: str, description: str, parameters: Any) -> bool:
    """Return False if a schema leaks secret-bearing vocabulary."""
    blob = f"{name}\n{description}\n{parameters!r}".lower()
    return not any(key in blob for key in _FORBIDDEN_SCHEMA_KEYS)


def _normalize_parameters(raw: Any) -> dict[str, Any]:
    """Coerce metadata parameters into a JSON-Schema object shape."""
    if not raw:
        return {"type": "object", "properties": {}}
    if not isinstance(raw, dict):
        raise ValueError("Tool parameters must be a mapping.")
    properties = raw.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("Tool parameters.properties must be a mapping.")
    required = raw.get("required", [])
    if not isinstance(required, list) or not all(
        isinstance(item, str) for item in required
    ):
        raise ValueError("Tool parameters.required must be a list of strings.")
    for prop_name, prop_spec in properties.items():
        if not isinstance(prop_spec, dict):
            raise ValueError(
                f"Tool parameter {prop_name!r} must declare a scalar type."
            )
        if prop_spec.get("type") not in _SCALAR_TYPES:
            raise ValueError(
                f"Tool parameter {prop_name!r} must declare a scalar type."
            )
    normalized = {"type": "object", "properties": dict(properties)}
    if required:
        normalized["required"] = list(required)
    return normalized


def tool_definition_for(tool: Any) -> ToolDefinition:
    """Build a provider-neutral definition from a registered Tool."""
    metadata = tool.metadata
    parameters = _normalize_parameters(getattr(metadata, "parameters", {}))
    if not _schema_is_safe(metadata.name, metadata.description, parameters):
        raise ValueError(
            f"Tool schema for {metadata.name!r} contains forbidden vocabulary."
        )
    return ToolDefinition(
        name=metadata.name,
        description=metadata.description,
        parameters=parameters,
    )


def tool_definitions_for(registry: Any) -> list[ToolDefinition]:
    """Build deterministic definitions for every tool in a registry."""
    definitions = [tool_definition_for(tool) for tool in registry.list_tools()]
    definitions.sort(key=lambda item: item.name)
    return definitions


# Intent-aware tool selection: hint value (from the deterministic
# orchestrator plan) -> tool names exposed to the model. The "none"
# verdict (explanation-only requests) exposes zero tools. Hints with no
# entry, and the "coding-tools" sentinel, keep the full active set so an
# open-ended or misclassified turn never starves the model. Unknown names
# in a hint set are ignored; an empty selection also falls back to the
# full set (fail-open toward capability, permissions still enforced at
# execution through ToolRouter/PermissionManager).
_TOOL_HINT_NAMES: dict[str, frozenset] = {
    "calculate": frozenset({"calculate"}),
    "web": frozenset({"web_search", "web_fetch"}),
    "time": frozenset({"current_time"}),
    "echo": frozenset({"echo"}),
    "translate": frozenset({"translate_text"}),
}


def select_tool_definitions(
    definitions: list[ToolDefinition], tool_hint: str | None
) -> list[ToolDefinition]:
    """Narrow definitions to the orchestrator hint (deterministic).

    ``"none"`` (explanation-only requests) returns an explicit empty list
    so the turn skips native calling and goes straight to plain
    generation. ``None``, ``"coding-tools"``, unknown hints, and hints
    matching nothing in the active registry all return the full list
    unchanged.
    """
    if tool_hint == "none":
        return []
    if not tool_hint or tool_hint == "coding-tools":
        return list(definitions)
    names = _TOOL_HINT_NAMES.get(tool_hint)
    if not names:
        return list(definitions)
    selected = [item for item in definitions if item.name in names]
    return selected or list(definitions)


def ollama_tools(definitions: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Render definitions in the Ollama /api/chat tools wire format."""
    return [
        {
            "type": "function",
            "function": {
                "name": item.name,
                "description": item.description,
                "parameters": item.parameters,
            },
        }
        for item in definitions
    ]


def _type_matches(expected: str, value: Any) -> bool:
    """Return whether an untrusted argument matches a schema scalar type."""
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def validate_call_arguments(
    definition: ToolDefinition, arguments: Any
) -> tuple[bool, str]:
    """Validate untrusted model arguments against a tool definition.

    Returns (True, "") when valid, else (False, reason). Unknown
    parameters are rejected: the model may only fill declared slots.
    """
    if not isinstance(arguments, dict):
        return False, "arguments must be a JSON object."
    properties = definition.parameters.get("properties", {})
    required = definition.parameters.get("required", [])
    for name in required:
        if name not in arguments or arguments[name] is None:
            return False, f"missing required parameter: {name!r}."
    for name, value in arguments.items():
        spec = properties.get(name)
        if spec is None:
            return False, f"unknown parameter: {name!r}."
        if not _type_matches(str(spec.get("type")), value):
            return False, (
                f"parameter {name!r} must be of type {spec.get('type')!r}."
            )
    return True, ""
