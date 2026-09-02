# C.O.R.E. — Communication, Organization and Resource Engine

**Version:** `0.2.0` · **Host:** Windows 11 (Intel Core Ultra 7 · 32 GB RAM · 1 TB) co-hosting **C.O.R.E.** and **R.E.S.C.S.** · **Python:** `>=3.10` (tested on `3.14.7` via `py` launcher)

C.O.R.E. is the lifecycle-aware, transport-agnostic orchestration spine for the R.I.S.A.R.M.S. platform. It owns runtime graphs, communication, routing, services, resources, organization, events, health, security, and R.E.S.C.S. persistence on a single Windows laptop that may offload agent execution for low-capability devices (phones, watches, R.O.V.E.R.T.).

## Quick Start (Windows PowerShell 5.1)

```powershell
py -m pip install -e .
py -m core --help
py -m core --config config/core.yaml --env development start   # foreground control loop (Ctrl+C to stop)
py -m core --config config/core.yaml status
py -m core --config config/core.yaml health
py -m core --config config/core.yaml resources
py -m core --config config/core.yaml services
py -m pytest -q
```

Configuration resolves `config/core.yaml` by default; `--config` overrides. Environment overrides via `CORE_*` (e.g., `CORE_COMPONENTS__HEALTH__ENABLED=false`, `CORE_DATABASE_HOST=env-host`, `CORE_SECURITY__PROVIDER=token`).

## Architecture

12 runtime components registered in dependency order (`core/application/app.py:120`):
`configuration → logging → security → resources → organization → events → communication → routing → health → rescs → dependencies → services → core`.

*   **Communication** — `Transport` ABC (`core/communication/transport.py:13`) with `LocalTransport` (`core/communication/transport.py:88`) and `TcpTransport` (`core/communication/tcp.py:1`) on `127.0.0.1` by default. `MessageSerializer` (`core/communication/serializer.py:11`) preserves `identity_id` over wire.
*   **Routing / Services** — `Router` (`core/routing/router.py:16`) + `ServiceManager`/`ServiceDispatcher` (`core/services/dispatch.py:18`) with pluggable security (`core/security/provider.py:1`).
*   **Resources** — `ResourceRegistry` (`core/resources/registry.py:1`) + typed helpers `create_device_resource`/`create_agent_resource` (`core/resources/models.py:73`).
*   **Runtime History** — `RuntimeHistory` (`core/runtime/history.py:1`) tracks device/agent/service intervals; persisted via adapter.
*   **R.E.S.C.S. Adapter** — `RescsAdapter` (`core/rescs/adapter.py:1`) with `InMemoryRescsAdapter`, `FileRescsAdapter` (`var/rescs.json`), `HttpRescsAdapter` stub.
*   **Health / Events** — `HealthMonitor` (`core/health/monitor.py:1`) bridges to `EventBus` (`core/events/bus.py:1`).

## Phase Matrix (v0.2)

| Phase | Title | Status | Notes |
|-------|-------|--------|-------|
| 1 | Runtime + App Orchestration | **IMPLEMENTED** | DFS start order, reverse shutdown, `tests/application/test_application_orchestration.py:10` |
| 2 | Communication + Transport | **IMPLEMENTED** | `LocalTransport` + `TcpTransport` (localhost), serializer fix `core/communication/serializer.py:11` |
| 3 | Routing + Service Execution | **IMPLEMENTED** | 5 routes `core/application/app.py:903`, 8 services |
| 4 | Resource + Organisation | **IMPLEMENTED** | `ResourceRegistry` + `OrganizationEngine` + Device/Agent helpers |
| 5 | Events | **IMPLEMENTED** | Failure-isolated bus |
| 6 | Health | **IMPLEMENTED** | 12 checks including `rescs` |
| 7 | Config Drives Runtime | **IMPLEMENTED** | `env` overrides, `network.enabled`, `communication.transport`, `rescs.*` |
| 8 | Security | **IMPLEMENTED** | Opt-in `enforce_authorization` (`false` default), `Existence`/`Token` providers |
| 9 | R.E.S.C.S. Adapter | **IMPLEMENTED** | Memory (default) + File (`var/rescs.json` on Windows) + Http stub |
| 10 | External Device Transport | **IMPLEMENTED** | `TcpTransport` localhost; external `0.0.0.0` + firewall **PLANNED** |
| 11 | CLI Lifecycle | **IMPLEMENTED** | `--config`/`--env`, foreground loop, legacy `execute(runtime)` deprecated |
| 12 | Integration Spine | **IMPLEMENTED** | `tests/integration/test_core_spine.py:1` |
| 13 | Cleanup / Docs / Release | **IMPLEMENTED** | This README · `pyproject.toml:7` `0.2.0` |

Deferred: Windows Service / Task Scheduler autostart, firewall rules, R.E.S.C.S. HTTP contract, agent scheduler.

## Configuration

`config/core.yaml:1` holds canonical nested-dot config validated by `core/configuration/validator.py:1`. Prefix `CORE_` maps `__` or `_` to `.` and coerces `true`/`false` to bool.

Key keys: `core.name/version`, `environment`, `logging.level`, `security.enforce_authorization/provider`, `communication.enabled/transport/host/port`, `network.enabled`, `rescs.enabled/adapter/path/endpoint`, `components.*.enabled`.

## Windows Co-Hosting

*   Both `C:\Users\rishi\Desktop\RISARMS\CORE` and `...\RESCS` run on the same laptop — no cross-host networking in `v0.2`.
*   `FileRescsAdapter` defaults to `var/rescs.json` via `pathlib.Path` for Windows paths; `InMemoryRescsAdapter` is default for tests.
*   `TcpTransport` binds `127.0.0.1` by default; `0.0.0.0` requires firewall exception (**deferred**).
*   Use `py` launcher (`py -m core`, `py -m pytest`) on Windows.

## Tests

324 tests (up from 320): `py -m pytest -q` · Integration spine in `tests/integration/test_core_spine.py:1`.

## Project Layout

```
CORE/
  core/
    application/    # CoreApplication
    communication/  # Transport, Local, Tcp, Serializer
    configuration/  # Manager, Loader, Models, Validator
    events/         # Bus, Types
    health/         # Monitor
    organization/   # Engine
    resources/      # Models, Registry (device/agent)
    rescs/          # Adapter (memory/file/http)
    runtime/        # Runtime, History
    security/       # Manager, Policy, Provider
    services/       # Manager, Dispatcher
    cli/            # Foreground loop, --config/--env
  config/core.yaml
  tests/
  var/              # rescs.json (ignored)
```

## Security

No hardcoded credentials. `TokenAuthenticationProvider` checks `identity.metadata["token"]` against message payload `credential`/`token`/`_credential`. Enforcement disabled until `security.enforce_authorization: true`.
