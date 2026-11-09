"""Integration: tags, metadata caps, and advanced filtering (Phases 18–19)."""

from __future__ import annotations

from fastapi.testclient import TestClient

RECORDS = "/api/v1/records"
FILES = "/api/v1/files"


def test_tag_validation(client: TestClient):
    base = {"namespace": "tg", "key": "k", "value": {}}
    # Too many tags -> 422 (limit 50).
    response = client.post(RECORDS, json={**base, "key": "t1", "tags": [f"t{i}" for i in range(51)]})
    assert response.status_code == 422
    # Illegal characters -> 422.
    bad = client.post(RECORDS, json={**base, "key": "t2", "tags": ["not a tag!"]})
    assert bad.status_code == 422
    # Valid tags accepted, echoed back.
    ok = client.post(
        RECORDS, json={**base, "key": "t3", "tags": ["important", "asis.memory"]}
    )
    assert ok.status_code == 201
    assert sorted(ok.json()["tags"]) == ["asis.memory", "important"]


def test_tags_change_etag_deterministically(client: TestClient):
    first = client.post(
        RECORDS, json={"namespace": "tg", "key": "etag", "value": {"v": 1}}
    ).json()
    second = client.post(
        RECORDS,
        json={"namespace": "tg", "key": "etag2", "value": {"v": 1}, "tags": ["b", "a"]},
    ).json()
    assert second["etag"] != first["etag"]
    # Tag order does not affect identity.
    third = client.post(
        RECORDS,
        json={"namespace": "tg", "key": "etag3", "value": {"v": 1}, "tags": ["a", "b"]},
    ).json()
    assert third["etag"] == second["etag"]
    # PATCH-ing tags rotates the etag and bumps the version.
    patched = client.patch(
        f"{RECORDS}/{first['id']}", json={"tags": ["b", "a"]}
    ).json()
    assert patched["etag"] == second["etag"]
    assert patched["version"] == 2


def test_tag_filtering_all_match(client: TestClient):
    client.post(RECORDS, json={"namespace": "tgf", "key": "a", "value": {}, "tags": ["x", "y"]})
    client.post(RECORDS, json={"namespace": "tgf", "key": "b", "value": {}, "tags": ["x"]})
    client.post(RECORDS, json={"namespace": "tgf", "key": "c", "value": {}})
    one = client.get(f"{RECORDS}?namespace=tgf&tags=x").json()
    assert one["total"] == 2
    both = client.get(f"{RECORDS}?namespace=tgf&tags=x&tags=y").json()
    assert both["total"] == 1
    assert both["items"][0]["key"] == "a"
    missing = client.get(f"{RECORDS}?namespace=tgf&tags=nope").json()
    assert missing["total"] == 0
    # Search honors tags too.
    searched = client.get(f"{RECORDS}?namespace=tgf&query=a&tags=x&tags=y").json()
    assert searched["total"] == 1


def test_time_window_and_ordering(client: TestClient):
    for key in ("w1", "w2", "w3"):
        client.post(RECORDS, json={"namespace": "tgw", "key": key, "value": {}})
    middle = client.get(f"{RECORDS}?namespace=tgw&key_prefix=w").json()["items"][1]
    after = middle["created_at"]
    later = client.get(f"{RECORDS}?namespace=tgw&created_after={after}").json()
    assert later["total"] >= 1
    for item in later["items"]:
        assert item["created_at"] >= after
    earlier = client.get(f"{RECORDS}?namespace=tgw&created_before={after}").json()
    assert all(item["created_at"] < after for item in earlier["items"])
    # Deterministic ordering: (created_at, id) ascending across pages.
    first_page = client.get(f"{RECORDS}?namespace=tgw&limit=2&offset=0").json()["items"]
    second_page = client.get(f"{RECORDS}?namespace=tgw&limit=2&offset=2").json()["items"]
    ids = [i["id"] for i in first_page] + [i["id"] for i in second_page]
    assert len(ids) == len(set(ids)) == 3


def test_file_filters(client: TestClient):
    client.post(
        FILES,
        files={"upload": ("a.txt", b"a" * 10, "text/plain")},
        data={"owner": "owner-F"},
    )
    big = client.post(
        FILES, files={"upload": ("b.bin", b"b" * 100, "application/octet-stream")}
    ).json()
    assert big["size"] == 100

    mime = client.get(f"{FILES}?mime_type=text/plain&owner=owner-F").json()
    assert mime["total"] == 1
    sized = client.get(f"{FILES}?size_min=50").json()
    assert all(item["size"] >= 50 for item in sized["items"])
    assert sized["total"] >= 1
    capped = client.get(f"{FILES}?size_max=50").json()
    assert all(item["size"] <= 50 for item in capped["items"])


def test_filters_respect_owner_scope(client: TestClient):
    client.post(
        RECORDS,
        json={"namespace": "tgo", "key": "a", "value": {}, "owner": "owner-A", "tags": ["x"]},
    )
    client.post(
        RECORDS,
        json={"namespace": "tgo", "key": "b", "value": {}, "owner": "owner-B", "tags": ["x"]},
    )
    only_a = client.get(f"{RECORDS}?namespace=tgo&tags=x&owner=owner-A").json()
    assert only_a["total"] == 1
    assert only_a["items"][0]["owner"] == "owner-A"

