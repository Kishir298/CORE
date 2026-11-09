"""Idempotent local → RESCS migration for ASIS cloud-bound records.

Additive tooling: local SQLite/JSON stays canonical. This copies explicit
in-memory record dicts into a RESCS ``StorageClient`` under the ASIS
domain, skipping byte-identical destinations (content-hash compare),
never deleting sources, and reporting per-key outcomes. ``dry_run=True``
(the default) reports without writing. Re-running is safe: identical
records are skipped, never duplicated (keys are stable per source).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from ..integrations.rescs.client import StorageClient, StoredRecord
from .domains import DomainError, DomainRouter


def _content_hash(data: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(data), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def migrate_records(
    records: Iterable[Mapping[str, Any]],
    *,
    client: StorageClient,
    router: DomainRouter | None = None,
    namespace: str = "asis.memory",
    dry_run: bool = True,
    owner: str = "asis",
) -> dict[str, list[str]]:
    """Copy ``records`` into RESCS; return a manifest dict.

    Each record needs ``key`` (str) and ``data`` (mapping). Destination
    keys are namespaced per record (``namespace`` enforced by the router).
    Identical destinations (same content hash stored under the ``_hash``
    metadata field) are skipped. Sources are never modified or deleted.
    """
    active = router or DomainRouter()
    active.check_namespace(namespace)
    manifest: dict[str, list[str]] = {
        "copied": [],
        "skipped_identical": [],
        "failed": [],
    }
    if not client.available():
        raise DomainError("RESCS storage client is not available")
    for index, record in enumerate(records):
        label = (
            str(record.get("key"))
            if isinstance(record, Mapping)
            else f"#{index}"
        )
        try:
            key = record.get("key") if isinstance(record, Mapping) else None
            data = record.get("data") if isinstance(record, Mapping) else None
            if not (isinstance(key, str) and key):
                raise DomainError(f"record #{index} is missing a valid key")
            if not isinstance(data, Mapping):
                raise DomainError(f"record #{index} is missing mapping data")
            digest = _content_hash(data)
            try:
                existing = client.retrieve(key, namespace)
            except Exception:
                existing = None
            if (
                existing is not None
                and isinstance(existing.data, dict)
                and existing.data.get("_hash") == digest
            ):
                manifest["skipped_identical"].append(key)
                continue
            if dry_run:
                manifest["copied"].append(key)
                continue
            stored = StoredRecord(
                key=key,
                data={**dict(data), "_hash": digest, "_owner": owner},
                namespace=namespace,
            )
            if client.store(stored):
                manifest["copied"].append(key)
            else:
                manifest["failed"].append(key)
        except DomainError:
            # Record-level problems are isolated per record; request-level
            # problems (bad namespace, unavailable client) raise instead.
            manifest["failed"].append(label)
        except Exception:
            manifest["failed"].append(label)
    return manifest
