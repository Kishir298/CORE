# Resumable Uploads

`POST /api/v1/files` streams single-shot uploads (bounded memory via spool +
`put_stream`). For large/interrupted transfers use sessions:

## Flow

1. `POST /api/v1/uploads {filename, content_type, total_size, chunk_size, checksum?, metadata?, tags?}` → `201 {id, received_bytes:0, expires_at (+24h)}`
   - `chunk_size` 64KiB–64MiB, default 8MiB. `total_size` must respect `RESCS_MAX_FILE_SIZE`.
2. `PUT /api/v1/uploads/{id}/chunks?offset=N` (raw bytes, or `Content-Range: bytes N-M/T`) → `200 {received_bytes}`
   - Duplicate identical chunk is idempotent; conflicting bytes at same offset → `409`.
   - Chunks outside `[0,total)` → `400`. Empty chunks → `400`.
   - Intermediate (non-final) chunks must equal `chunk_size`; only the final chunk may be smaller.
3. `GET /api/v1/uploads/{id}` → status.
4. `POST /api/v1/uploads/{id}/finalize` → `200 FileObject`. Streams chunks sequentially via `get_stream` → incremental SHA-256 → `put_stream` (no full-file RAM buffering); gaps → `400`, checksum mismatch → `400`, expired → `404`, concurrent second finalize → `409` (single winner). Atomic publish; no partial file visible.
5. `DELETE /api/v1/uploads/{id}` → cancel (`204`), chunks cleaned. Unknown/expired ids → `404` without touching other owners' data.

## Rules

- Owner-isolated (service-level lock check + router check); expired sessions read as `404` and are reclaimed by `POST /api/v1/admin/cleanup` (`uploads_cleaned`).
- Quotas (`max_file_size/metadata/files/bytes`) enforced at finalize with post-write rollback; failed finalization leaves no file and resets session to `active` for retry/cancel.
- Concurrent finalize is safe within one process: first wins, second sees closed session (`409`). Single-instance lock + status transition; cross-process single-winner requires a DB-level conditional status update (not yet implemented).

