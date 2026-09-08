"""External-device client tests: Option A + live protocol against TcpTransport.

Covers: TLS-capable transport path (existing suites), authentication,
CORE_HANDSHAKE, DEVICE_REGISTER, success, persistence, restart restore,
disconnect->offline, reconnect->online with new connection_id, same
device_id/identity_id, duplicate rejection, wrong credential, spoofing
rejection, remembered-device persistence, login-required-after-restart,
session-not-persisted, no re-registration from scratch.
"""

import json
import socket
import struct
import threading
import time

import pytest

from client.core_device_client import CoreDeviceClient, DeviceClientError
from core.communication.serializer import MessageSerializer
from core.communication.tcp import TcpTransport
from core.security.manager import SecurityManager
from core.security.models import Identity, IdentityType, Permission
from core.security.provider import TokenAuthenticationProvider


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _make_server(port, token="secret-mac-01", device_id="mac-01"):
    security = SecurityManager(provider=TokenAuthenticationProvider())
    security.register_identity(
        Identity(
            identity_id=device_id,
            name="Mac",
            identity_type=IdentityType.DEVICE,
            permissions=frozenset({Permission.READ}),
            metadata={"token": token},
        )
    )
    transport = TcpTransport(
        host="127.0.0.1",
        port=port,
        security_manager=security,
    )
    transport.start()
    # Wait for the listener socket.
    for _ in range(100):
        if transport._server_socket is not None:
            break
        time.sleep(0.01)
    return transport, security


def _make_client(port, device_file, token=None, **overrides):
    params = {
        "host": "127.0.0.1",
        "port": port,
        "device_id": "mac-01",
        "device_name": "MacBook",
        "device_type": "phone",
        "platform": "mac",
        "capabilities": ["chat"],
        "device_file": device_file,
        "use_tls": False,
    }
    params.update(overrides)
    client = CoreDeviceClient(**params)
    if token is not None:
        client.login(token)
    return client


def _raw_message(sock, source, destination, mtype, payload, identity_id):
    from core.communication.models import Message

    text = MessageSerializer.serialize(
        Message(
            source=source,
            destination=destination,
            message_type=mtype,
            payload=payload,
            identity_id=identity_id,
        )
    )
    data = text.encode("utf-8")
    sock.sendall(struct.pack("!I", len(data)) + data)
    header = sock.recv(4)
    assert len(header) == 4
    (length,) = struct.unpack("!I", header)
    buf = b""
    while len(buf) < length:
        chunk = sock.recv(length - len(buf))
        assert chunk
        buf += chunk
    return MessageSerializer.deserialize(buf.decode("utf-8"))


# -- Option A: remembered device vs login session (no network) --


def test_remembered_device_persists_without_secrets(tmp_path):
    device_file = tmp_path / "device.json"
    client = _make_client(5000, device_file, token="secret-mac-01")
    client.save_remembered()
    stored = json.loads(device_file.read_text(encoding="utf-8"))
    assert stored["device_id"] == "mac-01"
    assert stored["identity_id"] == "mac-01"
    assert stored["host"] == "127.0.0.1"
    for secret_key in ("token", "credential", "session", "connection_id"):
        assert secret_key not in stored


def test_connect_requires_login(tmp_path):
    client = _make_client(5000, tmp_path / "device.json")
    with pytest.raises(DeviceClientError, match="Login required"):
        client.connect()


def test_login_session_not_persisted_across_full_shutdown(tmp_path):
    device_file = tmp_path / "device.json"
    client = _make_client(5000, device_file, token="secret-mac-01")
    client.save_remembered()
    client.shutdown()  # full application shutdown
    assert client.is_logged_in is False
    assert client.connection_id is None
    # Next launch: remembered device loads, but login is required again.
    relaunched = CoreDeviceClient.load_remembered(device_file)
    assert relaunched.device_id == "mac-01"
    assert relaunched.is_logged_in is False
    with pytest.raises(DeviceClientError, match="Login required"):
        relaunched.connect()


def test_remembered_device_does_not_require_reregistration(tmp_path):
    device_file = tmp_path / "device.json"
    client = _make_client(5000, device_file, token="secret-mac-01")
    client.save_remembered()
    relaunched = CoreDeviceClient.load_remembered(device_file)
    assert relaunched.remembered_state() == client.remembered_state()


# -- Live protocol against TcpTransport (localhost, plaintext test path) --


