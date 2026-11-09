"""Versioned export / import of T.I.V.I.S.S. agent state.

The export is a plain JSON document marked ``{"tiviss_export": true,
"version": 1}`` with a SHA-256 integrity hash over the canonical payload.
Secrets (tokens, credentials, passwords, API keys) are never exported:
any mapping key that looks secret is dropped and listed under
``dropped_secrets``. Import validates format, version, integrity, and all
required fields before building anything — invalid input is rejected
without partial imports.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .identity.identity import AgentIdentity, IdentityState
from .identity.ownership import Ownership, OwnershipState, OwnershipTransfer

EXPORT_VERSION = 1
EXPORT_MARKER = "tiviss_export"

_SECRET_HINTS = ("token", "secret", "password", "api_key", "apikey", "credential")


def _looks_secret(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _SECRET_HINTS)


def _scrub_value(value: Any, *, prefix: str = "") -> tuple[Any, list]:
    """Recursively scrub secrets from any value (mappings, sequences, scalars).

    Returns (cleaned_value, dropped_paths).
    """
    dropped: list[str] = []

    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, val in dict(value).items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if _looks_secret(str(key)):
                dropped.append(path)
                continue
            cleaned_val, nested_dropped = _scrub_value(val, prefix=path)
            cleaned[key] = cleaned_val
            dropped.extend(nested_dropped)
        return cleaned, dropped

    elif isinstance(value, (list, tuple, set)):
        cleaned_list = []
        for idx, item in enumerate(value):
            path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            cleaned_item, item_dropped = _scrub_value(item, prefix=path)
            cleaned_list.append(cleaned_item)
            dropped.extend(item_dropped)
        # Preserve original type (list/tuple/set)
        if isinstance(value, tuple):
            return tuple(cleaned_list), dropped
        elif isinstance(value, set):
            return set(cleaned_list), dropped
        return cleaned_list, dropped

    else:
        return value, dropped


def _dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _parse_dt(value: Any, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise StateImportError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise StateImportError(f"{field_name} is not a valid datetime") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


class StateImportError(ValueError):
    """Raised when an exported state document is invalid."""


@dataclass(frozen=True)
class ExportedState:
    """Validated, secret-free agent state ready to be wired into a runtime."""

    agent_id: str
    identity: AgentIdentity
    ownership: Ownership
    model: dict[str, Any]
    permissions: dict[str, list[str]]
    memory_records: tuple
    handover_requests: tuple
    counters: dict[str, int]
    dropped_secrets: tuple[str, ...]


def _identity_to_dict(identity: AgentIdentity) -> tuple[dict, list]:
    meta, dropped = _scrub_value(identity.meta, prefix="identity.meta")
    return (
        {
            "agent_id": identity.agent_id,
            "name": identity.name,
            "version": identity.version,
            "state": identity.state.value,
            "owner_id": identity.owner_id,
            "created_at": _dt(identity.created_at),
            "meta": meta,
        },
        dropped,
    )


def _ownership_to_dict(ownership: Ownership) -> dict:
    return {
        "owner_id": ownership.owner_id,
        "state": ownership.state.value,
        "pending_target": ownership.pending_target,
        "created_at": _dt(ownership.created_at),
        "updated_at": _dt(ownership.updated_at),
        "history": [
            {
                "previous_owner": item.previous_owner,
                "new_owner": item.new_owner,
                "transferred_at": _dt(item.transferred_at),
            }
            for item in ownership.history
        ],
    }


def _memory_to_list(records) -> tuple[list, list]:
    out: list[dict] = []
    dropped: list[str] = []
    for record in records:
        try:
            data = record.to_dict()
        except AttributeError:
            continue
        meta, meta_dropped = _scrub_value(
            data.get("metadata") or {}, prefix=f"memory.{record.key}"
        )
        data["metadata"] = meta
        dropped.extend(meta_dropped)
        out.append(data)
    return out, dropped


def export_state(
    *,
    identity: AgentIdentity,
    ownership: Ownership,
    model: Mapping[str, Any],
    permissions: Mapping[str, Any],
    memory_records,
    handover_requests=(),
    counters: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Build a versioned, integrity-sealed export document (JSON-safe)."""
    identity_dict, dropped = _identity_to_dict(identity)
    memory_list, memory_dropped = _memory_to_list(memory_records)
    dropped.extend(memory_dropped)

    # Scrub model configuration
    model_dict, model_dropped = _scrub_value(dict(model), prefix="model")
    dropped.extend(model_dropped)

    handover_list = []
    for request in handover_requests:
        handover_list.append(
            {
                "request_id": request.request_id,
                "current_owner": request.current_owner,
                "target_owner": request.target_owner,
                "reason": request.reason,
                "stage": request.stage.value,
                "created_at": _dt(request.created_at),
                "updated_at": _dt(request.updated_at),
                "approver": request.approver,
            }
        )
    payload = {
        "identity": identity_dict,
        "ownership": _ownership_to_dict(ownership),
        "model": model_dict,
        "permissions": {
            "allow": sorted(permissions.get("allow", ())),
            "deny": sorted(permissions.get("deny", ())),
        },
        "memory_records": memory_list,
        "handover_requests": handover_list,
        "counters": dict(counters or {}),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        EXPORT_MARKER: True,
        "version": EXPORT_VERSION,
        "exported_at": _dt(datetime.now(UTC)),
        "integrity": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "dropped_secrets": sorted(set(dropped)),
        "payload": payload,
    }


