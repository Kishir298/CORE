"""R.E.S.C.S. retrieval seam for the C.O.R.E. data layer.

C.O.R.E. never touches R.E.S.C.S. internals. All reads go through
:class:`RescsDataReader`, which exposes exactly the five logical
operations the data organizer needs. Owner scoping is structural: a
reader is bound to one ``owner_scope`` at construction and refuses
cross-owner reads unless explicitly permitted, so C.O.R.E. cannot
retrieve-then-filter another owner's data.

Two backends:

- :class:`AdapterDataReader` — reads through the existing
  ``RescsAdapter`` (``fetch_resource`` / ``list_resources``). Records are
  projected from ``Resource`` objects (``namespace`` from
  ``metadata["namespace"]``, default ``core.resources``). Files are not
  supported by the adapter contract and report unavailable.
- :class:`HttpDataReader` — reads through the R.E.S.C.S. HTTP data
  contract (stdlib ``urllib`` only, fixed timeout, zero retries).

All failures surface as :class:`DataError` subclasses only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from core.communication.protocol import RESCS_REQUEST_TIMEOUT

from .errors import (
    DataAccessDenied,
    DataNotFound,
    DataRetrievalFailed,
    DataSourceUnavailable,
)

DEFAULT_NAMESPACE = "core.resources"
MAX_HTTP_RESPONSE_BYTES = 10 * 1024 * 1024
REMOTE_PAGE_SIZE = 500
MAX_COLLECTION_RECORDS = 10_000
MAX_FILE_CONTENT_BYTES = 10 * 1024 * 1024


class RescsDataReader(ABC):
    """Owner-scoped read interface over R.E.S.C.S. data."""

    def __init__(
        self,
        owner_scope: str | None,
        allow_cross_owner: bool = False,
    ) -> None:
        self._owner_scope = owner_scope
        self._allow_cross_owner = bool(allow_cross_owner)

    @property
    def owner_scope(self) -> str | None:
        """Return the owner this reader is scoped to."""
        return self._owner_scope

    def _check_owner(self, owner: str | None) -> str | None:
        """Enforce owner scoping. Returns the effective owner filter."""
        effective = owner if owner is not None else self._owner_scope
        if (
            not self._allow_cross_owner
            and self._owner_scope is not None
            and effective != self._owner_scope
        ):
            raise DataAccessDenied(
                f"Access denied for owner: {owner!r}."
            )
        return effective

    @abstractmethod
    def get_record(
        self, namespace: str, key: str, owner: str | None = None
    ) -> dict[str, Any]:
        """Return one raw record dict, or raise a DataError."""

    @abstractmethod
    def list_records(
        self,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return raw record dicts (unsorted, unpaginated)."""

    @abstractmethod
    def search_records(
        self,
        query: str,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return raw record dicts matching a substring query."""

    @abstractmethod
    def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Return one raw file-metadata dict, or raise a DataError."""

    @abstractmethod
    def get_file_bytes(self, file_id: str) -> tuple[dict[str, Any], bytes]:
        """Return ``(metadata, content_bytes)``, or raise a DataError."""


def _resource_to_record(resource: Any) -> dict[str, Any]:
    """Project a ``Resource`` into a raw record dict (no storage access)."""
    metadata = dict(getattr(resource, "metadata", {}) or {})
    namespace = metadata.get("namespace", DEFAULT_NAMESPACE)
    return {
        "id": getattr(resource, "resource_id", ""),
        "namespace": namespace,
        "key": metadata.get("key", getattr(resource, "resource_id", "")),
        "value": {
            "name": getattr(resource, "name", ""),
            "status": getattr(resource, "status", ""),
            "capabilities": list(getattr(resource, "capabilities", []) or []),
            "metadata": metadata,
        },
        "metadata": metadata,
        "owner": getattr(resource, "owner", None),
        "version": metadata.get("version"),
        "etag": metadata.get("etag"),
        "created_at": metadata.get("created_at"),
        "updated_at": metadata.get("updated_at"),
    }


class AdapterDataReader(RescsDataReader):
    """Read records through an existing ``RescsAdapter`` instance."""

    def __init__(
        self,
        adapter: Any,
        owner_scope: str | None,
        allow_cross_owner: bool = False,
    ) -> None:
        super().__init__(owner_scope, allow_cross_owner)
        self._adapter = adapter

    def _all_records(self) -> list[dict[str, Any]]:
        try:
            resources = self._adapter.list_resources()
        except Exception as exc:
            raise DataSourceUnavailable(
                "R.E.S.C.S. adapter is unavailable."
            ) from exc
        return [_resource_to_record(r) for r in resources or []]

    def get_record(
        self, namespace: str, key: str, owner: str | None = None
    ) -> dict[str, Any]:
        effective_owner = self._check_owner(owner)
        for record in self._all_records():
            if record["namespace"] != namespace or record["key"] != key:
                continue
            if effective_owner is not None and record["owner"] != effective_owner:
                continue
            return record
        raise DataNotFound(f"Record was not found: {namespace}/{key}.")

    def list_records(
        self,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        effective_owner = self._check_owner(owner)
        result = []
        for record in self._all_records():
            if namespace is not None and record["namespace"] != namespace:
                continue
            if key_prefix is not None and not str(record["key"]).startswith(key_prefix):
                continue
            if effective_owner is not None and record["owner"] != effective_owner:
                continue
            result.append(record)
        if offset is not None:
            result = result[offset:]
        if limit is not None:
            result = result[:limit]
        return result

    def search_records(
        self,
        query: str,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        needle = (query or "").lower()
        result = []
        for record in self.list_records(namespace, key_prefix, owner):
            haystacks = [
                str(record.get("key", "")),
                json.dumps(record.get("value", {}), default=str),
                str((record.get("metadata", {}) or {}).get("name", "")),
            ]
            if any(needle in hay.lower() for hay in haystacks):
                result.append(record)
        if offset is not None:
            result = result[offset:]
        if limit is not None:
            result = result[:limit]
        return result

    def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        raise DataSourceUnavailable(
            "File storage is not available on this R.E.S.C.S. adapter."
        )

    def get_file_bytes(self, file_id: str) -> tuple[dict[str, Any], bytes]:
        raise DataSourceUnavailable(
            "File storage is not available on this R.E.S.C.S. adapter."
        )


class HttpDataReader(RescsDataReader):
    """Read records/files through the R.E.S.C.S. HTTP data contract.

    Fixed timeout, zero retries. Only ``DataError`` subclasses escape.
    """

    def __init__(
        self,
        endpoint: str,
        owner_scope: str | None,
        allow_cross_owner: bool = False,
        timeout: float = RESCS_REQUEST_TIMEOUT,
        api_key: str | None = None,
    ) -> None:
        super().__init__(owner_scope, allow_cross_owner)
        self._endpoint = (endpoint or "").rstrip("/")
        self._timeout = float(timeout) if timeout else RESCS_REQUEST_TIMEOUT
        self._api_key = api_key

    def _url(self, path: str, params: dict | None = None) -> str:
        url = f"{self._endpoint}{path}"
        if params:
            query = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
            if query:
                url = f"{url}?{query}"
        return url

    def _get_json(self, path: str, params: dict | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        try:
            req = urllib.request.Request(
                self._url(path, params), headers=headers
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                raw = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
                if len(raw) > MAX_HTTP_RESPONSE_BYTES:
                    raise DataRetrievalFailed("R.E.S.C.S. response exceeds the read limit.")
                body = raw.decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise DataNotFound("Requested data was not found.")
            if exc.code in (401, 403):
                raise DataAccessDenied("Access denied by R.E.S.C.S..")
            raise DataRetrievalFailed("R.E.S.C.S. request failed.")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DataSourceUnavailable(
                "R.E.S.C.S. service is unavailable."
            ) from exc
        except Exception as exc:
            raise DataRetrievalFailed("R.E.S.C.S. request failed.") from exc
        try:
            return json.loads(body) if body else None
        except Exception as exc:
            raise DataRetrievalFailed("Invalid R.E.S.C.S. response.") from exc

    def _get_bytes(self, path: str, params: dict | None = None) -> bytes:
        """Fetch binary content with a hard read limit."""
        headers = {"Accept": "application/octet-stream"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        try:
            req = urllib.request.Request(
                self._url(path, params), headers=headers
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                content = response.read(MAX_FILE_CONTENT_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise DataNotFound("Requested data was not found.")
            if exc.code in (401, 403):
                raise DataAccessDenied("Access denied by R.E.S.C.S..")
            raise DataRetrievalFailed("R.E.S.C.S. request failed.")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DataSourceUnavailable(
                "R.E.S.C.S. service is unavailable."
            ) from exc
        except Exception as exc:
            raise DataRetrievalFailed("R.E.S.C.S. request failed.") from exc
        if len(content) > MAX_FILE_CONTENT_BYTES:
            raise DataRetrievalFailed(
                "R.E.S.C.S. file content exceeds the read limit."
            )
        return content

    @staticmethod
    def _parse_collection(data: Any) -> tuple[list[dict[str, Any]], int]:
        if isinstance(data, list):
            records = [item for item in data if isinstance(item, dict)]
            return records, len(records)
        if not isinstance(data, dict):
            raise DataRetrievalFailed("Invalid R.E.S.C.S. collection response.")
        records: list[dict[str, Any]] | None = None
        for key in ("items", "records", "data"):
            if isinstance(data.get(key), list):
                records = [item for item in data[key] if isinstance(item, dict)]
                break
        if records is None:
            raise DataRetrievalFailed("Invalid R.E.S.C.S. collection response.")
        total = data.get("total")
        if type(total) is not int or total < 0:
            total = len(records)
        return records, total

    def _collection(
        self, path: str, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int]:
        """Fetch every page of a R.E.S.C.S. collection, bounded.

        The remote default page is 100; asking for 500 keeps large
        collections from being silently truncated.
        """
        records: list[dict[str, Any]] = []
        total: int | None = None
        offset = 0
        while True:
            page_params = dict(params)
            page_params["limit"] = REMOTE_PAGE_SIZE
            page_params["offset"] = offset
            page = self._get_json(path, page_params)
            items, page_total = self._parse_collection(page)
            if total is None:
                total = page_total
            records.extend(items)
            if (
                len(records) > MAX_COLLECTION_RECORDS
                or (total is not None and total > MAX_COLLECTION_RECORDS)
            ):
                raise DataRetrievalFailed(
                    "R.E.S.C.S. collection exceeds the read limit."
                )
            if not items:
                break
            if total is not None and len(records) >= total:
                break
            if len(items) < REMOTE_PAGE_SIZE:
                break
            offset += len(items)
        return records, total if total is not None else len(records)

    def get_record(
        self, namespace: str, key: str, owner: str | None = None
    ) -> dict[str, Any]:
        effective_owner = self._check_owner(owner)
        records, _ = self._collection(
            "/api/v1/records",
            {
                "namespace": namespace,
                "key_prefix": key,
                "owner": effective_owner,
            },
        )
        for record in records:
            if record.get("namespace") != namespace or record.get("key") != key:
                continue
            if (
                effective_owner is not None
                and record.get("owner") != effective_owner
            ):
                continue
            return record
        raise DataNotFound(f"Record was not found: {namespace}/{key}.")

    def list_records(
        self,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        effective_owner = self._check_owner(owner)
        records, _ = self._collection(
            "/api/v1/records",
            {
                "namespace": namespace,
                "key_prefix": key_prefix,
                "owner": effective_owner,
            },
        )
        result = []
        for record in records:
            if namespace is not None and record.get("namespace") != namespace:
                continue
            if key_prefix is not None and not str(record.get("key", "")).startswith(
                key_prefix
            ):
                continue
            if (
                effective_owner is not None
                and record.get("owner") != effective_owner
            ):
                continue
            result.append(record)
        if offset is not None:
            result = result[offset:]
        if limit is not None:
            result = result[:limit]
        return result

    def search_records(
        self,
        query: str,
        namespace: str | None = None,
        key_prefix: str | None = None,
        owner: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        effective_owner = self._check_owner(owner)
        # Search is the ``query`` mode of the records collection.  R.E.S.C.S.
        # ignores key_prefix in that mode, so apply it (and owner/namespace)
        # locally as a fail-closed filter.
        records, _ = self._collection(
            "/api/v1/records",
            {
                "query": query,
                "namespace": namespace,
                "owner": effective_owner,
            },
        )
        result = []
        for record in records:
            if namespace is not None and record.get("namespace") != namespace:
                continue
            if key_prefix is not None and not str(record.get("key", "")).startswith(
                key_prefix
            ):
                continue
            if (
                effective_owner is not None
                and record.get("owner") != effective_owner
            ):
                continue
            result.append(record)
        if offset is not None:
            result = result[offset:]
        if limit is not None:
            result = result[:limit]
        return result

    def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        data = self._get_json(
            f"/api/v1/files/{urllib.parse.quote(file_id, safe='')}"
        )
        if not isinstance(data, dict) or not data.get("id"):
            raise DataNotFound("File was not found.")
        if self._owner_scope is not None and data.get("owner") != self._owner_scope:
            raise DataAccessDenied("Access denied for requested file owner.")
        return data

    def get_file_bytes(self, file_id: str) -> tuple[dict[str, Any], bytes]:
        # Owner is checked before any content request.
        meta = self.get_file_metadata(file_id)
        content = self._get_bytes(
            f"/api/v1/files/{urllib.parse.quote(file_id, safe='')}/content"
        )
        return meta, content


__all__ = [
    "DEFAULT_NAMESPACE",
    "AdapterDataReader",
    "HttpDataReader",
    "RescsDataReader",
]
