"""Storage-domain convention tests (offline, memory backend)."""

from __future__ import annotations

import uuid

from rescs.contract import RESERVED_NAMESPACE_PREFIXES, STORAGE_DOMAINS
from rescs.domain import RecordData


def _record(namespace: str, key: str, value: dict | None = None) -> RecordData:
    return RecordData(
        id=str(uuid.uuid4()), namespace=namespace, key=key, value=value or {"n": 1}
    )


def test_reserved_prefixes_include_domains():
    assert set(STORAGE_DOMAINS) == {"asis.", "tiviss.", "personal."}
    for prefix in (*STORAGE_DOMAINS, "core.", "rescs."):
        assert prefix in RESERVED_NAMESPACE_PREFIXES


def test_same_key_coexists_across_domains(sqlalchemy_record_repo):
    for namespace in ("asis.memory", "tiviss.memory", "personal.documents"):
        sqlalchemy_record_repo.create(_record(namespace, "shared"))
    for namespace in ("asis.memory", "tiviss.memory", "personal.documents"):
        page = sqlalchemy_record_repo.search(
            "shared", namespace=namespace, limit=10
        )
        keys = {(item.namespace, item.key) for item in page.items}
        assert (namespace, "shared") in keys


def test_domain_search_stays_in_namespace(sqlalchemy_record_repo):
    sqlalchemy_record_repo.create(_record("asis.memory", "k1", {"v": "alpha"}))
    sqlalchemy_record_repo.create(_record("tiviss.memory", "k2", {"v": "alpha"}))
    page = sqlalchemy_record_repo.search("alpha", namespace="asis.memory")
    assert {item.key for item in page.items} == {"k1"}

