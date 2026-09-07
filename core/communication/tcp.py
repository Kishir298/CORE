from __future__ import annotations

import socket
import struct
import threading
import time
from pathlib import Path
from typing import Any, Callable

from core.errors import MessageError

from .connection import ConnectionSession, ConnectionState
from .models import Message
from .serializer import MessageSerializer
from .transport import MessageHandler, Transport

# Fixed protocol limits (NOT configurable per hardening spec).
MAX_FRAME_SIZE = 10 * 1024 * 1024
MAX_CONNECTIONS = 64
HEADER_SIZE = 4
TLS_HANDSHAKE_TIMEOUT = 5.0
IDLE_CONNECTION_TIMEOUT = 300.0

HANDSHAKE_TYPE = "CORE_HANDSHAKE"
HANDSHAKE_RESPONSE_TYPE = "CORE_HANDSHAKE_RESPONSE"


class TcpTransport(Transport):
    """
    TCP message transport for Windows co-hosted deployment.

    Binds to ``127.0.0.1`` by default. External binding to ``0.0.0.0``
    requires TLS (fail closed — no plaintext downgrade) and per-connection
    handshake + authentication before application messages.

    Localhost operation without an injected ``security_manager`` preserves
    the legacy framing path so existing local tests keep passing.
    When a ``security_manager`` is injected (as ``CoreApplication`` does),
    every socket connection must complete::

        CORE_HANDSHAKE -> authenticate -> SESSION_ESTABLISHED

    before any application message is routed. Connections are persistent
    and support multiple messages until disconnect / idle timeout /
    protocol violation / shutdown.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        on_delivery: Callable[[Message], None] | None = None,
        use_tls: bool = False,
        certfile: str | Path | None = None,
        keyfile: str | Path | None = None,
        cafile: str | Path | None = None,
        require_client_cert: bool = False,
        security_manager: Any | None = None,
        version_negotiator: Callable[[str | None], str] | None = None,
        version_supported: Callable[[str], bool] | None = None,
        time_func: Callable[[], float] | None = None,
    ) -> None:
        from threading import RLock

        raw_host = (host or "127.0.0.1").strip()
        if raw_host == "":
            raw_host = "127.0.0.1"
        self._host = raw_host
        self._port = int(port) if isinstance(port, int) else 0
        if self._port < 0 or self._port > 65535:
            raise ValueError(f"TCP port out of range: {self._port}")
        self._on_delivery = on_delivery

        self._use_tls = bool(use_tls)
        self._certfile = Path(certfile) if certfile else None
        self._keyfile = Path(keyfile) if keyfile else None
        self._cafile = Path(cafile) if cafile else None
        self._require_client_cert = bool(require_client_cert)
        self._tls_active = False
        self._ssl_context = None  # type: ignore

        # External binding mandates TLS — fail closed at construction.
        if self.is_external and not self._use_tls:
            raise ValueError(
                "External TCP (0.0.0.0) requires TLS: "
                "set use_tls=True with a valid certfile."
            )
        if self._use_tls:
            try:
                self._ssl_context = self._build_ssl_context()
                self._tls_active = True
            except Exception as exc:
                if self.is_external:
                    # FAIL CLOSED for external devices: never downgrade.
                    raise
                # Localhost legacy fallback: plaintext with warning state.
                self._ssl_context = None
                self._tls_active = False
                _ = exc

        self._security_manager = security_manager
        # External binding mandates credential-based auth — fail closed.
        # Localhost keeps legacy behavior (handshake disabled without a
        # security manager; existence provider tolerated).
        if self.is_external:
            provider = (
                getattr(security_manager, "provider", None)
                if security_manager is not None
                else None
            )
            provider_name = (
                type(provider).__name__ if provider is not None else "None"
            )
            if security_manager is None or provider_name in (
                "ExistenceAuthenticationProvider",
                "None",
            ):
                raise ValueError(
                    "External TCP (0.0.0.0) requires a credential-based "
                    "authentication provider (TokenAuthenticationProvider); "
                    f"got {provider_name}."
                )
        self._version_negotiator = version_negotiator
        self._version_supported = version_supported
        if self._version_negotiator is None or self._version_supported is None:
            try:
                from core.version import is_supported as _is_supported
                from core.version import negotiate as _negotiate

                if self._version_negotiator is None:
                    self._version_negotiator = _negotiate
                if self._version_supported is None:
                    self._version_supported = _is_supported
            except Exception:
                pass
        self._time = time_func or time.monotonic

        self._handlers: dict[str, MessageHandler] = {}
        self._lock = RLock()
        self._active = True
        self._messages_sent = 0
        self._messages_received = 0

        # Hardened session registry + metrics.
        # _reserved counts connections admitted but not yet registered,
        # so reserved + active can never exceed MAX_CONNECTIONS.
        self._connections: dict[str, ConnectionSession] = {}
        self._reserved = 0
        self._total_connections = 0
        self._rejected_connections = 0
        self._authentication_failures = 0
        self._protocol_failures = 0

        self._server_socket: socket.socket | None = None
        self._server_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # -- properties ------------------------------------------------------

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_external(self) -> bool:
        """Return whether the transport is bound for external LAN access."""
        return self._host == "0.0.0.0"

    @property
    def is_tls(self) -> bool:
        """Return whether TLS is configured and active."""
        return self._tls_active

    @property
    def uses_tls(self) -> bool:
        """Return whether TLS was requested (may be inactive if fallback)."""
        return self._use_tls

    @property
    def hardened(self) -> bool:
        """Return whether per-connection handshake/auth is enforced."""
        return self._security_manager is not None

    def _build_ssl_context(self):  # type: ignore
        """Build an SSLContext for the TLS listener (TLS 1.2+ only)."""
        import ssl

        if self._certfile is not None and not self._certfile.exists():
            raise FileNotFoundError(f"TLS certfile not found: {self._certfile}")
        if self._keyfile is not None and not self._keyfile.exists():
            raise FileNotFoundError(f"TLS keyfile not found: {self._keyfile}")
        if self._cafile is not None and not self._cafile.exists():
            raise FileNotFoundError(f"TLS cafile not found: {self._cafile}")

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            ctx.options |= getattr(ssl, "OP_NO_TLSv1", 0) | getattr(
                ssl, "OP_NO_TLSv1_1", 0
            )
        if self._certfile:
            ctx.load_cert_chain(
                certfile=str(self._certfile),
                keyfile=str(self._keyfile) if self._keyfile else None,
            )
        else:
            raise FileNotFoundError("TLS certfile not configured for TLS mode")

        if self._require_client_cert and self._cafile:
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.load_verify_locations(cafile=str(self._cafile))
        elif self._cafile:
            ctx.verify_mode = ssl.CERT_OPTIONAL
            ctx.load_verify_locations(cafile=str(self._cafile))

        return ctx

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Start the transport and optional TCP listener."""
        needs_server = False
        with self._lock:
            if not self._active:
                self._active = True
                self._stop_event.clear()
                needs_server = self._port != 0 and self._server_socket is None
            else:
                needs_server = self._port != 0 and self._server_socket is None

        if needs_server:
            # Fail-closed errors propagate for external; localhost keeps
            # legacy best-effort fallback.
            try:
                self._start_server()
            except Exception:
                if self.is_external:
                    raise
                pass

    def stop(self) -> None:
        """Stop the transport, close sessions, retain endpoints."""
        with self._lock:
            self._active = False
            self._stop_event.set()
        self._close_all_connections()
        self._stop_server()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._active

    # -- endpoints (unchanged public API) --------------------------------

    def register(self, endpoint: str, handler: MessageHandler) -> None:
        if not endpoint:
            raise MessageError("Communication endpoint cannot be empty.")
        if not callable(handler):
            raise MessageError(f"Handler for endpoint '{endpoint}' is not callable.")
        with self._lock:
            if endpoint in self._handlers:
                raise MessageError(f"Endpoint already registered: {endpoint}")
            self._handlers[endpoint] = handler

    def unregister(self, endpoint: str) -> None:
        with self._lock:
            self._handlers.pop(endpoint, None)

    def has_endpoint(self, endpoint: str) -> bool:
        with self._lock:
            return endpoint in self._handlers

    def endpoint_count(self) -> int:
        with self._lock:
            return len(self._handlers)

    def send(self, message: Message) -> Message | None:
        if not isinstance(message, Message):
            raise MessageError("Communication can only send Message instances.")

        with self._lock:
            if not self._active:
                raise MessageError("Communication layer is not running.")
            handler = self._handlers.get(message.destination)
            if handler is None:
                raise MessageError(f"Destination not registered: {message.destination}")
            self._messages_sent += 1

        try:
            serialized = MessageSerializer.serialize(message)
            deserialized = MessageSerializer.deserialize(serialized)
            response = handler(deserialized)
        except MessageError:
            raise
        except Exception as exc:
            raise MessageError(
                f"Message handling failed for destination: {message.destination}"
            ) from exc

        with self._lock:
            self._messages_received += 1

        if response is not None and not isinstance(response, Message):
            raise MessageError("Communication handlers must return a Message or None.")

        if self._on_delivery is not None:
            try:
                self._on_delivery(message)
            except Exception:
                pass

        return response

    def request(
        self,
        source: str,
        destination: str,
        message_type: str,
        payload: dict | None = None,
    ) -> Message | None:
        message = Message(
            source=source,
            destination=destination,
            message_type=message_type,
            payload=payload or {},
        )
        return self.send(message)

    def message_count(self) -> int:
        with self._lock:
            return self._messages_sent

    def response_count(self) -> int:
        with self._lock:
            return self._messages_received

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()
            self._messages_sent = 0
            self._messages_received = 0
            self._connections.clear()
            self._reserved = 0
            self._total_connections = 0
            self._rejected_connections = 0
            self._authentication_failures = 0
            self._protocol_failures = 0

    def count(self) -> int:
        return self.endpoint_count()

    # -- session registry + metrics (additive API) ------------------------

    def get_connection(self, connection_id: str) -> ConnectionSession | None:
        with self._lock:
            return self._connections.get(connection_id)

    def list_connections(self) -> list[ConnectionSession]:
        with self._lock:
            return list(self._connections.values())

    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def active_connections(self) -> int:
        return self.connection_count()

    def total_connections(self) -> int:
        with self._lock:
            return self._total_connections

    def rejected_connections(self) -> int:
        with self._lock:
            return self._rejected_connections

    def authentication_failures(self) -> int:
        with self._lock:
            return self._authentication_failures

    def protocol_failures(self) -> int:
        with self._lock:
            return self._protocol_failures

    def _register_session(
        self, session: ConnectionSession, has_reservation: bool = False
    ) -> bool:
        """Register a session if capacity allows. Returns True if admitted.

        When has_reservation is True the caller already owns one reserved
        slot (via try_reserve_slot); registration consumes it. Direct
        callers without a reservation are capped against active + reserved.
        """
        with self._lock:
            if session.connection_id in self._connections:
                return True
            if has_reservation:
                if self._reserved > 0:
                    self._reserved -= 1
                if len(self._connections) >= MAX_CONNECTIONS:
                    self._rejected_connections += 1
                    return False
            else:
                if len(self._connections) + self._reserved >= MAX_CONNECTIONS:
                    self._rejected_connections += 1
                    return False
            self._connections[session.connection_id] = session
            self._total_connections += 1
            return True

    def try_reserve_slot(self) -> bool:
        """Atomically reserve one connection slot before expensive work.

        Returns True when the caller owns a reservation; False when the
        64-slot budget (active + reserved) is exhausted. Rejections
        increment rejected_connections exactly once here.
        """
        with self._lock:
            if len(self._connections) + self._reserved >= MAX_CONNECTIONS:
                self._rejected_connections += 1
                return False
            self._reserved += 1
            return True

    def release_reservation(self, count_rejection: bool = False) -> None:
        """Release a previously reserved slot (e.g. TLS/handshake failure)."""
        with self._lock:
            if self._reserved > 0:
                self._reserved -= 1
            if count_rejection:
                self._rejected_connections += 1

    def reserved_slots(self) -> int:
        """Return admitted-but-not-yet-registered slot count."""
        with self._lock:
            return self._reserved

    def _remove_session(self, connection_id: str) -> None:
        with self._lock:
            session = self._connections.pop(connection_id, None)
            if session is not None:
                session.transition(ConnectionState.CLOSED)

    def _close_all_connections(self) -> None:
        with self._lock:
            ids = list(self._connections.keys())
            self._reserved = 0
        for cid in ids:
            self._remove_session(cid)

    # -- TCP server --------------------------------------------------------

    def _start_server(self) -> None:
        if self._server_socket is not None:
            return

        # External binding mandates active TLS — fail closed.
        if self.is_external:
            if not self._use_tls:
                raise ValueError("External TCP (0.0.0.0) requires TLS.")
            if self._ssl_context is None:
                try:
                    self._ssl_context = self._build_ssl_context()
                except Exception:
                    self._tls_active = False
                    raise
                else:
                    self._tls_active = True
            if not self._tls_active or self._ssl_context is None:
                raise ValueError("External TCP requires active TLS context.")
            is_tls = True
        else:
            is_tls = False
            if self._use_tls:
                if self._ssl_context is None:
                    try:
                        self._ssl_context = self._build_ssl_context()
                    except Exception:
                        self._tls_active = False
                        self._ssl_context = None
                    else:
                        self._tls_active = True
                is_tls = self._tls_active and self._ssl_context is not None
            else:
                self._tls_active = False

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass

        bind_host = self._host if self._host else "127.0.0.1"
        sock.bind((bind_host, self._port))
        actual_port = sock.getsockname()[1]
        self._port = actual_port
        sock.listen(5)
        sock.settimeout(1.0)
        self._server_socket = sock

        def _accept_loop() -> None:
            while not self._stop_event.is_set():
                try:
                    conn, addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                # Atomic admission: reserve before expensive TLS work so a
                # concurrent burst can never admit more than 64 total.
                if not self.try_reserve_slot():
                    try:
                        conn.close()
                    except Exception:
                        pass
                    continue

                remote = f"{addr[0]}:{addr[1]}" if addr else ""
                if is_tls and self._ssl_context is not None:
                    try:
                        conn.settimeout(TLS_HANDSHAKE_TIMEOUT)
                        conn = self._ssl_context.wrap_socket(
                            conn, server_side=True, do_handshake_on_connect=True
                        )
                    except Exception:
                        # TLS failure releases the reservation (no session);
                        # count the rejection exactly once.
                        self.release_reservation(count_rejection=True)
                        try:
                            conn.close()
                        except Exception:
                            pass
                        continue

                threading.Thread(
                    target=self._handle_connection,
                    args=(conn, remote, is_tls, True),
                    daemon=True,
                ).start()

        self._server_thread = threading.Thread(target=_accept_loop, daemon=True)
        self._server_thread.start()

    def _stop_server(self) -> None:
        sock = self._server_socket
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
            self._server_socket = None
        thread = self._server_thread
        if thread is not None:
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass
            self._server_thread = None

    # -- connection handling ----------------------------------------------

    def _handle_connection(
        self,
        conn: socket.socket,
        remote_address: str = "",
        is_tls: bool = False,
        has_reservation: bool = False,
    ) -> None:
        now = self._time()
        session = ConnectionSession(
            remote_address=remote_address,
            connected_at=now,
            last_activity=now,
        )
        session.transition(
            ConnectionState.TLS_ESTABLISHED if is_tls else ConnectionState.CONNECTED
        )
        if not self._register_session(session, has_reservation=has_reservation):
            try:
                conn.close()
            except Exception:
                pass
            return
        try:
            if self._security_manager is not None:
                self._serve_hardened(conn, session)
            else:
                self._serve_legacy(conn, session)
        finally:
            try:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                conn.close()
            except Exception:
                pass
            session.transition(ConnectionState.CLOSING)
            self._remove_session(session.connection_id)

    def _serve_legacy(self, conn: socket.socket, session: ConnectionSession) -> None:
        """Persistent legacy framing loop (no handshake) for localhost compat."""
        try:
            while not self._stop_event.is_set():
                if not self._wait_readable(conn, session):
                    return
                frame = self._recv_frame(conn, session)
                if frame is None:
                    return
                try:
                    message = MessageSerializer.deserialize(frame)
                except Exception:
                    with self._lock:
                        self._protocol_failures += 1
                    return
                try:
                    self._validate_message_shape(message)
                except MessageError:
                    with self._lock:
                        self._protocol_failures += 1
                    return
                session.messages_received += 1
                session.touch(self._time())
                try:
                    response = self.send(message)
                except MessageError:
                    with self._lock:
                        self._protocol_failures += 1
                    return
                if response is not None:
                    session.messages_sent += 1
                    self._send_frame(conn, response)
                    session.touch(self._time())
        except Exception:
            with self._lock:
                self._protocol_failures += 1
            return

    def _serve_hardened(self, conn: socket.socket, session: ConnectionSession) -> None:
        """Handshake -> authenticate -> persistent validated message loop."""
        try:
            session.transition(ConnectionState.AUTHENTICATING)
            if not self._wait_readable(conn, session):
                with self._lock:
                    self._protocol_failures += 1
                return
            frame = self._recv_frame(conn, session)
            if frame is None:
                with self._lock:
                    self._protocol_failures += 1
                return
            try:
                hello = MessageSerializer.deserialize(frame)
            except Exception:
                with self._lock:
                    self._protocol_failures += 1
                return
            ok = self._process_handshake(conn, session, hello)
            if not ok:
                return
            # Authenticated message loop.
            while not self._stop_event.is_set():
                if not self._wait_readable(conn, session):
                    return
                frame = self._recv_frame(conn, session)
                if frame is None:
                    return
                try:
                    message = MessageSerializer.deserialize(frame)
                except Exception:
                    with self._lock:
                        self._protocol_failures += 1
                    return
                if message.message_type == HANDSHAKE_TYPE:
                    # Duplicate handshake is a protocol violation.
                    with self._lock:
                        self._protocol_failures += 1
                    return
                try:
                    self._validate_message_shape(message)
                    self._enforce_identity(message, session)
                except MessageError:
                    with self._lock:
                        self._protocol_failures += 1
                    return
                session.messages_received += 1
                session.touch(self._time())
                try:
                    response = self.send(message)
                except MessageError:
                    with self._lock:
                        self._protocol_failures += 1
                    return
                if response is not None:
                    session.messages_sent += 1
                    self._send_frame(conn, response)
                    session.touch(self._time())
        except Exception:
            with self._lock:
                self._protocol_failures += 1
            return

    def _process_handshake(
        self, conn: socket.socket, session: ConnectionSession, hello: Message
    ) -> bool:
        """Validate handshake, authenticate, reply. Returns True on success."""
        if hello.message_type != HANDSHAKE_TYPE:
            # Application message before handshake.
            with self._lock:
                self._protocol_failures += 1
            return False
        payload = hello.payload if isinstance(hello.payload, dict) else None
        if payload is None:
            with self._lock:
                self._protocol_failures += 1
            return False
        identity_id = payload.get("identity_id")
        credential = payload.get("credential")
        protocol_version = payload.get("protocol_version")
        if not identity_id or credential is None or not protocol_version:
            with self._lock:
                self._protocol_failures += 1
            return False
        if not isinstance(identity_id, str) or not isinstance(protocol_version, str):
            with self._lock:
                self._protocol_failures += 1
            return False
        # Version validation via existing infrastructure.
        try:
            supported = (
                self._version_supported(str(protocol_version))
                if self._version_supported is not None
                else True
            )
            negotiated = (
                self._version_negotiator(str(protocol_version))
                if self._version_negotiator is not None
                else str(protocol_version)
            )
        except Exception:
            with self._lock:
                self._protocol_failures += 1
            return False
        if not supported:
            with self._lock:
                self._protocol_failures += 1
            return False
        # External auth must not use existence-only provider, and the
        # identity must have a credential/token configured: existence
        # alone never authenticates an external connection.
        provider = getattr(self._security_manager, "provider", None)
        provider_name = type(provider).__name__ if provider is not None else ""
        if provider_name == "ExistenceAuthenticationProvider":
            with self._lock:
                self._authentication_failures += 1
            return False
        try:
            identity = self._security_manager.get_identity(str(identity_id))
        except Exception:
            with self._lock:
                self._authentication_failures += 1
            return False
        metadata = getattr(identity, "metadata", {}) or {}
        try:
            has_token = any(
                key in metadata
                for key in ("token", "credential", "api_token", "password")
            )
        except Exception:
            has_token = False
        if not has_token:
            with self._lock:
                self._authentication_failures += 1
            return False
        try:
            self._security_manager.authenticate(str(identity_id), credential)
        except Exception:
            with self._lock:
                self._authentication_failures += 1
            return False
        session.mark_authenticated(str(identity_id), self._time())
        session.messages_received += 1
        response = Message(
            source="core",
            destination=str(identity_id),
            message_type=HANDSHAKE_RESPONSE_TYPE,
            payload={
                "authenticated": True,
                "identity_id": str(identity_id),
                "protocol_version": negotiated,
                "connection_id": session.connection_id,
            },
            identity_id=str(identity_id),
        )
        try:
            self._send_frame(conn, response)
        except Exception:
            with self._lock:
                self._protocol_failures += 1
            return False
        session.messages_sent += 1
        return True

    # -- validation --------------------------------------------------------

    @staticmethod
    def _validate_message_shape(message: Message) -> None:
        if (
            not message.message_id
            or not message.source
            or not message.destination
            or not message.message_type
            or message.timestamp is None
            or not isinstance(message.payload, dict)
        ):
            raise MessageError("Malformed message.")

    @staticmethod
    def _enforce_identity(message: Message, session: ConnectionSession) -> None:
        if session.identity_id is None or not session.authenticated:
            raise MessageError("Unauthenticated session.")
        if message.identity_id != session.identity_id:
            raise MessageError("identity_id mismatch.")
        if message.source != session.identity_id:
            raise MessageError("source mismatch.")

    # -- framing I/O -------------------------------------------------------

    def _wait_readable(self, conn: socket.socket, session: ConnectionSession) -> bool:
        """Wait until data is available or idle timeout expires."""
        import select

        while not self._stop_event.is_set():
            remaining = IDLE_CONNECTION_TIMEOUT - (self._time() - session.last_activity)
            if remaining <= 0:
                return False
            try:
                r, _, _ = select.select([conn], [], [], min(1.0, remaining))
            except Exception:
                return False
            if r:
                return True
        return False

    def _recv_frame(self, conn: socket.socket, session: ConnectionSession) -> str | None:
        header = self._recv_exact(conn, HEADER_SIZE, session)
        if header is None:
            return None
        (length,) = struct.unpack("!I", header)
        if length <= 0 or length > MAX_FRAME_SIZE:
            return None
        data = self._recv_exact(conn, length, session)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except Exception:
            return None

    def _recv_exact(
        self, conn: socket.socket, n: int, session: ConnectionSession | None = None
    ) -> bytes | None:
        buf = b""
        while len(buf) < n:
            if session is not None:
                if self._time() - session.last_activity > IDLE_CONNECTION_TIMEOUT:
                    return None
            try:
                chunk = conn.recv(n - len(buf))
            except socket.timeout:
                if session is not None and (
                    self._time() - session.last_activity > IDLE_CONNECTION_TIMEOUT
                ):
                    return None
                continue
            except OSError:
                return None
            if not chunk:
                return None
            buf += chunk
            if session is not None:
                session.touch(self._time())
        return buf

    def _send_frame(self, conn: socket.socket, message: Message) -> None:
        text = MessageSerializer.serialize(message)
        payload = text.encode("utf-8")
        if len(payload) == 0 or len(payload) > MAX_FRAME_SIZE:
            raise MessageError("Response frame size invalid.")
        conn.sendall(struct.pack("!I", len(payload)) + payload)


__all__ = [
    "TcpTransport",
    "MAX_FRAME_SIZE",
    "MAX_CONNECTIONS",
    "HEADER_SIZE",
    "TLS_HANDSHAKE_TIMEOUT",
    "IDLE_CONNECTION_TIMEOUT",
    "HANDSHAKE_TYPE",
    "HANDSHAKE_RESPONSE_TYPE",
]
