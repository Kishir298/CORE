# Changelog

All notable changes to R.E.S.C.S. are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Resumable finalize now streams (`get_stream` → incremental SHA-256 → `put_stream`, no `b"".join`), enforces file quotas/metadata caps with post-write rollback, single-winner CAS + thread lock (retry → `409`, concurrent → one winner)
- Upload chunk rules: reject empty chunks, enforce exact `chunk_size` for intermediate chunks; service-level owner-lock checks in chunk/finalize/cancel; cancel no longer touches storage on unknown ids; glob metachars escaped in chunk probing
- Backup tool: `--verify` re-hashing, atomic staging + rename, exit `2` on missing DB/storage/hash mismatch/existing out, recursive blob copy with `path/mtime/total_bytes`/versions, real `pg_dump` execution (no silent success)
- Rate limiter: SHA-256-hashed keys, 10k bounded LRU map (was unbounded raw-key dict)
- Health probe: `try/finally` blob cleanup; bulk schema `max_length=1000` fail-fast; `upload_sessions (status, expires_at)` composite index

## [0.3.0]

### Added

- TTL `ttl_seconds` wiring for records/files (+ file form param), `RESCS_MAX_TTL_SECONDS` enforcement, mutual-exclusion with `expires_at`
- Tags raised 32 → 50/resource (case-sensitive, strip, reject-empty)
- Streaming uploads/downloads: `ObjectStore.put_stream/get_stream/size`, `FileService.create_stream/download_stream`, spool-bounded `POST /files`, `StreamingResponse` above `RESCS_STREAMING_THRESHOLD_BYTES`
- Resumable uploads `/api/v1/uploads` (create/chunk/status/finalize/cancel, 64KiB–64MiB chunks, 24h expiry, checksum verify, owner isolation, `admin/cleanup uploads_cleaned`)
- Bulk owner-isolation per item (403) + documented partial-success (non-atomic); quota post-write race guards
- S3 abstraction: `RESCS_STORAGE_BACKEND=local|memory|s3`, `FakeS3ObjectStore` for tests, `S3ObjectStore` (boto3) for live, `build_object_store` selector
- Backup tooling `scripts/rescs_backup.py` + `docs/backups.md` (RPO/RTO, manifest verify)
- `docs/encryption.md` (delegated at-rest model), `docs/deployment.md`, `docs/uploads.md`, `docs/rate-limiting.md`
- In-memory rate limiting (`RESCS_RATE_LIMIT_ENABLED`, 429 + Retry-After, health exempt)
- Perf indexes (`ix_records_owner_updated/expires`, `ix_file_objects_owner_updated/size`) + schema 0.3.0 (`upload_sessions` table)
- Tests: `test_uploads.py`, `test_storage_s3.py`, `test_rate_limit.py`, `test_reliability_v03.py`; migration tests track `SCHEMA_VERSION`

### Validation status

- Automated integration COMPLETE for all implementable objectives
- EXTERNAL VALIDATION REQUIRED: live PostgreSQL, real S3, prod HTTPS deploy, multi-machine, 24/7 endurance, live DR drill

## [0.2.0]

### Added - Phase 14 (soft delete & recovery)

- Tombstoned deletion for records and files (`deleted_at`/`deleted_by`,
  version + 1); ordinary reads/lists treat tombstones as `404`
- `POST .../restore` (409 on live-key collision, `If-Match` supported) and
  `DELETE .../purge` (permanent; file purge reclaims the blob)
- Live-only `(namespace, key)` uniqueness: partial unique index on
  PostgreSQL/SQLite plus application-level guards; keys reusable while a
  tombstone exists
- Admin recovery listings (`/admin/records/deleted`, `/admin/files/deleted`,
  `?include_deleted=true`) with owner scoping

### Added - Phase 15 (TTL & data expiration)

- Optional UTC `expires_at` on records/files (past values rejected);
  expired rows read as absent and are transparently reclaimed by writes
- Explicit `POST /api/v1/admin/cleanup` (`dry_run`, bounded `batch`) purging
  expired metadata + blobs; no background scheduler

### Added - Phase 18 (metadata & tagging)

- `tags` on records/files (≤32, charset-validated, 422 otherwise), filterable
  (all-match) and part of the record ETag (sorted; untagged hashes unchanged)

### Added - Phase 19 (advanced search & filtering)

- Time-window, MIME, size-range, tag, and deleted/expired filters on list and
  search with deterministic ordering; owner scoping on every filter

### Added - Phase 20 (bulk operations)

- `POST /api/v1/records/bulk` bounded batches (default max 100) with
  per-item statuses and explicit partial-failure semantics

### Added - Phase 21 (quotas & governance)

- `RESCS_MAX_{RECORDS,FILES,BYTES}_PER_OWNER`, `MAX_FILE_SIZE`,
  `MAX_METADATA_BYTES`, `MAX_BULK_BATCH` enforced server-side
  (`403 QUOTA_EXCEEDED` / `413 PAYLOAD_TOO_LARGE`); live non-expired
  accounting per owner

### Added - Phase 22 (audit logging)

