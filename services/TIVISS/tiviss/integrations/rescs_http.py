"""Real R.E.S.C.S. client over HTTP (stdlib only).

Speaks the versioned R.E.S.C.S. records API with ``urllib``: no third-party
HTTP client, no bundled R.E.S.C.S. code. Authentication is a single
``X-API-Key`` header; the key is never logged. Records are confined to
``tiviss.*`` namespaces by default (see :mod:`tiviss.integrations.domains`
conventions in the sibling workstream); any other namespace requires
explicit opt-in.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

DEFAULT_NAMESPACE_PREFIX = "tiviss."
API_VERSION = "v1"


class RescsClientError(RuntimeError):
    """Transport or API failure talking to R.E.S.C.S."""

    def __init__(self, message: str, *, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _redacted_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key, "Content-Type": "application/json"}


class RescsHttpClient:
    """Minimal R.E.S.C.S. records client (namespace-guarded)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        owner: str = "tiviss",
        timeout_s: float = 10.0,
        allow_foreign_namespaces: bool = False,
    ) -> None:
        if not (isinstance(base_url, str) and base_url.strip()):
            raise RescsClientError("base_url must be a non-empty string")
        if not (isinstance(api_key, str) and len(api_key) >= 1):
            raise RescsClientError("api_key must be a non-empty string")
        if timeout_s is not None and (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, (int, float))
            or not timeout_s > 0
        ):
            raise RescsClientError("timeout_s must be a positive number of seconds")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.owner = owner
        self.timeout_s = float(timeout_s)
        self.allow_foreign_namespaces = bool(allow_foreign_namespaces)

    def _check_namespace(self, namespace: str) -> str:
        if not (isinstance(namespace, str) and namespace):
            raise RescsClientError("namespace must be a non-empty string")
        if not self.allow_foreign_namespaces and not namespace.startswith(
            DEFAULT_NAMESPACE_PREFIX
        ):
            raise RescsClientError(
                f"namespace {namespace!r} is outside {DEFAULT_NAMESPACE_PREFIX!r}"
            )
        return namespace

    def _call(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/api/{API_VERSION}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in dict(query).items() if v is not None}
            )
        data = None
        headers = _redacted_headers(self._api_key)
        if body is not None:
            try:
                data = json.dumps(dict(body)).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise RescsClientError(f"body is not JSON-serializable: {exc}") from exc
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except OSError as exc:
            raise RescsClientError(f"request failed: {exc}") from exc
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise RescsClientError(f"invalid JSON response: {exc}") from exc

    @staticmethod
    def _http_error(exc: urllib.error.HTTPError) -> RescsClientError:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, ValueError):
            payload = {}
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        return RescsClientError(
            f"rescs error: {error.get('message', exc.reason)}",
            code=str(error.get("code", "")),
            status=int(exc.code or 0),
        )

    # -- records ---------------------------------------------------------

    def create_record(
        self,
        *,
        namespace: str,
        key: str,
        value: Mapping[str, Any],
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a record; returns the created representation."""
        body = {
            "namespace": self._check_namespace(namespace),
            "key": key,
            "value": dict(value),
            "owner": self.owner,
            "tags": list(tags or []),
        }
        result = self._call("POST", "/records", body=body)
        if not isinstance(result, dict):
            raise RescsClientError("unexpected create response")
        return result

    def get_record(self, record_id: str) -> dict[str, Any]:
        """Fetch one record by ID."""
        result = self._call("GET", f"/records/{urllib.parse.quote(record_id, safe='')}")
        if not isinstance(result, dict):
            raise RescsClientError("unexpected get response")
        return result

    def update_record(
        self,
        record_id: str,
        fields: Mapping[str, Any],
        *,
        if_match: str | None = None,
    ) -> dict[str, Any]:
        """Partial update; ``if_match`` carries an etag for concurrency."""
        query = {"if_match": if_match} if if_match else None
        result = self._call(
            "PATCH", f"/records/{urllib.parse.quote(record_id, safe='')}",
            query=query, body=fields,
        )
        if not isinstance(result, dict):
            raise RescsClientError("unexpected update response")
        return result

    def delete_record(self, record_id: str) -> dict[str, Any]:
        """Soft-delete a record."""
        result = self._call(
            "DELETE", f"/records/{urllib.parse.quote(record_id, safe='')}"
        )
        return result if isinstance(result, dict) else {}

    def list_records(
        self,
        *,
        namespace: str,
        limit: int = 100,
        key_prefix: str | None = None,
    ) -> dict[str, Any]:
        """List records in a namespace (namespace-guarded)."""
        result = self._call(
            "GET",
            "/records",
            query={
                "namespace": self._check_namespace(namespace),
                "owner": self.owner,
                "limit": limit,
                "key_prefix": key_prefix,
            },
        )
        if not isinstance(result, dict):
            raise RescsClientError("unexpected list response")
        return result

    def search_records(
        self, query: str, *, namespace: str, limit: int = 100
    ) -> dict[str, Any]:
        """Full-text search confined to a namespace (namespace-guarded)."""
        result = self._call(
            "GET",
            "/records",
            query={
                "query": query,
                "namespace": self._check_namespace(namespace),
                "owner": self.owner,
                "limit": limit,
            },
        )
        if not isinstance(result, dict):
            raise RescsClientError("unexpected search response")
        return result