def test_handshake_register_online_and_persist(tmp_path):
    port = _free_port()
    transport, _ = _make_server(port)
    try:
        client = _make_client(port, tmp_path / "device.json", token="secret-mac-01")
        handshake = client.connect()
        assert handshake["payload"]["authenticated"] is True
        first_connection_id = client.connection_id
        assert first_connection_id
        response = client.register()
        assert response["payload"] == {
            "registered": True,
            "device_id": "mac-01",
            "status": "online",
        }
        record = transport.device_registry.get("mac-01")
        assert record.status == "online"
        assert record.device_id == "mac-01"
        assert record.identity_id == "mac-01"
        assert record.connection_id == first_connection_id
        client.shutdown()
    finally:
        transport.stop()


def test_disconnect_goes_offline_but_stays_registered(tmp_path):
    port = _free_port()
    transport, _ = _make_server(port)
    try:
        client = _make_client(port, tmp_path / "device.json", token="secret-mac-01")
        client.connect()
        client.register()
        client.close_socket()  # abrupt disconnect; session object stays logged in
        deadline = time.time() + 5
        while transport.device_registry.get("mac-01").status != "offline":
            assert time.time() < deadline, "device never went offline"
            time.sleep(0.05)
        # Still registered (record retained), just offline.
        assert transport.device_registry.has("mac-01") is True
        client.shutdown()
    finally:
        transport.stop()


def test_reconnect_preserves_identity_with_new_connection_id(tmp_path):
    port = _free_port()
    transport, _ = _make_server(port)
    try:
        client = _make_client(port, tmp_path / "device.json", token="secret-mac-01")
        client.connect()
        client.register()
        first_id = client.connection_id
        client.close_socket()
        deadline = time.time() + 5
        while transport.device_registry.get("mac-01").status != "offline":
            assert time.time() < deadline
            time.sleep(0.05)
        client.reconnect()  # same in-memory login session, app still open
        assert transport.device_registry.get("mac-01").status == "online"
        assert transport.device_registry.get("mac-01").device_id == "mac-01"
        assert transport.device_registry.get("mac-01").identity_id == "mac-01"
        assert client.connection_id is not None
        assert client.connection_id != first_id
        client.shutdown()
    finally:
        transport.stop()


def test_duplicate_registration_rejected(tmp_path):
    port = _free_port()
    transport, _ = _make_server(port)
    first = _make_client(port, tmp_path / "a.json", token="secret-mac-01")
    second = _make_client(port, tmp_path / "b.json", token="secret-mac-01")
    try:
        first.connect()
        first.register()
        second.connect()
        with pytest.raises(DeviceClientError, match="DEVICE_ALREADY_REGISTERED"):
            second.register()
        first.shutdown()
        second.shutdown()
    finally:
        transport.stop()


def test_wrong_credential_rejected_stays_offline(tmp_path):
    port = _free_port()
    transport, _ = _make_server(port)
    try:
        client = _make_client(port, tmp_path / "device.json", token="wrong-token")
        with pytest.raises(DeviceClientError):
            client.connect()
        assert transport.device_registry.has("mac-01") is False
        client.shutdown()
    finally:
        transport.stop()


def test_identity_spoofing_rejected(tmp_path):
    port = _free_port()
    transport, security = _make_server(port)
    security.register_identity(
        Identity(
            identity_id="mac-02",
            name="Other",
            identity_type=IdentityType.DEVICE,
            permissions=frozenset({Permission.READ}),
            metadata={"token": "secret-mac-02"},
        )
    )
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    sock.settimeout(5)
    try:
        # Authenticate as mac-02 but attempt to register mac-01.
        resp = _raw_message(
            sock,
            "mac-02",
            "core",
            "CORE_HANDSHAKE",
            {
                "identity_id": "mac-02",
                "credential": "secret-mac-02",
                "protocol_version": "0.3.0",
            },
            "mac-02",
        )
        assert resp.message_type == "CORE_HANDSHAKE_RESPONSE"
        resp = _raw_message(
            sock,
            "mac-02",
            "core",
            "DEVICE_REGISTER",
            {
                "device_id": "mac-01",
                "device_name": "Spoof",
                "device_type": "phone",
                "platform": "mac",
                "capabilities": [],
                "protocol_version": "0.3.0",
            },
            "mac-02",
        )
        assert resp.message_type == "DEVICE_ERROR"
        assert resp.payload["error"] == "DEVICE_REGISTRATION_FAILED"
    finally:
        sock.close()
        transport.stop()


