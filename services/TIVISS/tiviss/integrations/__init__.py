"""Integration adapters for future C.O.R.E. and R.E.S.C.S. connectivity.

These are interfaces plus local/mock implementations only. They do NOT depend
on the actual C.O.R.E. or R.E.S.C.S. repositories.
"""

from .base import (
    IntegrationAdapter,
    IntegrationRequest,
    IntegrationResponse,
    IntegrationStatus,
)
from .core import COREAdapter, LocalCOREAdapter
from .rescs import LocalRESCSAdapter, RESCSAdapter

__all__ = [
    "IntegrationAdapter",
    "IntegrationRequest",
    "IntegrationResponse",
    "IntegrationStatus",
    "COREAdapter",
    "LocalCOREAdapter",
    "RESCSAdapter",
    "LocalRESCSAdapter",
]
