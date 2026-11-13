from __future__ import annotations

import copy
import json
import os
import tempfile
import time
import warnings
from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import quote, urlencode

from core.resources.models import Resource
from core.runtime.history import RuntimeRecord

# C.O.R.E.-managed R.E.S.C.S. record namespaces.  C.O.R.E. persists its
# operational state as ordinary R.E.S.C.S. records under reserved
# ``core.*`` namespaces; it never relies on the legacy /resources,
# /runtimes, /devices or /clear routes.
RESCS_RESOURCE_NAMESPACE = "core.resources"
RESCS_RUNTIME_NAMESPACE = "core.runtimes"
RESCS_DEVICE_NAMESPACE = "core.devices"
# R.E.S.C.S. accepts list limits of 1..500.
RESCS_PAGE_SIZE = 500
# Defence-in-depth bound for collection reads; exceeding it is an error
# rather than a silent truncation.
RESCS_MAX_COLLECTION_RECORDS = 10_000


class RescsAdapter(ABC):
    """
    Abstract persistence adapter for the Windows co-hosted R.E.S.C.S.

    The adapter is intentionally transport-agnostic and never imports
    R.E.S.C.S. internals. The default is in-memory; file and HTTP
    variants provide durability or cross-process sharing on the same
    32GB/1TB laptop.
    """

    @abstractmethod
    def persist_resource(self, resource: Resource) -> None:
        """Persist a resource snapshot."""

    @abstractmethod
    def fetch_resource(self, resource_id: str) -> Resource | None:
        """Fetch a persisted resource."""

    @abstractmethod
    def delete_resource(self, resource_id: str) -> None:
        """Delete a persisted resource."""

    @abstractmethod
    def list_resources(self) -> list[Resource]:
        """List all persisted resources."""

    @abstractmethod
    def persist_runtime(self, record: RuntimeRecord) -> None:
        """Persist a runtime history record."""

    @abstractmethod
    def list_runtimes(self) -> list[RuntimeRecord]:
        """List persisted runtime records."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return adapter health information."""

    @abstractmethod
    def clear(self) -> None:
        """Clear all persisted state."""

    # -- registered device identities --------------------------------------
    # Dedicated device records (plain JSON dicts, keyed by device_id).
    # ResourceRegistry remains a runtime mirror only, never the device
    # persistence authority. Default implementations raise so older
    # third-party adapters stay import-compatible until they opt in.

    def persist_device(self, device: dict[str, Any]) -> None:
        """Persist one sanitized device identity snapshot."""
        raise NotImplementedError("Device persistence is not supported.")

    def fetch_device(self, device_id: str) -> dict[str, Any] | None:
        """Fetch one persisted device identity, or None."""
        raise NotImplementedError("Device persistence is not supported.")

    def delete_device(self, device_id: str) -> None:
        """Delete one persisted device identity."""
        raise NotImplementedError("Device persistence is not supported.")

    def list_devices(self) -> list[dict[str, Any]]:
        """List all persisted device identities."""
        raise NotImplementedError("Device persistence is not supported.")


def _validate_device_dict(device: dict[str, Any]) -> dict[str, Any]:
    """Validate + snapshot a device identity dict for storage."""
    if not isinstance(device, dict):
        raise ValueError("Device identity must be a JSON object.")
    device_id = device.get("device_id")
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("Device identity requires a non-empty device_id.")
    return json.loads(json.dumps(device))


