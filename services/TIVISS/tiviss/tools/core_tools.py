"""C.O.R.E.-backed tools for T.I.V.I.S.S."""

from __future__ import annotations

from typing import Any

from ..integrations.core import normalize_result
from ..permissions.permissions import Permission
from .interface import Tool, ToolResult, ToolStatus


def _core_of(tool: CoreToolBase) -> Any:
    return tool._core


def _unavailable(tool_name: str) -> ToolResult:
    return ToolResult(
        tool_id=tool_name,
        status=ToolStatus.FAILED,
        error="CORE_UNAVAILABLE: C.O.R.E. is not connected.",
    )


def _from_response(resp: Any, tool_name: str) -> ToolResult:
    if hasattr(resp, "ok") and resp.ok:
        return ToolResult(
            tool_id=tool_name,
            status=ToolStatus.OK,
            data=normalize_result(resp.data),
        )
    return ToolResult(
        tool_id=tool_name,
        status=ToolStatus.FAILED,
        error=str(getattr(resp, "error", None) or "CORE_ERROR"),
    )


class CoreToolBase(Tool):
    """Shared CORE plumbing: resolve adapter, guard availability."""

    def __init__(self, core=None) -> None:
        self._core = core

    def _adapter(self) -> Any | None:
        core = self._core
        adapter = getattr(core, "adapter", core)
        if adapter is None:
            return None
        try:
            if not adapter.is_connected():
                return None
        except Exception:
            return None
        return adapter

    def execute(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    @property
    def tool_id(self) -> str:
        return self.metadata.name

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def permission(self) -> Permission:
        return self.metadata.permission


class CoreDiscoverDevicesTool(CoreToolBase):
    """List devices known to C.O.R.E.-HOST."""

    def __init__(self, core=None):
        super().__init__(core)
        self.metadata = type("Metadata", (), {
            "name": "core_discover_devices",
            "description": "List devices connected to R.I.S.A.R.M.S. via C.O.R.E.",
            "category": "core",
            "permission": Permission.of("tools.core"),
            "tags": ("core", "discovery", "network"),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        })()

    def execute(self, **kwargs: Any) -> ToolResult:
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.metadata.name)
        try:
            resp = adapter.send_request("core", "DEVICE_DISCOVER", {})
        except Exception as exc:
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error=f"CORE_UNAVAILABLE: {exc}",
            )
        return _from_response(resp, self.metadata.name)

class CoreDeviceInfoTool(CoreToolBase):
    """Fetch one CORE-authoritative device record."""

    

    def __init__(self, core=None):
        super().__init__(core)
        self.metadata = type("Metadata", (), {
            "name": "core_device_info",
            "description": "Fetch identity/capabilities for one C.O.R.E. device.",
            "category": "core",
            "permission": Permission.of("tools.core"),
            "tags": ("core", "device", "network"),
            "parameters": {
                "type": "object",
                "properties": {"device_id": {"type": "string"}},
                "required": ["device_id"],
            },
        })()

    def execute(self, **kwargs: Any) -> ToolResult:
        device_id = kwargs.get("device_id", "")
        if not isinstance(device_id, str) or not device_id.strip():
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="'device_id' must be a non-empty string.",
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.metadata.name)
        try:
            resp = adapter.send_request(
                "core", "DEVICE_INFO", {"device_id": device_id.strip()}
            )
        except Exception as exc:
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error=f"CORE_UNAVAILABLE: {exc}",
            )
        return _from_response(resp, self.metadata.name)

class CoreStatusTool(CoreToolBase):
    """Local CORE connection/device snapshot (no new network request)."""

    

    def __init__(self, core=None):
        super().__init__(core)
        self.metadata = type("Metadata", (), {
            "name": "core_status",
            "description": "Report local C.O.R.E. connection state and device identity.",
            "category": "core",
            "permission": Permission.of("tools.safe"),
            "tags": ("core", "status"),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        })()

    def execute(self, **kwargs: Any) -> ToolResult:
        core = self._core
        if core is None:
            return _unavailable(self.metadata.name)
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
                return ToolResult(
                    tool_id=self.metadata.name,
                    status=ToolStatus.OK,
                    data=normalize_result(data),
                )
            resp = core.device_status()
            return _from_response(resp, self.metadata.name)
        except Exception as exc:
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error=f"CORE_UNAVAILABLE: {exc}",
            )

class CoreServiceRequestTool(CoreToolBase):
    """Invoke a host service operation (service:<id>/operation)."""

    

    def __init__(self, core=None):
        super().__init__(core)
        self.metadata = type("Metadata", (), {
            "name": "core_service_request",
            "description": "Invoke a C.O.R.E.-HOST service operation.",
            "category": "core",
            "permission": Permission.of("tools.core"),
            "tags": ("core", "service", "network"),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "operation": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["service", "operation"],
            },
        })()

    def execute(self, **kwargs: Any) -> ToolResult:
        service = kwargs.get("service", "")
        operation = kwargs.get("operation", "")
        params = kwargs.get("params", {})
        if not isinstance(service, str) or not service.strip():
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="service must be a non-empty string.",
            )
        if not isinstance(operation, str) or not operation.strip():
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="operation must be a non-empty string.",
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="params must be a mapping.",
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.metadata.name)
        try:
            if hasattr(adapter, "request_service"):
                resp = adapter.request_service(
                    service=service.strip(),
                    operation=operation.strip(),
                    params=dict(params),
                )
            else:
                resp = adapter.send_request(
                    "service:" + service.strip(),
                    "SERVICE_REQUEST",
                    {"operation": operation.strip(), **dict(params)}
                )
        except Exception as exc:
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error=f"CORE_UNAVAILABLE: {exc}",
            )
        return _from_response(resp, self.metadata.name)

