# C.O.R.E. — Communication, Organization and Resource Engine

**Version:** `0.2.1` · **Host:** Windows 11 (Intel Core Ultra 7 · 32 GB RAM · 1 TB) co-hosting **C.O.R.E.** and **R.E.S.C.S.** · **Python:** `>=3.10` (tested on `3.14.6` via `py` launcher, `3.14.7` on Windows)

C.O.R.E. is the lifecycle-aware, transport-agnostic orchestration spine for the R.I.S.A.R.M.S. platform. It owns runtime graphs, communication, routing, services, resources, organization, events, health, security, R.E.S.C.S. persistence and agent scheduling on a single Windows laptop that may offload agent execution for low-capability devices (phones, watches, R.O.V.E.R.T.).

## Quick Start (Windows PowerShell 5.1)

```powershell
py -m pip install -e .
py -m core --help
py -m core --config config/core.yaml --env development start   # foreground control loop (Ctrl+C to stop)
py -m core --config config/core.yaml status
py -m core --config config/core.yaml health
py -m core --config config/core.yaml resources
py -m core --config config/core.yaml services
py -m core --config config/core.yaml agents
py -m pytest -q
```

Configuration resolves `config/core.yaml` by default; `--config` overrides. Environment overrides via `CORE_*` (e.g., `CORE_COMPONENTS__HEALTH__ENABLED=false`, `CORE_DATABASE_HOST=env-host`, `CORE_SECURITY__PROVIDER=token`).

## Architecture

13 runtime components registered in dependency order (`core/application/app.py:120`):
`configuration → logging → security → resources → organization → events → communication → routing → health → rescs → dependencies → services → core`.

*   **Communication** — `Transport` ABC (`core/communication/transport.py:13`) with `LocalTransport` (`core/communication/transport.py:88`) and `TcpTransport` (`core/communication/tcp.py:1`) on `127.0.0.1` by default, `0.0.0.0` when `network.enabled=true` for LAN exposure. `MessageSerializer` (`core/communication/serializer.py:11`) preserves `identity_id` over wire. External binding requires Windows firewall rule (`docs/windows-firewall.md`).
*   **Routing / Services** — `Router` (`core/routing/router.py:16`) + `ServiceManager`/`ServiceDispatcher` (`core/services/dispatch.py:18`) with pluggable security (`core/security/provider.py:1`). 9 services including `agent` scheduler.
*   **Resources** — `ResourceRegistry` (`core/resources/registry.py:1`) + typed helpers `create_device_resource`/`create_agent_resource` (`core/resources/models.py:73`).
*   **Runtime History** — `RuntimeHistory` (`core/runtime/history.py:1`) tracks device/agent/service intervals; persisted via adapter.
*   **R.E.S.C.S. Adapter** — `RescsAdapter` (`core/rescs/adapter.py:1`) with `InMemoryRescsAdapter`, `FileRescsAdapter` (`var/rescs.json`), `HttpRescsAdapter` (real HTTP with fallback, `rescs.endpoint/timeout/fallback`).
*   **Agent Scheduler** — `AgentScheduler` (`core/scheduler/scheduler.py:1`) capability-driven `Device → suitable Agent → windows-host` offload, 3 default profiles (`asis-local`, `asis-offload`, `tiviss-compat`), exposed via `agent` service (`assign/release/profiles/assignments`).
*   **Health / Events** — `HealthMonitor` (`core/health/monitor.py:1`) 13 checks including `agent`/`rescs`, bridges to `EventBus` (`core/events/bus.py:1`).

## Phase Matrix (v0.2.1)

