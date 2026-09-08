# C.O.R.E. — Communication, Organization and Resource Engine

**Version:** `0.3.0` · **Host:** Windows 11 (Intel Core Ultra 7 · 32 GB RAM · 1 TB) co-hosting **C.O.R.E.** and **R.E.S.C.S.** · **Python:** `>=3.10` (tested on `3.14.6` via `py` launcher, `3.14.7` on Windows)

C.O.R.E. is the lifecycle-aware, transport-agnostic orchestration spine for the R.I.S.A.R.M.S. platform. It owns runtime graphs, communication, routing, services, resources, organization, events, health, security, R.E.S.C.S. persistence and agent scheduling on a single Windows laptop that may offload agent execution for low-capability devices (phones, watches, R.O.V.E.R.T.). **Legacy versions `0.2.0`/`0.2.1` remain supported** via negotiation (`core/version.py:1`, `runtime.version` service, `CORE_VERSION`).

> **Legacy preservation:** All `0.2.x` clients (plaintext `LocalTransport`/`TcpTransport` localhost, explicit `agent.assign`, `InMemory`/`File` RESCS) continue to work. `0.3.0` adds TLS + auto-assign + Http fallback as **opt-in higher versions** — no breaking change.

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
*   **Organization Ingestion** — `ResourceIngestor` (`core/organization/ingestion.py:1`): R.E.S.C.S. adapter → strict contract validation → normalize into existing `Resource` (storage extras dropped) → registry upsert → stable `resource:<id>` entries via existing `categorize_resource` (idempotent, in-place updates, explicit-deletion removal, backend failure never deletes) → `reconcile()` for authoritative refresh (`added/updated/removed/unchanged/failed/errors`, deterministic). `OrganizationEngine` (`core/organization/engine.py:1`) is thread-safe (`RLock`, snapshot iteration), validates entries (`OrganizationValidationError`), preserves full metadata (`resource_type/owner/source/status/capabilities/metadata/connection_info` with defensive copies; `last_seen/registered_at` stay lifecycle-only), and exposes `organize_resource/ingest_resource/ingest_all/reconcile/forget_resource` reusing the ingestor. Full spec in `docs/organization-rescs.md`; boundary tests in `tests/organization/test_organization_ingestion.py:1` + validation/metadata/concurrency/reconciliation suites.
*   **Runtime History** — `RuntimeHistory` (`core/runtime/history.py:1`) tracks device/agent/service intervals; persisted via adapter.
*   **R.E.S.C.S. Adapter** — `RescsAdapter` (`core/rescs/adapter.py:1`) with `InMemoryRescsAdapter`, `FileRescsAdapter` (`var/rescs.json`), `HttpRescsAdapter` (real HTTP with fallback, `rescs.endpoint/timeout/fallback`).
*   **Agent Scheduler** — `AgentScheduler` (`core/scheduler/scheduler.py:1`) capability-driven `Device → suitable Agent → windows-host` offload, 3 default profiles (`asis-local`, `asis-offload`, `tiviss-compat`), exposed via `agent` service (`assign/release/profiles/assignments`).
*   **Health / Events** — `HealthMonitor` (`core/health/monitor.py:1`) 14 checks including `devices`/`agent`/`rescs`, bridges to `EventBus` (`core/events/bus.py:1`).
*   **Device Communication** — `DeviceRegistry` (`core/communication/devices.py:1`, authoritative, thread-safe, mirrored into `ResourceRegistry`) + protocol constants (`core/communication/protocol.py:1`): `DEVICE_REGISTER`/`DISCOVER`/`INFO` with presence (`online`/`offline`), destination validation, `device -> C.O.R.E. -> device` routing preserving `message_id`/`request_id`/`identity_id`, `DEVICE_ERROR` envelopes, `DEVICE_CONNECTED`/`DISCONNECTED` events. Full spec in `docs/device-communication.md`; localhost simulation in `tests/integration/test_device_messaging.py:1`.
*   **Data Organization** — `DataOrganizer` (`core/data/organizer.py:1`): `DATA_REQUEST` → owner-scoped R.E.S.C.S. retrieval (`core/data/rescs_reader.py:1`: existing-adapter + HTTP backends, 2.0 s timeout, 0 retries) → normalization, deterministic ordering (`updated_at` DESC, `id` ASC), pagination (`limit` 1–500, `offset` ≥ 0) → `DATA_RESPONSE`/`DATA_ERROR` via existing device routing incl. `destination_device_id` distribution. Limits: 500 items, 5 MiB record/file-metadata budgets, 1 MiB inline files with SHA-256 verification. Full spec in `docs/data-distribution.md`; localhost simulation in `tests/integration/test_data_distribution.py:1`.

