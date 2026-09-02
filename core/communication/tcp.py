from __future__ import annotations

import socket
import struct
import threading
from typing import Callable

from core.errors import MessageError

from .models import Message
from .serializer import MessageSerializer
from .transport import MessageHandler, Transport


class TcpTransport(Transport):
    """
    TCP message transport for Windows co-hosted deployment.

    For v0.2, TcpTransport provides the same deterministic in-process
    delivery as LocalTransport plus optional TCP framing for external
    devices (phones, watches, R.O.V.E.R.T.). On the 32GB/1TB Windows
    laptop it binds to ``127.0.0.1`` by default to avoid firewall prompts;
    external binding requires explicit configuration and firewall rules
    (deferred).

    Message framing uses length-prefixed JSON via MessageSerializer so
    identity_id and routing survive the wire.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        on_delivery: Callable[[Message], None] | None = None,
    ) -> None:
        from threading import RLock

        self._host = host if host else "127.0.0.1"
        self._port = int(port) if isinstance(port, int) else 0
        self._on_delivery = on_delivery

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

    def start(self) -> None:
        """Start the transport and optional TCP listener."""

        with self._lock:
            if self._active:
                return
            self._active = True
            self._stop_event.clear()

        # Lazily start TCP listener only when a non-zero port is requested
        # and we are on Windows. Failures fall back to local-only mode.
        if self._port != 0:
            try:
                self._start_server()
            except Exception:
                # TCP is optional for v0.2; local delivery remains available
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

        # Bind to localhost by default to avoid firewall prompts
        bind_host = self._host if self._host not in ("0.0.0.0", "", None) else "127.0.0.1"
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
