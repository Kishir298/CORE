# R.E.S.C.S. Architecture

## What R.E.S.C.S. is

R.E.S.C.S. (**R**ishik's **E**fficient **S**ystem for **C**loud **S**torage)
is the cloud storage and data persistence subsystem of the R.I.S.A.R.M.S.
ecosystem.

Boundary of responsibility:

```text
R.I.S.A.R.M.S.
       |
       v
    C.O.R.E.          (manages, coordinates, routes)
       |
       +---- A.S.I.S. (intelligence)
       +---- R.E.S.C.S.(storage)
                     |
                     v
              PostgreSQL / cloud object storage
```

C.O.R.E. manages. A.S.I.S. provides intelligence. R.E.S.C.S. stores. These
responsibilities are deliberately kept separate; projects are developed
independently and never import each other.

## Target architecture

```text
                R.E.S.C.S.
                    |
     +--------------+---------------+------+
     v              v               v      v
  Records        Files          Metadata  Health/Security
     |              |              |       |
     +--------------+--------------+       |
                    |                       |
             Storage Service                |
                    |                       |
             Storage Abstraction            |
                    |                       |
        +-----------+-----------+        +--+
        v                       v
   Repository              Object Store
   (SQLAlchemy: SQLite/     (local filesystem,
   PostgreSQL/Supabase)     cloud-adoptable)
```

Layered without shortcuts:

```text
API layer        -> HTTP handlers, validation, error mapping
Service layer    -> business operations, orchestration
Repository layer -> data access behind a Protocol
Storage layer    -> binary object persistence behind a Protocol
Database layer   -> SQLAlchemy engine/session wiring
```

No API route contains direct database logic.

## Project structure

> v0.3.0 note: also ships `rate_limit.py`, `contract.py`, `security.py`, `observability.py`; `services/uploads.py`; `models/upload_session.py` + `models/audit.py`; `api/uploads.py`, `api/contract.py`, `api/admin.py`; storage `s3.py` (+ fake).

```
src/rescs/
├── main.py            # application factory, lifespan wiring
├── config.py          # pydantic-settings configuration (env / .env)
├── logging.py         # process logging foundation
├── errors.py          # domain error hierarchy (codes + HTTP status)
├── health.py          # named dependency checks + aggregate report
├── domain.py          # storage-agnostic domain dataclasses (RecordData, FileObjectData)
├── etag.py            # deterministic content identifiers
├── db/base.py         # SQLAlchemy declarative base
├── db/                # engine, sessions, schema manager, bootstrap
├── models/            # SQLAlchemy ORM models (records, file_objects, audit_events)
├── schemas/           # Pydantic request/response schemas + validation
├── interfaces/        # repository + object-store protocols
├── repositories/      # in-memory + SQLAlchemy implementations
├── services/          # record + file + audit services, composition root
├── storage/           # object stores (local, memory)
└── api/               # versioned HTTP API (v1), routers, deps, errors, health
```

## Development roadmap

| Phase | Focus | Status |
| --- | --- | --- |
| 1 | Project foundation and architecture | Complete (v0.1.0) |
| 2 | Data model and storage abstraction | Complete |
| 3 | Database and persistence | Complete |
| 4 | Storage service | Complete |
| 5 | File storage | Complete |
| 6 | API and service integration | Complete |
| 7 | Security and access control | Complete |
| 8 | Synchronization and consistency | Complete |
| 9 | C.O.R.E. integration contract | Complete |
| 10 | Observability and health | Complete |
| 11 | Testing and integration | Complete + Automated Tested |
| 12 | R.I.S.A.R.M.S. readiness | Complete + Automated Tested |
| 13 | Cleanup, documentation, release | Complete (v0.1.0) |
| 14 | Soft delete & recovery | Complete + Automated Tested (v0.2.0) |
| 15 | TTL & data expiration (`expires_at` + `ttl_seconds`, max-TTL) | Complete + Automated Tested (v0.3.0) |
| 16 | Large file & streaming storage | Complete + Automated Tested (v0.3.0) |
| 17 | Chunked / resumable uploads (`/api/v1/uploads`) | Complete + Automated Tested (v0.3.0) |
| 18 | Metadata & tagging (50/resource) | Complete + Automated Tested (v0.3.0) |
| 19 | Advanced search & filtering | Complete + Automated Tested (v0.2.0) |
| 20 | Bulk operations (owner-isolated, partial-success) | Complete + Automated Tested (v0.3.0) |
| 21 | Storage quotas & governance (race-safe) | Complete + Automated Tested (v0.3.0) |
| 22 | Audit logging | Complete + Automated Tested (v0.3.0, extended events) |
| 23 | Backup & restore (tooling + docs) | Complete (tooling) + Automated Tested; live DR drill external |
| 24 | S3-compatible object storage (abstraction + fake) | Complete + Automated Tested; live S3 external |
| 25 | Encryption & security hardening (delegated model) | Complete (docs) |
| 26 | Rate limiting & abuse protection (in-memory) | Complete + Automated Tested (v0.3.0); distributed limiter external |
| 27 | Performance & DB optimization (targeted indexes) | Complete (indexes + migration) |
| 28 | Deployment readiness (docs + health) | Complete (docs); prod deploy external |
| 29 | Endurance & reliability | Partial (bounded automated tests; no 24/7 deployment claimed) |

Live PostgreSQL/Supabase, deployed CORE ↔ RESCS interop, multi-machine
and endurance validation remain **Ready for External Validation** (see
`CHANGELOG.md`): the implementation is cloud-ready with gated
compatibility tests (`RESCS_INTEGRATION_DATABASE_URL`), but no live
cloud/deployment run is claimed.

Each phase ends with: full test run, documentation update, Git commit, and a
push to `main`.
