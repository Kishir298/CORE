# T.I.V.I.S.S. - Though I'm Vanquished, I'm Still Stronger

**T.I.V.I.S.S.** is an independent AI agent within the **R.I.S.A.R.M.S.** ecosystem.

## What is T.I.V.I.S.S.?

T.I.V.I.S.S. stands for **"Though I'm Vanquished, I'm Still Stronger"**.

It is a separate AI agent designed to eventually be handed over to another
person. Because of that, it is architected around an independent identity,
configuration, memory, permission model, ownership model, and lifecycle --
with a controlled handover mechanism at its core.

Current implementation status: **v0.2.0 — foundation + CLI, export/import, logging, voice, timeouts, offline-tested transports**.

## Why is it separate from A.S.I.S.?

A.S.I.S. ("A Smart Intelligence System") is the primary intelligence system
of R.I.S.A.R.M.S. T.I.V.I.S.S. is **not** A.S.I.S.:

- T.I.V.I.S.S. has its own architecture and is not a copy or rename of A.S.I.S.
- T.I.V.I.S.S. owns its own identity, memory, permissions, and ownership.
- T.I.V.I.S.S. does not import A.S.I.S. internals and is not dependent on A.S.I.S.

## Relationship with C.O.R.E.

C.O.R.E. ("Communication, Organization and Resource Engine") is the central
ecosystem management engine. T.I.V.I.S.S. is designed to integrate with
C.O.R.E. later through an adapter, but does **not** depend on a running C.O.R.E.

## Relationship with R.E.S.C.S.

R.E.S.C.S. ("Rishik's Efficient System for Cloud Storage") is the cloud
storage system of the ecosystem. T.I.V.I.S.S. defines a memory abstraction and
will integrate with R.E.S.C.S. later through an adapter. R.E.S.C.S. is **not**
bundled inside T.I.V.I.S.S. and is not required for development.

## Ownership and handover purpose

T.I.V.I.S.S.'s defining characteristic is that it can eventually be handed
over to a new owner through a controlled, validated, and auditable process.

This version defines the ownership state model, the handover request state
machine, and the audit events. Real-world transfer is intentionally **not**
implemented yet.

## Current implementation status

| Area | Status |
| --- | --- |
| Package structure | **IMPLEMENTED** |
| Identity model | **IMPLEMENTED** |
| Ownership state model | **IMPLEMENTED** |
| Agent runtime and lifecycle | **IMPLEMENTED** |
| Conversation (request/response) contracts | **IMPLEMENTED** |
| Memory abstraction + local memory | **IMPLEMENTED** |
| Model provider abstraction + mock provider | **IMPLEMENTED** |
| Permissions and policy (default deny) | **IMPLEMENTED** |
| Tool framework + safe mock tools | **IMPLEMENTED** |
| Events (local bus) | **IMPLEMENTED** |
| Handover architecture (state model + audit) | **IMPLEMENTED** |
| Configuration | **IMPLEMENTED** |
| C.O.R.E. integration adapter (local/mock) | **IMPLEMENTED** |
| R.E.S.C.S. integration adapter (local/mock) | **IMPLEMENTED** |
| Cross-component integration tests | **IMPLEMENTED** |
| Real C.O.R.E. transport (`core_tcp`, TCP+TLS) | **IMPLEMENTED** (tested offline vs fakes) |
| Real R.E.S.C.S. transport (`rescs_http`, urllib) | **IMPLEMENTED** (tested offline vs fakes) |
| Interactive CLI (`tiviss` REPL + `--message`) | **IMPLEMENTED** |
| State export/import (versioned, secret-free) | **IMPLEMENTED** |
| Structured JSON-lines logging | **IMPLEMENTED** |
| Voice abstraction + mocks | **IMPLEMENTED** |
| Provider/request timeouts | **IMPLEMENTED** |
| A.S.I.S. integration | PLANNED |
| External-device control | PLANNED / FUTURE |
| Handover to a real person | FUTURE |
| Production deployment | FUTURE |

> **Note:** an adapter/interface exists for C.O.R.E. and R.E.S.C.S. integration.
> A live integration is **not** claimed until the other systems are ready.

## Architecture

```
                    T.I.V.I.S.S.
                         |
             +-----------+-----------+
             |           |           |
          Identity    Agent      Memory
                       Runtime
             |           |           |
             +           +           +
         Ownership   Model    /  Storage interface
             |           |
             +           +
         Permissions  Events
             |
             +
          Handover
```

Future ecosystem integration (later phases):

```
                    T.I.V.I.S.S.
                         |
                         v
                      C.O.R.E.
                         |
              +----------+-----------+
              |          |           |
              v          v           v
           R.E.S.C.S.  Devices    Services
```

## Development roadmap

1. Project foundation + package structure -- **done**
2. Identity + ownership -- **done**
3. Agent runtime + lifecycle -- **done**
4. Request/response model -- **done**
5. Memory abstraction + local memory -- **done**
6. Model/provider abstraction -- **done**
7. Permissions + policy -- **done**
8. Tool abstraction -- **done**
9. Events -- **done**
10. Handover architecture -- **done**
11. Configuration -- **done**
12. C.O.R.E. adapter -- **done**
13. R.E.S.C.S. adapter -- **done**
14. Cross-component integration tests -- **done**
15. Interactive CLI + state export/import + logging + voice -- **done**
16. Real C.O.R.E./R.E.S.C.S. transports (offline-tested) -- **done**
17. Documentation + cleanup + release -- **done**

## Testing

Tests are offline and deterministic; no external services are required.

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

## Usage

```text
.venv\Scripts\python -m tiviss --help
.venv\Scripts\python -m tiviss --message "hello"
.venv\Scripts\python -m tiviss          # interactive REPL (tiviss> )
```

The REPL drives the real pipeline (permissions → provider → memory).
`/help`, `/status`, `/clear`, `/quit` are built in.

## Storage domains

TIVISS cloud data lives under `tiviss.*` RESCS namespaces
(`tiviss.memory`, `tiviss.conversations`, ...); see
`../RESCS/docs/storage-domains.md`. The HTTP client refuses other
namespaces unless explicitly allowed. `asis.*` and `personal.*` are
never touched.

## Future integrations

- C.O.R.E.: register agent, report health, publish events, route messages
- R.E.S.C.S.: persistent memory via the memory backend interface
- A.S.I.S.: interoperability without shared internals
- Real owner handover workflows

## Development rules

- T.I.V.I.S.S. does not modify other R.I.S.A.R.M.S. repositories.
- T.I.V.I.S.S. does not depend on a running C.O.R.E., R.E.S.C.S., or A.S.I.S.
- No hard-coded secrets; configuration comes from validated settings + env vars.
- Security boundaries are explicit; integration boundaries are treated as untrusted.