| Phase | Title | Status | Notes |
|-------|-------|--------|-------|
| 1 | Runtime + App Orchestration | **IMPLEMENTED** | DFS start order, reverse shutdown, `tests/application/test_application_orchestration.py:10` |
| 2 | Communication + Transport | **IMPLEMENTED** | `LocalTransport` + `TcpTransport` (localhost + `0.0.0.0` LAN), serializer fix `core/communication/serializer.py:11` |
| 3 | Routing + Service Execution | **IMPLEMENTED** | 5 routes `core/application/app.py:903`, 9 services incl. `agent` |
| 4 | Resource + Organisation | **IMPLEMENTED** | `ResourceRegistry` + `OrganizationEngine` + Device/Agent helpers |
| 5 | Events | **IMPLEMENTED** | Failure-isolated bus |
| 6 | Health | **IMPLEMENTED** | 13 checks including `rescs` + `agent` |
| 7 | Config Drives Runtime | **IMPLEMENTED** | `env` overrides, `network.enabled`, `communication.transport/host/port`, `rescs.*` |
| 8 | Security | **IMPLEMENTED** | Opt-in `enforce_authorization` (`false` default), `Existence`/`Token` providers |
| 9 | R.E.S.C.S. Adapter | **IMPLEMENTED** | Memory (default) + File (`var/rescs.json`) + Http real (fallback, `timeout`/`fallback`) |
| 10 | External Device Transport | **IMPLEMENTED** | `TcpTransport` `127.0.0.1` + `0.0.0.0` LAN with firewall (`docs/windows-firewall.md`) |
| 11 | CLI Lifecycle | **IMPLEMENTED** | `--config`/`--env`, foreground loop, `agents` command, `execute(runtime)` deprecated → removal v0.4.0 |
| 12 | Integration Spine | **IMPLEMENTED** | `tests/integration/test_core_spine.py:1` + scheduler `agent` flow |
| 13 | Cleanup / Docs / Release | **IMPLEMENTED** | This README · `pyproject.toml:7` `0.2.1` |

No deferred items for v0.2.1 — all 13 phases are implemented. Future: TLS for external transport, NSSM Windows Service alternative (`docs/windows-autostart.md`), auto-scheduler on device connect.

## Configuration

`config/core.yaml:1` holds canonical nested-dot config validated by `core/configuration/validator.py:1`. Prefix `CORE_` maps `__` or `_` to `.` and coerces `true`/`false` to bool.

Key keys: `core.name/version`, `environment`, `logging.level`, `security.enforce_authorization/provider`, `communication.enabled/transport/host/port`, `network.enabled`, `rescs.enabled/adapter/path/endpoint/timeout/fallback`, `components.*.enabled`.

```yaml
communication:
  host: "127.0.0.1"   # or "0.0.0.0" for LAN (requires network.enabled: true + firewall)
  port: 0            # 0 = ephemeral / local-only; set e.g. 5000 for TCP listener
  transport: local   # local | tcp | network | external
network:
  enabled: false
rescs:
  adapter: memory    # memory | file | http
  endpoint: http://localhost:8081
  timeout: 2.0
  fallback: true     # use in-memory fallback when HTTP unreachable
```

## Windows Co-Hosting

*   Both `C:\Users\rishi\Desktop\RISARMS\CORE` and `...\RESCS` run on the same laptop.
*   `FileRescsAdapter` defaults to `var/rescs.json` via `pathlib.Path`; `InMemoryRescsAdapter` is default for tests; `HttpRescsAdapter` delegates to `http://localhost:8081` with fallback.
*   `TcpTransport` binds `127.0.0.1` by default; `0.0.0.0` with `network.enabled: true` listens on all interfaces — add firewall rule (`docs/windows-firewall.md`) and autostart (`docs/windows-autostart.md`, `scripts/windows/install_core_task.ps1`).
*   Use `py` launcher (`py -m core`, `py -m pytest`) on Windows; `python3 -m pytest` on macOS/Linux.

## Tests

332 tests: `python3 -m pytest -q` (or `py -m pytest -q` on Windows) · Integration spine in `tests/integration/test_core_spine.py:1` + scheduler via `agent` service.

## Project Layout

```
CORE/
  core/
    application/    # CoreApplication
    communication/  # Transport, Local, Tcp, Serializer
    configuration/  # Manager, Loader, Models, Validator
    events/         # Bus, Types
    health/         # Monitor (13 checks)
    organization/   # Engine
    resources/      # Models, Registry (device/agent)
    rescs/          # Adapter (memory/file/http)
    runtime/        # Runtime, History
    scheduler/      # AgentScheduler, AgentProfile, Assignment
    security/       # Manager, Policy, Provider
    services/       # Manager, Dispatcher (9 services)
    cli/            # Foreground loop, --config/--env, agents
  config/core.yaml
  docs/
    windows-autostart.md
    windows-firewall.md
  scripts/windows/
    install_core_task.ps1
  tests/
  var/              # rescs.json (ignored)
```

## Security

No hardcoded credentials. `TokenAuthenticationProvider` checks `identity.metadata["token"]` against message payload `credential`/`token`/`_credential`. Enforcement disabled until `security.enforce_authorization: true`.
