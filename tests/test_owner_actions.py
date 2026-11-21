"""Owner actions are queued and never applied without a bound owner device."""
from __future__ import annotations

import pytest

from core.web.gateway import Gateway

PASSWORD = "test-password-long-enough"


@pytest.fixture()
def gateway(tmp_path):
    app = Gateway(directory=tmp_path)
    yield app
    app.close()


def login(gateway, username):
    if username == "owner" and gateway.accounts.empty():
        gateway.accounts.create(username, PASSWORD, "Owner", first=True)
    elif username != "owner" and not any(p["username"] == username for p in gateway.accounts.profiles()):
        gateway.accounts.create(username, PASSWORD, username.title())
    status, body, cookie = gateway.dispatch("POST", "/api/login", {
        "username": username, "password": PASSWORD, "remember_device": True,
    }, {})
    assert status == 200
    return {"Cookie": cookie.split(";")[0], "X-Core-CSRF": body["csrf"]}, body["profile"]


def test_member_request_queues_without_applying(gateway):
    owner_headers, _ = login(gateway, "owner")
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    member_headers, member = login(gateway, "member")
    status, body, _ = gateway.dispatch("POST", "/api/owner-actions", {
        "action": "service_grant", "payload": {"profile_id": member["id"], "service": "ascs"},
    }, member_headers)
    assert status == 202
    action = body["action"]
    assert action["status"] == "pending"
    assert gateway.accounts.service_allowed(member["id"], "ascs") is False
    with pytest.raises(PermissionError):
        gateway.dispatch("GET", "/api/owner-actions", {}, member_headers)
    mine = gateway.dispatch("GET", "/api/owner-actions/mine", {}, member_headers)[1]["actions"]
    assert [item["id"] for item in mine] == [action["id"]]


def test_owner_approval_requires_admin_unlock_then_applies(gateway):
    owner_headers, _ = login(gateway, "owner")
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    member_headers, member = login(gateway, "member")
    action = gateway.dispatch("POST", "/api/owner-actions", {
        "action": "service_grant", "payload": {"profile_id": member["id"], "service": "ascs"},
    }, member_headers)[1]["action"]

    plain_owner, _ = login(gateway, "owner")
    with pytest.raises(PermissionError, match="Re-enter"):
        gateway.dispatch("POST", "/api/owner-actions/" + action["id"] + "/approve", {}, plain_owner)
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, plain_owner)
    status, body, _ = gateway.dispatch("POST", "/api/owner-actions/" + action["id"] + "/approve", {}, plain_owner)
    assert status == 200 and body["action"]["status"] == "approved"
    assert gateway.accounts.service_allowed(member["id"], "ascs") is True
    with pytest.raises(ValueError, match="already decided"):
        gateway.dispatch("POST", "/api/owner-actions/" + action["id"] + "/approve", {}, plain_owner)


def test_rejection_and_quota_actions(gateway):
    owner_headers, _ = login(gateway, "owner")
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    member_headers, member = login(gateway, "member")
    reject = gateway.dispatch("POST", "/api/owner-actions", {
        "action": "quota_set", "payload": {"username": "member", "bytes": 8 * 1024 * 1024},
    }, member_headers)[1]["action"]
    status, body, _ = gateway.dispatch("POST", "/api/owner-actions/" + reject["id"] + "/reject", {}, owner_headers)
    assert status == 200 and body["action"]["status"] == "rejected"
    assert gateway.library.quota(member["id"]) != 8 * 1024 * 1024

    quota = gateway.dispatch("POST", "/api/owner-actions", {
        "action": "quota_set", "payload": {"username": "member", "bytes": 16 * 1024 * 1024},
    }, member_headers)[1]["action"]
    status, body, _ = gateway.dispatch("POST", "/api/owner-actions/" + quota["id"] + "/approve", {}, owner_headers)
    assert status == 200 and body["action"]["status"] == "approved"
    assert gateway.library.quota(member["id"]) == 16 * 1024 * 1024


def test_pending_owner_action_queue_is_bounded(gateway):
    owner_headers, _ = login(gateway, "owner")
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    member_headers, member = login(gateway, "member")
    for _ in range(20):
        status, _, _ = gateway.dispatch("POST", "/api/owner-actions", {
            "action": "service_grant", "payload": {"profile_id": member["id"], "service": "ascs"},
        }, member_headers)
        assert status == 202
    with pytest.raises(ValueError, match="Too many pending"):
        gateway.dispatch("POST", "/api/owner-actions", {
            "action": "service_grant", "payload": {"profile_id": member["id"], "service": "ascs"},
        }, member_headers)


def test_claimed_action_resumes_after_crash(gateway):
    owner_headers, owner = login(gateway, "owner")
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    member_headers, member = login(gateway, "member")
    action = gateway.dispatch("POST", "/api/owner-actions", {
        "action": "service_grant", "payload": {"profile_id": member["id"], "service": "ascs"},
    }, member_headers)[1]["action"]

    claimed = gateway.accounts.claim_owner_action(action["id"], owner["id"])
    assert claimed["status"] == "applying"
    assert gateway.accounts.service_allowed(member["id"], "ascs") is False

    status, body, _ = gateway.dispatch("POST", "/api/owner-actions/" + action["id"] + "/approve", {}, owner_headers)
    assert status == 200
    assert body["action"]["status"] == "approved"
    assert gateway.accounts.service_allowed(member["id"], "ascs") is True


def test_claimed_action_cannot_be_taken_by_another_owner(gateway):
    owner_headers, owner = login(gateway, "owner")
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    member_headers, member = login(gateway, "member")
    action = gateway.dispatch("POST", "/api/owner-actions", {
        "action": "service_grant", "payload": {"profile_id": member["id"], "service": "tiviss"},
    }, member_headers)[1]["action"]

    gateway.accounts.claim_owner_action(action["id"], owner["id"])
    with pytest.raises(ValueError, match="another owner"):
        gateway.accounts.claim_owner_action(action["id"], member["id"])
    with pytest.raises(ValueError, match="already being applied"):
        gateway.accounts.decide_owner_action(action["id"], owner["id"], "rejected")


def test_failed_apply_marks_the_action_failed(gateway):
    owner_headers, _ = login(gateway, "owner")
    gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, owner_headers)
    gateway.dispatch("POST", "/api/profiles", {"username": "member", "password": PASSWORD, "name": "Member"}, owner_headers)
    member_headers, member = login(gateway, "member")
    action = gateway.dispatch("POST", "/api/owner-actions", {
        "action": "quota_set", "payload": {"username": "missing-user", "bytes": 1024},
    }, member_headers)[1]["action"]

    with pytest.raises(ValueError, match="Account is unavailable"):
        gateway.dispatch("POST", "/api/owner-actions/" + action["id"] + "/approve", {}, owner_headers)
    stored = gateway.accounts.owner_action(action["id"])
    assert stored["status"] == "failed"
    assert "Account is unavailable" in stored["error"]
    assert gateway.library.quota(member["id"]) != 1024
