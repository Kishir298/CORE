"""Tool abstraction: interface, results, and exceptions.

Tools never grant unrestricted system access. Each tool declares its
permission requirements, validates its input, and returns a structured
result, allowing the registry and permission layer to gate execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..permissions.permissions import Permission


class ToolError(Exception):
    """Raised for tool input validation failures and internal tool errors."""


class ToolStatus(StrEnum):
    OK = "ok"
    DENIED = "denied"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolResult:
    """Structured result of a tool execution."""

    tool_id: str
    status: ToolStatus
    output: Any = None
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is ToolStatus.OK


class Tool(ABC):
    """A unit of capability exposed to the agent."""

    @property
    @abstractmethod
    def tool_id(self) -> str:
        """Stable unique identifier for the tool."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """What the tool does."""

    @property
    @abstractmethod
    def permission(self) -> Permission:
        """The permission required to run this tool (e.g. ``tools.echo``)."""

    def required_permissions(self) -> list[Permission]:
        return [self.permission]

    def validate_input(self, params: Mapping[str, Any]) -> Mapping[str, Any]:
        """Validate and normalize parameters.

        Raise :class:`ToolError` on invalid input.
        """
        return dict(params)

    @abstractmethod
    def execute(self, params: Mapping[str, Any]) -> ToolResult:
        """Execute the tool. Should not raise under normal operation."""
        raise ToolError(f"tool {self.tool_id} has no execution implementation")
