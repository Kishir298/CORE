"""
C.O.R.E.-backed tools for A.S.I.S.

Thin wrappers over the C.O.R.E. adapter surface. All network access flows
through the EXISTING ToolRegistry/Router/Executor + permission system —
no second tool runtime. Results are redacted and size-bounded before they
reach the model. Every tool fails cleanly with CORE_UNAVAILABLE when the
optional CORE session is offline.
"""

from __future__ import annotations

from typing import Any

from asis.integrations.core.client import CoreResponse
from asis.integrations.core.protocol import normalize_result
from asis.permissions.models import PermissionLevel

from ..base import Tool, ToolMetadata
from ..result import ToolResult


def _core_of(tool: CoreToolBase) -> Any:
    return tool._core


def _unavailable(tool_name: str) -> ToolResult:
    return ToolResult.failure(
        error="CORE_UNAVAILABLE: C.O.R.E. is not connected.",
        tool_name=tool_name,
    )


def _from_response(resp: CoreResponse, tool_name: str) -> ToolResult:
    if resp.ok:
        return ToolResult.ok(
            data=normalize_result(resp.data),
            tool_name=tool_name,
        )
    return ToolResult.failure(
        error=str(resp.error or "CORE_ERROR"), tool_name=tool_name
    )


class CoreToolBase(Tool):
    """Shared CORE plumbing: resolve adapter, guard availability."""

    metadata: ToolMetadata  # set by subclasses

    def __init__(self, core: Any | None = None) -> None:
        self._core = core

    def _adapter(self) -> Any | None:
        core = self._core
        # Accept a manager or a raw adapter interchangeably.
        adapter = getattr(core, "adapter", core)
        if adapter is None:
            return None
        try:
            if not adapter.is_connected():
                return None
        except Exception:
            return None
        return adapter

    def execute(self, **kwargs: Any) -> ToolResult:  # pragma: no cover - overridden
        raise NotImplementedError


class CoreDiscoverDevicesTool(CoreToolBase):
    """List devices known to C.O.R.E.-HOST."""

    metadata = ToolMetadata(
        name="core_discover_devices",
        description="List devices connected to R.I.S.A.R.M.S. via C.O.R.E.",
        category="core",
        permission=PermissionLevel.HIGH,
        tags=("core", "discovery", "network"),
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.name)
        try:
            resp = adapter.send_request("core", "DEVICE_DISCOVER", {})
        except Exception as exc:
            return ToolResult.failure(
                error=f"CORE_UNAVAILABLE: {exc}", tool_name=self.name
            )
        return _from_response(resp, self.name)


