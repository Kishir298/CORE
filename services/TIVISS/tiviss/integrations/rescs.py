"""R.E.S.C.S. integration adapter (interface + local mock).

Provides the contract for future persistent cloud memory through R.E.S.C.S.
The local implementation wraps the deterministic local memory backend so the
contract is testable without a live R.E.S.C.S. deployment.

R.E.S.C.S. is NOT bundled inside T.I.V.I.S.S.; only this adapter boundary
exists.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from typing import Any

from ..memory.interface import MemoryBackend, MemoryKeyError, MemoryRecord
from ..memory.local import LocalMemory
from .base import (
    IntegrationAdapter,
    IntegrationRequest,
    IntegrationResponse,
    IntegrationStatus,
)


class RESCSAdapter(IntegrationAdapter, ABC):
    """Interface to a future R.E.S.C.S. connection for persistent memory."""

    adapter_id = "rescs.adapter"

    def put(self, record: MemoryRecord) -> IntegrationResponse:
        raise NotImplementedError

    def get(self, record_id: str) -> IntegrationResponse:
        raise NotImplementedError

    def search(self, query: str) -> IntegrationResponse:
        raise NotImplementedError

    def clear(self) -> IntegrationResponse:
        raise NotImplementedError


class LocalRESCSAdapter(RESCSAdapter):
    """In-memory mock transport for the R.E.S.C.S. contract.

    Backed by the deterministic :class:`LocalMemory` backend for tests and
    development. Records interactions for inspection.
    """

    adapter_id = "rescs.local"

    def __init__(
        self, *, backend: MemoryBackend | None = None, failure_mode: bool = False
    ) -> None:
        self._backend = backend or LocalMemory()
        self._failure_mode = failure_mode
        self._connected = False
        self.interactions: list[IntegrationRequest] = []

    def connect(self, *, authorized: bool = False) -> bool:
        if not authorized:
            return False
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def connected(self) -> bool:
        return self._connected

    def health(self) -> Mapping[str, Any]:
        return {
            "adapter": self.adapter_id,
            "connected": self._connected,
            "failure_mode": self._failure_mode,
            "stored_records": len(self._backend),
        }

    @property
    def backend(self) -> MemoryBackend:
        return self._backend

    def _response(
        self,
        request: IntegrationRequest,
        *,
        ok: bool,
        payload: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> IntegrationResponse:
        self.interactions.append(request)
        if self._failure_mode:
            return IntegrationResponse(
                request_id=request.request_id,
                status=IntegrationStatus.ERROR,
                error="rescs adapter is in failure mode",
            )
        if not self._connected:
            return self._unavailable(request)
        return IntegrationResponse(
            request_id=request.request_id,
            status=IntegrationStatus.OK if ok else IntegrationStatus.ERROR,
            payload=dict(payload or {}),
            error=error,
        )

    def put(self, record: MemoryRecord) -> IntegrationResponse:
        request = IntegrationRequest(
            operation="put", payload={"record_id": record.record_id}, source="tiviss"
        )
        # Check failure/connection BEFORE mutating the backend so a failed
        # or disconnected adapter never stores data it reports as failed.
        if self._failure_mode:
            return self._response(request, ok=True, payload={})
        if not self.connected():
            return self._unavailable(request)
        stored = self._backend.store(record)
        return self._response(
            request,
            ok=True,
            payload={"record_id": stored.record_id, "key": stored.key},
        )

    def get(self, record_id: str) -> IntegrationResponse:
        request = IntegrationRequest(
            operation="get", payload={"record_id": record_id}, source="tiviss"
        )
        if self._failure_mode:
            return self._response(request, ok=True, payload={})
        if not self.connected():
            return self._unavailable(request)
        try:
            record = self._backend.retrieve(record_id)
        except MemoryKeyError:
            return self._response(
                request, ok=False, error=f"record not found: {record_id}"
            )
        return self._response(request, ok=True, payload=record.to_dict())

    def search(self, query: str) -> IntegrationResponse:
        request = IntegrationRequest(
            operation="search", payload={"query": query}, source="tiviss"
        )
        if self._failure_mode:
            return self._response(request, ok=True, payload={})
        if not self.connected():
            return self._unavailable(request)
        result = self._backend.search(query)
        return self._response(
            request,
            ok=True,
            payload={
                "query": query,
                "total": result.total,
                "records": [r.to_dict() for r in result.records],
            },
        )

    def clear(self) -> IntegrationResponse:
        request = IntegrationRequest(operation="clear", payload={}, source="tiviss")
        if self._failure_mode:
            return self._response(request, ok=True, payload={})
        if not self.connected():
            return self._unavailable(request)
        self._backend.clear()
        return self._response(request, ok=True, payload={"cleared": True})

    def health_report(self) -> Mapping[str, Any]:
        return self.health()
