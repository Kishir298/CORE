# R.E.S.C.S. Lifecycle: Soft Delete, TTL, Cleanup, Audit

v0.2 resource-lifecycle model. Ordinary operations only ever see **live,
non-expired** resources; recovery and administration happen through explicit
endpoints.

## Soft delete & recovery (Phase 14)

`DELETE /api/v1/records/{id}` (and `/files/{id}`) tombstones the resource:

- metadata is preserved with `deleted_at` / `deleted_by`, `version` + 1;
- normal `GET`/`LIST`/`SEARCH`/download behave as `404 NOT_FOUND`;
- file blobs are **retained** so restore is instant;
- the `(namespace, key)` reservation is released: only live rows are unique,
  so the key can be reused while the tombstone exists.

Recovery:

```
POST   /api/v1/records/{id}/restore   -> 200 Record
DELETE /api/v1/records/{id}/purge     -> 204 (permanent)
POST   /api/v1/files/{id}/restore     -> 200 File
DELETE /api/v1/files/{id}/purge       -> 204 (metadata + blob removed)
```

Rules:

- Restoring a live resource is `400 INVALID_REQUEST`.
- Restoring onto a live `(namespace, key)` occupant is `409 CONFLICT`
  (purge the occupant or the tombstone first).
- Restoring a file whose blob is missing is `500 STORAGE_ERROR` (never a
  dangling metadata resurrection).
- Restore/purge honor `If-Match` like other mutations.
- Idempotency keys stay bound for the key's lifetime: replaying a key that
  belongs to a deleted resource is `409 CONFLICT` (purge frees the key).
- Recovery listings: `GET ...?include_deleted=true` and
  `GET /api/v1/admin/records/deleted`, `GET /api/v1/admin/files/deleted`
  (owner scoping enforced).

## TTL & expiration (Phase 15)

Records/files/uploads accept optional UTC `expires_at` (ISO-8601; naive assumed UTC; past values `400`) and/or `ttl_seconds` (0..RESCS_MAX_TTL_SECONDS; mutually exclusive with `expires_at` — supplying both is `400`):

- expired resources behave as absent for ordinary operations (`404`/excluded
  from lists), but remain visible with `include_expired=true`;
- writes transparently reclaim expired occupants (PUT/upsert replaces them,
  no `409`);
- restoring an expired tombstone keeps its `expires_at` (data is never
  silently rewritten); it stays expired-filtered until cleaned or replaced.

There is no background scheduler. Expiry is enforced deterministically at
read/write time; physical removal happens through explicit cleanup:

```
POST /api/v1/admin/cleanup
{"dry_run": false, "batch": 500}   # batch: 1..5000, default 500
-> {"dry_run": false, "records_purged": N, "files_purged": M, "uploads_cleaned": U, "audit_pruned": K}
```

`dry_run: true` reports counts without changing anything. File cleanup
removes blobs as well as metadata. Expired rows are purged regardless of
tombstone state.

## Audit trail (Phase 22)

Mutations (`create/put/update/delete/restore/purge`, uploads, downloads,
bulk, cleanup) append to the `audit_events` table with timestamp, operation,
resource type/id, owner, request ID, outcome (`ok`/`error`/`denied`) and
error code. Failures are recorded with the resource identity where known.
Audit writes are best-effort and never fail the primary operation.

Never stored: API keys, headers, record values/metadata contents, file
bytes, connection strings, tracebacks.

```
GET /api/v1/admin/audit?owner=&operation=&since=&limit=&offset=
```

Owner scoping applies. Retention: admin cleanup prunes events older than
`RESCS_AUDIT_RETENTION_DAYS` (`0` = keep forever).

