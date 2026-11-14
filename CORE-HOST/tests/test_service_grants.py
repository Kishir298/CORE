"""Per-profile service grants replace owner-role service gates."""
import sqlite3
from unittest.mock import patch

import pytest

from core.web.accounts import Accounts
from core.web.gateway import Gateway
from core.web.services import CATALOG

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
        "POST", "/api/login", {"username": username, "password": PASSWORD}, {})
    assert status == 200
    headers = {"Cookie": cookie.split(";", 1)[0], "X-Core-CSRF": body["csrf"]}
    if body["profile"]["role"] == "owner":
        gateway.dispatch("POST", "/api/reauth", {"password": PASSWORD}, headers)
    return headers, body["profile"]


def make_member(gateway, owner_headers, username="member"):
    status, profile, _ = gateway.dispatch("POST", "/api/profiles", {
        "username": username, "password": PASSWORD, "name": username.title()}, owner_headers)
    assert status == 201
    return profile


def catalog_by_id(gateway, headers):
    return {row["id"]: row for row in gateway.dispatch("GET", "/api/services", {}, headers)[1]["services"]}


def test_owner_has_implicit_access_to_every_service(gateway):
    headers, owner = login(gateway)
    assert all(gateway.accounts.service_allowed(owner["id"], service) for service in CATALOG)
    services = catalog_by_id(gateway, headers)
    assert set(services) == set(CATALOG)
    assert all(row["allowed"] for row in services.values())
    grants = gateway.dispatch("GET", "/api/service-grants", {}, headers)[1]["grants"]
    entry = next(row for row in grants if row["profile_id"] == owner["id"])
    assert set(entry["services"]) == set(CATALOG)
    assert gateway.dispatch("DELETE", f"/api/profiles/{owner['id']}/service-grants/ascs", {}, headers)[0] == 200
    assert gateway.accounts.service_allowed(owner["id"], "ascs")


def test_member_defaults_to_asis_only(gateway):
    owner_headers, _ = login(gateway)
    member = make_member(gateway, owner_headers)
    member_headers, member_profile = login(gateway, "member")
    assert gateway.accounts.service_grants(member["id"]) == ["asis"]
    assert gateway.accounts.service_allowed(member["id"], "asis")
    assert not gateway.accounts.service_allowed(member["id"], "ascs")
    services = catalog_by_id(gateway, member_headers)
    assert services["asis"]["allowed"] is True
    assert services["ascs"]["allowed"] is False
    assert services["tiviss"]["allowed"] is False
    with pytest.raises(PermissionError):
        gateway.services.command("ascs", member_profile, "hello", "plan")
    with patch.object(gateway.services, "command") as command:
        with pytest.raises(PermissionError):
            gateway.dispatch("POST", "/api/jobs", {"service": "ascs", "prompt": "hello"}, member_headers)
        command.assert_not_called()


def test_owner_can_grant_then_revoke_member_service_access(gateway, tmp_path):
    owner_headers, owner = login(gateway)
    member = make_member(gateway, owner_headers)
    member_headers, member_profile = login(gateway, "member")
    status, result, _ = gateway.dispatch(
        "PUT", f"/api/profiles/{member['id']}/service-grants/ascs", {}, owner_headers)
    assert status == 200
    assert result == {"profile_id": member["id"], "service": "ascs", "allowed": True}
    assert gateway.accounts.service_allowed(member["id"], "ascs")
    assert catalog_by_id(gateway, member_headers)["ascs"]["allowed"] is True
    gateway.services.models["ascs"] = "installed:test"
    argv, _, _ = gateway.services.command("ascs", member_profile, "hello", "plan")
    assert "core.web.chat_worker" in argv
    with patch.object(gateway.services, "command", return_value=(["python"], tmp_path, {})), \
         patch.object(gateway.services, "_run"):
        assert gateway.dispatch("POST", "/api/jobs", {"service": "ascs", "prompt": "hello"}, member_headers)[0] == 202
    status, result, _ = gateway.dispatch(
        "DELETE", f"/api/profiles/{member['id']}/service-grants/ascs", {}, owner_headers)
    assert status == 200
    assert result == {"profile_id": member["id"], "service": "ascs", "allowed": False}
    assert not gateway.accounts.service_allowed(member["id"], "ascs")
    assert catalog_by_id(gateway, member_headers)["ascs"]["allowed"] is False
    with pytest.raises(PermissionError):
        gateway.dispatch("POST", "/api/jobs", {"service": "ascs", "prompt": "hello"}, member_headers)


def test_service_grant_endpoints_are_owner_only_and_visibility_scoped(gateway):
    owner_headers, owner = login(gateway)
    member = make_member(gateway, owner_headers)
    other = make_member(gateway, owner_headers, "other")
    member_headers, _ = login(gateway, "member")
    with pytest.raises(PermissionError):
        gateway.dispatch("PUT", f"/api/profiles/{member['id']}/service-grants/ascs", {}, member_headers)
    with pytest.raises(PermissionError):
        gateway.dispatch("DELETE", f"/api/profiles/{member['id']}/service-grants/asis", {}, member_headers)
    own = gateway.dispatch("GET", "/api/service-grants", {}, member_headers)[1]["grants"]
    assert [row["profile_id"] for row in own] == [member["id"]]
    with pytest.raises(PermissionError):
        gateway.dispatch("GET", "/api/service-grants?profile_id=" + other["id"], {}, member_headers)
    all_grants = gateway.dispatch("GET", "/api/service-grants", {}, owner_headers)[1]["grants"]
    assert {row["profile_id"] for row in all_grants} == {owner["id"], member["id"], other["id"]}
    with pytest.raises(ValueError):
        gateway.dispatch("PUT", f"/api/profiles/{member['id']}/service-grants/unknown", {}, owner_headers)


def test_grants_persist_across_store_reopen(tmp_path):
    accounts = Accounts(tmp_path)
    owner = accounts.create("owner", PASSWORD, "Owner", first=True)
    member = accounts.create("member", PASSWORD, "Member")
    assert accounts.service_grants(member["id"]) == ["asis"]
    accounts.grant_service(member["id"], "ascs", owner["id"])
    accounts.close()
    reopened = Accounts(tmp_path)
    try:
        assert reopened.service_grants(member["id"]) == ["ascs", "asis"]
        assert reopened.service_allowed(member["id"], "ascs")
        assert not reopened.service_allowed(member["id"], "tiviss")
        assert reopened.service_allowed(owner["id"], "tiviss")
    finally:
        reopened.close()


def test_existing_database_migration_backfills_default_member_grant(tmp_path):
    accounts = Accounts(tmp_path)
    accounts.create("owner", PASSWORD, "Owner", first=True)
    member = accounts.create("member", PASSWORD, "Member")
    accounts.close()
    with sqlite3.connect(tmp_path / "accounts.sqlite3") as db:
        db.execute("DROP TABLE service_grants")
    reopened = Accounts(tmp_path)
    try:
        assert reopened.service_grants(member["id"]) == ["asis"]
        assert not reopened.service_allowed(member["id"], "ascs")
    finally:
        reopened.close()
