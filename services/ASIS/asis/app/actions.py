"""
Application-level tool action mechanism for A.S.I.S.

Implements the smallest safe bridge between model output and the existing
tool subsystem: a typed ``ToolRequest`` is parsed (structured JSON first,
conservative heuristics second), validated, then dispatched through the
mandatory ``ToolRouter``/``ToolExecutor`` permission path. Single
inference/action cycle only — no autonomous agent loop.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from asis.tools.result import ToolResult

_ECHO_PREFIX = re.compile(r"^\s*echo\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)
_TIME_PATTERN = re.compile(
    r"\b(what\s+(is\s+the\s+)?(time|date|day)|current\s+time|time\s+now)\b",
    re.IGNORECASE,
)
# Conservative coding heuristics (explicit mode switching stays primary).
_READ_PATTERN = re.compile(
    r"\bread\s+(?:the\s+)?file\s+([A-Za-z0-9_.\-/~]+)", re.IGNORECASE
)
_DIFF_PATTERN = re.compile(
    r"\b(show|what).{0,20}\b(diff|changed|changes)\b", re.IGNORECASE
)
_TEST_PATTERN = re.compile(
    r"\b(run|execute)\b.{0,20}\b(tests?|pytest|test suite)\b", re.IGNORECASE
)

# Per-call bound on tool results re-injected as model context. Tool-side
# limits still apply first (e.g. web 8k, coding outputs up to 60-200k);
# this cap keeps the next model request bounded even when a tool returns
# a large payload, well within the 12k assembler budget across up to
# max_calls_per_turn calls.
_TOOL_RESULT_MAX_CHARS = 4000


@dataclass(frozen=True)
class ToolRequest:
    """Validated request to execute one registered tool."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("ToolRequest.tool_name must be a non-empty string.")
        if not isinstance(self.arguments, dict):
            raise ValueError("ToolRequest.arguments must be a dict.")
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("ToolRequest.request_id must be a non-empty string.")


def _parse_structured(text: str) -> ToolRequest | None:
    """Parse an explicit JSON tool call; None when absent/invalid."""
    stripped = text.strip()
    if not stripped:
        return None
    candidates = [stripped]
    start, end = stripped.find("{"), stripped.rfind("}")
    if 0 <= start < end:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        name = payload.get("tool", payload.get("tool_name", payload.get("name")))
        if not isinstance(name, str) or not name.strip():
            continue
        args = payload.get(
            "arguments", payload.get("args", payload.get("parameters", {}))
        )
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return None  # present but malformed -> caller treats as no-action
        request_id = payload.get("request_id", payload.get("requestId", ""))
        if not isinstance(request_id, str) or not request_id.strip():
            request_id = uuid.uuid4().hex
        try:
            return ToolRequest(
                tool_name=name.strip(), arguments=args, request_id=request_id
            )
        except ValueError:
            return None
    return None


def parse_tool_request(
    model_text: str,
    user_text: str = "",
    coding: bool = False,
) -> ToolRequest | None:
    """Decide whether a tool should run for this turn.

    Priority: structured JSON in model output, then conservative
    heuristics (coding heuristics only when ``coding`` is True).
    Returns None for normal conversation.
    """
    structured = _parse_structured(model_text or "")
    if structured is not None:
        return structured

    combined = f"{user_text}\n{model_text}".lower()
    if _TIME_PATTERN.search(combined):
        return ToolRequest(tool_name="current_time", arguments={})
    echo_match = _ECHO_PREFIX.search((model_text or "").strip())
    if echo_match and echo_match.group(1).strip():
        return ToolRequest(
            tool_name="echo", arguments={"text": echo_match.group(1).strip()}
        )
    if coding:
        read_match = _READ_PATTERN.search(combined)
        if read_match and read_match.group(1).strip():
            return ToolRequest(
                tool_name="read_file",
                arguments={"path": read_match.group(1).strip()},
            )
        if _DIFF_PATTERN.search(combined):
            return ToolRequest(tool_name="git_diff", arguments={})
        if _TEST_PATTERN.search(combined):
            return ToolRequest(tool_name="run_tests", arguments={})
    return None


def format_tool_result_for_context(result: ToolResult) -> str:
    """Render a tool result as model context, never as user authorship."""
    if result.success:
        text = f"[tool {result.tool_name or 'unknown'} result] {result.data!r}"
    else:
        text = (
            f"[tool {result.tool_name or 'unknown'} error] "
            f"{result.error or 'failed'}"
        )
    if len(text) > _TOOL_RESULT_MAX_CHARS:
        clipped = text[:_TOOL_RESULT_MAX_CHARS].rstrip()
        text = f"{clipped}…[truncated {len(text) - len(clipped)} chars]"
    return text
