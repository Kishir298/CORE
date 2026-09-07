# R.E.S.C.S. → C.O.R.E. Organization Ingestion

How stored R.E.S.C.S. data enters the C.O.R.E. Organization index:
retrieved through the adapter, validated against a fixed contract,
normalized into the existing `Resource` model, then organized into
stable `OrganizationEntry` records for Routing, Services and Agents.

```text
                 R.E.S.C.S.
                    │
                    │ stored resource
                    ▼
             R.E.S.C.S. Adapter
          (fetch_resource / list_resources)
                    │
                    │ raw response (external input)
                    ▼
          validate_rescs_resource
                    │
                    │ contract dict
                    ▼
            normalize_resource
                    │
                    │ C.O.R.E. Resource
                    ▼
             ResourceRegistry
          (register new / update existing)
                    │
                    ▼
             OrganizationEngine
          (categorize_resource -> resource:<id>)
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
       Routing    Services   Agents
```

R.E.S.C.S. owns persistent storage. The C.O.R.E. resource layer
represents/registers resources inside C.O.R.E. Organization categorizes,
indexes, links and discovers. Organization never stores and never touches
database or HTTP internals — it depends only on the C.O.R.E.-side
adapter interface.

## Resource contract

Every R.E.S.C.S. response consumed here must provide:

```text
resource_id      non-empty string (stable identity)
resource_type    non-empty string (becomes the entry category)
name             non-empty string
owner            non-empty string, or absent (normalizes to None)
metadata         object, or absent (normalizes to {})
```

Optional pass-throughs: `source` (non-empty string), `capabilities`
(list of strings). Anything else (storage paths, internal database ids,
backend timestamps) is intentionally dropped — R.E.S.C.S. remains its
owner and it can always be re-fetched by `resource_id`.

Violations raise `InvalidResourceData`. Nothing is fabricated: missing
required fields fail instead of producing default resources.

## Normalization

`normalize_resource()` maps the validated contract onto the existing
`Resource` model (no duplicate model). Deterministic: the same logical
resource always yields the same `resource_id`, hence the same entry id
`resource:<id>` and category. `registered_at`/`last_seen` are C.O.R.E.-side
lifecycle fields, not storage clocks.

## Ingestor (`ResourceIngestor`)

Constructed with `(adapter, registry, organization)` — e.g. via
`CoreApplication.create_organization_ingestor()`, which always binds the
currently active adapter:

- `ingest_resource(id)` — fetch → validate → normalize → register new or
  update existing in place (entry id unchanged). Idempotent: ten calls
  still yield exactly one entry. A changed `resource_type` re-registers
  so the category stays exact.
- `ingest_all()` — every resource in `resource_id` order; returns
  `{ingested, updated, failed, errors}`. Invalid items are collected,
  never aborting the run.
- `forget_resource(id)` — drops the C.O.R.E.-side registry/organization
  entry only. Never deletes from R.E.S.C.S. storage.

## Deletions vs failures (different states)

- Backend unreachable/timeout → `RescsUnavailable`; existing index data
  is left untouched.
- Fetch explicitly returns nothing → the C.O.R.E.-side entry is removed
  (if present) and `RescsResourceNotFound` is raised.
- Explicit operator removal → `forget_resource()`.

## Errors

`IngestionError` (base) → `InvalidResourceData`, `RescsUnavailable`,
`RescsResourceNotFound`, all under the existing `OrganizationError`.
Backend exceptions are translated, never leaked; nothing is swallowed
into `None`.

## Validation status

Implemented and automated-tested via localhost suites
(`tests/organization/test_organization_ingestion.py`: contract,
normalization, idempotency, updates, deletion, failure safety, discovery).
No network or physical-device integration is involved in this boundary.
