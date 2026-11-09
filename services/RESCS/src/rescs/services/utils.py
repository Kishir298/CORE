"""Shared service-layer helpers."""

from __future__ import annotations

MAX_LIMIT = 500


def clamp_pagination(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, MAX_LIMIT)), max(0, offset)
