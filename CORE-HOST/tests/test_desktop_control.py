"""Desktop control-channel contracts: devices, renewal, tickets and idempotency."""
import queue
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.web.gateway import Gateway

PASSWORD = "test-password-long-enough"


@pytest.fixture()
def gateway(tmp_path):
    app = Gateway(directory=tmp_path)
    yield app
    app.close()


def login(gateway, username="owner", remember=True):
    if gateway.accounts.empty():
        gateway.accounts.create(username, PASSWORD, "Owner", first=True)
    status, body, cookie = gateway.dispatch("POST", "/api/login", {
        "username": username, "password": PASSWORD, "remember_device": remember,
        "device_name": "Test desktop", "device_type": "desktop", "platform": "macOS",
    }, {})
    assert status == 200
    headers = {"Cookie": cookie.split(";", 1)[0], "X-Core-CSRF": body["csrf"]}
    return headers, body


def test_health_advertises_desktop_and_event_capabilities(gateway):
    health = gateway.dispatch("GET", "/api/health", {}, {})[1]
    assert health["ws"] is True
    assert health["version"]
    for capability in ("ws_ticket_v1", "session_renewal_v1", "device_credentials_v1", "job_idempotency_v1"):
        assert capability in health["capabilities"]


def test_login_issues_a_revocable_device_credential(gateway):
    headers, body = login(gateway)
    credential = body["device_credential"]
    assert body["device"]["device_name"] == "Test desktop"
    status, result, cookie = gateway.dispatch("POST", "/api/login/device", {"credential": credential}, {})
    assert status == 200 and result["profile"]["username"] == "owner" and cookie
    device_id = body["device"]["device_id"]
    gateway.dispatch("POST", f"/api/devices/{device_id}/revoke", {}, headers)
    with pytest.raises(PermissionError):
        gateway.dispatch("POST", "/api/login/device", {"credential": credential}, {})


def test_member_cannot_revoke_another_accounts_device(gateway):
    owner_headers, owner_body = login(gateway)
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    member_headers, _ = login(gateway, "member", remember=False)
    with pytest.raises(ValueError):
        gateway.dispatch("POST", f"/api/devices/{owner_body['device']['device_id']}/revoke", {}, member_headers)


def test_device_listing_is_account_scoped_and_owner_can_see_all(gateway):
    headers, _ = login(gateway)
    devices = gateway.dispatch("GET", "/api/devices", {}, headers)[1]["devices"]
    assert len(devices) == 1 and devices[0]["status"] == "active"
    owner_headers = headers
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    login(gateway, "member")
    assert len(gateway.dispatch("GET", "/api/devices?all=1", {}, owner_headers)[1]["devices"]) == 2


def test_session_renewal_extends_without_losing_csrf(gateway):
    headers, body = login(gateway)
    renewed = gateway.dispatch("POST", "/api/session/renew", {}, headers)[1]
    assert renewed["expires_in"] == 43200
    assert renewed["csrf"] == body["csrf"]
    assert gateway.dispatch("GET", "/api/me", {}, headers)[1]["profile"]["id"] == body["profile"]["id"]


def test_ws_ticket_is_single_use_and_requires_a_session(gateway):
    headers, _ = login(gateway)
    ticket = gateway.dispatch("POST", "/api/ws-ticket", {}, headers)[1]["ticket"]
    assert gateway.tickets.consume(ticket)
    assert gateway.tickets.consume(ticket) is None
    with pytest.raises(PermissionError):
        gateway.dispatch("POST", "/api/ws-ticket", {}, {})


def test_job_idempotency_reuses_the_started_job(gateway):
    headers, _ = login(gateway)
    view = {"id": "j", "status": "running", "events": []}
    fake = SimpleNamespace(view=lambda: view)
    with patch.object(gateway.services, "start", return_value={"id": "j"}) as start, \
         patch.object(gateway.services, "get", return_value=fake):
        first = gateway.dispatch("POST", "/api/jobs", {"service": "asis", "prompt": "hello"}, {**headers, "Idempotency-Key": "key-12345678"})
        second = gateway.dispatch("POST", "/api/jobs", {"service": "asis", "prompt": "hello"}, {**headers, "Idempotency-Key": "key-12345678"})
    assert first[0] == second[0] == 202
    assert first[1] == {"id": "j"}
    assert second[1] == view
    assert start.call_count == 1


def test_revoked_device_publishes_a_control_event(gateway):
    headers, body = login(gateway)
    channel = gateway.events.subscribe(body["profile"]["id"])
    gateway.dispatch("POST", f"/api/devices/{body['device']['device_id']}/revoke", {}, headers)
    event = channel.get(timeout=2)
    assert event["type"] == "session.revoked" and event["reason"] == "device_revoked"
    gateway.events.unsubscribe(body["profile"]["id"], channel)


def test_password_change_revokes_devices(gateway):
    _headers, body = login(gateway)
    gateway.accounts.change_password(body["profile"]["id"], PASSWORD, "new-password-long-enough")
    with pytest.raises(PermissionError):
        gateway.accounts.device_login(body["device_credential"])


def test_ticket_store_expires_and_prunes(monkeypatch):
    from core.web.events import TicketStore

    store = TicketStore(ttl=0.01)
    ticket = store.issue("a" * 32)["ticket"]
    assert store.consume(ticket) == "a" * 32
    stale = store.issue("b" * 32)["ticket"]
    import time
    time.sleep(0.02)
    assert store.consume(stale) is None


def test_websocket_channel_delivers_only_ticketed_events(gateway):
    import json
    from core.web.ws import WebSocketServer
    from websockets.sync.client import connect

    server = WebSocketServer(gateway.events, gateway.tickets, port=0)
    assert server.start()
    try:
        port = server._server.socket.getsockname()[1]
        ticket = gateway.tickets.issue("a" * 32)["ticket"]
        with connect(f"ws://127.0.0.1:{port}/api/ws?ticket={ticket}", open_timeout=3) as socket:
            assert json.loads(socket.recv(timeout=3))["type"] == "channel.ready"
            gateway.events.publish(["b" * 32], {"type": "not-for-you"})
            gateway.events.publish(["a" * 32], {"type": "hello"})
            assert json.loads(socket.recv(timeout=3))["type"] == "hello"
    finally:
        server.stop()
