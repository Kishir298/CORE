# R.E.S.C.S. File Storage

## Separation of metadata and bytes

Large binary payloads never live inside database rows. Each file is split
into:

- **Metadata** — `file_objects` database row: id, filename, MIME type, size,
  SHA-256, owner, version, etag, timestamps.
- **Blob** — the raw bytes in an object store, addressed by the file id.

```
FileService
    |                          [
    +-- metadata  ->  FileObjectRepository (PostgreSQL / SQLite host)
    |
    +-- blob      ->  ObjectStore  (local filesystem now,
                                    S3-compatible backend implemented (+ fake for tests))
```

## Object store abstraction

`rescs/interfaces/object_store.py` defines a `Protocol` with:

```
put(object_id, data) -> None
get(object_id) -> bytes          # raises StorageError when missing
delete(object_id) -> None
exists(object_id) -> bool
put_stream(object_id, chunks) -> None   # bounded-memory write
get_stream(object_id, chunk_size=1MiB) -> Iterator[bytes]  # bounded-memory read
size(object_id) -> int
```

Implemented backends:

| Backend | Location | Use |
| --- | --- | --- |
| `LocalObjectStore` | `rescs/storage/local.py` | local filesystem under `RESCS_STORAGE_DIR` (default) |
| `MemoryObjectStore` | `rescs/storage/memory.py` | deterministic test double |
| `S3ObjectStore` / `FakeS3ObjectStore` | `rescs/storage/s3.py` | S3-compatible live backend (`boto3` extra) / in-memory fake for tests |

A cloud object store implements the same protocol; the storage service and
API are unchanged.

## File lifecycle

- **Create/upload** — bytes hashed (SHA-256), written to the object store,
  then metadata recorded. If the metadata write fails the blob is cleaned up.
  Governance caps (`RESCS_MAX_FILE_SIZE`, byte quotas) are enforced first.
- **Read/download** — metadata read from the repository, bytes read from the
  store. Metadata without a blob surfaces as `STORAGE_ERROR`. Deleted and
  expired files read as `404`.
- **Delete (soft)** — metadata tombstoned (`deleted_at`/`deleted_by`); the
  blob is **retained** so restore is instant.
- **Restore** — tombstone cleared (version + 1); refused with `STORAGE_ERROR`
  if the blob went missing.
- **Purge** — metadata removed, then blob cleanup (best-effort, logged).
- **Expiry cleanup** — admin cleanup purges expired metadata and blobs.
- **List** — paginated metadata listing with owner, tag, MIME, size, time,
  and deleted/expired filters (see `docs/quotas.md`).

## Integrity

- Every upload gets a content-derived `sha256` and a deterministic `etag`
  (hash of fingerprint + size).
- File ids are UUIDs; the local store validates identifiers to prevent path
  traversal.
- Idempotent uploads via `idempotency_key`.
