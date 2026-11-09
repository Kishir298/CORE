"""
Explicit ``core:`` user commands for A.S.I.S.

Deterministic command prefix (same idea as CLI verbs): explicit user
commands bypass model inference and execute one CORE tool directly.
Model-driven tool use continues through ``actions.parse_tool_request``.

```text
core:devices                  -> core_discover_devices
core:device <id>              -> core_device_info
core:status                   -> core_status
core:service <svc> <op>       -> core_service_request
core:agent <op>               -> core_agent_request
core:data <request-type>      -> core_data_request
core:send <device> <type> ... -> core_send_to_device
```
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoreIntent:
    """A parsed explicit CORE tool request."""

    tool_name: str
    kwargs: dict


def parse_core_intent(text: str) -> CoreIntent | None:
    """Parse a ``core:`` command prefix into a tool call, if present."""
    stripped = (text or "").strip()
    if not stripped.lower().startswith("core:"):
        return None
    parts = stripped[5:].strip().split()
    if not parts:
        return None
    verb = parts[0].lower()
    args = parts[1:]
    if verb in ("devices", "discover"):
        return CoreIntent("core_discover_devices", {})
    if verb == "device" and args:
        return CoreIntent("core_device_info", {"device_id": args[0]})
    if verb == "status":
        return CoreIntent("core_status", {})
    if verb == "service" and len(args) >= 2:
        return CoreIntent(
            "core_service_request",
            {"service": args[0], "operation": args[1], "params": {}},
        )
    if verb == "agent" and args:
        return CoreIntent("core_agent_request", {"operation": args[0], "params": {}})
    if verb == "data" and args:
        return CoreIntent("core_data_request", {"request_type": args[0], "params": {}})
    if verb == "send" and len(args) >= 2:
        return CoreIntent(
            "core_send_to_device",
            {
                "device_id": args[0],
                "message_type": args[1],
                "payload": {"text": " ".join(args[2:])} if len(args) > 2 else {},
            },
        )
    return None
