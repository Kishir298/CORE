"""
Structured logging for A.S.I.S.

Use `get_logger(name)` anywhere in the codebase. Important lifecycle
events (startup, shutdown, model loading, inference, tool execution,
voice pipeline and errors) are logged through this subsystem.
"""

from .logger import get_logger

__all__ = ["get_logger"]