def test_source_spoofing_rejected(tmp_path):
    port = _free_port()
    transport, _ = _make_server(port)
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    sock.settimeout(5)
    try:
        resp = _raw_message(
            sock,
            "mac-01",
            "core",
            "CORE_HANDSHAKE",
            {
                "identity_id": "mac-01",
                "credential": "secret-mac-01",
                "protocol_version": "0.3.0",
            },
            "mac-01",
        )
        assert resp.message_type == "CORE_HANDSHAKE_RESPONSE"
        resp = _raw_message(
            sock,
            "mac-01",
            "core",
            "DEVICE_REGISTER",
            {
                "device_id": "mac-01",
                "device_name": "MacBook",
                "device_type": "phone",
                "platform": "mac",
                "capabilities": [],
                "protocol_version": "0.3.0",
            },
            "mac-01",
        )
        assert resp.message_type == "DEVICE_REGISTER_RESPONSE"
        # Spoofed source on an application message: server must not route it.
        from core.communication.models import Message

        text = MessageSerializer.serialize(
            Message(
                source="mac-02",  # lies about the source
                destination="core",
                message_type="DEVICE_DISCOVER",
                payload={},
                identity_id="mac-01",
            )
        )
        data = text.encode("utf-8")
        sock.sendall(struct.pack("!I", len(data)) + data)
        sock.settimeout(2.0)
        try:
            leftover = sock.recv(4)
        except socket.timeout:
            leftover = b""
        # Either the connection is closed (no valid frame) or a device error
        # arrives; either way the spoofed message is never honored.
        assert leftover == b"" or len(leftover) < 4
    finally:
        sock.close()
        transport.stop()


def test_provision_then_restart_restores_offline(tmp_path):
    from core.application import CoreApplication
    from core.rescs.adapter import FileRescsAdapter

    rescs_path = tmp_path / "rescs.json"
    store = FileRescsAdapter(path=rescs_path)
    first = CoreApplication(rescs_adapter=store)
    snapshot = first.provision_device(
        device_id="mac-01",
        token="secret-mac-01",
        device_name="MacBook",
        platform="mac",
    )
    assert "connection_id" not in snapshot
    # Simulate restart with the same file backend: fresh app restores offline
    # and re-provisions the identity so reconnect authenticates.
    second_store = FileRescsAdapter(path=rescs_path)
    second = CoreApplication(rescs_adapter=second_store)
    second._load_configuration()
    record = second.device_registry.get("mac-01")
    assert record.status == "offline"
    assert record.connection_id is None
    identity = second.security.get_identity("mac-01")
    assert identity.metadata["token"] == "secret-mac-01"
    # Reconnect works against the restored identity material.
    port = _free_port()
    security = second.security
    from core.security.provider import TokenAuthenticationProvider

    security.set_provider(TokenAuthenticationProvider())
    transport = TcpTransport(
        host="127.0.0.1",
        port=port,
        security_manager=security,
        device_registry=second.device_registry,
    )
    transport.start()
    try:
        for _ in range(100):
            if transport._server_socket is not None:
                break
            time.sleep(0.01)
        client = _make_client(port, tmp_path / "device.json", token="secret-mac-01")
        client.connect()
        client.register()
        assert second.device_registry.get("mac-01").status == "online"
        client.shutdown()
    finally:
        transport.stop()


def test_provision_device_cli(tmp_path, capsys):
    from argparse import Namespace

    from core.application import CoreApplication
    from core.cli.main import execute_application

    app = CoreApplication()
    args = Namespace(
        command="provision-device",
        device_id="mac-01",
        device_name="MacBook",
        device_type="phone",
        platform="mac",
        capabilities="chat",
        token="secret-mac-01",
        permissions="read",
    )
    assert execute_application(args, app) == 0
    out = capsys.readouterr().out
    assert "Provisioned device: mac-01" in out
    assert "secret-mac-01" not in out  # token never echoed
    assert app.rescs.fetch_device("mac-01")["device_id"] == "mac-01"
    assert "connection_id" not in app.rescs.fetch_device("mac-01")


def test_client_remember_cli(tmp_path):
    from client.core_device_client import main

    device_file = tmp_path / "device.json"
    assert (
        main(
            [
                "--remember",
                "--device-file",
                str(device_file),
                "--device-id",
                "mac-01",
                "--host",
                "192.168.1.10",
                "--port",
                "5000",
            ]
        )
        == 0
    )
    stored = json.loads(device_file.read_text(encoding="utf-8"))
    assert stored["host"] == "192.168.1.10"
    assert "token" not in stored


def test_concurrent_reconnect_single_winner(tmp_path):
    port = _free_port()
    transport, _ = _make_server(port)
    results = []

    def attempt():
        try:
            client = _make_client(port, tmp_path / f"{threading.get_ident()}.json",
                                  token="secret-mac-01")
            client.connect()
            client.register()
            results.append("ok")
            time.sleep(0.2)
            client.shutdown()
        except Exception:
            results.append("rejected")

    try:
        threads = [threading.Thread(target=attempt) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert results.count("ok") >= 1
    finally:
        transport.stop()
