# R.E.S.C.S. Organization & Governance: Tags, Search, Bulk, Quotas

## Tags & metadata (Phase 18)

Records and files carry `tags: list[str]` (up to 50 tags/resource, 1–64 chars each,
`[A-Za-z0-9._-]`; violations are `422`). Tags are part of the record ETag
(sorted before hashing, so order never affects identity); records without
tags hash exactly as in v0.1. Serialized metadata is capped by
`RESCS_MAX_METADATA_BYTES` (default 64 KB); oversized metadata is
`413 PAYLOAD_TOO_LARGE`.

## Search & filtering (Phase 19)

List endpoints accept (all optional, combinable, paginated as before):

- records: `tags` (repeatable, all-match), `created_after/before`,
  `updated_after/before` (ISO-8601), `include_deleted`, `include_expired`;
- files: the above plus `mime_type`, `size_min`, `size_max`;
- search (`?query=`) additionally accepts `tags`, `include_deleted`,
  `include_expired`.

Ordering is deterministic (`updated_at`, then `id`; deleted listings use
`deleted_at`). Existing search semantics and the `{items, total, limit,
offset}` envelope are unchanged. Owner scoping applies to every filter —
no cross-owner leakage. Expired resources are always excluded unless
`include_expired=true`.

## Bulk operations (Phase 20)

```
POST /api/v1/records/bulk
{
  "operations": [
    {"op": "create", "record": {...}},
    {"op": "put", "record": {...}, "if_match": "<etag>"},
    {"op": "delete", "id": "..."},
    {"op": "restore", "id": "..."},
    {"op": "purge", "id": "..."}
  ]
}
```

Response: `{"results": [{"index": 0, "status": "created", "id": "..."},
{"index": 2, "status": "error", "code": "NOT_FOUND", ...}]}`.

Semantics: batch bounded by `RESCS_MAX_BULK_BATCH` (default 100, max 1000;
over-limit is `400`); per-item independent execution with explicit
per-item statuses (partial failure is normal and reported, never silent);
each item individually enforces ownership, ETags, idempotency, and quotas.

## Quotas & limits (Phase 21)

Configured through `RESCS_MAX_*` (`0` = unlimited). Enforcement is
server-side in the service layer on every write path:

| Limit | Applies to | Failure |
| --- | --- | --- |
| `MAX_RECORDS_PER_OWNER` | record creates/upsert-creates | `403 QUOTA_EXCEEDED` |
| `MAX_FILES_PER_OWNER` | uploads | `403 QUOTA_EXCEEDED` |
| `MAX_BYTES_PER_OWNER` | uploads (used + size) | `403 QUOTA_EXCEEDED` |
| `MAX_FILE_SIZE` | upload bytes | `413 PAYLOAD_TOO_LARGE` |
| `MAX_METADATA_BYTES` | record/file metadata | `413 PAYLOAD_TOO_LARGE` |
| `MAX_BULK_BATCH` | bulk request size | `400 INVALID_REQUEST` |

Accounting counts live, non-expired resources per owner (deleted and
expired rows stop consuming quota, encouraging cleanup). Counts are
best-effort under concurrency (check-then-act; document, don't oversell).

Locked mode: when `RESCS_API_KEY_OWNER` is set, every request is scoped to
that single owner (writes claiming another `owner` are `401`, reads of
another owner's resource are `403`); quotas then apply to the locked owner
only.

