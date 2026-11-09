# R.E.S.C.S. ↔ C.O.R.E. Integration Contract

This document is the **contract** between the C.O.R.E. subsystem (operation
gateway / knowledge coordinator) and R.E.S.C.S. (storage). C.O.R.E. and
R.E.S.C.S. are independent projects: they are built, versioned and released
separately and **never import each other**. The only shared surface is the one
below — HTTP + the envelope + the reserved namespaces.

## Roles

- **C.O.R.E.** is the caller. It persists operational state (RUNNABLES,
  Ops), provides the knowledge store (IDEAS), and coordinates the ecosystem.
- **R.E.S.C.S.** is the callee. It stores documents (records) and binary
  files, and it never initiates calls into C.O.R.E.
- Runtime discovery: `GET /api/v1/contract` returns this contract as data so
  C.O.R.E. does not hard-code capabilities.

## Transport

- Base URL is the deployed R.E.S.C.S. instance over HTTPS.
- Every API call requires `X-API-Key: <RESCS_API_KEY>` (min 16 chars).
  Missing/invalid keys get `401 {"error":{"code":"UNAUTHORIZED",...}}`.
- Resources always live under `/api/v1`. Interactive schema: `/docs`.

## Envelope

Requests and responses are JSON with no wrapper. Errors use a stable envelope:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "record not found",
    "details": { "id": "..." }
  }
}
```

`code` is a stable machine-readable string (see table); `message` is
human-readable; `details` is optional structured context. Clients should switch
on `code`, never on the HTTP status alone.

| HTTP | code | C.O.R.E. reaction |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | fix request |
| 401 | `UNAUTHORIZED` | refresh API key |
| 403 | `FORBIDDEN` | owner conflict; do not retry |
| 403 | `QUOTA_EXCEEDED` | quota reached; free resources or retry later |
| 404 | `NOT_FOUND` | treat storage state as absent (incl. deleted/expired) |
| 409 | `CONFLICT` | duplicate within namespace; re-check |
| 412 | `PRECONDITION_FAILED` | re-read, then retry with new etag |
| 429 | `RATE_LIMITED` | back off; retry after window (only when limiter enabled) |
| 413 | `PAYLOAD_TOO_LARGE` | shrink file/metadata; check configured caps |
| 422 | `VALIDATION_ERROR` | fix body |
| 500 | `STORAGE_ERROR` | backend fault; retry after backoff |
| 503 | `DEPENDENCY_UNAVAILABLE` | database/object store down; retry after backoff |

## Namespaces

R.E.S.C.S. stores every record under `(namespace, key, owner)`. Two prefixes
are reserved to keep the ecosystem tidy:

| Reserved prefix | Intended use |
| --- | --- |
| `core.*` | C.O.R.E. state: e.g. `core.ops.runnables`, `core.ideas`, `core.memory` |
| `rescs.*` | RESCS-internal bookkeeping |

C.O.R.E. SHOULD use distinct keys per logical document and one `owner` value
per deployment/tenant (see Owner scoping). Examples:

```
namespace: core.ops.runnables   key: <runnable-id>      value: {state, provenance, outputs}
namespace: core.ideas           key: <idea-id>          value: {prompt, neighbor_links, memory_xrefs}
namespace: core.memory          key: <source-uri>       value: {sha256, mined, embeddings_ref}
```

## Guarantees R.E.S.C.S. provides

1. **Identity and ordering** — every record/file carries `version` (monotonic,
   starts at 1) and `created_at`/`updated_at` (UTC). Version bumps on every
   content-changing write.
2. **Content addressing** — records carry a content `etag`
   (`sha256(canonical(value, metadata, sorted(tags)))`; untagged records
   hash exactly as in v0.1); files carry `etag` (from
   `sha256(blob):size`) plus `sha256` and `size` so C.O.R.E. can dedupe
   identical payloads.
3. **Optimistic concurrency** — mutations accept `If-Match: <etag>`. A stale
   etag yields `412 PRECONDITION_FAILED` with `current_etag` in `details`.
   C.O.R.E. MUST re-read and retry rather than blindly overwrite.
4. **Idempotent creates** — identical `idempotency_key` on repeated
   `POST /api/v1/records` / `POST /api/v1/files` returns the previously stored
   result. Safe client retries.
5. **Blob integrity** — file downloads verify the stored bytes against
   `sha256` before streaming (`X-File-SHA256`, `X-File-Size`, `ETag` response
   headers) and refuse corrupted blobs with `STORAGE_ERROR`.
6. **Pagination** — list/search return `{items, total, limit, offset}`;
   `limit` is 1..500 (default 100), `offset >= 0`.
7. **Owner scoping** — when `RESCS_API_KEY_OWNER` is configured, the key is
   locked to that single owner (single-tenant deployment). Otherwise callers
   supply `owner` (default `system`).
8. **Recoverable deletion** — `DELETE` tombstones (hidden from ordinary
   reads, key released); `POST .../restore` recovers; `DELETE .../purge`
   removes permanently. Restore onto a live key is `409`.
9. **TTL** — optional `expires_at` (UTC); expired rows read as absent and
   are reclaimed by writes; physical removal via `POST /api/v1/admin/cleanup`.
10. **Bulk** — `POST /api/v1/records/bulk` applies bounded batches with
    per-item statuses; partial failure is explicit.
11. **Governance** — per-owner quotas and size caps (`RESCS_MAX_*`);
    exhaustion is `403 QUOTA_EXCEEDED` / `413 PAYLOAD_TOO_LARGE`.
12. **Audit** — mutations are recorded secret-free and inspectable at
    `GET /api/v1/admin/audit` (see `docs/lifecycle.md`).

## C.O.R.E. integration conventions

- Prefer PUT upserts (`PUT /api/v1/records`) or idempotent POST for Ops state,
  so restarts re-converge.
- Before overwriting a RUNNABLE that may have been updated concurrently,
  send `If-Match: <etag>` from the last read; on `412`, re-read and merge.
- Read IDEAS with the search endpoint (`GET /api/v1/records?query=...`) for
  neighbor discovery, and use `metadata.neighbor_links` for the graph.
- Store large mined artifacts as files, and reference them from record
  metadata by file id, keeping database rows small.

## Database note

If C.O.R.E. and R.E.S.C.S. share a PostgreSQL deployment, each keeps its own
schema and migration story. R.E.S.C.S. touches **only** its own tables
(`records`, `file_objects`, `audit_events`, `schema_info`) and is configured
with its own `DATABASE_URL`. The API above is the supported integration path;
direct cross-schema queries are out of contract.
