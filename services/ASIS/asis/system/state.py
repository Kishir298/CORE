"""
Runtime state definitions for A.S.I.S.
"""

from __future__ import annotations

from enum import StrEnum


class RuntimeState(StrEnum):
    """Lifecycle states of the A.S.I.S. runtime."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