class CoreDeviceInfoTool(CoreToolBase):
    """Fetch one CORE-authoritative device record."""

    metadata = ToolMetadata(
        name="core_device_info",
        description="Fetch identity/capabilities for one C.O.R.E. device.",
        category="core",
        permission=PermissionLevel.HIGH,
        tags=("core", "device", "network"),
        parameters={
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        device_id = kwargs.get("device_id", "")
        if not isinstance(device_id, str) or not device_id.strip():
            return ToolResult.failure(
                error="'device_id' must be a non-empty string.", tool_name=self.name
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.name)
        try:
            resp = adapter.send_request(
                "core", "DEVICE_INFO", {"device_id": device_id.strip()}
            )
        except Exception as exc:
            return ToolResult.failure(
                error=f"CORE_UNAVAILABLE: {exc}", tool_name=self.name
            )
        return _from_response(resp, self.name)


class CoreStatusTool(CoreToolBase):
    """Local CORE connection/device snapshot (no new network request)."""

    metadata = ToolMetadata(
        name="core_status",
        description="Report local C.O.R.E. connection state and device identity.",
        category="core",
        permission=PermissionLevel.SAFE,
        tags=("core", "status"),
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        core = self._core
        if core is None:
            return _unavailable(self.name)
        try:
            if hasattr(core, "status"):
                status = core.status()
                data = {
                    "state": getattr(status.state, "value", str(status.state)),
                    "connected": bool(status.connected),
                    "lease": status.lease_state,
                    "device": (
                        {
                            "device_id": status.device.device_id,
                            "join_name": status.device.join_name,
                            "platform": status.device.platform,
                            "status": status.device.status,
                        }
                        if status.device
                        else None
                    ),
                }
                return ToolResult.ok(data=normalize_result(data), tool_name=self.name)
            resp = core.device_status()
            return _from_response(resp, self.name)
        except Exception as exc:
            return ToolResult.failure(
                error=f"CORE_UNAVAILABLE: {exc}", tool_name=self.name
            )


class CoreServiceRequestTool(CoreToolBase):
    """Invoke a host service operation (service:<id>/operation)."""

    metadata = ToolMetadata(
        name="core_service_request",
        description="Invoke a C.O.R.E.-HOST service operation.",
        category="core",
        permission=PermissionLevel.HIGH,
        tags=("core", "service", "network"),
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "operation": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["service", "operation"],
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        service = kwargs.get("service", "")
        operation = kwargs.get("operation", "")
        params = kwargs.get("params", {})
        if not isinstance(service, str) or not service.strip():
            return ToolResult.failure(
                error="'service' must be a non-empty string.", tool_name=self.name
            )
        if not isinstance(operation, str) or not operation.strip():
            return ToolResult.failure(
                error="'operation' must be a non-empty string.", tool_name=self.name
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return ToolResult.failure(
                error="'params' must be a mapping.", tool_name=self.name
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.name)
        try:
            from asis.integrations.core.client import ServiceRequest

            if hasattr(adapter, "request_service"):
                resp = adapter.request_service(
                    ServiceRequest(
                        service=service.strip(),
                        operation=operation.strip(),
                        params=dict(params),
                    )
                )
            else:
                resp = adapter.send_request(
                    f"service:{service.strip()}",
                    "SERVICE_REQUEST",
                    {"operation": operation.strip(), **dict(params)},
                )
        except Exception as exc:
            return ToolResult.failure(
                error=f"CORE_UNAVAILABLE: {exc}", tool_name=self.name
            )
        return _from_response(resp, self.name)


class CoreAgentRequestTool(CoreToolBase):
    """Agent operations via the host agent service (assign/list/status...)."""

    metadata = ToolMetadata(
        name="core_agent_request",
        description="Run a C.O.R.E. agent operation (profiles/assign/release/status).",
        category="core",
        permission=PermissionLevel.HIGH,
        tags=("core", "agent", "network"),
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["operation"],
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        operation = kwargs.get("operation", "")
        params = kwargs.get("params", {})
        if not isinstance(operation, str) or not operation.strip():
            return ToolResult.failure(
                error="'operation' must be a non-empty string.", tool_name=self.name
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return ToolResult.failure(
                error="'params' must be a mapping.", tool_name=self.name
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.name)
        try:
            from asis.integrations.core.client import ServiceRequest

            if hasattr(adapter, "request_service"):
                resp = adapter.request_service(
                    ServiceRequest(
                        service="agent",
                        operation=operation.strip(),
                        params=dict(params),
                    )
                )
            else:
                resp = adapter.send_request(
                    "service:agent",
                    "SERVICE_REQUEST",
                    {"operation": operation.strip(), **dict(params)},
                )
        except Exception as exc:
            return ToolResult.failure(
                error=f"CORE_UNAVAILABLE: {exc}", tool_name=self.name
            )
        return _from_response(resp, self.name)


class CoreDataRequestTool(CoreToolBase):
    """Query host data (records/files) via DATA_REQUEST."""

    metadata = ToolMetadata(
        name="core_data_request",
        description="Query C.O.R.E.-HOST data (record_get/list/search, file_metadata).",
        category="core",
        permission=PermissionLevel.HIGH,
        tags=("core", "data", "network"),
        parameters={
            "type": "object",
            "properties": {
                "request_type": {"type": "string"},
                "params": {"type": "object"},
                "destination": {"type": "string"},
            },
            "required": ["request_type"],
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        request_type = kwargs.get("request_type", "")
        params = kwargs.get("params", {})
        destination = kwargs.get("destination", "core")
        if not isinstance(request_type, str) or not request_type.strip():
            return ToolResult.failure(
                error="'request_type' must be a non-empty string.",
                tool_name=self.name,
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return ToolResult.failure(
                error="'params' must be a mapping.", tool_name=self.name
            )
        if not isinstance(destination, str) or not destination.strip():
            return ToolResult.failure(
                error="'destination' must be a non-empty string.",
                tool_name=self.name,
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.name)
        try:
            if hasattr(adapter, "data_request"):
                resp = adapter.data_request(
                    request_type.strip(), dict(params), destination.strip()
                )
            else:
                resp = adapter.send_request(
                    destination.strip(),
                    "DATA_REQUEST",
                    {"request_type": request_type.strip(), **dict(params)},
                )
        except Exception as exc:
            return ToolResult.failure(
                error=f"CORE_UNAVAILABLE: {exc}", tool_name=self.name
            )
        return _from_response(resp, self.name)


class CoreSendToDeviceTool(CoreToolBase):
    """Send a device-to-device application message via the host router."""

    metadata = ToolMetadata(
        name="core_send_to_device",
        description=(
            "Send an application message to another C.O.R.E. device. "
            "Host routing is one-way: expect a timeout-shaped result, "
            "not a reply envelope."
        ),
        category="core",
        permission=PermissionLevel.HIGH,
        tags=("core", "device", "network"),
        parameters={
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "message_type": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["device_id", "message_type"],
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        device_id = kwargs.get("device_id", "")
        message_type = kwargs.get("message_type", "")
        payload = kwargs.get("payload", {})
        if not isinstance(device_id, str) or not device_id.strip():
            return ToolResult.failure(
                error="'device_id' must be a non-empty string.",
                tool_name=self.name,
            )
        if not isinstance(message_type, str) or not message_type.strip():
            return ToolResult.failure(
                error="'message_type' must be a non-empty string.",
                tool_name=self.name,
            )
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return ToolResult.failure(
                error="'payload' must be a mapping.", tool_name=self.name
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.name)
        try:
            if hasattr(adapter, "send_to_device"):
                resp = adapter.send_to_device(
                    device_id.strip(), message_type.strip(), dict(payload)
                )
            else:
                resp = adapter.send_request(
                    device_id.strip(), message_type.strip(), dict(payload)
                )
        except Exception as exc:
            return ToolResult.failure(
                error=f"CORE_UNAVAILABLE: {exc}", tool_name=self.name
            )
        return _from_response(resp, self.name)


def build_core_tools(core: Any | None = None) -> list[Tool]:
    """Build the CORE tool set bound to one adapter/manager (or offline)."""
    return [
        CoreDiscoverDevicesTool(core),
        CoreDeviceInfoTool(core),
        CoreStatusTool(core),
        CoreDataRequestTool(core),
        CoreServiceRequestTool(core),
        CoreAgentRequestTool(core),
        CoreSendToDeviceTool(core),
    ]


def register_core_tools(registry: Any, core: Any | None = None) -> list[str]:
    """Register CORE tools on an existing ToolRegistry; return names."""
    names: list[str] = []
    for tool in build_core_tools(core):
        registry.register(tool)
        names.append(tool.name)
    return names
