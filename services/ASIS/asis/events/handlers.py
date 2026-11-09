"""
Event handler protocol for A.S.I.S.
"""

from __future__ import annotations

from collections.abc import Callable

from .events import Event

EventHandler = Callable[[Event], None]

__all__ = ["EventHandler"]