## Phase Matrix (v0.3.0)

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
| 13 | Cleanup / Docs / Release | **IMPLEMENTED** | This README · `pyproject.toml:7` `0.3.0` |

All 13 phases are implemented as of v0.3.0 (TLS for external transport, auto-scheduler on device connect, NSSM alternative in `docs/windows-autostart.md`). Legacy `0.2.1` clients remain supported via negotiation.

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

  569 passed, 3 skipped: `python3 -m pytest -q` (or `py -m pytest -q` on Windows) · Integration spine in `tests/integration/test_core_spine.py:1` + scheduler via `agent` service + device localhost simulation in `tests/integration/test_device_messaging.py:1` and `tests/communication/test_device_protocol.py:1` + data distribution simulation in `tests/integration/test_data_distribution.py:1` and `tests/data/:1` + persistence simulation in `tests/communication/test_device_persistence.py:1` + organization boundary in `tests/organization/test_organization_ingestion.py:1`. Physical-device communication has NOT been demonstrated; all device behavior is validated via `127.0.0.1` simulation (see `docs/lan-readiness.md`, status NOT YET PERFORMED).

## Project Layout

```
CORE/
  core/
    application/    # CoreApplication
    communication/  # Transport, Local, Tcp, Serializer, Protocol, DeviceRegistry
    configuration/  # Manager, Loader, Models, Validator
    data/           # DataOrganizer, RescsDataReader, validation, normalization
    events/         # Bus, Types
    health/         # Monitor (14 checks)
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
    data-distribution.md
    device-communication.md
    lan-readiness.md
    organization-rescs.md
    windows-autostart.md
    windows-firewall.md
  scripts/windows/
    install_core_task.ps1
  tests/
  var/              # rescs.json (ignored)
```

## Security

No hardcoded credentials. `TokenAuthenticationProvider` checks `identity.metadata["token"]` against message payload `credential`/`token`/`_credential`. Enforcement disabled until `security.enforce_authorization: true`.

## External-Device Communication

Current C.O.R.E. version = 0.3.0.

External TCP requires TLS. External devices authenticate before application messages.
Connections are persistent. Maximum frame size is 10 MB. Maximum active connections is 64.
Idle connections expire after 300 seconds. TLS handshake timeout is 5 seconds.

* `0.0.0.0` binding fails closed without valid TLS (no plaintext downgrade); `127.0.0.1` keeps legacy plaintext for local operation/tests. TLS minimum is 1.2.
* External authentication cannot use existence-only authentication: `TokenAuthenticationProvider` is required for external-device configuration; missing or existence-only configuration fails closed and the listener does not start. External identities must have a configured token.
* Handshake: `CORE_HANDSHAKE {identity_id, credential, protocol_version}` → `CORE_HANDSHAKE_RESPONSE {authenticated, identity_id, protocol_version, connection_id}` using existing `Message` format + `core.version` negotiation.
* Every application message must carry `identity_id == connection.identity_id` and `source == connection.identity_id`; violations close the connection.
* States: `CONNECTED → TLS_ESTABLISHED → AUTHENTICATING → AUTHENTICATED → CLOSING → CLOSED`.
