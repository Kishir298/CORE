"""
C.O.R.E. integration surface for A.S.I.S.
"""

from .adapter import RealCoreAdapter
from .client import CoreClient, CoreResponse, ServiceRequest
from .connection import CoreConnectionManager, build_connection_manager_from_settings
from .errors import (
    CoreAuthError,
    CoreError,
    CoreProtocolError,
    CoreTimeout,
    CoreUnavailable,
)
from .mock import MockCoreAdapter
from .models import CoreConnectionState, CoreDeviceInfo, CoreRequest, CoreStatus

__all__ = [
    "CoreClient",
    "CoreResponse",
    "ServiceRequest",
    "MockCoreAdapter",
    "RealCoreAdapter",
    "CoreConnectionManager",
    "build_connection_manager_from_settings",
    "CoreAuthError",
    "CoreError",
    "CoreProtocolError",
    "CoreTimeout",
    "CoreUnavailable",
    "CoreConnectionState",
    "CoreDeviceInfo",
    "CoreRequest",
    "CoreStatus",
]