class InMemoryRescsAdapter(RescsAdapter):
    """In-memory implementation (default, deterministic, no I/O)."""

    def __init__(self) -> None:
        self._resources: dict[str, Resource] = {}
        self._runtimes: dict[str, RuntimeRecord] = {}
        self._devices: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def persist_resource(self, resource: Resource) -> None:
        with self._lock:
            # Deep copy so later caller-side mutation cannot alias the
            # stored record (and vice versa).
            self._resources[resource.resource_id] = copy.deepcopy(resource)

    def fetch_resource(self, resource_id: str) -> Resource | None:
        with self._lock:
            found = self._resources.get(resource_id)
            # Deep copy: callers must persist explicitly; mutating a
            # fetched record never alters the store (symmetric with persist).
            return copy.deepcopy(found) if found is not None else None

    def delete_resource(self, resource_id: str) -> None:
        with self._lock:
            self._resources.pop(resource_id, None)

    def list_resources(self) -> list[Resource]:
        with self._lock:
            return copy.deepcopy(list(self._resources.values()))

    def persist_runtime(self, record: RuntimeRecord) -> None:
        with self._lock:
            self._runtimes[record.entity_id] = copy.deepcopy(record)

    def list_runtimes(self) -> list[RuntimeRecord]:
        with self._lock:
            return copy.deepcopy(list(self._runtimes.values()))

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "adapter": "memory",
                "resources": len(self._resources),
                "runtimes": len(self._runtimes),
                "devices": len(self._devices),
                "healthy": True,
            }

    def clear(self) -> None:
        with self._lock:
            self._resources.clear()
            self._runtimes.clear()
            self._devices.clear()

    def persist_device(self, device: dict[str, Any]) -> None:
        snapshot = _validate_device_dict(device)
        with self._lock:
            self._devices[snapshot["device_id"]] = snapshot

    def fetch_device(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            found = self._devices.get(device_id)
            return json.loads(json.dumps(found)) if found is not None else None

    def delete_device(self, device_id: str) -> None:
        with self._lock:
            self._devices.pop(device_id, None)

    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            return [json.loads(json.dumps(d)) for d in self._devices.values()]


class FileRescsAdapter(RescsAdapter):
    """
    File-backed adapter for Windows host persistence across restarts.

    Stores JSON at ``var/rescs.json`` (or custom ``path``) using
    pathlib for Windows compatibility. File writes are atomic via
    temporary file + replace. Failures are surfaced as exceptions for
    the caller to handle as degraded health.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        default = Path("var") / "rescs.json"
        self._path = Path(path) if path else default
        self._lock = RLock()
        self._memory = InMemoryRescsAdapter()
        # Ensure parent directory exists
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            # Never silently lose data: preserve the corrupt file for
            # forensics as <name>.corrupt.<ts> and start empty.
            try:
                ts = int(time.time())
                corrupt = self._path.with_name(
                    f"{self._path.name}.corrupt.{ts}"
                )
                self._path.replace(corrupt)
                warnings.warn(
                    f"corrupt RESCS file {self._path} preserved as {corrupt}: {exc}",
                    UserWarning,
                    stacklevel=2,
                )
            except Exception:
                pass
            return
        if not isinstance(data, dict):
            try:
                ts = int(time.time())
                corrupt = self._path.with_name(
                    f"{self._path.name}.corrupt.{ts}"
                )
                self._path.replace(corrupt)
                warnings.warn(
                    f"corrupt RESCS file {self._path} (not an object) "
                    f"preserved as {corrupt}",
                    UserWarning,
                    stacklevel=2,
                )
            except Exception:
                pass
            return

        from datetime import datetime

        # Hydrate resources
        for item in data.get("resources", []):
            try:
                # Reconstruct Resource from dict
                resource = Resource(
                    resource_id=item["resource_id"],
                    name=item["name"],
                    resource_type=item["resource_type"],
                    status=item.get("status", "offline"),
                    owner=item.get("owner"),
                    source=item.get("source"),
                    capabilities=item.get("capabilities", []),
                    metadata=item.get("metadata", {}),
                    connection_info=item.get("connection_info", {}),
                )
                # Preserve timestamps if available
                if item.get("last_seen"):
                    from datetime import datetime

                    try:
                        resource.last_seen = datetime.fromisoformat(  # type: ignore
                            item["last_seen"]
                        )
                    except Exception:
                        pass
                if item.get("registered_at"):
                    try:
                        resource.registered_at = datetime.fromisoformat(  # type: ignore
                            item["registered_at"]
                        )
                    except Exception:
                        pass
                self._memory.persist_resource(resource)
            except Exception:
                continue

        # Hydrate runtimes (lightweight - store as RuntimeRecord with same fields)
        from datetime import datetime

        for item in data.get("runtimes", []):
            try:
                record = RuntimeRecord(
                    entity_id=item["entity_id"],
                    entity_type=item["entity_type"],
                    status=item.get("status", "running"),
                    metadata=item.get("metadata", {}),
                )
                # Restore times/durations if present
                if item.get("start_time"):
                    record.start_time = datetime.fromisoformat(item["start_time"])  # type: ignore
                if item.get("end_time"):
                    record.end_time = datetime.fromisoformat(item["end_time"])  # type: ignore
                if item.get("duration") is not None:
                    record.duration = item["duration"]  # type: ignore
                self._memory.persist_runtime(record)
            except Exception:
                continue

        # Hydrate registered device identities (tolerate per-item corruption)
        for item in data.get("devices", []):
            try:
                if isinstance(item, dict) and item.get("device_id"):
                    self._memory.persist_device(item)
            except Exception:
                continue

    def _save(self) -> None:
        data = {
            "resources": [r.to_dict() for r in self._memory.list_resources()],
            "runtimes": [r.to_dict() for r in self._memory.list_runtimes()],
            "devices": self._memory.list_devices(),
        }
        # Atomic write via temp file
        temp = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=self._path.name + ".", suffix=".tmp", dir=self._path.parent)
            temp = Path(name)
            # mkstemp creates mode 0600 on POSIX, including during writes;
            # snapshots may contain provisioned device credentials.
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp.replace(self._path)
        except Exception as exc:
            if temp is not None:
                temp.unlink(missing_ok=True)
            raise OSError(f"Failed to persist R.E.S.C.S. file: {exc}") from exc

    def persist_resource(self, resource: Resource) -> None:
        with self._lock:
            self._memory.persist_resource(resource)
            self._save()

    def fetch_resource(self, resource_id: str) -> Resource | None:
        with self._lock:
            return self._memory.fetch_resource(resource_id)

    def delete_resource(self, resource_id: str) -> None:
        with self._lock:
            self._memory.delete_resource(resource_id)
            self._save()

    def list_resources(self) -> list[Resource]:
        with self._lock:
            return self._memory.list_resources()

    def persist_runtime(self, record: RuntimeRecord) -> None:
        with self._lock:
            self._memory.persist_runtime(record)
            self._save()

    def list_runtimes(self) -> list[RuntimeRecord]:
        with self._lock:
            return self._memory.list_runtimes()

    def persist_device(self, device: dict[str, Any]) -> None:
        with self._lock:
            self._memory.persist_device(device)
            self._save()

    def fetch_device(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._memory.fetch_device(device_id)

    def delete_device(self, device_id: str) -> None:
        with self._lock:
            self._memory.delete_device(device_id)
            self._save()

    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._memory.list_devices()

    def health(self) -> dict[str, Any]:
        with self._lock:
            base = self._memory.health()
            base["adapter"] = "file"
            base["path"] = str(self._path)
            # Check writability
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                healthy = self._path.parent.exists()
            except Exception:
                healthy = False
            base["healthy"] = healthy
            return base

    def clear(self) -> None:
        with self._lock:
            self._memory.clear()
            self._save()


class HttpRescsAdapter(RescsAdapter):
    """
    HTTP adapter for cross-process R.E.S.C.S. on the Windows laptop.

    Delegates persistence over HTTP to a co-hosted R.E.S.C.S. service
    (e.g. ``http://localhost:8081``) using the standard library only.
    When the endpoint is unreachable the adapter falls back to an
    in-memory cache so local operation is undisturbed while health
    correctly reports ``healthy=False`` until the remote is reachable.

    Persistence mapping (R.E.S.C.S. v1 record API):

    ==================  =============================================
    C.O.R.E. object     R.E.S.C.S. record
    ==================  =============================================
    Resource            namespace ``core.resources``, key
                        ``resource_id``, value ``Resource.to_dict()``
    RuntimeRecord       namespace ``core.runtimes``, key ``entity_id``,
                        value ``RuntimeRecord.to_dict()``
    device identity     namespace ``core.devices``, key ``device_id``,
                        value the sanitized device snapshot
    ==================  =============================================

    Records are upserted with ``PUT /api/v1/records`` (namespace/key) and
    addressed by their server-assigned ``id`` for reads/deletes.  The
    record ``owner`` is deliberately left at the R.E.S.C.S. default
    (``system`` or the configured key owner) because C.O.R.E.'s logical
    owner lives inside ``value`` and a locked deployment must be allowed
    to reject an arbitrary storage owner.

    Contract (JSON over HTTP) - RESCS v1 API:
      PUT    /api/v1/records          {namespace,key,value,metadata}
      GET    /api/v1/records          -> {items:[...], total:int, limit, offset}
      GET    /api/v1/records/{id}     -> record or 404
      DELETE /api/v1/records/{id}     -> 204 or 404
      GET    /health                  -> {status:"ok"|..., checks:{...}}
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:8081",
        timeout: float = 2.0,
        fallback: bool = True,
        api_key: str | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") if endpoint else "http://localhost:8081"
        self._timeout = float(timeout) if timeout else 2.0
        self._fallback_enabled = bool(fallback)
        self._fallback = InMemoryRescsAdapter()
        self._lock = RLock()
        self._last_error: str | None = None
        self._healthy: bool | None = None
        self._api_key = api_key
        self._last_durable_success: bool = False

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self._endpoint + path

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        allow_not_found: bool | None = None,
    ) -> Any | None:
        import urllib.error
        import urllib.request

        method = method.upper()
        # A 404 means "absent" only for reads by default.  Writes never
        # turn a missing route/object into success; callers that can
        # tolerate a concurrent delete opt in explicitly.
        if allow_not_found is None:
            allow_not_found = method == "GET"
        url = self._url(path)
        data = None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        if body is not None:
            if method == "GET":
                query = urlencode({key: value for key, value in body.items() if value is not None})
                if query:
                    url += ("&" if "?" in url else "?") + query
            else:
                data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                text = raw.decode("utf-8")
                if not text.strip():
                    return None
                try:
                    return json.loads(text)
                except Exception:
                    return text
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and allow_not_found:
                return None
            raise OSError(f"R.E.S.C.S. HTTP {method} {path} -> {exc.code} {exc.reason}") from exc
        except Exception as exc:
            raise OSError(f"R.E.S.C.S. HTTP {method} {path} failed: {exc}") from exc

    # -- remote collection / mapping helpers -------------------------------

    def _mark_remote_success(self, *, durable: bool = False) -> None:
        self._last_error = None
        self._healthy = True
        if durable:
            self._last_durable_success = True

    def _mark_remote_failure(self, exc: Exception) -> None:
        self._last_error = str(exc)
        self._healthy = False
        # A failed write (or any remote failure) must not inherit a
        # previous durable-success claim.
        if isinstance(exc, OSError):
            self._last_durable_success = False

    @staticmethod
    def _parse_collection(result: Any) -> tuple[list[dict[str, Any]], int]:
        if isinstance(result, list):
            items = [item for item in result if isinstance(item, dict)]
            return items, len(items)
        if not isinstance(result, dict):
            return [], 0
        items: list[dict[str, Any]] | None = None
        for key in ("items", "records", "data"):
            if isinstance(result.get(key), list):
                items = [item for item in result[key] if isinstance(item, dict)]
                break
        if items is None and any(
            key in result for key in ("id", "resource_id", "entity_id")
        ):
            items = [result]
        total = result.get("total")
        if type(total) is not int or total < 0:
            total = len(items) if items is not None else 0
        return items or [], total

    def _collection(
        self, path: str, params: dict[str, Any] | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Read every page of a R.E.S.C.S. collection, bounded.

        Uses the documented 1..500 page limit and stops when the remote
        ``total`` is reached (or a short/empty page is returned by an
        older server).  More than :data:`RESCS_MAX_COLLECTION_RECORDS`
        is a hard failure so a caller never silently receives a partial
        collection.
        """
        records: list[dict[str, Any]] = []
        total: int | None = None
        offset = 0
        while True:
            page_params = dict(params or {})
            page_params["limit"] = RESCS_PAGE_SIZE
            page_params["offset"] = offset
            result = self._request("GET", path, page_params)
            if result is None:
                raise OSError("Missing R.E.S.C.S. collection response.")
            items, page_total = self._parse_collection(result)
            if total is None:
                total = page_total
            records.extend(items)
            if (
                len(records) > RESCS_MAX_COLLECTION_RECORDS
                or (total is not None and total > RESCS_MAX_COLLECTION_RECORDS)
            ):
                raise OSError(
                    "R.E.S.C.S. collection exceeds "
                    f"{RESCS_MAX_COLLECTION_RECORDS} records."
                )
            if not items:
                break
            if total is not None and len(records) >= total:
                break
            if total is None and len(items) < RESCS_PAGE_SIZE:
                break
            offset += len(items)
        return records, total if total is not None else len(records)

    def _find_record(self, namespace: str, key: str) -> dict[str, Any] | None:
        """Find one record by its C.O.R.E. ``(namespace, key)`` identity."""
        records, _ = self._collection(
            "/api/v1/records", {"namespace": namespace, "key_prefix": key}
        )
        for record in records:
            if record.get("namespace") == namespace and record.get("key") == key:
                return record
        return None

    def _write_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Upsert one record and require a server-confirmed write."""
        result = self._request("PUT", "/api/v1/records", payload)
        if not isinstance(result, dict) or not result.get("id"):
            raise OSError("Invalid R.E.S.C.S. record write response.")
        return result

    @staticmethod
    def _resource_payload(resource: Resource) -> dict[str, Any]:
        return {
            "namespace": RESCS_RESOURCE_NAMESPACE,
            "key": resource.resource_id,
            "value": resource.to_dict(),
            "metadata": {},
        }

    @staticmethod
    def _runtime_payload(record: RuntimeRecord) -> dict[str, Any]:
        return {
            "namespace": RESCS_RUNTIME_NAMESPACE,
            "key": record.entity_id,
            "value": record.to_dict(),
            "metadata": {},
        }

    @staticmethod
    def _device_payload(device: dict[str, Any]) -> dict[str, Any]:
        snapshot = _validate_device_dict(device)
        return {
            "namespace": RESCS_DEVICE_NAMESPACE,
            "key": snapshot["device_id"],
            "value": snapshot,
            "metadata": {},
        }

    def _resource_from_dict(self, data: dict[str, Any]) -> Resource:
        from datetime import datetime

        resource = Resource(
            resource_id=data["resource_id"],
            name=data["name"],
            resource_type=data["resource_type"],
            status=data.get("status", "offline"),
            owner=data.get("owner"),
            source=data.get("source"),
            capabilities=data.get("capabilities", []),
            metadata=data.get("metadata", {}),
            connection_info=data.get("connection_info", {}),
        )
        if data.get("last_seen"):
            try:
                resource.last_seen = datetime.fromisoformat(data["last_seen"])  # type: ignore
            except Exception:
                pass
        if data.get("registered_at"):
            try:
                resource.registered_at = datetime.fromisoformat(data["registered_at"])  # type: ignore
            except Exception:
                pass
        return resource

    def _record_from_dict(self, data: dict[str, Any]) -> RuntimeRecord:
        from datetime import datetime

        record = RuntimeRecord(
            entity_id=data["entity_id"],
            entity_type=data["entity_type"],
            status=data.get("status", "running"),
            metadata=data.get("metadata", {}),
        )
        if data.get("start_time"):
            try:
                record.start_time = datetime.fromisoformat(data["start_time"])  # type: ignore
            except Exception:
                pass
        if data.get("end_time"):
            try:
                record.end_time = datetime.fromisoformat(data["end_time"])  # type: ignore
            except Exception:
                pass
        if data.get("duration") is not None:
            try:
                record.duration = data["duration"]  # type: ignore
            except Exception:
                pass
        return record

    def _resource_from_record(self, record: dict[str, Any]) -> Resource:
        """Project a R.E.S.C.S. record into a C.O.R.E. ``Resource``.

        The canonical representation is ``value = Resource.to_dict()``.
        Flat legacy records are tolerated so old local fixtures and any
        hand-seeded data remain readable.
        """
        value = record.get("value")
        if not isinstance(value, dict) or "resource_id" not in value:
            value = {
                key: record.get(key)
                for key in (
                    "resource_id",
                    "name",
                    "resource_type",
                    "status",
                    "owner",
                    "source",
                    "capabilities",
                    "metadata",
                    "connection_info",
                    "last_seen",
                    "registered_at",
                )
                if key in record
            }
        data = dict(value)
        data.setdefault("resource_id", record.get("key") or record.get("id") or "")
        data.setdefault("name", data["resource_id"])
        data.setdefault("resource_type", "unknown")
        if "owner" not in data:
            data["owner"] = record.get("owner")
        return self._resource_from_dict(data)

    def _runtime_from_record(self, record: dict[str, Any]) -> RuntimeRecord:
        """Project a R.E.S.C.S. record into a ``RuntimeRecord``."""
        value = record.get("value")
        if not isinstance(value, dict) or "entity_id" not in value:
            value = {
                key: record.get(key)
                for key in (
                    "entity_id",
                    "entity_type",
                    "start_time",
                    "end_time",
                    "duration",
                    "status",
                    "metadata",
                )
                if key in record
            }
        data = dict(value)
        data.setdefault("entity_id", record.get("key") or "")
        if not data.get("entity_type"):
            metadata = record.get("metadata")
            if isinstance(metadata, dict) and metadata.get("entity_type"):
                data["entity_type"] = metadata["entity_type"]
            else:
                data["entity_type"] = "unknown"
        return self._record_from_dict(data)

    def _device_from_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Project a R.E.S.C.S. record into a device identity dict."""
        value = record.get("value")
        data = dict(value) if isinstance(value, dict) else {}
        if "device_id" not in data:
            data["device_id"] = record.get("key")
        return _validate_device_dict(data)

    def persist_resource(self, resource: Resource) -> None:
        with self._lock:
            # Always keep fallback in sync
            self._fallback.persist_resource(resource)
            try:
                self._write_record(self._resource_payload(resource))
                self._mark_remote_success(durable=True)
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise

    def fetch_resource(self, resource_id: str) -> Resource | None:
        with self._lock:
            try:
                record = self._find_record(
                    RESCS_RESOURCE_NAMESPACE, resource_id
                )
                if record is None:
                    self._mark_remote_success()
                    return (
                        self._fallback.fetch_resource(resource_id)
                        if self._fallback_enabled
                        else None
                    )
                resource = self._resource_from_record(record)
                if resource.resource_id != resource_id:
                    raise OSError(
                        "R.E.S.C.S. record identity does not match the "
                        "requested resource."
                    )
                self._mark_remote_success()
                return resource
            except Exception as exc:
                self._mark_remote_failure(exc)
                if self._fallback_enabled:
                    return self._fallback.fetch_resource(resource_id)
                raise

    def delete_resource(self, resource_id: str) -> None:
        with self._lock:
            self._fallback.delete_resource(resource_id)
            try:
                record = self._find_record(
                    RESCS_RESOURCE_NAMESPACE, resource_id
                )
                if record is not None:
                    record_id = record.get("id")
                    if not isinstance(record_id, str) or not record_id:
                        raise OSError(
                            "R.E.S.C.S. record is missing its server id."
                        )
                    # The exact record was just observed, so a concurrent
                    # 404 means the delete already happened (idempotent).
                    self._request(
                        "DELETE",
                        f"/api/v1/records/{quote(record_id, safe='')}",
                        allow_not_found=True,
                    )
                self._mark_remote_success(durable=True)
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise

    def list_resources(self) -> list[Resource]:
        with self._lock:
            try:
                records, _ = self._collection(
                    "/api/v1/records",
                    {"namespace": RESCS_RESOURCE_NAMESPACE},
                )
                out: list[Resource] = []
                for item in records:
                    try:
                        out.append(self._resource_from_record(item))
                    except Exception:
                        continue
                self._mark_remote_success()
                return out
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise
                return self._fallback.list_resources()

    def persist_runtime(self, record: RuntimeRecord) -> None:
        with self._lock:
            self._fallback.persist_runtime(record)
            try:
                self._write_record(self._runtime_payload(record))
                self._mark_remote_success(durable=True)
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise

    def list_runtimes(self) -> list[RuntimeRecord]:
        with self._lock:
            try:
                records, _ = self._collection(
                    "/api/v1/records",
                    {"namespace": RESCS_RUNTIME_NAMESPACE},
                )
                out: list[RuntimeRecord] = []
                for item in records:
                    try:
                        out.append(self._runtime_from_record(item))
                    except Exception:
                        continue
                self._mark_remote_success()
                return out
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise
                return self._fallback.list_runtimes()

    def health(self) -> dict[str, Any]:
        with self._lock:
            try:
                result = self._request("GET", "/health")
                if not isinstance(result, dict):
                    raise OSError("Invalid R.E.S.C.S. health response.")
                status = result.get("status")
                if status is not None:
                    healthy = status == "ok"
                else:
                    # Never assume healthy when the remote omitted status.
                    healthy = result.get("healthy") is True
                self._healthy = healthy
                self._last_error = None if healthy else (
                    f"R.E.S.C.S. status={status!r}"
                    if status is not None
                    else "R.E.S.C.S. health response has no status."
                )
                result = dict(result)
                result["healthy"] = healthy
                result.setdefault("adapter", "http")
                result.setdefault("endpoint", self._endpoint)
                result.setdefault(
                    "last_durable_success", self._last_durable_success
                )
                return result
            except Exception as exc:
                self._last_error = str(exc)
                self._healthy = False
                return {
                    "adapter": "http",
                    "endpoint": self._endpoint,
                    "healthy": False,
                    "error": str(exc),
                    "last_durable_success": self._last_durable_success,
                    "fallback_records": len(self._fallback.list_resources()),
                    "fallback_runtimes": len(self._fallback.list_runtimes()),
                    "fallback_devices": len(self._fallback.list_devices()),
                }

    def persist_device(self, device: dict[str, Any]) -> None:
        snapshot = _validate_device_dict(device)
        with self._lock:
            self._fallback.persist_device(snapshot)
            try:
                self._write_record(self._device_payload(snapshot))
                self._mark_remote_success(durable=True)
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise

    def fetch_device(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            try:
                record = self._find_record(RESCS_DEVICE_NAMESPACE, device_id)
                if record is None:
                    self._mark_remote_success()
                    return (
                        self._fallback.fetch_device(device_id)
                        if self._fallback_enabled
                        else None
                    )
                device = self._device_from_record(record)
                if device["device_id"] != device_id:
                    raise OSError(
                        "R.E.S.C.S. record identity does not match the "
                        "requested device."
                    )
                self._mark_remote_success()
                return device
            except Exception as exc:
                self._mark_remote_failure(exc)
                if self._fallback_enabled:
                    return self._fallback.fetch_device(device_id)
                raise

    def delete_device(self, device_id: str) -> None:
        with self._lock:
            self._fallback.delete_device(device_id)
            try:
                record = self._find_record(RESCS_DEVICE_NAMESPACE, device_id)
                if record is not None:
                    record_id = record.get("id")
                    if not isinstance(record_id, str) or not record_id:
                        raise OSError(
                            "R.E.S.C.S. record is missing its server id."
                        )
                    self._request(
                        "DELETE",
                        f"/api/v1/records/{quote(record_id, safe='')}",
                        allow_not_found=True,
                    )
                self._mark_remote_success(durable=True)
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise

    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            try:
                records, _ = self._collection(
                    "/api/v1/records", {"namespace": RESCS_DEVICE_NAMESPACE}
                )
                out: list[dict[str, Any]] = []
                for item in records:
                    try:
                        out.append(self._device_from_record(item))
                    except Exception:
                        continue
                self._mark_remote_success()
                return out
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise
                return self._fallback.list_devices()

    def clear(self) -> None:
        with self._lock:
            self._fallback.clear()
            try:
                # The real API has no global /clear.  Only delete the
                # namespaces C.O.R.E. owns; foreign records are preserved.
                for namespace in (
                    RESCS_RESOURCE_NAMESPACE,
                    RESCS_RUNTIME_NAMESPACE,
                    RESCS_DEVICE_NAMESPACE,
                ):
                    records, _ = self._collection(
                        "/api/v1/records", {"namespace": namespace}
                    )
                    for record in records:
                        record_id = record.get("id")
                        if not isinstance(record_id, str) or not record_id:
                            raise OSError(
                                "R.E.S.C.S. record is missing its server id."
                            )
                        self._request(
                            "DELETE",
                            f"/api/v1/records/{quote(record_id, safe='')}",
                            allow_not_found=True,
                        )
                self._mark_remote_success(durable=True)
            except Exception as exc:
                self._mark_remote_failure(exc)
                if not self._fallback_enabled:
                    raise


__all__ = [
    "FileRescsAdapter",
    "HttpRescsAdapter",
    "InMemoryRescsAdapter",
    "RescsAdapter",
]
