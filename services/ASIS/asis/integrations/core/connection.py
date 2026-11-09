"""
C.O.R.E. connection lifecycle for A.S.I.S.

A RuntimeComponent owning the optional CORE session. A.S.I.S. runs fully
standalone when CORE is disabled or unreachable; failures here never take
down the local assistant. Reconnect is bounded and stop-aware.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from typing import Any

from asis.logging.logger import get_logger
from asis.system.component import RuntimeComponent
from asis.system.context import RuntimeContext

from .client import CoreClient
from .models import CoreConnectionState, CoreStatus


class CoreConnectionManager(RuntimeComponent):
    """Lifecycle-aware holder for the optional C.O.R.E. session."""

    name = "core-connection"

    def __init__(
        self,
        adapter: CoreClient,
        *,
        enabled: bool = False,
        credential_provider: Callable[[], str | None] | None = None,
        reconnect_enabled: bool = True,
        reconnect_delay: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        self._logger = get_logger("integrations.core.connection")
        self._adapter = adapter
        self._enabled = bool(enabled)
        self._credential_provider = credential_provider
        self._reconnect_enabled = bool(reconnect_enabled)
        self._reconnect_delay = max(0.0, float(reconnect_delay))
        self._max_retries = max(0, int(max_retries))
        self._state = CoreConnectionState.DISCONNECTED
        self._stop = threading.Event()
        self._detail = ""

    @property
    def state(self) -> CoreConnectionState:
        adapter_state = getattr(self._adapter, "connection_state", None)
        if (
            isinstance(adapter_state, CoreConnectionState)
            and self._adapter.is_connected()
        ):
            return CoreConnectionState.CONNECTED
        return self._state

    @property
    def adapter(self) -> CoreClient:
        return self._adapter

    def start(self, context: RuntimeContext) -> None:
        self._stop.clear()
        context.register("core", self._adapter)
        context.register("core_connection", self)
        if not self._enabled:
            self._state = CoreConnectionState.DISABLED
            self._detail = "disabled"
            self._logger.info("CORE disabled; running standalone.")
            return
        self._connect_with_retries()

    def stop(self, context: RuntimeContext) -> None:
        self._stop.set()
        self._state = CoreConnectionState.STOPPING
        with contextlib.suppress(Exception):
            self._adapter.disconnect()
        self._state = (
            CoreConnectionState.DISABLED
            if not self._enabled
            else CoreConnectionState.DISCONNECTED
        )
        self._logger.info("CORE stopped; ephemeral session cleared.")

    # -- application path --
    def is_available(self) -> bool:
        try:
            return bool(self._adapter.is_connected())
        except Exception:
            return False

    def request(
        self,
        destination: str,
        message_type: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ):
        if not self.is_available():
            from .client import CoreResponse

            return CoreResponse(ok=False, error="CORE_UNAVAILABLE: not connected.")
        return self._adapter.send_request(destination, message_type, payload, timeout)

    def status(self) -> CoreStatus:
        connected = self.is_available()
        if connected:
            state = CoreConnectionState.CONNECTED
        elif not self._enabled:
            state = CoreConnectionState.DISABLED
        else:
            state = self._state
            if state == CoreConnectionState.CONNECTED:
                state = CoreConnectionState.DISCONNECTED
        lease = "UNKNOWN"
        device = None
        try:
            resp = self._adapter.device_status()
            if resp.ok and isinstance(resp.data, dict):
                from .models import CoreDeviceInfo

                device = CoreDeviceInfo(
                    device_id=str(resp.data.get("device_id", "")),
                    join_name=str(resp.data.get("join_name", "")),
                    device_name=str(resp.data.get("device_name", "")),
                    platform=str(resp.data.get("platform", "")),
                    capabilities=tuple(resp.data.get("capabilities", []) or []),
                    status=str(resp.data.get("status", "")),
                )
                lease = device.status
        except Exception:
            pass
        return CoreStatus(
            state=state,
            connected=connected,
            device=device,
            lease_state=lease if connected else "DISCONNECTED",
            detail=self._detail,
        )

    def reconnect_now(self) -> bool:
        """Manual bounded reconnect (e.g. after the host comes back)."""
        if not self._enabled or self._stop.is_set():
            return False
        self._state = CoreConnectionState.RECONNECTING
        with contextlib.suppress(Exception):
            self._adapter.disconnect()
        return self._connect_once()

    # -- internals --
    def _credential(self) -> str | None:
        if self._credential_provider is None:
            return None
        try:
            value = self._credential_provider()
        except Exception:
            return None
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _connect_with_retries(self) -> None:
        if self._connect_once():
            return
        if self._detail.startswith("no credential"):
            # Expected standalone state, not a failure.
            self._state = CoreConnectionState.DISCONNECTED
            return
        if not self._reconnect_enabled:
            self._state = CoreConnectionState.FAILED
            return
        self._state = CoreConnectionState.RECONNECTING
        for attempt in range(1, self._max_retries + 1):
            if self._stop.is_set():
                self._state = CoreConnectionState.STOPPING
                return
            delay = self._reconnect_delay * attempt
            self._logger.info(
                "CORE retry %s/%s in %.1fs", attempt, self._max_retries, delay
            )
            if delay > 0 and self._stop.wait(delay):
                self._state = CoreConnectionState.STOPPING
                return
            if self._connect_once():
                return
        self._state = CoreConnectionState.FAILED
        self._logger.info("CORE unavailable; continuing standalone.")

    def _connect_once(self) -> bool:
        self._state = CoreConnectionState.CONNECTING
        credential = self._credential()
        if not credential:
            self._detail = "no credential (runtime-only)"
            self._state = CoreConnectionState.DISCONNECTED
            self._logger.info("CORE credential absent; running standalone.")
            return False
        try:
            resp = self._adapter.connect(credential)
        except Exception as exc:
            self._detail = str(exc)[:200]
            self._state = CoreConnectionState.DISCONNECTED
            return False
        if resp.ok:
            self._state = CoreConnectionState.CONNECTED
            self._detail = ""
            self._logger.info("CORE session established.")
            return True
        self._detail = str(resp.error or "")[:200]
        self._state = CoreConnectionState.DISCONNECTED
        self._logger.info("CORE connect failed; running standalone.")
        return False


def build_connection_manager_from_settings(
    settings_obj: Any,
    adapter: CoreClient,
    credential_provider: Callable[[], str | None] | None = None,
) -> CoreConnectionManager:
    """Build a manager from centralized Settings (no scattered getenv)."""
    core = getattr(settings_obj, "core", None)
    return CoreConnectionManager(
        adapter,
        enabled=bool(getattr(core, "enabled", False)),
        credential_provider=credential_provider,
        reconnect_enabled=bool(getattr(core, "reconnect_enabled", True)),
        reconnect_delay=float(getattr(core, "reconnect_delay", 5) or 0),
    )
