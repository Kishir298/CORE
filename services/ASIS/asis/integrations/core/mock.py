"""
Local mock implementation of the C.O.R.E. client.

Lets A.S.I.S. run fully independently while exposing the same surface a
real C.O.R.E. adapter will provide. Never pretend this is C.O.R.E. — it
is a development stand-in.
"""

from __future__ import annotations

import uuid
from typing import Any

from asis.logging.logger import get_logger

from .client import CoreClient, CoreResponse, ServiceRequest
from .models import CoreConnectionState, CoreDeviceInfo, CoreStatus
from .protocol import normalize_result, redact


class MockCoreAdapter(CoreClient):
    """In-process mock of a C.O.R.E. instance."""

    def __init__(self) -> None:
        self._logger = get_logger("integrations.core.mock")
        self._messages: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._resources: dict[str, Any] = {}
        self._components: dict[str, dict[str, Any]] = {}
        self._connected = False
        self._requests: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock-core"

    def send_message(self, recipient: str, payload: dict[str, Any]) -> CoreResponse:
        record = {
            "message_id": str(uuid.uuid4()),
            "recipient": recipient,
            "payload": redact(payload),
        }

        self._messages.append(record)
        self._logger.info("Mock C.O.R.E. message to %s", recipient)

        return CoreResponse(ok=True, data=record)

    def request_service(self, request: ServiceRequest) -> CoreResponse:
        self._logger.info(
            "Mock C.O.R.E. service request: %s/%s",
            request.service,
            request.operation,
        )

        return CoreResponse(
            ok=False,
            error=(
                f"Mock C.O.R.E. has no registered handler for "
                f"{request.service}/{request.operation}."
            ),
        )

    def publish_event(
        self, event_type: str, data: dict[str, Any] | None = None
    ) -> None:
        self._events.append(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "data": redact(data or {}),
            }
        )

    def get_resource(self, name: str) -> CoreResponse:
        resource = self._resources.get(name)

        if resource is None:
            return CoreResponse(
                ok=False,
                error=f"Resource not found: {name}",
            )

        return CoreResponse(ok=True, data=normalize_result(resource))

    def set_resource(self, name: str, value: Any) -> None:
        """Mock helper: register a local resource."""
        self._resources[name] = value

    def register_component(
        self, component_id: str, metadata: dict[str, Any] | None = None
    ) -> CoreResponse:
        self._components[component_id] = redact(metadata or {})

        return CoreResponse(ok=True, data={"component_id": component_id})

    def get_health(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "status": "operational",
            "messages": len(self._messages),
            "events": len(self._events),
            "components": list(self._components),
        }

    def clear(self) -> None:
        """Reset all mock state."""
        self._messages.clear()
        self._events.clear()
        self._resources.clear()
        self._components.clear()
        self._requests.clear()
        self._connected = False

    # -- lifecycle + application requests (mock session) --
    def connect(self, credential: str | None = None) -> CoreResponse:
        self._connected = True
        return CoreResponse(ok=True, data={"adapter": self.name})

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def device_status(self) -> CoreResponse:
        return CoreResponse(
            ok=True,
            data={
                "device_id": "mock-device",
                "join_name": "mock-mock-device",
                "device_name": "MockDevice",
                "platform": "mock",
                "capabilities": [],
                "status": "online" if self._connected else "offline",
            },
        )

    def send_request(
        self,
        destination: str,
        message_type: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> CoreResponse:
        record = {
            "message_id": str(uuid.uuid4()),
            "destination": destination,
            "message_type": message_type,
            "payload": redact(payload or {}),
        }
        self._requests.append(record)
        if not self._connected:
            return CoreResponse(ok=False, error="CORE_UNAVAILABLE: mock is offline.")
        return CoreResponse(ok=True, data=normalize_result(record))

    @property
    def connection_state(self) -> CoreConnectionState:
        return (
            CoreConnectionState.CONNECTED
            if self._connected
            else CoreConnectionState.DISCONNECTED
        )

    def status(self) -> CoreStatus:
        return CoreStatus(
            state=self.connection_state,
            connected=self._connected,
            device=CoreDeviceInfo(device_id="mock-device", status="online"),
            lease_state="ONLINE" if self._connected else "DISCONNECTED",
        )
