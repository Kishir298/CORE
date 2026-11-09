# Storage Domains

R.E.S.C.S. records live in free-form `namespace` strings. Three logical
ownership domains partition that space by naming convention:

```text
RESCS
├── asis.*      → data owned by A.S.I.S.
├── tiviss.*    → data owned by T.I.V.I.S.S.
└── personal.*  → general user-owned cloud data (NOT agent state)
```

`core.*` and `rescs.*` remain reserved for infrastructure. See
`src/rescs/contract.py` (`RESERVED_NAMESPACE_PREFIXES`, `STORAGE_DOMAINS`)
and `GET /api/v1/contract` (`reserved_namespaces`).

## Why convention, not separate databases

Identity is `(namespace, key)` globally — two owners cannot hold the same
pair. Distinct prefixes give each domain an isolated key space with zero
schema changes: the distinction is **logical ownership and access
isolation**, enforced client-side by each agent's adapter. The physical
implementation stays an implementation detail.

## Ownership

| Domain | Owner | Writer |
|---|---|---|
| `asis.*` | A.S.I.S. | ASIS storage adapter only |
| `tiviss.*` | T.I.V.I.S.S. | TIVISS RESCS adapter only |
| `personal.*` | the user | user-driven flows (documents, projects, backups, media) |

## Access boundaries

- An agent reads/writes **only its own prefix** by default. Cross-domain
  access requires an explicit, authorized operation — never silent sharing.
- `personal.*` must not become a dumping ground for agent internals
  (memory, state, handover data belong under the agent prefix).
- Files have no namespace field: file ownership follows the `owner`
  convention (`owner="asis"`, `"tiviss"`, `"personal"`) and/or id-refs
  from namespaced records.

## Data categories

- `asis.memory`, `asis.conversations`, `asis.state`, `asis.metadata`
- `tiviss.memory`, `tiviss.conversations`, `tiviss.state`,
  `tiviss.identity`, `tiviss.ownership`, `tiviss.permissions`,
  `tiviss.handover`
- `personal.documents`, `personal.projects`, `personal.backups`,
  `personal.media`, `personal.archives`

## Integration contracts

- TIVISS: `tiviss/integrations/rescs_http.py` (namespace-guarded client).
- ASIS: `asis/storage/domains.py` (DomainRouter) + `asis/storage/migrate.py`.
- Cross-domain reads are rejected client-side unless explicitly authorized.

