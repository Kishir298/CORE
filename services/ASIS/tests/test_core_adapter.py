"""Adapter boundary: real adapter over injected device clients, redaction, limits."""

from __future__ import annotations

import json

import pytest

from asis.integrations.core.adapter import RealCoreAdapter
from asis.integrations.core.client import CoreResponse, ServiceRequest
from asis.integrations.core.errors import CoreProtocolError, CoreUnavailable
from asis.integrations.core.mock import MockCoreAdapter
from asis.integrations.core.models import CoreConnectionState
from asis.integrations.core.protocol import (
    MAX_RESULT_CHARS,
    contains_secret_keys,
    normalize_result,
    redact,
    validate_envelope,
)


class FakeDevice:
    """Minimal CORE-CLIENT surface double (no network, no host imports)."""

    def __init__(self, **kw):
        self.kw = kw
        self.credential = None
        self.connected = False
        self.registered = False
        self.shut_down = False

    def login(self, credential):
        if not credential or not credential.strip():
            raise ValueError("Login required")
        self.credential = credential

    def connect(self):
        self.connected = True
        return {"message_type": "CORE_HANDSHAKE_RESPONSE"}

    def register(self):
        self.registered = True
        return {"message_type": "DEVICE_REGISTER_RESPONSE"}

    @property
    def is_connected(self):
        return self.connected and self.registered

    def remembered_state(self):
        return {
            "device_id": self.kw.get("device_id", "asis-01"),
            "join_name": "ASIS-asis-01",
            "device_name": "ASIS",
            "platform": "mac",
            "capabilities": ["inference"],
        }

    @property
    def lease_state(self):
        return "ONLINE" if self.is_connected else "DISCONNECTED"

    def request(self, destination, message_type, payload=None, timeout=None):
        assert self.is_connected, "not connected"
        assert payload is not None and "_session_token" not in payload
        return {
            "message_id": "m-1",
            "source": "core",
            "destination": destination,
            "message_type": message_type + "_RESPONSE",
            "timestamp": "now",
            "request_id": "r-1",
            "payload": {"echo": dict(payload or {})},
            "identity_id": "core",
        }

    def service_request(self, service_id, operation, params=None):
        return {
            "message_id": "m-2",
            "source": "core",
            "destination": f"service:{service_id}",
            "message_type": "SERVICE_RESPONSE",
            "timestamp": "now",
            "request_id": "r-2",
            "payload": {
                "service_id": service_id,
                "operation": operation,
                "result": dict(params or {}),
                "success": True,
            },
            "identity_id": "core",
        }

    def data_request(
        self, request_type, payload=None, destination="core", timeout=None
    ):
        return {
            "message_id": "m-3",
            "source": "core",
            "destination": destination,
            "message_type": "DATA_RESPONSE",
            "timestamp": "now",
            "request_id": "r-3",
            "payload": {"request_type": request_type},
            "identity_id": "core",
        }

    def shutdown(self):
        self.shut_down = True
        self.connected = False
        self.registered = False


def _adapter(**over):
    kw = {"device_id": "asis-01"}
    kw.update(over)
    made = {}

    def factory(**fkw):
        made.update(fkw)
        return FakeDevice(**fkw)

    return RealCoreAdapter(client_factory=factory, **kw), made


def test_connect_requires_credential():
    adapter, _ = _adapter()
    resp = adapter.connect(None)
    assert resp.ok is False
    assert "credential" in (resp.error or "").lower()
    assert adapter.is_connected() is False


def test_connect_disconnect_lifecycle():
    adapter, made = _adapter(host="10.0.0.5", port=5000)
    assert adapter.connection_state == CoreConnectionState.DISCONNECTED
    resp = adapter.connect("provision-secret")
    assert resp.ok is True
    assert made["host"] == "10.0.0.5"
    assert adapter.is_connected() is True
    assert adapter.connection_state == CoreConnectionState.CONNECTED
    status = adapter.device_status()
    assert status.ok is True
    assert status.data["device_id"] == "asis-01"
    adapter.disconnect()
    assert adapter.is_connected() is False
    assert adapter.connection_state == CoreConnectionState.DISCONNECTED


def test_missing_client_package_is_unavailable():
    def bad_factory(**kw):
        raise CoreUnavailable("no package")

    adapter = RealCoreAdapter(client_factory=bad_factory)
    resp = adapter.connect("cred")
    assert resp.ok is False
    assert "CORE_UNAVAILABLE" in (resp.error or "")


