# R.E.S.C.S. Synchronization and Consistency

R.E.S.C.S. gives clients everything they need to keep a local/remote copy
consistent with the stored state: a monotonic `version`, a content-derived
`etag`, idempotent creates, and conditional (optimistic concurrency) writes.

## Conflict model

Every modification that touches content (except delete) bumps `version` by 1
and recomputes `etag`. `updated_at` reflects the mutation time. A client
therefore always knows:

- **current version** — a strict ordering counter for a single document;
- **current etag** — a fingerprint of `(value, metadata)` for records and of
  `(sha256, size)` for files, so identical documents share an etag and a
  document is only "changed" when it is actually different.

| Field | Records | Files |
| --- | --- | --- |
| `version` | incremented on create (1) and every update/put | incremented on upload (1) |
| `etag` | `sha256(canonical(value, metadata))` | `sha256(sha256(blob):size)` |
| `idempotency_key` | optional, stored | optional, stored |
| `created_at` / `updated_at` | UTC ISO-8601 | UTC ISO-8601 |

## Optimistic concurrency (If-Match)

Mutations accept an optional `If-Match` header. If the header is present and
does **not** match the document's current etag, R.E.S.C.S. refuses the write
with `412 PRECONDITION_FAILED` and returns the `current_etag` in `details`,
so the caller can re-read and retry.

```
PATCH  /api/v1/records/{id}     If-Match: <etag>
PUT    /api/v1/records          If-Match: <etag>
DELETE /api/v1/records/{id}     If-Match: <etag>
DELETE /api/v1/files/{id}       If-Match: <etag>
```

- Bare etag (canonical form), RFC 9110 quoted `"..."`, and weak `W/"..."`
  values are all accepted.
- `If-Match: *` means "only if the resource exists" and maps to no etag
  constraint (a missing resource already yields `404`).
- A `PUT` with `If-Match` against a record that does not exist returns `412`
  (the caller guards against clobbering; use PUT without `If-Match` to
  create-or-replace).

Every read/201/200 mutation response carries the current `ETag` header, and
every document carries its `etag` in the body.

## Idempotent creates

Passing the same `idempotency_key` on consecutive create/upload calls
(`POST /api/v1/records`, `POST /api/v1/files`) returns the **existing**
record/file instead of creating a duplicate. This makes retries safe:

```json
{ "namespace": "n", "key": "k", "value": {},
  "idempotency_key": "order-123-retry-1" }
```

Idempotency is checked on the shared key regardless of payload equality, so a
retry with an identical key always converges to the first stored result.

Idempotency keys are single-lifecycle: replaying a key that belongs to a
**deleted** resource is `409 CONFLICT` (purge the tombstone or use a new
key); replaying a key whose resource **expired** transparently replaces it.

## Lifecycle and concurrency

- Soft delete and restore are versioned mutations (`version` + 1) that keep
  the content etag; both honor `If-Match`.
- Restore onto a live `(namespace, key)` occupant is `409 CONFLICT` with the
  occupant id in `details` — never a silent overwrite.
- Record etags cover `(value, metadata, tags)` with tags sorted; tag order
  never changes identity, and untagged records hash exactly as in v0.1.
- Bulk items each enforce ETags/idempotency independently; per-item `412` /
  `409` results are explicit, never silent.

## Blob integrity

`GET /api/v1/files/{id}/content` verifies the stored bytes match
`sha256` before streaming: a corrupted or substituted blob raises
`500 STORAGE_ERROR` with `expected_sha256` / `actual_sha256` in `details`.
The response also includes `X-File-SHA256`, `X-File-Size` and `ETag` headers
for client-side verification.