class CoreAgentRequestTool(CoreToolBase):
    """Agent operations via the host agent service (assign/list/status...)."""

    

    def __init__(self, core=None):
        super().__init__(core)
        self.metadata = type("Metadata", (), {
            "name": "core_agent_request",
            "description": "Run a C.O.R.E. agent operation (profiles/assign/release/status).",
            "category": "core",
            "permission": Permission.of("tools.core"),
            "tags": ("core", "agent", "network"),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["operation"],
            },
        })()

    def execute(self, **kwargs: Any) -> ToolResult:
        operation = kwargs.get("operation", "")
        params = kwargs.get("params", {})
        if not isinstance(operation, str) or not operation.strip():
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="operation must be a non-empty string.",
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="params must be a mapping.",
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.metadata.name)
        try:
            if hasattr(adapter, "request_service"):
                resp = adapter.request_service(
                    service="agent",
                    operation=operation.strip(),
                    params=dict(params),
                )
            else:
                resp = adapter.send_request(
                    "service:agent",
                    "SERVICE_REQUEST",
                    {"operation": operation.strip(), **dict(params)}
                )
        except Exception as exc:
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error=f"CORE_UNAVAILABLE: {exc}",
            )
        return _from_response(resp, self.metadata.name)

class CoreDataRequestTool(CoreToolBase):
    """Query host data (records/files) via DATA_REQUEST."""

    

    def __init__(self, core=None):
        super().__init__(core)
        self.metadata = type("Metadata", (), {
            "name": "core_data_request",
            "description": "Query C.O.R.E.-HOST data (record_get/list/search, file_metadata).",
            "category": "core",
            "permission": Permission.of("tools.core"),
            "tags": ("core", "data", "network"),
            "parameters": {
                "type": "object",
                "properties": {
                    "request_type": {"type": "string"},
                    "params": {"type": "object"},
                    "destination": {"type": "string"},
                },
                "required": ["request_type"],
            },
        })()

    def execute(self, **kwargs: Any) -> ToolResult:
        request_type = kwargs.get("request_type", "")
        params = kwargs.get("params", {})
        destination = kwargs.get("destination", "core")
        if not isinstance(request_type, str) or not request_type.strip():
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="request_type must be a non-empty string.",
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="params must be a mapping.",
            )
        if not isinstance(destination, str) or not destination.strip():
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="destination must be a non-empty string.",
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.metadata.name)
        try:
            if hasattr(adapter, "data_request"):
                resp = adapter.data_request(
                    request_type.strip(), dict(params), destination.strip()
                )
            else:
                resp = adapter.send_request(
                    destination.strip(),
                    "DATA_REQUEST",
                    {"request_type": request_type.strip(), **dict(params)}
                )
        except Exception as exc:
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error=f"CORE_UNAVAILABLE: {exc}",
            )
        return _from_response(resp, self.metadata.name)

class CoreSendToDeviceTool(CoreToolBase):
    """Send a device-to-device application message via the host router."""

    

    def __init__(self, core=None):
        super().__init__(core)
        self.metadata = type("Metadata", (), {
            "name": "core_send_to_device",
            "description": "Send an application message to another C.O.R.E. device. Host routing is one-way: expect a timeout-shaped result, not a reply envelope.",
            "category": "core",
            "permission": Permission.of("tools.core"),
            "tags": ("core", "device", "network"),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {"type": "string"},
                    "message_type": {"type": "string"},
                    "payload": {"type": "object"},
                },
                "required": ["device_id", "message_type"],
            },
        })()

    def execute(self, **kwargs: Any) -> ToolResult:
        device_id = kwargs.get("device_id", "")
        message_type = kwargs.get("message_type", "")
        payload = kwargs.get("payload", {})
        if not isinstance(device_id, str) or not device_id.strip():
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="device_id must be a non-empty string.",
            )
        if not isinstance(message_type, str) or not message_type.strip():
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="message_type must be a non-empty string.",
            )
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error="payload must be a mapping.",
            )
        adapter = self._adapter()
        if adapter is None:
            return _unavailable(self.metadata.name)
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
            return ToolResult(
                tool_id=self.metadata.name,
                status=ToolStatus.FAILED,
                error=f"CORE_UNAVAILABLE: {exc}",
            )
        return _from_response(resp, self.metadata.name)


def build_core_tools(core: Any = None) -> list[Tool]:
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


def register_core_tools(registry: Any, core: Any = None) -> list[str]:
    """Register CORE tools on an existing ToolRegistry; return names."""
    names: list[str] = []
    for tool in build_core_tools(core):
        registry.register(tool)
        names.append(tool.metadata.name)
    return names