def test_send_request_offline_fails_cleanly():
    adapter, _ = _adapter()
    resp = adapter.send_request("core", "DEVICE_DISCOVER", {})
    assert resp.ok is False
    assert "CORE_UNAVAILABLE" in (resp.error or "")


def test_send_request_roundtrip_and_alias():
    adapter, _ = _adapter()
    adapter.connect("cred")
    resp = adapter.send_request("core", "DEVICE_DISCOVER", {"a": 1})
    assert resp.ok is True
    assert "echo" in resp.data
    alias = adapter.request("core", "DEVICE_DISCOVER", {})
    assert alias.ok is True


def test_request_service_prefers_device_service_api():
    adapter, _ = _adapter()
    adapter.connect("cred")
    resp = adapter.request_service(ServiceRequest(service="health", operation="status"))
    assert resp.ok is True
    assert resp.data["service_id"] == "health"


def test_credential_never_in_results_or_status():
    adapter, _ = _adapter()
    adapter.connect("super-secret-cred")
    resp = adapter.send_request("core", "DEVICE_DISCOVER", {})
    assert "super-secret-cred" not in json.dumps(resp.data)
    assert not contains_secret_keys(resp.data)
    health = adapter.get_health()
    assert "super-secret-cred" not in json.dumps(health)


def test_redact_and_truncate():
    dirty = {"session_token": "abc", "nested": {"credential": "x"}, "ok": 1}
    cleaned = redact(dirty)
    assert cleaned["session_token"] == "***REDACTED***"
    assert cleaned["nested"]["credential"] == "***REDACTED***"
    big = {"blob": "x" * (MAX_RESULT_CHARS + 100)}
    out = normalize_result(big)
    assert out["truncated"] is True
    assert len(out["preview"]) <= MAX_RESULT_CHARS


def test_validate_envelope_rejects_bad_shapes():
    with pytest.raises(CoreProtocolError):
        validate_envelope({"nope": True})
    with pytest.raises(CoreProtocolError):
        validate_envelope({"message_type": "", "payload": {}})


def test_no_host_imports_in_adapter_surface():
    import pathlib

    root = (
        pathlib.Path(__file__).resolve().parents[1] / "asis" / "integrations" / "core"
    )
    forbidden = ("from core.communication", "from core.", "import core.")
    for path in root.glob("*.py"):
        text = path.read_text()
        for marker in forbidden:
            assert (
                marker not in text
            ), f"{path.name} must not import CORE-HOST ({marker})"


def test_mock_standalone_path():
    mock = MockCoreAdapter()
    assert mock.is_connected() is False
    assert mock.connect().ok is True
    assert mock.send_request("core", "DEVICE_DISCOVER", {}).ok is True
    mock.disconnect()
    assert mock.send_request("core", "DEVICE_DISCOVER", {}).ok is False


def test_legacy_surface_never_claims_fake_support():
    adapter, _ = _adapter()
    adapter.connect("cred")
    resp = adapter.get_resource("notes")
    assert isinstance(resp, CoreResponse)


class _BadEnvelopeDevice(FakeDevice):
    def __init__(self, payload, **kw):
        super().__init__(**kw)
        self._payload = payload

    def request(self, destination, message_type, payload=None, timeout=None):
        assert self.is_connected
        return self._payload


def _bad_adapter(payload):
    def factory(**fkw):
        device = _BadEnvelopeDevice(payload, **fkw)
        device.login("cred")
        device.connect()
        device.register()
        return device

    adapter = RealCoreAdapter(client_factory=factory, device_id="asis-01")
    assert adapter.connect("cred").ok is True
    return adapter


def test_malformed_response_is_structured_error():
    adapter = _bad_adapter({"bogus": True})
    resp = adapter.send_request("core", "DEVICE_DISCOVER", {})
    assert resp.ok is False
    assert "CORE_PROTOCOL_ERROR" in (resp.error or "")
    adapter.disconnect()


def test_oversized_response_is_bounded():
    from asis.integrations.core.protocol import MAX_RESULT_CHARS

    adapter = _bad_adapter(
        {
            "message_id": "m",
            "source": "core",
            "destination": "mac-01",
            "message_type": "DEVICE_DISCOVER_RESPONSE",
            "timestamp": "now",
            "request_id": "r",
            "payload": {"blob": "x" * (MAX_RESULT_CHARS + 500)},
            "identity_id": "core",
        }
    )
    resp = adapter.send_request("core", "DEVICE_DISCOVER", {})
    assert resp.ok is True
    assert resp.data.get("truncated") is True
    adapter.disconnect()
