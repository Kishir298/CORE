"""Deterministic local R.E.S.C.S. HTTP fixture for data-layer tests.

Implements the R.E.S.C.S. v1 HTTP data contract over ``127.0.0.1``
using only the standard library. No real R.E.S.C.S. installation
required.

Endpoints::

- ``GET /health`` -> ``{service, version, status, checks}`` (no auth)
- ``GET /api/v1/records?namespace=&key_prefix=&owner=&query=&limit=&offset=``
  (``query`` switches to search, which ignores ``key_prefix``)
- ``GET /api/v1/records/{record_id}``
- ``PUT /api/v1/records`` (upsert by ``namespace/key``)
- ``POST /api/v1/records`` (create; conflict when present)
- ``DELETE /api/v1/records/{record_id}``
- ``GET /api/v1/files/{file_id}`` (metadata object, no wrapper)
- ``GET /api/v1/files/{file_id}/content`` (raw binary)

Record collection responses are ``{items, total, limit, offset}`` and
are ordered by ``(updated_at, id)`` like the real service. All routes
except ``/health`` require ``X-API-Key``.

Failure injection via :attr:`RescsFixture.fail_mode`:

- ``None`` — normal operation
- ``"unauthorized"`` — all requests answer 403
- ``"error"`` — all requests answer 500
- ``"timeout"`` — all requests sleep past the client timeout
- ``"garbage"`` — all requests answer 200 with a non-JSON body
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = "rescs-fixture-key-0123456789"
DEFAULT_OWNER = "system"
MAX_PAGE_SIZE = 500


def _seed_records():
    records = {}
    specs = [
        # (namespace, key, owner, topic, updated_day)
        ("core.memory", "flight-plan", "device-a", "pilot checklist", 12),
        ("core.memory", "pilot-notes", "device-a", "pilot observations", 10),
        ("core.memory", "shopping", "device-a", "groceries", 11),
        ("core.memory", "pilot-log", "device-b", "pilot hours", 9),
        ("core.memory", "shared-cache", "device-b", "pilot shared", 8),
        ("core.other", "pilot-misc", "device-a", "pilot misc", 7),
    ]
    for index, (namespace, key, owner, topic, day) in enumerate(specs, start=1):
        record_id = f"rec-{index:06d}"
        records[(namespace, key)] = {
            "id": record_id,
            "namespace": namespace,
            "key": key,
            "value": {"topic": topic, "index": day},
            "metadata": {"name": key},
            "owner": owner,
            "version": 1,
            "etag": f"etag-{namespace}-{key}",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": f"2026-02-{day:02d}T00:00:00+00:00",
        }
    return records


def _seed_files():
    small = b"pilot-manual-bytes"
    big = b"y" * (1024 * 1024 + 8)
    files = {}
    for file_id, content, owner in (
        ("manual", small, "device-a"),
        ("big-blob", big, "device-a"),
    ):
        files[file_id] = (
            {
                "id": file_id,
                "filename": f"{file_id}.bin",
                "mime_type": "application/octet-stream",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "etag": f"etag-{file_id}",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-02-01T00:00:00+00:00",
                "owner": owner,
            },
            content,
        )
    return files


class _Handler(BaseHTTPRequestHandler):
    server_version = "RescsFixture/0.2"

    def log_message(self, *args):  # silence test output
        pass

    def _send(self, status, payload, content_type="application/json"):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _preflight(self, fixture) -> bool:
        mode = fixture.fail_mode
        if mode == "timeout":
            time.sleep(fixture.timeout_delay)
            self._send(200, {"items": []})
            return False
        if mode == "unauthorized":
            self._send(403, {"error": "forbidden"})
            return False
        if mode == "error":
            self._send(500, {"error": "boom"})
            return False
        if mode == "garbage":
            self._send(200, "not-json{{{", "text/plain")
            return False
        return True

    def _authorized(self, fixture) -> bool:
        if not fixture.api_key:
            return True
        supplied = self.headers.get("X-API-Key", "")
        if hmac.compare_digest(supplied, fixture.api_key):
            return True
        self._send(401, {"error": "a valid X-API-Key header is required"})
        return False

    @staticmethod
    def _parts(path: str) -> list[str]:
        return [
            urllib.parse.unquote(part)
            for part in urllib.parse.urlparse(path).path.split("/")
            if part
        ]

    @staticmethod
    def _params(path: str) -> dict[str, str]:
        parsed = urllib.parse.urlparse(path)
        return {
            key: values[0]
            for key, values in urllib.parse.parse_qs(parsed.query).items()
        }

    def _json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return None
            raw = self.rfile.read(length)
            payload = json.loads(raw)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _dispatch(self, method: str):
        fixture = self.server.fixture  # type: ignore[attr-defined]
        fixture.paths.append((method, self.path))
        if not self._preflight(fixture):
            return
        parts = self._parts(self.path)
        if method == "GET" and parts == ["health"]:
            return self._send(
                200,
                {
                    "service": "rescs",
                    "version": "fixture",
                    "status": "ok",
                    "checks": {"database": "ok"},
                },
            )
        if not self._authorized(fixture):
            return
        params = self._params(self.path)
        try:
            if parts[:3] == ["api", "v1", "records"]:
                if method == "GET" and len(parts) == 3:
                    return self._record_list(fixture, params)
                if method == "GET" and len(parts) == 4:
                    return self._record_one(fixture, parts[3])
                if method == "PUT" and len(parts) == 3:
                    return self._record_put(fixture, self._json_body())
                if method == "POST" and len(parts) == 3:
                    return self._record_post(fixture, self._json_body())
                if method == "DELETE" and len(parts) == 4:
                    return self._record_delete(fixture, parts[3])
            if parts[:3] == ["api", "v1", "files"]:
                if method == "GET" and len(parts) == 3:
                    return self._file_list(fixture, params)
                if method == "GET" and len(parts) == 4:
                    return self._file_metadata(fixture, parts[3])
                if method == "GET" and len(parts) == 5 and parts[4] == "content":
                    return self._file_content(fixture, parts[3])
        except (BrokenPipeError, ConnectionResetError):
            return None
        return self._send(404, {"error": "not found"})

    def do_GET(self):
        return self._dispatch("GET")

    def do_PUT(self):
        return self._dispatch("PUT")

    def do_POST(self):
        return self._dispatch("POST")

    def do_DELETE(self):
        return self._dispatch("DELETE")

    def _filtered(self, fixture, params, query=None):
        owner = params.get("owner") or fixture.principal_owner
        records = []
        for record in fixture.records.values():
            if params.get("namespace") and record["namespace"] != params["namespace"]:
                continue
            if query is None and params.get("key_prefix") and not record["key"].startswith(
                params["key_prefix"]
            ):
                continue
            if owner and record["owner"] != owner:
                continue
            if query is not None:
                needle = query.lower()
                haystack = json.dumps(
                    [record["value"], record.get("metadata", {})],
                    sort_keys=True,
                    default=str,
                ).lower()
                if needle not in record["key"].lower() and needle not in haystack:
                    continue
            records.append(record)
        records.sort(key=lambda record: (record["updated_at"], record["id"]))
        return records

    def _page(self, fixture, params, query=None):
        try:
            limit = int(params.get("limit", "100"))
            offset = int(params.get("offset", "0"))
        except (TypeError, ValueError):
            self._send(400, {"error": "invalid pagination"})
            return None
        if limit < 1 or limit > MAX_PAGE_SIZE or offset < 0:
            self._send(400, {"error": "invalid pagination"})
            return None
        records = self._filtered(fixture, params, query)
        return records, limit, offset

    def _record_list(self, fixture, params):
        query = params.get("query")
        page = self._page(fixture, params, query or None)
        if page is None:
            return None
        records, limit, offset = page
        return self._send(
            200,
            {
                "items": records[offset : offset + limit],
                "total": len(records),
                "limit": limit,
                "offset": offset,
            },
        )

    def _record_one(self, fixture, record_id):
        record = next(
            (item for item in fixture.records.values() if item["id"] == record_id),
            None,
        )
        if record is None:
            return self._send(404, {"error": "not found"})
        if not fixture.can_access(record):
            return self._send(403, {"error": "forbidden"})
        return self._send(200, record)

    def _record_put(self, fixture, payload):
        if not payload or not all(key in payload for key in ("namespace", "key", "value")):
            return self._send(400, {"error": "namespace, key and value are required"})
        owner = payload.get("owner") or fixture.principal_owner
        existing = fixture.records.get((payload["namespace"], payload["key"]))
        if existing is not None:
            if existing["owner"] != owner:
                return self._send(403, {"error": "record owner mismatch"})
            existing["value"] = payload["value"]
            existing["metadata"] = payload.get("metadata") or {}
            existing["version"] += 1
            existing["etag"] = f"etag-{existing['id']}-{existing['version']}"
            existing["updated_at"] = fixture.now()
            return self._send(200, existing)
        record = fixture.new_record(
            payload["namespace"],
            payload["key"],
            payload["value"],
            payload.get("metadata") or {},
            owner,
        )
        return self._send(200, record)

    def _record_post(self, fixture, payload):
        if not payload or not all(key in payload for key in ("namespace", "key", "value")):
            return self._send(400, {"error": "namespace, key and value are required"})
        if (payload["namespace"], payload["key"]) in fixture.records:
            return self._send(409, {"error": "record already exists"})
        owner = payload.get("owner") or fixture.principal_owner
        record = fixture.new_record(
            payload["namespace"],
            payload["key"],
            payload["value"],
            payload.get("metadata") or {},
            owner,
        )
        return self._send(201, record)

    def _record_delete(self, fixture, record_id):
        natural_key = next(
            (
                key
                for key, item in fixture.records.items()
                if item["id"] == record_id
            ),
            None,
        )
        if natural_key is None:
            return self._send(404, {"error": "not found"})
        del fixture.records[natural_key]
        return self._send(204, b"")

    def _file_metadata(self, fixture, file_id):
        entry = fixture.files.get(file_id)
        if entry is None:
            return self._send(404, {"error": "not found"})
        meta, _content = entry
        return self._send(200, meta)

    def _file_content(self, fixture, file_id):
        entry = fixture.files.get(file_id)
        if entry is None:
            return self._send(404, {"error": "not found"})
        _meta, content = entry
        return self._send(200, content, "application/octet-stream")

    def _file_list(self, fixture, params):
        owner = params.get("owner") or fixture.principal_owner
        items = [
            meta
            for meta, _content in fixture.files.values()
            if not owner or meta["owner"] == owner
        ]
        return self._send(
            200,
            {"items": items, "total": len(items), "limit": len(items), "offset": 0},
        )


class RescsFixture:
    """Running deterministic R.E.S.C.S. HTTP fixture (context-managed)."""

    def __init__(self, api_key: str | None = API_KEY):
        self.records = _seed_records()
        self.files = _seed_files()
        self.api_key = api_key
        self.principal_owner = DEFAULT_OWNER
        self.fail_mode: str | None = None
        self.timeout_delay = 5.0
        self.paths: list[tuple[str, str]] = []
        self._next = len(self.records) + 1
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        """Return the fixture base URL (valid after start)."""
        assert self._server is not None, "fixture is not running"
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def can_access(self, _record) -> bool:
        return True

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")

    def new_record(self, namespace, key, value, metadata, owner):
        record_id = f"rec-{self._next:06d}"
        self._next += 1
        moment = self.now()
        record = {
            "id": record_id,
            "namespace": namespace,
            "key": key,
            "value": value,
            "metadata": metadata,
            "owner": owner,
            "version": 1,
            "etag": f"etag-{record_id}-1",
            "created_at": moment,
            "updated_at": moment,
        }
        self.records[(namespace, key)] = record
        return record

    def start(self) -> RescsFixture:
        """Start serving on an ephemeral localhost port."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.fixture = self  # type: ignore[attr-defined]
        server.daemon_threads = True
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Shut down cleanly."""
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None
        if self._thread is not None:
            try:
                self._thread.join(timeout=5)
            except Exception:
                pass
            self._thread = None

    def __enter__(self) -> RescsFixture:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


__all__ = ["API_KEY", "RescsFixture"]