- Secret-free persistent `audit_events` trail (operation, resource, owner,
  request ID, outcome, error code) with `GET /api/v1/admin/audit` and
  retention pruning via admin cleanup

### Changed

- v0.1 → v0.2 additive migration: new nullable columns, `audit_events`
  table, live-only unique index (SQLite rebuild covered by
  `tests/unit/test_db_migration_v02.py`; PostgreSQL statements validated by
  inspection, live run deferred)
- `DELETE` endpoints now soft-delete (documented behavior change from v0.1)
- Version 0.1.0 → 0.2.0

### Validation status

- Automated integration COMPLETE (soft delete, TTL, tags, search, bulk,
  quotas, audit, migration, backend parity)
- READY FOR VALIDATION: live PostgreSQL migration run, S3, deployment,
  multi-machine, 24/7 endurance

## [0.1.0] (Phases 1-13)

### Added - Phase 1 (foundation)

- `src/rescs` package with application factory (`create_app`)
- Environment / `.env` configuration via pydantic-settings (`RESCS_*`)
- Required API key configuration (`RESCS_API_KEY`, min 16 chars)
- Logging foundation (`rescs.logging`)
- Domain error hierarchy with stable codes and HTTP status mapping
- Health/readiness reporting foundation (`rescs.health`)
- Health endpoints: `/health/live`, `/health/ready`, `/health`
- Project metadata (`pyproject.toml`), pinned dependencies, `.gitignore`,
  `.env.example`
- Test suite: configuration, errors, health service, health API

### Added - Phase 2 (data model and storage abstraction)

- Storage-agnostic domain dataclasses (`RecordData`, `FileObjectData`)
- SQLAlchemy ORM models (`records`, `file_objects`) with unique constraints,
  timestamps, versions and idempotency keys
- Repository protocols decoupling services from database backends
- In-memory repository implementations (deterministic test doubles)
- SQLAlchemy repository implementations with conflict/not-found translation
- Pydantic schemas with JSON-serializability validation and domain mapping
- Test suite: domain, models, schemas, in-memory and SQLAlchemy repositories

### Added - Phase 3 (database and persistence)

- `db.engine`: per-backend engine construction (SQLite static pool, network
  backends with `pool_pre_ping` and connect timeouts)
- `db.session`: session factories and the `session_scope` transaction
  manager (commit/rollback, domain-error translation)
- `db.schema`: `SchemaManager` for idempotent schema creation with a
  versioned `schema_info` table
- `db.bootstrap`: `bootstrap_database` wiring engine, connectivity check,
  schema and session factory from settings
- Startup connectivity check with fail-fast `DEPENDENCY_UNAVAILABLE`
- `RESCS_AUTO_CREATE_SCHEMA` configuration
- Persistent file-backed storage verified by tests
- Docs: `docs/database.md`

### Added - Phase 4 (storage service)

- `RecordService` operations: create, put (upsert), get, update, delete,
  list, search
- Idempotent creates via `idempotency_key`
- Version tracking, ETag computation (`rescs.etag`) and `updated_at` bumps
  on every modification
- Repository `search` across key, value and metadata (portable across
  SQLite/PostgreSQL and in-memory backends)
- Pagination clamping in the service layer
- Service composition root (`build_services`) for memory and persistent
  backends
- Test suite: record service behaviour, factory wiring

### Added - Phase 5 (file storage)

- Object store protocol (`interfaces/object_store`) separating blobs from
  metadata
- `LocalObjectStore` (filesystem, atomic writes, path-traversal protection)
  and `MemoryObjectStore` (test double)
- `FileService`: upload, download, metadata read, delete, list
- Content fingerprints (`sha256`), size tracking and file etags
- Blob cleanup on metadata-write failure; best-effort blob deletion on remove
- Composition root now wires record + file services with an object store
- Docs: `docs/storage.md`

### Added - Phase 6 (API and service integration)

- Versioned HTTP API under `/api/v1` (`rescs.api.routers`)
- Record endpoints: create (201), upsert (PUT), read, patch, delete (204),
  list and search with pagination
- File endpoints: upload (multipart, 201), metadata read, content download,
  delete (204), list
- API dependencies (`api.deps`) exposing settings and the composed services
- Real health probes wired into `/health/ready` (database connectivity,
  object-store read/write probe)
- Consistent `{error: {code, message, details}}` response envelope for domain
  and validation errors (`api.errors`)
- Application factory lifecycle: bootstrap database + services on startup,
  dispose engine on shutdown
- Interactive OpenAPI docs at `/docs` and `/redoc`
- Docs: `docs/api.md`

### Added - Phase 7 (security and access control)

- `X-API-Key` authentication enforced on every `/api/v1` route with
  constant-time comparison (`rescs.security`)
- `401 UNAUTHORIZED` envelope for missing/invalid credentials
- Owner scoping via `RESCS_API_KEY_OWNER`: single-owner lock mode forcing
  `owner` on writes, on list filters, and authorizing reads/deletes
