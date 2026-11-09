# R.E.S.C.S. HTTP API

Interactive documentation is generated automatically at `/docs` (Swagger UI)
and `/redoc`. Versioned under `/api/v1`.

## Convention

- **Authentication**: every `/api/v1` route requires the `X-API-Key` header
  matching the configured `RESCS_API_KEY` (min 16 chars). Health and
  introspection endpoints (`/health*`, `/`, `/docs`) are open.
- **Owner scoping**: when `RESCS_API_KEY_OWNER` is set, all requests are
  locked to that single owner; writes claiming a different `owner` and reads
  of another owner's resource are rejected (`401`/`403`). Otherwise the
  requester supplies `owner` freely (default `system`).
- **Request correlation**: every HTTP request is assigned a request id
  (`X-Request-ID`), which is echoed back on the response for tracing/audit.
  A caller-supplied `X-Request-ID` matching `^[A-Za-z0-9._-]{1,128}$` is
  honoured when present; otherwise one is generated. The header name is
  configurable via `RESCS_REQUEST_ID_HEADER` (default `X-Request-ID`).
- Requests/responses are JSON unless noted (file uploads/downloads are
  binary multipart).
- List endpoints paginate with `limit` (1..500, default 100) and `offset`.
- Every error follows the envelope:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "record not found",
    "details": { "id": "..." }
  }
}
```

| HTTP | Code | Meaning |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | malformed request semantics |
| 401 | `UNAUTHORIZED` | missing/invalid credentials |
| 403 | `FORBIDDEN` | authenticated but not allowed |
| 403 | `QUOTA_EXCEEDED` | per-owner quota reached (see `docs/quotas.md`) |
| 404 | `NOT_FOUND` | unknown resource (incl. soft-deleted/expired via ordinary reads) |
| 409 | `CONFLICT` | violates uniqueness (incl. restore onto a live key) |
| 412 | `PRECONDITION_FAILED` | stale `If-Match` etag; re-read and retry |
| 413 | `PAYLOAD_TOO_LARGE` | file/metadata exceeds configured caps |
| 422 | `VALIDATION_ERROR` | body fails validation |
| 429 | `RATE_LIMITED` | in-memory limiter enabled and bucket exceeded (see `docs/rate-limiting.md`) |
| 500 | `STORAGE_ERROR` / `INTERNAL_ERROR` | storage/backend failure |
| 503 | `DEPENDENCY_UNAVAILABLE` | database/object store unreachable |

## Records

### Create

```
POST /api/v1/records        -> 201 Record
```

```json
{ "namespace": "default", "key": "profile", "value": { "name": "x" }, "metadata": {} }
```

Adding an `idempotency_key` makes the create idempotent (same key returns the
existing record).

### Upsert by namespace/key

```
PUT /api/v1/records         -> 200 Record
```

Creates or replaces the record for `(namespace, key)`; bumps `version`.

### Read

```
GET /api/v1/records/{id}    -> 200 Record
```

### Partial update

```
PATCH /api/v1/records/{id}  -> 200 Record
```

Body may contain any of `value`, `metadata`, `namespace`, `key`. Version is
incremented and the etag recomputed.

### Delete (soft)

```
DELETE /api/v1/records/{id} -> 204
```

Soft-deletes: metadata is preserved as a tombstone but hidden from ordinary
reads/lists. See `docs/lifecycle.md`.

### Restore / purge

```
POST   /api/v1/records/{id}/restore -> 200 Record
DELETE /api/v1/records/{id}/purge   -> 204
```

Both honor `If-Match`. Restoring onto a live `(namespace, key)` occupant is
`409`; restoring a live resource is `400`.

### Bulk

```
POST /api/v1/records/bulk -> 200 {"results": [...]}
```

Bounded batch of create/put/delete/restore/purge with per-item statuses;
partial failure is explicit. See `docs/quotas.md`.

### List / search

```
GET /api/v1/records?namespace=&key_prefix=&owner=&limit=&offset=
GET /api/v1/records?query=blue&namespace=&owner=&limit=&offset=
GET /api/v1/records?tags=a&tags=b&created_after=&updated_before=
```

`query` performs a case-insensitive substring search across key, value and
metadata. `key_prefix` filters the key without searching content. `tags`
(repeatable) requires all listed tags. `include_deleted` / `include_expired`
opt into tombstones/expired rows (owner scope still applies). Response:

```json
{ "items": [Record, ...], "total": 7, "limit": 100, "offset": 0 }
```

## Files

### Upload

```
POST /api/v1/files          -> 201 File (multipart/form-data)
```

Field: `upload` (the file bytes). Filename and Content-Type are taken from
the part. The server computes `size`, `sha256` and `etag`. Optional form
fields: repeatable `tags`, ISO-8601 `expires_at`.

### Metadata

```
GET /api/v1/files/{id}      -> 200 File
```

### Download

```
GET /api/v1/files/{id}/content -> 200 bytes
```

Response headers: `Content-Type`, `Content-Disposition`, `ETag`,
`X-File-SHA256`, `X-File-Size`.

### Delete (soft)

```
DELETE /api/v1/files/{id}         -> 204
POST   /api/v1/files/{id}/restore -> 200 File
DELETE /api/v1/files/{id}/purge   -> 204
```

Soft delete retains the blob for instant restore; purge removes metadata
and blob. Restoring a file whose blob is missing is `500 STORAGE_ERROR`.

### List

```
GET /api/v1/files?owner=&tags=&mime_type=&size_min=&size_max=&limit=&offset=
```

Time-window (`created_after/before`, `updated_after/before`) and
`include_deleted` / `include_expired` filters mirror the record API.

## Administration

```
POST /api/v1/admin/cleanup            -> 200 {dry_run, records_purged, files_purged, uploads_cleaned, audit_pruned}
GET  /api/v1/admin/audit?...          -> 200 AuditPage
GET  /api/v1/admin/records/deleted... -> 200 RecordPage
GET  /api/v1/admin/files/deleted...   -> 200 FileObjectPage
```

Cleanup accepts `{"dry_run": bool, "batch": 1..5000}` and purges expired
records/files plus audit events older than `RESCS_AUDIT_RETENTION_DAYS`.
See `docs/lifecycle.md`.

## Uploads (resumable)

```
POST   /api/v1/uploads -> 201 create session {owner, filename, content_type?, total_size, chunk_size?, checksum?, metadata?, tags?}
PUT    /api/v1/uploads/{id}/chunks?offset=N (or Content-Range) -> 200 append chunk (offset-checked)
GET    /api/v1/uploads/{id} -> 200 session status
POST   /api/v1/uploads/{id}/finalize -> 200 File (SHA-256 verified)
DELETE /api/v1/uploads/{id} -> 204 cancel
```
Upload sessions expire server-side (+24h, `expires_at`); create takes no
`expires_at`/`ttl_seconds`. Chunk bodies are bounded to `chunk_size`
(`RESCS_MAX_FILE_SIZE` when smaller); oversize is `413 PAYLOAD_TOO_LARGE`.
See `docs/uploads.md`.

## Contract

```
GET /api/v1/contract -> machine-readable CORE contract (requires X-API-Key)
```

Errors include `429 RATE_LIMITED` when the in-memory limiter is enabled (see `docs/rate-limiting.md`; also listed in contract).

## Health

```
GET /health/live    -> process liveness (always 200 when the process runs)
GET /health/ready   -> dependency readiness (database, storage)
GET /health         -> full status (service + version + checks)
```

- **Liveness** (`/health/live`) reports `{"status":"alive",...}` and never
  probes dependencies. It is public (no `X-API-Key`).
- **Readiness** (`/health/ready`) reports
  `{"status":"ready"|"not_ready","checks":{"database":"ok"|"down","storage":"ok"|"down"}}`.
  Healthy dependencies yield `200 ready`; any `down`/`degraded` dependency
  yields **`503 not_ready`** with the same body shape. Checks never expose
  connection strings, credentials, SQL or tracebacks.
- **Summary** (`/health`) returns `{service, version, status, checks}` with
  `200` when healthy and `503` when any dependency is down/degraded.
- Every health response (success and `503`) echoes `X-Request-ID` (see
  Request correlation above and `docs/observability.md`).

## Record / File document shapes

```
Record {
  id, namespace, key, value, metadata, owner,
  version, idempotency_key, etag, created_at, updated_at,
  tags, expires_at, deleted_at, deleted_by
}
File {
  id, filename, mime_type, size, storage_path, sha256, metadata, owner,
  version, idempotency_key, etag, created_at, updated_at,
  tags, expires_at, deleted_at, deleted_by
}
(`ttl_seconds` is input-only for create/update; reads expose `expires_at`.)
Audit {
  id, timestamp, operation, resource_type, resource_id, owner,
  request_id, outcome, error_code
}
```
