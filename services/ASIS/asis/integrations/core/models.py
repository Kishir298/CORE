"""
C.O.R.E. adapter models for A.S.I.S.

Lifecycle states, device identity views, and structured request/response
shapes crossing the A.S.I.S. ↔ C.O.R.E. boundary. No credentials live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CoreConnectionState(str, Enum):  # noqa: UP042 - str+Enum for py3.10 compat (StrEnum needs 3.11+)
    """Lifecycle states for the optional C.O.R.E. connection."""

    DISABLED = "DISABLED"
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


@dataclass(frozen=True)
class CoreDeviceInfo:
    """Authoritative external-device identity (owned by CORE-CLIENT)."""

    device_id: str
    join_name: str = ""
    device_name: str = ""
    platform: str = ""
    capabilities: tuple[str, ...] = ()
    status: str = "unknown"


@dataclass(frozen=True)
class CoreRequest:
    """Bounded application request to C.O.R.E."""

    destination: str
    message_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0


@dataclass(frozen=True)
class CoreStatus:
    """Point-in-time connection/lease snapshot (no secrets)."""

    state: CoreConnectionState
    connected: bool
    device: CoreDeviceInfo | None = None
    lease_state: str = "DISCONNECTED"
    detail: str = ""
