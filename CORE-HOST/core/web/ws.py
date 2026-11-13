"""Optional loopback WebSocket endpoint for CORE event delivery.

Caddy terminates TLS and proxies /api/ws to this loopback listener. The
handshake uses a short-lived, single-use ticket issued over the authenticated
HTTPS API.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from urllib.parse import parse_qs, urlparse

try:
    from websockets.sync.server import serve as _serve
except Exception:  # dependency absent: polling remains fully supported
    _serve = None

_LOG = logging.getLogger(__name__)


def available() -> bool:
    return _serve is not None


class WebSocketServer:
    def __init__(self, bus, tickets, host="127.0.0.1", port=8781):
        self.bus = bus
        self.tickets = tickets
        self.host = host
        self.port = int(port)
        self._server = None
        self._thread = None

    def start(self) -> bool:
        if _serve is None:
            _LOG.warning("websockets is not installed; event channel stays disabled")
            return False
        try:
            self._server = _serve(
                self._handle, self.host, self.port,
                ping_interval=20, ping_timeout=20, max_size=65536, close_timeout=5,
            )
        except Exception:
            _LOG.exception("Could not start the event channel on %s:%s", self.host, self.port)
            return False
        self._thread = threading.Thread(target=self._server.serve_forever, name="core-events", daemon=True)
        self._thread.start()
        return True

    def _handle(self, connection):
        request = getattr(connection, "request", None)
        path = getattr(request, "path", "") or getattr(connection, "path", "") or ""
        try:
            user_id = self.tickets.consume(parse_qs(urlparse(path).query).get("ticket", [""])[0])
        except Exception:
            user_id = None
        if not user_id:
            try:
                connection.close(code=1008, reason="invalid ticket")
            except Exception:
                pass
            return
        channel = self.bus.subscribe(user_id)
        try:
            connection.send(json.dumps({"type": "channel.ready"}))
            while True:
                try:
                    event = channel.get(timeout=10)
                except queue.Empty:
                    continue
                connection.send(json.dumps(event, separators=(",", ":")))
        except Exception:
            pass
        finally:
            self.bus.unsubscribe(user_id, channel)
            try:
                connection.close()
            except Exception:
                pass

    def stop(self):
        if self._server is not None:
            try:
                self._server.close()
            except Exception:
                _LOG.exception("Event channel shutdown failed")
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
