"""Real C.O.R.E. transport over TCP+TLS (stdlib only).

Implements the external-device wire protocol independently: 4-byte
big-endian length prefix + JSON envelope with ``message_id``,
``source``, ``destination``, ``message_type``, ``timestamp``,
``request_id``, ``payload``, ``identity_id``. Flow: TCP connect (TLS
1.2+ when enabled) → ``CORE_HANDSHAKE`` → ``DEVICE_REGISTER`` → online.

This module re-implements the wire contract; it never imports C.O.R.E.
(or A.S.I.S.) code. Session tokens stay in RAM and are never logged.
"""

from __future__ import annotations

import json
import math
import socket
import ssl
import struct
import uuid
import warnings
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

PROTOCOL_VERSION = "0.3.0"
HEADER_SIZE = 4
MAX_FRAME_SIZE = 10 * 1024 * 1024


class DeviceClientError(RuntimeError):
    """Transport or protocol failure talking to C.O.R.E."""


def _validate_timeout_s(value: Any, *, field: str = "timeout_s") -> float:
    """Validate a timeout: finite number > 0 (rejects bool/inf/nan)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DeviceClientError(f"{field} must be a positive number of seconds")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DeviceClientError(
            f"{field} must be a positive number of seconds"
        ) from None
    if not math.isfinite(number) or number <= 0:
        raise DeviceClientError(f"{field} must be a positive number of seconds")
    return number


def _validate_endpoint_str(value: Any, *, field: str) -> str:
    if not (isinstance(value, str) and value.strip()):
        raise DeviceClientError(f"{field} must be a non-empty string")
    return value.strip()


def _new_message(
    *,
    source: str,
    destination: str,
    message_type: str,
    payload: Mapping[str, Any],
    identity_id: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "message_id": str(uuid.uuid4()),
        "source": source,
        "destination": destination,
        "message_type": message_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "payload": dict(payload),
        "identity_id": identity_id,
    }


def encode_frame(message: Mapping[str, Any]) -> bytes:
    """Encode one envelope to length-prefixed wire bytes."""
    data = json.dumps(dict(message)).encode("utf-8")
    if not data or len(data) > MAX_FRAME_SIZE:
        raise DeviceClientError("outbound frame size invalid")
    return struct.pack("!I", len(data)) + data


def decode_frame(header: bytes, body: bytes) -> dict[str, Any]:
    """Decode one frame; raises :class:`DeviceClientError` when malformed."""
    if len(header) != HEADER_SIZE:
        raise DeviceClientError("short frame header")
    (length,) = struct.unpack("!I", header)
    if length <= 0 or length > MAX_FRAME_SIZE or len(body) != length:
        raise DeviceClientError("invalid inbound frame size")
    try:
        message = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DeviceClientError("invalid inbound message encoding") from exc
    if not isinstance(message, dict) or not message.get("message_type"):
        raise DeviceClientError("malformed inbound message")
    return message


class CoreTcpClient:
    """Authenticated C.O.R.E. device session over TCP+TLS."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        device_id: str,
        credential: str,
        device_name: str = "",
        use_tls: bool = True,
        ca_file: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        if not (isinstance(device_id, str) and device_id.strip()):
            raise DeviceClientError("device_id must be a non-empty string")
        if not (isinstance(credential, str) and credential):
            raise DeviceClientError("credential must be a non-empty string")
        validated_timeout = _validate_timeout_s(timeout_s, field="timeout_s")
        self.host = host
        self.port = int(port)
        self.device_id = device_id.strip()
        self.identity_id = self.device_id
        self.device_name = device_name or self.device_id
        self._credential = credential
        self.use_tls = bool(use_tls)
        self.ca_file = ca_file
        self.timeout_s = validated_timeout
        self._sock: socket.socket | None = None
        self._session_token: str | None = None
        self._connection_id: str | None = None
        self._registered = False

    @property
    def connected(self) -> bool:
        """True when the socket is open (registration tracked separately)."""
        return self._sock is not None

    @property
    def registered(self) -> bool:
        """True after a successful ``DEVICE_REGISTER`` round-trip."""
        return self._registered

    def close(self) -> None:
        """Close the transport and drop session state (credential kept)."""
        sock, self._sock = self._sock, None
        if sock is not None:
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            with suppress(OSError):
                sock.close()
        self._session_token = None
        self._connection_id = None
        self._registered = False

    def _send(self, message: Mapping[str, Any]) -> None:
        if self._sock is None:
            raise DeviceClientError("not connected")
        try:
            self._sock.sendall(encode_frame(message))
        except OSError as exc:
            self.close()
            raise DeviceClientError(f"send failed: {exc}") from exc

    def _recv(self) -> dict[str, Any]:
        if self._sock is None:
            raise DeviceClientError("not connected")
        try:
            header = self._recv_exact(HEADER_SIZE)
            (length,) = struct.unpack("!I", header)
            if length <= 0 or length > MAX_FRAME_SIZE:
                raise DeviceClientError("invalid inbound frame size")
            return decode_frame(header, self._recv_exact(length))
        except DeviceClientError:
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise DeviceClientError(f"receive failed: {exc}") from exc

    def _recv_exact(self, count: int) -> bytes:
        assert self._sock is not None
        buf = b""
        while len(buf) < count:
            chunk = self._sock.recv(count - len(buf))
            if not chunk:
                raise DeviceClientError("connection closed by host")
            buf += chunk
        return buf

    def _tls_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        try:
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        except AttributeError:
            context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
        # Hostname check stays off for self-signed LAN certs (CN=localhost);
        # chain verification via ca_file is still the trust root. Falling back
        # to system CAs is a MITM risk on hostile networks: warn loudly so
        # operators pin ca_file in production.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        if self.ca_file is not None:
            import os

            if not os.path.isfile(self.ca_file):
                raise DeviceClientError(f"ca_file not found: {self.ca_file}")
            context.load_verify_locations(cafile=self.ca_file)
        else:
            warnings.warn(
                "CoreTcpClient: no ca_file configured; falling back to system "
                "CAs with check_hostname=False (MITM risk). Provide ca_file "
                "pinning the C.O.R.E. host certificate in production.",
                UserWarning,
                stacklevel=2,
            )
            with suppress(ssl.SSLError):
                context.load_default_certs()
        return context

    def connect(self) -> dict[str, Any]:
        """TCP (+TLS) connect and ``CORE_HANDSHAKE`` round-trip."""
        self.close()
        try:
            raw = socket.create_connection(
                (self.host, self.port), timeout=self.timeout_s
            )
            raw.settimeout(self.timeout_s)
        except OSError as exc:
            raise DeviceClientError(f"connect failed: {exc}") from exc
        sock: socket.socket = raw
        if self.use_tls:
            try:
                sock = self._tls_context().wrap_socket(raw, server_hostname=self.host)
            except (OSError, ssl.SSLError) as exc:
                raw.close()
                raise DeviceClientError(f"TLS handshake failed: {exc}") from exc
            try:
                version = sock.version()
            except (OSError, ssl.SSLError):
                version = ""
            if version in ("TLSv1", "TLSv1.1"):
                sock.close()
                raise DeviceClientError(f"weak {version}; need TLS 1.2+")
        self._sock = sock
        hello = _new_message(
            source=self.identity_id,
            destination="core",
            message_type="CORE_HANDSHAKE",
            payload={
                "identity_id": self.identity_id,
                "credential": self._credential,
                "protocol_version": PROTOCOL_VERSION,
                "join_name": self.device_name,
            },
            identity_id=self.identity_id,
        )
        self._send(hello)
        response = self._recv()
        if response.get("message_type") != "CORE_HANDSHAKE_RESPONSE" or not (
            isinstance(response.get("payload"), dict)
            and response["payload"].get("authenticated") is True
        ):
            self.close()
            raise DeviceClientError("authentication rejected by host")
        payload = response["payload"]
        token = payload.get("session_token")
        if not (isinstance(token, str) and token):
            self.close()
            raise DeviceClientError("host did not issue a session token")
        self._connection_id = payload.get("connection_id")
        self._session_token = token
        return response

    def register(self, *, capabilities: list[str] | None = None) -> dict[str, Any]:
        """``DEVICE_REGISTER`` round-trip over the authenticated session."""
        if self._sock is None or self._session_token is None:
            raise DeviceClientError("connect and handshake first")
        message = _new_message(
            source=self.identity_id,
            destination="core",
            message_type="DEVICE_REGISTER",
            payload={
                "device_id": self.device_id,
                "device_name": self.device_name,
                "join_name": self.device_name,
                "protocol_version": PROTOCOL_VERSION,
                "capabilities": list(capabilities or []),
                "_session_token": self._session_token,
            },
            identity_id=self.identity_id,
        )
        self._send(message)
        response = self._recv()
        if response.get("message_type") == "DEVICE_ERROR":
            detail = response.get("payload", {})
            raise DeviceClientError(f"registration rejected: {detail}")
        if response.get("message_type") != "DEVICE_REGISTER_RESPONSE":
            raise DeviceClientError("unexpected response to DEVICE_REGISTER")
        self._registered = True
        return response

    def request(
        self,
        destination: str,
        message_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        """Send one request and wait for the correlated response."""
        if self._sock is None or not self._registered:
            raise DeviceClientError("register before sending requests")
        destination = _validate_endpoint_str(destination, field="destination")
        message_type = _validate_endpoint_str(message_type, field="message_type")
        if payload is not None and not isinstance(payload, Mapping):
            raise DeviceClientError("payload must be a mapping or None")
        if timeout_s is None:
            wait = self.timeout_s
        else:
            wait = _validate_timeout_s(timeout_s, field="timeout_s")
        message = _new_message(
            source=self.identity_id,
            destination=destination,
            message_type=message_type,
            payload={
                **dict(payload or {}),
                "_session_token": self._session_token,
            },
            identity_id=self.identity_id,
            request_id=str(uuid.uuid4()),
        )
        sock = self._sock
        try:
            previous = sock.gettimeout()
        except OSError:
            previous = None
        try:
            with suppress(OSError):
                sock.settimeout(wait)
            self._send(message)
            response = self._recv()
        finally:
            with suppress(OSError):
                sock.settimeout(previous if previous is not None else self.timeout_s)
        if not isinstance(response, dict):
            raise DeviceClientError("malformed response")
        if response.get("message_type") in ("DEVICE_ERROR", "DATA_ERROR"):
            raise DeviceClientError(f"host error: {response.get('payload')}")
        # Hosts correlate with our request_id or our message_id.
        if response.get("request_id") not in (
            message["request_id"],
            message["message_id"],
        ):
            self.close()
            raise DeviceClientError("response correlation mismatch")
        return response

    def discover(self) -> dict[str, Any]:
        """List devices via ``DEVICE_DISCOVER``."""
        return self.request("core", "DEVICE_DISCOVER")

    def device_info(self, device_id: str) -> dict[str, Any]:
        """Fetch one device record via ``DEVICE_INFO``."""
        if not (isinstance(device_id, str) and device_id.strip()):
            raise DeviceClientError("device_id must be a non-empty string")
        return self.request("core", "DEVICE_INFO", {"device_id": device_id.strip()})
