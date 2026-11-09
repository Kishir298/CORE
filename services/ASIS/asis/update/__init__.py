"""
ASIS Update System - Offline-first with optional online auto-updates.

This module provides automatic update checking and installation for:
- ASIS code (git)
- Python dependencies (pip)
- Ollama models

All network operations are opt-in and gracefully degrade when offline.
"""

from __future__ import annotations

from .detectors import NetworkDetector, is_online
from .manager import ComponentUpdate, UpdateManager, UpdateResult

__all__ = [
    "NetworkDetector",
    "is_online",
    "UpdateManager",
    "UpdateResult",
    "ComponentUpdate",
]
