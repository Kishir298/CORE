"""Human-to-human messaging: account isolation, approval and idempotency."""
import pytest

from core.web.gateway import Gateway

PASSWORD = "test-password-long-enough"


@pytest.fixture()
def gateway(tmp_path):
    app = Gateway(directory=tmp_path)
    yield app
    app.close()


def login(gateway, username="owner"):
    if gateway.accounts.empty():
        gateway.accounts.create(username, PASSWORD, "Owner", first=True)
    status, body, cookie = gateway.dispatch(
        "POST", "/api/login", {"username": username, "password": PASSWORD}, {}
    )
    assert status == 200
    headers = {"Cookie": cookie.split(";", 1)[0], "X-Core-CSRF": body["csrf"]}
    if body["profile"]["role"] == "owner":
        gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, headers)
    return headers, body["profile"]


def make_member(gateway, owner_headers, username="member"):
    gateway.dispatch("POST", "/api/profiles", {"username": username, "password": PASSWORD, "name": username.title()}, owner_headers)
    return login(gateway, username)


def test_approved_accounts_can_exchange_messages(gateway):
    owner, owner_profile = login(gateway)
    member, member_profile = make_member(gateway, owner)

    status, sent, _ = gateway.dispatch(
        "POST", "/api/messages", {"recipient": "member", "body": "hello"}, owner
    )
    assert status == 201
    assert sent["recipient"] == member_profile["id"]

    status, inbox, _ = gateway.dispatch("GET", f"/api/messages?peer={owner_profile['id']}", {}, member)
    assert status == 200
    assert [m["body"] for m in inbox["messages"]] == ["hello"]
    assert inbox["messages"][0]["sender"] == owner_profile["id"]


def test_retry_with_same_client_id_does_not_duplicate(gateway):
    owner, owner_profile = login(gateway)
    member, _ = make_member(gateway, owner)
    payload = {"recipient": "member", "body": "once", "client_id": "client-0001"}

    first = gateway.dispatch("POST", "/api/messages", payload, owner)[1]
    second = gateway.dispatch("POST", "/api/messages", payload, owner)[1]

    assert first["id"] == second["id"]
    inbox = gateway.dispatch("GET", f"/api/messages?peer={owner_profile['id']}", {}, member)[1]
    assert len(inbox["messages"]) == 1


def test_conversations_are_isolated_between_accounts(gateway):
    owner, owner_profile = login(gateway)
    alice, alice_profile = make_member(gateway, owner, "alice")
    bob, bob_profile = make_member(gateway, owner, "bob")

    gateway.dispatch("POST", "/api/messages", {"recipient": "alice", "body": "for alice"}, owner)

    alice_inbox = gateway.dispatch("GET", f"/api/messages?peer={owner_profile['id']}", {}, alice)[1]
    assert [m["body"] for m in alice_inbox["messages"]] == ["for alice"]

    # Bob cannot read a conversation he is not part of.
    bob_view = gateway.dispatch("GET", f"/api/messages?peer={owner_profile['id']}", {}, bob)[1]
    assert bob_view["messages"] == []
    assert gateway.dispatch("GET", "/api/messages", {}, bob)[1]["threads"] == []


def test_pending_accounts_cannot_message_or_be_messaged(gateway):
    owner, _ = login(gateway)
    gateway.dispatch("POST", "/api/register", {"username": "newbie", "password": PASSWORD, "name": "New"}, {})

    with pytest.raises(ValueError):
        gateway.dispatch("POST", "/api/messages", {"recipient": "owner", "body": "hi"}, owner)
    with pytest.raises(PermissionError):
        gateway.dispatch("POST", "/api/messages", {"recipient": "owner", "body": "hi"}, {"Cookie": "core_session=none", "X-Core-CSRF": "x"})

    # A pending account cannot even obtain a session, so it cannot message.
    with pytest.raises(PermissionError):
        gateway.dispatch("POST", "/api/login", {"username": "newbie", "password": PASSWORD}, {})


def test_messaging_grant_no_service_access(gateway):
    owner, _ = login(gateway)
    member, _ = make_member(gateway, owner)
    with pytest.raises(PermissionError):
        gateway.dispatch("GET", "/api/settings", {}, member)
    with pytest.raises(PermissionError):
        gateway.dispatch("POST", "/api/jobs", {"service": "ascs", "prompt": "x"}, member)


def test_read_state_is_recorded_for_the_recipient_only(gateway):
    owner, owner_profile = login(gateway)
    member, member_profile = make_member(gateway, owner)

    sent = gateway.dispatch("POST", "/api/messages", {"recipient": "member", "body": "read me"}, owner)[1]
    gateway.dispatch("GET", f"/api/messages?peer={owner_profile['id']}", {}, member)  # opens thread
    with pytest.raises(ValueError):
        gateway.dispatch("POST", f"/api/messages/{sent['id']}/read", {}, owner)
    assert gateway.dispatch("POST", f"/api/messages/{sent['id']}/read", {}, member)[0] == 200


def test_message_body_is_validated(gateway):
    owner, _ = login(gateway)
    make_member(gateway, owner)
    with pytest.raises(ValueError):
        gateway.dispatch("POST", "/api/messages", {"recipient": "member", "body": "   "}, owner)
    with pytest.raises(ValueError):
        gateway.dispatch("POST", "/api/messages", {"recipient": "owner", "body": "self"}, owner)
    with pytest.raises(ValueError):
        gateway.dispatch("POST", "/api/messages", {"recipient": "nobody", "body": "hi"}, owner)
