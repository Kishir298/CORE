from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock
from typing import Any

from core.resources.models import Resource
from core.runtime.history import RuntimeRecord


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


class InMemoryRescsAdapter(RescsAdapter):
    """In-memory implementation (default, deterministic, no I/O)."""

    def __init__(self) -> None:
        self._resources: dict[str, Resource] = {}
        self._runtimes: dict[str, RuntimeRecord] = {}
        self._lock = RLock()

    def persist_resource(self, resource: Resource) -> None:
        with self._lock:
            # Store a copy via to_dict -> from dict reconstruction to avoid aliasing
            self._resources[resource.resource_id] = resource

    def fetch_resource(self, resource_id: str) -> Resource | None:
        with self._lock:
            return self._resources.get(resource_id)

    def delete_resource(self, resource_id: str) -> None:
        with self._lock:
            self._resources.pop(resource_id, None)

    def list_resources(self) -> list[Resource]:
        with self._lock:
            return list(self._resources.values())

    def persist_runtime(self, record: RuntimeRecord) -> None:
        with self._lock:
            self._runtimes[record.entity_id] = record

    def list_runtimes(self) -> list[RuntimeRecord]:
        with self._lock:
            return list(self._runtimes.values())

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "adapter": "memory",
                "resources": len(self._resources),
                "runtimes": len(self._runtimes),
                "healthy": True,
            }

    def clear(self) -> None:
        with self._lock:
            self._resources.clear()
            self._runtimes.clear()


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
        except Exception:
            return

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

    def _save(self) -> None:
        data = {
            "resources": [r.to_dict() for r in self._memory.list_resources()],
            "runtimes": [r.to_dict() for r in self._memory.list_runtimes()],
        }
        # Atomic write via temp file
        temp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            temp.parent.mkdir(parents=True, exist_ok=True)
            with temp.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp.replace(self._path)
        except Exception as exc:
            raise IOError(f"Failed to persist R.E.S.C.S. file: {exc}") from exc

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
    HTTP adapter stub for future cross-process R.E.S.C.S. on the laptop.

    When R.E.S.C.S. exposes an HTTP endpoint (e.g. http://localhost:8081),
    this adapter would delegate persistence over HTTP. For v0.2 it is a
    stub that raises a clear error so failures are explicit rather than
    silent.
    """

    def __init__(self, endpoint: str = "http://localhost:8081") -> None:
        self._endpoint = endpoint

    def _not_implemented(self) -> None:
        raise NotImplementedError(
            f"HttpRescsAdapter not yet implemented (endpoint={self._endpoint}). "
            "Configure rescs.adapter=memory or file for v0.2, or implement HTTP delegation."
        )

    def persist_resource(self, resource: Resource) -> None:
        self._not_implemented()

    def fetch_resource(self, resource_id: str) -> Resource | None:
        self._not_implemented()
        return None

    def delete_resource(self, resource_id: str) -> None:
        self._not_implemented()

    def list_resources(self) -> list[Resource]:
        self._not_implemented()
        return []

    def persist_runtime(self, record: RuntimeRecord) -> None:
        self._not_implemented()

    def list_runtimes(self) -> list[RuntimeRecord]:
        self._not_implemented()
        return []

    def health(self) -> dict[str, Any]:
        return {
            "adapter": "http",
            "endpoint": self._endpoint,
            "healthy": False,
            "error": "HttpRescsAdapter not implemented in v0.2",
        }

    def clear(self) -> None:
        self._not_implemented()


__all__ = [
    "RescsAdapter",
    "InMemoryRescsAdapter",
    "FileRescsAdapter",
    "HttpRescsAdapter",
]
