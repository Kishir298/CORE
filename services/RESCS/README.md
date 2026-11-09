# R.E.S.C.S.

**Rishik's Efficient System for Cloud Storage**

R.E.S.C.S. is the cloud storage and data persistence subsystem of the
[R.I.S.A.R.M.S.](https://github.com/Kishir298) ecosystem. It stores
information, files, records and metadata in cloud-backed storage and makes
them retrievable by authorized R.I.S.A.R.M.S. systems.

```
                    R.I.S.A.R.M.S.
                           |
                           v
                        C.O.R.E.
                           |
                    Storage requests
                           |
                           v
                       R.E.S.C.S.
                           |
                           v
                     Cloud Database
                           +
                      File/Object Storage
```

R.E.S.C.S. is **not** the ecosystem controller. C.O.R.E. coordinates the
ecosystem; R.E.S.C.S. provides storage. The two projects are developed
independently and connected through a stable contract (see
`docs/core-integration-contract.md`).

## Status

v0.4.0 — v0.3.0 storage features plus the Raspberry Pi deployment
foundation: signed CORE owner scope (`X-RESCS-Signature`), required
`/srv/core` mount guard, systemd unit/installer and real CORE loopback
validation (`docs/RESCS-Pi-Handoff.md`). This includes soft delete & recovery,
TTL/`ttl_seconds` expiration + admin cleanup (records/files/uploads), tags
(50/resource), advanced search, bulk (owner-isolated, partial-success),
race-safe quotas, audit trail, streaming uploads/downloads
(`RESCS_STREAMING_THRESHOLD_BYTES`), resumable uploads (`/api/v1/uploads`),
S3-compatible backend abstraction (+ fake), backup tooling
(`scripts/rescs_backup.py`), delegated encryption model, in-memory rate
limiting, and deployment docs. Live PostgreSQL/Supabase, real S3,
deployed CORE ↔ RESCS interop, real Pi/ARM64 and 24/7 endurance remain Ready
for External Validation. See `docs/architecture.md` and `CHANGELOG.md`.

## Stack

- **API:** FastAPI (OpenAPI docs at `/docs`)
- **Persistence:** SQLAlchemy 2.0 with PostgreSQL (`psycopg` 3) support;
  SQLite used by default for development and tests
- **Validation / config:** Pydantic v2, pydantic-settings
- **Tests:** pytest, httpx TestClient

## Project structure

```
src/rescs/
├── main.py            # application factory, lifespan wiring
├── config.py          # pydantic-settings configuration (env / .env)
├── logging.py         # process logging foundation
├── errors.py          # domain error hierarchy (codes + HTTP status)
├── health.py          # named dependency checks + aggregate report
├── domain.py          # storage-agnostic domain dataclasses
├── etag.py            # deterministic content identifiers
├── security.py        # X-API-Key auth + owner scoping
├── observability.py   # request-ID middleware + access logging
├── rate_limit.py      # in-memory rate limiting (429 RATE_LIMITED)
├── contract.py        # machine-readable CORE contract
├── db/                # engine, sessions, schema manager, bootstrap
├── models/            # SQLAlchemy ORM models (records, file_objects, upload_sessions, audit)
├── schemas/           # Pydantic request/response schemas + validation
├── interfaces/        # repository + object-store protocols
├── repositories/      # in-memory + SQLAlchemy implementations
├── services/          # record + file + upload + audit services, composition root
├── storage/           # object stores (local, memory, s3/fake)
└── api/               # versioned HTTP API (v1), routers, deps, errors
```

Key v0.2 capabilities: recoverable deletion (`DELETE` → `POST .../restore`
→ `DELETE .../purge`), record/file `expires_at` TTL with admin cleanup
(`POST /api/v1/admin/cleanup`), tags + rich list/search filters, bulk
record operations (`POST /api/v1/records/bulk`), per-owner quotas and size
caps, and a secret-free audit trail (`GET /api/v1/admin/audit`). Details in
`docs/lifecycle.md` and `docs/quotas.md`.

Detailed phase-by-phase documentation lives in `docs/`.

## Installation

Requires Python 3.11+ (developed on 3.14).

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

## Configuration

Copy `.env.example` to `.env` and set the required values. Secrets are never
committed.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `RESCS_API_KEY` | Yes (min 16 chars) | — | API authentication key, sent via `X-API-Key` |
| `RESCS_ENV` | No | `development` | `development`, `test`, or `production` |
| `RESCS_DATABASE_URL` | No | `sqlite:///rescs_dev.db` | SQLAlchemy URL; use `postgresql+psycopg://` for PostgreSQL/Supabase |
| `RESCS_STORAGE_DIR` | No | `rescs_storage` | Local object-store directory |
| `RESCS_LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `RESCS_REQUEST_ID_HEADER` | No | `X-Request-ID` | Request correlation header echoed on every response |
| `RESCS_MAX_RECORDS_PER_OWNER` | No | `0` (unlimited) | Per-owner live-record quota |
| `RESCS_MAX_FILES_PER_OWNER` | No | `0` (unlimited) | Per-owner live-file quota |
| `RESCS_MAX_BYTES_PER_OWNER` | No | `0` (unlimited) | Per-owner stored-bytes quota |
| `RESCS_MAX_FILE_SIZE` | No | `0` (unlimited) | Maximum accepted upload bytes |
| `RESCS_MAX_METADATA_BYTES` | No | `65536` | Maximum serialized metadata bytes |
| `RESCS_MAX_BULK_BATCH` | No | `100` | Maximum operations per bulk request (1–1000) |
| `RESCS_AUDIT_RETENTION_DAYS` | No | `90` | Audit pruning horizon for admin cleanup (`0` = keep) |
| `RESCS_API_KEY_OWNER` | No | — (multi-owner) | Single-owner lock mode |
| `RESCS_AUTO_CREATE_SCHEMA` | No | `true` | Create schema on startup (`false` in prod with managed migrations) |
| `RESCS_MAX_TTL_SECONDS` | No | `31536000` | Maximum accepted TTL seconds (`0` = unlimited) |
| `RESCS_STREAMING_THRESHOLD_BYTES` | No | `8388608` | Size at/above which downloads stream |
| `RESCS_STORAGE_BACKEND` | No | `local` | `local`, `memory`, or `s3` (s3 needs `boto3`, see `docs/deployment.md`) |
| `RESCS_S3_ENDPOINT` / `RESCS_S3_BUCKET` / `RESCS_S3_REGION` | No | — | S3-compatible backend settings (never commit keys) |
| `RESCS_S3_ACCESS_KEY` / `RESCS_S3_SECRET_KEY` / `RESCS_S3_PATH_PREFIX` | No | — | S3 credentials/prefix via env/secret manager only |
| `RESCS_RATE_LIMIT_ENABLED` | No | `false` | In-memory single-instance limiter (`true` to enable) |
| `RESCS_RATE_LIMIT_GENERAL_PER_MINUTE` | No | `100` | General bucket limit |
| `RESCS_RATE_LIMIT_WRITES_PER_MINUTE` | No | `60` | Write bucket limit |
| `RESCS_RATE_LIMIT_UPLOADS_PER_MINUTE` | No | `20` | Upload bucket limit |

## Running

```powershell
.\.venv\Scripts\python.exe -m uvicorn rescs.main:create_app --factory --reload --port 8000
```

Verify:

```text
GET http://127.0.0.1:8000/health/live
GET http://127.0.0.1:8000/health/ready
```

## Running tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Development workflow

The system is developed in phases; each phase ends with a full test run, a
Git commit, and a push to `main`. See `docs/architecture.md` for the roadmap
and `CHANGELOG.md` for per-phase notes.

## License

Proprietary — all rights reserved (no LICENSE file; MIT provisional claim removed 2026-09-24).