def import_state(document: Mapping[str, Any]) -> ExportedState:
    """Validate a document and rebuild state. Rejects invalid input wholly."""
    if not isinstance(document, Mapping):
        raise StateImportError("export document must be a mapping")
    if document.get(EXPORT_MARKER) is not True:
        raise StateImportError("not a TIVISS export document")
    if document.get("version") != EXPORT_VERSION:
        raise StateImportError(
            f"unsupported export version: {document.get('version')!r}"
        )
    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise StateImportError("export payload must be a mapping")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if document.get("integrity") != digest:
        raise StateImportError("export integrity check failed")

    for section in (
        "identity",
        "ownership",
        "model",
        "permissions",
        "memory_records",
        "handover_requests",
        "counters",
    ):
        if section not in payload:
            raise StateImportError(f"export payload is missing {section!r}")

    raw_identity = payload["identity"]
    try:
        identity = AgentIdentity.create(
            agent_id=str(raw_identity["agent_id"]),
            name=str(raw_identity["name"]),
            version=str(raw_identity["version"]),
            owner_id=str(raw_identity["owner_id"]),
            state=IdentityState(str(raw_identity["state"])),
            created_at=_parse_dt(raw_identity["created_at"], field_name="created_at"),
            meta=dict(raw_identity.get("meta") or {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StateImportError(f"invalid identity section: {exc}") from exc

    raw_ownership = payload["ownership"]
    try:
        ownership = Ownership(
            owner_id=str(raw_ownership["owner_id"]),
            state=OwnershipState(str(raw_ownership["state"])),
            pending_target=raw_ownership.get("pending_target"),
            created_at=_parse_dt(raw_ownership["created_at"], field_name="created_at"),
            updated_at=_parse_dt(raw_ownership["updated_at"], field_name="updated_at"),
            history=[
                OwnershipTransfer(
                    previous_owner=str(item["previous_owner"]),
                    new_owner=str(item["new_owner"]),
                    transferred_at=_parse_dt(
                        item["transferred_at"], field_name="transferred_at"
                    ),
                )
                for item in raw_ownership.get("history", [])
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StateImportError(f"invalid ownership section: {exc}") from exc
    if not ownership.owner_id.strip():
        raise StateImportError("ownership owner_id must be non-empty")

    from .memory.interface import MemoryRecord

    memory_records = []
    for entry in payload["memory_records"]:
        try:
            memory_records.append(MemoryRecord.from_dict(entry))
        except (KeyError, TypeError, ValueError) as exc:
            raise StateImportError(f"invalid memory record: {exc}") from exc

    model = payload["model"]
    permissions = payload["permissions"]
    if not isinstance(model, dict) or not isinstance(permissions, dict):
        raise StateImportError("model and permissions sections must be mappings")
    counters = payload["counters"]
    if not isinstance(counters, dict):
        raise StateImportError("counters section must be a mapping")

    dropped = document.get("dropped_secrets", [])
    if not isinstance(dropped, list):
        raise StateImportError("dropped_secrets must be a list")

    return ExportedState(
        agent_id=identity.agent_id,
        identity=identity,
        ownership=ownership,
        model=dict(model),
        permissions={
            "allow": [str(p) for p in permissions.get("allow", [])],
            "deny": [str(p) for p in permissions.get("deny", [])],
        },
        memory_records=tuple(memory_records),
        handover_requests=tuple(payload["handover_requests"]),
        counters={str(k): int(v) for k, v in counters.items()},
        dropped_secrets=tuple(str(d) for d in dropped),
    )