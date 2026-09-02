from __future__ import annotations

import socket
import struct
import threading
from pathlib import Path
from typing import Callable

from core.errors import MessageError

from .models import Message
from .serializer import MessageSerializer
from .transport import MessageHandler, Transport


class TcpTransport(Transport):
    """
    TCP message transport for Windows co-hosted deployment.

    For v0.3, TcpTransport provides the same deterministic in-process
    delivery as LocalTransport plus TCP framing for external devices
    (phones, watches, R.O.V.E.R.T.). On the 32GB/1TB Windows laptop it
    binds to ``127.0.0.1`` by default to avoid firewall prompts.
    External binding to ``0.0.0.0`` is available when
    ``network.enabled=true`` and ``communication.host=0.0.0.0`` — this
    exposes the transport on all interfaces and requires a Windows
    firewall exception.

    TLS (v0.3): set ``communication.tls.enabled=true`` with
    ``communication.tls.certfile/keyfile`` to wrap the TCP listener in
    TLS. When TLS is disabled or certs are missing the transport falls
    back to plaintext — legacy clients remain compatible.

    Message framing uses length-prefixed JSON via MessageSerializer so
    identity_id and routing survive the wire. TLS is transport-level only
    and does not change the message format.
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
    ) -> None:
        from threading import RLock

        # Normalize host, preserving 0.0.0.0 for external LAN exposure
        raw_host = (host or "127.0.0.1").strip()
        if raw_host == "":
            raw_host = "127.0.0.1"
        self._host = raw_host
        self._port = int(port) if isinstance(port, int) else 0
        if self._port < 0 or self._port > 65535:
            raise ValueError(f"TCP port out of range: {self._port}")
        self._on_delivery = on_delivery

        # TLS state — plaintext fallback preserves legacy compatibility
        self._use_tls = bool(use_tls)
        self._certfile = Path(certfile) if certfile else None
        self._keyfile = Path(keyfile) if keyfile else None
        self._cafile = Path(cafile) if cafile else None
        self._require_client_cert = bool(require_client_cert)
        self._tls_active = False  # becomes True only after successful context build
        self._ssl_context = None  # type: ignore
        if self._use_tls:
            try:
                self._ssl_context = self._build_ssl_context()
                self._tls_active = True
            except Exception:
                # Defer failure to start — fallback to plaintext with warning
                self._ssl_context = None
                self._tls_active = False

        self._handlers: dict[str, MessageHandler] = {}
        self._lock = RLock()
        self._active = True
        self._messages_sent = 0
        self._messages_received = 0

        # Optional TCP server state
        self._server_socket: socket.socket | None = None
        self._server_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

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
        """Return whether TLS was requested (may be inactive if certs missing)."""
        return self._use_tls

    def _build_ssl_context(self):  # type: ignore
        """Build an SSLContext for the TLS listener."""
        import ssl

        # Validate certfiles exist when TLS is requested
        if self._certfile is not None and not self._certfile.exists():
            raise FileNotFoundError(f"TLS certfile not found: {self._certfile}")
        if self._keyfile is not None and not self._keyfile.exists():
            raise FileNotFoundError(f"TLS keyfile not found: {self._keyfile}")
        if self._cafile is not None and not self._cafile.exists():
            raise FileNotFoundError(f"TLS cafile not found: {self._cafile}")

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # Modern TLS 1.2+ only; fallback to plaintext on failure is handled by caller
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            # Fallback for older Python
            ctx.options |= getattr(ssl, "OP_NO_TLSv1", 0) | getattr(ssl, "OP_NO_TLSv1_1", 0)
        if self._certfile:
            ctx.load_cert_chain(
                certfile=str(self._certfile),
                keyfile=str(self._keyfile) if self._keyfile else None,
            )
        else:
            # No cert — cannot do TLS; caller will treat as fallback
            raise FileNotFoundError("TLS certfile not configured for TLS mode")

        if self._require_client_cert and self._cafile:
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.load_verify_locations(cafile=str(self._cafile))
        elif self._cafile:
            ctx.verify_mode = ssl.CERT_OPTIONAL
            ctx.load_verify_locations(cafile=str(self._cafile))

        return ctx

    def start(self) -> None:
        """Start the transport and optional TCP listener."""

        needs_server = False
        with self._lock:
            if not self._active:
                self._active = True
                self._stop_event.clear()
                needs_server = self._port != 0 and self._server_socket is None
            else:
                # Already active — ensure TCP listener is started if requested port
                # was set post-construction (e.g., config-driven) and server missing.
                # Preserves legacy plaintext fallback: failures keep local-only mode.
                needs_server = self._port != 0 and self._server_socket is None

        # Lazily start TCP listener only when a non-zero port is requested.
        # Failures fall back to local-only mode.
        if needs_server:
            try:
                self._start_server()
            except Exception:
                # TCP is optional; local delivery remains available
                pass

    def stop(self) -> None:
        """Stop the transport while retaining registered endpoints."""

        with self._lock:
            self._active = False
            self._stop_event.set()

        self._stop_server()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._active

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

        # If a real TCP peer is not involved, deliver locally.
        # This keeps deterministic behaviour for single-host Windows deployment
        # while preserving serializer round-trip for future network hops.
        try:
            # Simulate wire serialization for external destinations
            # (no-op for local, but ensures identity_id survives)
            serialized = MessageSerializer.serialize(message)
            deserialized = MessageSerializer.deserialize(serialized)
            # Use deserialized for handler to verify round-trip
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
        # Keep server socket state; caller may restart

    def count(self) -> int:
        return self.endpoint_count()

    # -- TCP server helpers (optional, v0.2 stub) -------------------------

    def _start_server(self) -> None:
        if self._server_socket is not None:
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Windows-friendly socket options
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass

        # Respect 0.0.0.0 for external LAN exposure (requires firewall rule)
        bind_host = self._host if self._host else "127.0.0.1"
        if bind_host == "0.0.0.0":
            # Listening on all interfaces — caller must ensure firewall is configured
            pass
        # Attempt TLS wrapping — fallback to plaintext on failure preserves legacy compatibility
        is_tls = False
        if self._use_tls:
            if self._ssl_context is None:
                try:
                    self._ssl_context = self._build_ssl_context()
                except Exception:
                    # Fallback: plaintext listener so legacy clients still connect
                    self._tls_active = False
                    self._ssl_context = None
                else:
                    self._tls_active = True
            is_tls = self._tls_active and self._ssl_context is not None
        else:
            self._tls_active = False

        sock.bind((bind_host, self._port))
        # Update port if ephemeral (0)
        actual_port = sock.getsockname()[1]
        self._port = actual_port
        sock.listen(5)
        sock.settimeout(1.0)
        self._server_socket = sock

        def _accept_loop() -> None:
            while not self._stop_event.is_set():
                try:
                    conn, _addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                # TLS: wrap the accepted connection so legacy plaintext clients
                # are gracefully rejected without crashing the listener; legacy
                # plaintext fallback listeners (is_tls=False) accept normally.
                if is_tls and self._ssl_context is not None:
                    try:
                        # Wrap with timeout to avoid blocking forever on handshake
                        conn.settimeout(5.0)
                        conn = self._ssl_context.wrap_socket(  # type: ignore
                            conn, server_side=True, do_handshake_on_connect=True
                        )
                    except Exception:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        continue

                threading.Thread(
                    target=self._handle_connection,
                    args=(conn,),
                    daemon=True,
                ).start()

        self._server_thread = threading.Thread(
            target=_accept_loop, daemon=True
        )
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

    def _handle_connection(self, conn: socket.socket) -> None:
        with conn:
            try:
                # Read 4-byte length prefix
                header = self._recv_exact(conn, 4)
                if not header:
                    return
                length = struct.unpack("!I", header)[0]
                if length <= 0 or length > 10 * 1024 * 1024:
                    return
                data = self._recv_exact(conn, length)
                if not data:
                    return
                text = data.decode("utf-8")
                message = MessageSerializer.deserialize(text)
                response = self.send(message)
                if response is not None:
                    resp_text = MessageSerializer.serialize(response)
                    resp_data = resp_text.encode("utf-8")
                    conn.sendall(struct.pack("!I", len(resp_data)) + resp_data)
            except Exception:
                pass

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int) -> bytes | None:
        buf = b""
        while len(buf) < n:
            try:
                chunk = conn.recv(n - len(buf))
            except socket.timeout:
                continue
            if not chunk:
                return None
            buf += chunk
        return buf


__all__ = ["TcpTransport"]
