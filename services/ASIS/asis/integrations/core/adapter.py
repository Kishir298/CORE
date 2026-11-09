"""
Real C.O.R.E. adapter for A.S.I.S.

Wraps the external CORE-CLIENT device client over TCP+TLS. Never imports
CORE-HOST internals — the protocol boundary is intentionally network-based.

The CORE-CLIENT package is an optional runtime dependency injected via
``client_factory`` so A.S.I.S. stays fully usable standalone and unit tests
can substitute fakes. The provisioning credential is runtime-only and is
never persisted, logged, or exposed to the model.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from asis.logging.logger import get_logger

from .client import CoreClient, CoreResponse, ServiceRequest
from .errors import CoreProtocolError, CoreUnavailable
from .models import CoreConnectionState, CoreDeviceInfo, CoreStatus
from .protocol import error_message, normalize_result, redact, validate_envelope

_IMPORT_HINT = (
    "CORE-CLIENT package not found. Install it alongside A.S.I.S. or set "
    "PYTHONPATH to the CORE-CLIENT repo so 'client.core_device_client' "
    "is importable; A.S.I.S. continues standalone until then."
)


def default_client_factory(
    *,
    host: str,
    port: int,
    device_id: str,
    device_name: str = "",
    device_file: str = "",
    ca_file: str = "",
    insecure: bool = False,
    timeout: float = 10.0,
) -> Any:
    """Build a CORE-CLIENT device client or raise CoreUnavailable."""
    try:
        from client.core_device_client import CoreDeviceClient
    except Exception as exc:
        raise CoreUnavailable(_IMPORT_HINT) from exc
    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "device_id": device_id,
        "device_name": device_name or device_id,
        "timeout": timeout,
        "insecure": insecure,
    }
    if device_file:
        kwargs["device_file"] = device_file
    if ca_file:
        kwargs["ca_file"] = ca_file
    return CoreDeviceClient(**kwargs)


class RealCoreAdapter(CoreClient):
    """CoreClient backed by a real CORE-CLIENT device connection."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 5000,
        device_id: str = "asis-01",
        device_name: str = "ASIS",
        device_file: str = "",
        ca_file: str = "",
        insecure: bool = False,
        connect_timeout: float = 10.0,
        request_timeout: float = 30.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._logger = get_logger("integrations.core.adapter")
        self._host = host
        self._port = int(port)
        self._device_id = device_id
        self._device_name = device_name or device_id
        self._device_file = device_file
        self._ca_file = ca_file
        self._insecure = bool(insecure)
        self._connect_timeout = float(connect_timeout)
        self._request_timeout = float(request_timeout)
        self._factory = client_factory or default_client_factory
        self._device: Any | None = None
        self._state = CoreConnectionState.DISCONNECTED

    @property
    def name(self) -> str:
        return "core-client"

    @property
    def connection_state(self) -> CoreConnectionState:
        return self._state

    # -- lifecycle --
    def connect(self, credential: str | None = None) -> CoreResponse:
        if self.is_connected():
            return CoreResponse(ok=True, data={"adapter": self.name})
        if not credential or not credential.strip():
            return CoreResponse(
                ok=False, error="CORE_AUTH_ERROR: provisioning credential required."
            )
        self._state = CoreConnectionState.CONNECTING
        self._logger.info("CORE connecting to %s:%s", self._host, self._port)
        try:
            device = self._factory(
                host=self._host,
                port=self._port,
                device_id=self._device_id,
                device_name=self._device_name,
                device_file=self._device_file,
                ca_file=self._ca_file,
                insecure=self._insecure,
                timeout=self._connect_timeout,
            )
        except CoreUnavailable as exc:
            self._state = CoreConnectionState.FAILED
            return CoreResponse(ok=False, error=error_message(exc))
        except Exception as exc:
            self._state = CoreConnectionState.FAILED
            return CoreResponse(ok=False, error=error_message(exc))
        try:
            device.login(credential)
            self._state = CoreConnectionState.AUTHENTICATING
            device.connect()
            device.register()
        except Exception as exc:
            self._state = CoreConnectionState.FAILED
            with contextlib.suppress(Exception):
                device.shutdown()
            self._device = None
            return CoreResponse(ok=False, error=self._classify(exc))
        self._device = device
        self._state = CoreConnectionState.CONNECTED
        self._logger.info("CORE connected device=%s", self._device_id)
        return CoreResponse(ok=True, data={"adapter": self.name})

    def disconnect(self) -> None:
        self._state = CoreConnectionState.STOPPING
        device, self._device = self._device, None
        if device is not None:
            try:
                if hasattr(device, "shutdown"):
                    device.shutdown()
                else:
                    device.close_socket()
            except Exception:
                pass
        self._state = CoreConnectionState.DISCONNECTED
        self._logger.info("CORE disconnected device=%s", self._device_id)

    def is_connected(self) -> bool:
        device = self._device
        if device is None:
            return False
        try:
            connected = device.is_connected
            return bool(connected() if callable(connected) else connected)
        except Exception:
            return False

    def device_status(self) -> CoreResponse:
        device = self._device
        if device is None:
            return CoreResponse(ok=False, error="CORE_UNAVAILABLE: not connected.")
        try:
            remembered = (
                device.remembered_state() if hasattr(device, "remembered_state") else {}
            )
            lease = device.lease_state if hasattr(device, "lease_state") else "UNKNOWN"
            lease_state = lease() if callable(lease) else lease
            info = CoreDeviceInfo(
                device_id=str(remembered.get("device_id", self._device_id)),
                join_name=str(remembered.get("join_name", "")),
                device_name=str(remembered.get("device_name", self._device_name)),
                platform=str(remembered.get("platform", "")),
                capabilities=tuple(remembered.get("capabilities", []) or []),
                status=str(lease_state),
            )
            return CoreResponse(
                ok=True,
                data={
                    "device_id": info.device_id,
                    "join_name": info.join_name,
                    "device_name": info.device_name,
                    "platform": info.platform,
                    "capabilities": list(info.capabilities),
                    "status": info.status,
                },
            )
        except Exception as exc:
            return CoreResponse(ok=False, error=error_message(exc))

    def status(self) -> CoreStatus:
        device_resp = self.device_status()
        device = None
        if device_resp.ok and isinstance(device_resp.data, dict):
            data = device_resp.data
            device = CoreDeviceInfo(
                device_id=str(data.get("device_id", self._device_id)),
                join_name=str(data.get("join_name", "")),
                device_name=str(data.get("device_name", "")),
                platform=str(data.get("platform", "")),
                capabilities=tuple(data.get("capabilities", []) or []),
                status=str(data.get("status", "unknown")),
            )
        connected = self.is_connected()
        state = (
            self._state
            if not connected and self._state == CoreConnectionState.CONNECTED
            else self._state
        )
        if connected:
            state = CoreConnectionState.CONNECTED
        elif state == CoreConnectionState.CONNECTED:
            state = CoreConnectionState.DISCONNECTED
        return CoreStatus(
            state=state,
            connected=connected,
            device=device,
            lease_state=(device.status if device else "DISCONNECTED"),
        )

    # -- application requests --
    def send_request(
        self,
        destination: str,
        message_type: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> CoreResponse:
        device = self._device
        if device is None or not self.is_connected():
            return CoreResponse(ok=False, error="CORE_UNAVAILABLE: not connected.")
        if timeout is not None and timeout <= 0:
            return CoreResponse(ok=False, error="CORE_ERROR: timeout must be positive.")
        wait = self._request_timeout if timeout is None else float(timeout)
        self._logger.info("CORE request %s -> %s", message_type, destination)
        try:
            raw = device.request(
                destination, message_type, dict(payload or {}), timeout=wait
            )
            message = validate_envelope(raw)
            data = normalize_result(message.get("payload"))
            self._logger.info("CORE response %s ok", message.get("message_type"))
            return CoreResponse(ok=True, data=data)
        except Exception as exc:
            text = self._classify(exc)
            self._logger.info("CORE request failed: %s", text.split(":")[0])
            if "CORE_UNAVAILABLE" in text and "closed" in str(exc).lower():
                self._drop_session()
            return CoreResponse(ok=False, error=text)

    def data_request(
        self,
        request_type: str,
        params: dict[str, Any] | None = None,
        destination: str = "core",
        timeout: float | None = None,
    ) -> CoreResponse:
        """Query host data via the device client's DATA_REQUEST API."""
        device = self._device
        if device is None or not self.is_connected():
            return CoreResponse(ok=False, error="CORE_UNAVAILABLE: not connected.")
        try:
            if hasattr(device, "data_request"):
                raw = device.data_request(
                    request_type,
                    dict(params or {}),
                    destination,
                    timeout=self._request_timeout if timeout is None else timeout,
                )
                message = validate_envelope(raw)
                return CoreResponse(
                    ok=True, data=normalize_result(message.get("payload"))
                )
        except Exception as exc:
            return CoreResponse(ok=False, error=self._classify(exc))
        return self.send_request(
            destination,
            "DATA_REQUEST",
            {"request_type": request_type, **dict(params or {})},
            timeout=self._request_timeout if timeout is None else timeout,
        )

    def send_to_device(
        self,
        device_id: str,
        message_type: str,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> CoreResponse:
        """Send a device-to-device message via the host router."""
        device = self._device
        if device is None or not self.is_connected():
            return CoreResponse(ok=False, error="CORE_UNAVAILABLE: not connected.")
        try:
            if hasattr(device, "send_to_device"):
                raw = device.send_to_device(
                    device_id,
                    message_type,
                    dict(payload or {}),
                    timeout=self._request_timeout if timeout is None else timeout,
                )
                message = validate_envelope(raw)
                return CoreResponse(
                    ok=True, data=normalize_result(message.get("payload"))
                )
        except Exception as exc:
            return CoreResponse(ok=False, error=self._classify(exc))
        return self.send_request(
            device_id,
            message_type,
            dict(payload or {}),
            timeout=self._request_timeout if timeout is None else timeout,
        )

    # -- legacy surface mapped onto supported host operations only --
    def send_message(self, recipient: str, payload: dict[str, Any]) -> CoreResponse:
        return self.send_request(recipient, "APP_MESSAGE", dict(payload or {}))

    def request_service(self, request: ServiceRequest) -> CoreResponse:
        device = self._device
        if device is None or not self.is_connected():
            return CoreResponse(ok=False, error="CORE_UNAVAILABLE: not connected.")
        try:
            if hasattr(device, "service_request"):
                raw = device.service_request(
                    request.service, request.operation, dict(request.params)
                )
                message = validate_envelope(raw)
                return CoreResponse(
                    ok=True, data=normalize_result(message.get("payload"))
                )
        except Exception as exc:
            return CoreResponse(ok=False, error=self._classify(exc))
        return self.send_request(
            f"service:{request.service}",
            "SERVICE_REQUEST",
            {"operation": request.operation, **dict(request.params)},
        )

    def publish_event(
        self, event_type: str, data: dict[str, Any] | None = None
    ) -> None:
        self._logger.info("CORE event %s (local-only; no host event API)", event_type)

    def get_resource(self, name: str) -> CoreResponse:
        device = self._device
        if device is None or not self.is_connected():
            return CoreResponse(ok=False, error="CORE_UNAVAILABLE: not connected.")
        try:
            if hasattr(device, "data_request"):
                raw = device.data_request("record_get", {"key": name})
                message = validate_envelope(raw)
                return CoreResponse(
                    ok=True, data=normalize_result(message.get("payload"))
                )
        except Exception as exc:
            return CoreResponse(ok=False, error=self._classify(exc))
        return CoreResponse(ok=False, error="CORE_ERROR: resource API not mapped.")

    def register_component(
        self, component_id: str, metadata: dict[str, Any] | None = None
    ) -> CoreResponse:
        redacted = redact(metadata or {})
        self._logger.info("CORE register component %s (local-only)", component_id)
        return CoreResponse(
            ok=True, data={"component_id": component_id, "meta": redacted}
        )

    def get_health(self) -> dict[str, Any]:
        status = self.status()
        return {
            "adapter": self.name,
            "status": "connected" if status.connected else "disconnected",
            "state": status.state.value,
            "lease": status.lease_state,
            "device": status.device.device_id if status.device else None,
        }

    # -- internals --
    def _drop_session(self) -> None:
        device, self._device = self._device, None
        if device is not None:
            try:
                if hasattr(device, "mark_disconnected"):
                    device.mark_disconnected()
                elif hasattr(device, "close_socket"):
                    device.close_socket()
            except Exception:
                pass
        self._state = CoreConnectionState.DISCONNECTED

    def _classify(self, exc: BaseException) -> str:
        text = str(exc)
        lowered = text.lower()
        if isinstance(exc, CoreUnavailable):
            return error_message(exc)
        if "login required" in lowered or "auth" in lowered or "credential" in lowered:
            return f"CORE_AUTH_ERROR: {text}"
        if "expired" in lowered or "session" in lowered and "token" in lowered:
            return f"CORE_AUTH_ERROR: {text}"
        if "timeout" in lowered or "timed out" in lowered:
            return f"CORE_TIMEOUT: {text}"
        if "host error" in lowered or "malformed" in lowered or "frame" in lowered:
            if isinstance(exc, CoreProtocolError):
                return error_message(exc)
            if "host error" in lowered:
                return f"CORE_ERROR: {text}"
            return f"CORE_PROTOCOL_ERROR: {text}"
        if (
            "closed" in lowered
            or "connection" in lowered
            or "register before" in lowered
        ):
            self._drop_session()
            return f"CORE_UNAVAILABLE: {text}"
        return error_message(exc)