- Cross-owner access rejected with `401` (claiming another owner) or `403`
  (touching another owner's resource)
- Owner field plumbed through file uploads and all record routes
- Test suite: authentication, scoped-owner enforcement across records

### Added - Phase 8 (synchronization and consistency)

- Optimistic concurrency via `If-Match` / etag precondition on record
  `PATCH`/`PUT`/`DELETE` and file `DELETE` (`412 PRECONDITION_FAILED`)
- RFC 9110 etag parsing (bare, quoted `"..."`, weak `W/"..."`, `*`)
- `ETag` response header on read/create/update routes
- Idempotent creates/upload formalized and covered by unit + API tests
- Blob integrity verification on download (sha256 mismatch ->
  `STORAGE_ERROR` with expected/actual digests)
- Docs: `docs/synchronization.md`

### Added - Phase 9 (C.O.R.E. integration contract)

- `GET /api/v1/contract`: machine-readable capability/discovery endpoint
  (`rescs.contract`) covering auth, owner scoping, pagination, error envelope,
  etag forms and the reserved namespace conventions
- Reserved namespace prefixes `core.*` and `rescs.*`
- Docs: `docs/core-integration-contract.md` (transport, envelope,
  guarantees, C.O.R.E. conventions, database boundary)

### Added - Phase 11 (testing and integration)

- `tests/integration/test_persistence_restart.py`: file-backed SQLite +
  LocalObjectStore restart proof (records + file metadata/bytes survive
  rebuild; versions, etags, owners, timestamps preserved)
- `tests/integration/test_lifecycle.py`: full record/file lifecycle matrix
  (auth 401s, 404s, 409s, 422s, pagination bounds, empty results,
  content-integrity headers, missing-blob `STORAGE_ERROR` with no orphan
  metadata)
- `tests/integration/test_concurrency_owner.py`: client-A/client-B stale
  etag `412` with `current_etag` and no silent overwrite, monotonic
  versions, idempotent record replay (HTTP) + file idempotency at the
  service boundary, multi-owner list isolation, scoped-mode lock and the
  403 service-boundary guard
- `tests/integration/test_postgres_compat.py`: `RESCS_INTEGRATION_DATABASE_URL`
  gate — skips cleanly when unset, exercises connectivity/schema/CRUD when
  set; never falls back to SQLite silently
- `tests/integration/test_contract_consumer.py`: error-envelope matrix
  (401/404/409/412/422/500/405/unknown-route) with secret-leak negatives,
  hypothetical-CORE HTTP round-trip (discover → paginate → conditional
  write), app-level health + request-ID behavior
- `tests/integration/test_reliability.py`: install/factory smoke,
  no-cross-subsystem-import guard, fail-fast unreachable-database domain
  error, persistent-app storage-outage `503`, bounded endurance loop
  (`RESCS_ENDURANCE_SECONDS`, default 5s)
- `tests/unit/test_storage_local.py`: extended traversal vectors
  (`../`, `../../`, absolute paths, subpaths, empty/overlong ids) proven
  contained in the storage base

### Added - Phase 12 (R.I.S.A.R.M.S. readiness)

- External-consumer validation without sibling imports: contract endpoint
  matches `docs/core-integration-contract.md` (transport, envelope,
  pagination, etag forms, owner guarantees)
- Security audit: no hard-coded secrets; `X-API-Key` (min 16 chars,
  constant-time compare) on all `/api/v1` routes; owner lock + 403
  boundary; no credential/traceback leakage in responses or logs
- Production configuration audit: fail-fast key validation, `development`
  / `test` / `production` allowlist, no CORS/debug insecure defaults,
  `RESCS_AUTO_CREATE_SCHEMA=false` path for migration-managed deployments
- Validation status: automated integration COMPLETE; live PostgreSQL /
  Supabase, deployed CORE ↔ RESCS interop, multi-machine and 24/7
  endurance are READY FOR VALIDATION (not claimed)

### Added - Phase 13 (cleanup, documentation, release)

- Hygiene sweep: no TODO/FIXME/legacy/placeholder code in `src/`/`tests/`;
  tracked tree contains only source, tests, docs and packaging (caches,
  `.venv`, storage dirs remain git-ignored)
- Docs reconciled with code: roadmap Phases 11–13 marked complete,
  README status + project structure updated, release stays at v0.1.0
   across `pyproject.toml`, `README.md` and this changelog

### Added - Phase 10 (observability and health)

- Request-ID middleware (`rescs.observability`): honours caller-supplied
  `X-Request-ID` (≤128 chars) else generates, echoes on every response
  including errors, propagates via context/scope, access-logged
- Readiness semantics: `/health/ready` and `/health` return `200` when
  healthy and `503` with the same `{status, checks}` body when any
  database/storage check is `down`/`degraded`
- Stable error envelopes for unknown routes (`404 NOT_FOUND`) and unhandled
  failures (`500 INTERNAL_ERROR`) with request-ID propagation and no
  traceback/credential leakage
- Test suite: readiness failure matrix (db/storage/both/exception/degraded),
  secret-leakage, public-health policy, request-ID on success and failure
- Docs: `docs/observability.md`, health semantics in `docs/api.md`,
  architecture roadmap Phase 10 complete
