import json
import socket
import struct
import threading
from contextlib import suppress

import pytest

from tiviss.integrations.core_tcp import (
    CoreTcpClient,
    DeviceClientError,
    decode_frame,
    encode_frame,
)


def _read_frame(sock):
    header = sock.recv(4)
    if len(header) < 4:
        raise ConnectionError("peer closed")
    (length,) = struct.unpack("!I", header)
    body = b""
    while len(body) < length:
        chunk = sock.recv(length - len(body))
        if not chunk:
            raise ConnectionError("peer closed")
        body += chunk
    return json.loads(body.decode("utf-8"))


def _write_frame(sock, message):
    data = json.dumps(message).encode("utf-8")
    sock.sendall(struct.pack("!I", len(data)) + data)


def test_frame_roundtrip():
    message = {"message_type": "PING", "payload": {"a": 1}}
    assert decode_frame(encode_frame(message)[:4], encode_frame(message)[4:]) == message


def test_frame_rejects_garbage():
    with pytest.raises(DeviceClientError):
        decode_frame(b"\x00\x00", b"")
    with pytest.raises(DeviceClientError):
        decode_frame(struct.pack("!I", 0), b"")
    with pytest.raises(DeviceClientError):
        decode_frame(struct.pack("!I", 3), b"no}")
    with pytest.raises(DeviceClientError):
        decode_frame(struct.pack("!I", 2), b"{}")


def test_encode_rejects_oversize():
    with pytest.raises(DeviceClientError):
        encode_frame(
            {"message_type": "X", "payload": {"blob": "y" * (11 * 1024 * 1024)}}
        )


def test_constructor_validation():
    with pytest.raises(DeviceClientError):
        CoreTcpClient(host="h", port=1, device_id="  ", credential="c")
    with pytest.raises(DeviceClientError):
        CoreTcpClient(host="h", port=1, device_id="d", credential="")
    with pytest.raises(DeviceClientError):
        CoreTcpClient(host="h", port=1, device_id="d", credential="c", timeout_s=0)


def _peer_script(sock, script):
    """Run scripted (request_type -> response dict) peer on a thread."""
    def run():
        try:
            while True:
                try:
                    incoming = _read_frame(sock)
                except (ConnectionError, OSError, ValueError):
                    return
                response = script(incoming)
                if response is None:
                    return
                _write_frame(sock, response)
        finally:
            with suppress(OSError):
                sock.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def _handshake_response():
    return {
        "message_id": "m1",
        "source": "core",
        "destination": "d",
        "message_type": "CORE_HANDSHAKE_RESPONSE",
        "timestamp": "t",
        "request_id": None,
        "payload": {
            "authenticated": True,
            "connection_id": "c-1",
            "session_token": "s-1",
        },
        "identity_id": "d",
    }


def test_handshake_and_register_over_socketpair():
    client_end, peer_end = socket.socketpair()
    client = CoreTcpClient(host="h", port=1, device_id="d", credential="c")
    client._sock = client_end

    def script(incoming):
        if incoming["message_type"] == "CORE_HANDSHAKE":
            assert incoming["payload"]["credential"] == "c"
            return _handshake_response()
        if incoming["message_type"] == "DEVICE_REGISTER":
            assert incoming["payload"]["_session_token"] == "s-1"
            return {
                "message_id": "m2",
                "source": "core",
                "destination": "d",
                "message_type": "DEVICE_REGISTER_RESPONSE",
                "timestamp": "t",
                "request_id": incoming.get("request_id"),
                "payload": {"registered": True},
                "identity_id": "d",
            }
        return None

    _peer_script(peer_end, script)
    # Bypass connect(): drive the post-socket flow manually.
    client._sock = client_end
    # Simulate post-handshake state then register.
    client._session_token = "s-1"
    client._connection_id = "c-1"
    response = client.register(capabilities=["chat"])
    assert response["message_type"] == "DEVICE_REGISTER_RESPONSE"
    assert client.registered is True
    client.close()
    assert client.connected is False


def test_request_id_mismatch_drops_connection():
    client_end, peer_end = socket.socketpair()
    client = CoreTcpClient(host="h", port=1, device_id="d", credential="c")
    client._sock = client_end
    client._session_token = "s-1"
    client._registered = True

    def script(incoming):
        reply = dict(_handshake_response())
        reply.update(
            {
                "message_type": "DEVICE_INFO_RESPONSE",
                "request_id": "someone-elses-id",
                "payload": {},
            }
        )
        return reply

    _peer_script(peer_end, script)
    with pytest.raises(DeviceClientError, match="correlation mismatch"):
        client.request("core", "DEVICE_INFO", {"device_id": "d"})
    assert client.connected is False


def test_host_error_raises():
    client_end, peer_end = socket.socketpair()
    client = CoreTcpClient(host="h", port=1, device_id="d", credential="c")
    client._sock = client_end
    client._session_token = "s-1"
    client._registered = True

    def script(incoming):
        return {
            "message_id": "m9",
            "source": "core",
            "destination": "d",
            "message_type": "DEVICE_ERROR",
            "timestamp": "t",
            "request_id": incoming.get("request_id"),
            "payload": {"error": "DEVICE_NOT_FOUND", "message": "nope"},
            "identity_id": "d",
        }

    _peer_script(peer_end, script)
    with pytest.raises(DeviceClientError, match="DEVICE_NOT_FOUND"):
        client.request("core", "DEVICE_INFO", {})
    client.close()


def test_auth_rejected_clears_state(monkeypatch):
    client_end, peer_end = socket.socketpair()
    monkeypatch.setattr(
        "tiviss.integrations.core_tcp.socket.create_connection",
        lambda *args, **kwargs: client_end,
    )

    def script(incoming):
        reply = _handshake_response()
        reply["payload"] = {"authenticated": False}
        _write_frame(peer_end, reply)

    thread = threading.Thread(
        target=lambda: script(_read_frame(peer_end)), daemon=True
    )
    thread.start()
    client = CoreTcpClient(
        host="h", port=1, device_id="d", credential="bad", use_tls=False
    )
    with pytest.raises(DeviceClientError, match="authentication rejected"):
        client.connect()
    assert client.connected is False
    assert client.registered is False
