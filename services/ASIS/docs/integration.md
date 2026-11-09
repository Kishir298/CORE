# Integrations (C.O.R.E. real / R.E.S.C.S. future)

C.O.R.E. is a **real, optional** uplink — A.S.I.S. runs fully without
it. R.E.S.C.S. remains a future boundary. Nothing in `asis/` imports
C.O.R.E.-HOST or R.E.S.C.S. server code.

## C.O.R.E. (implemented)

```text
A.S.I.S. (AssistantApp, GENERAL + A.S.C.S. modes, voice)
   ↓  ToolRouter / PermissionManager / ToolExecutor
CORE tools (core_status/discover/device_info/data/service/agent/send)
   ↓
CoreClient ABC  asis/integrations/core/client.py
   ↓
RealCoreAdapter asis/integrations/core/adapter.py (lifecycle: CoreConnectionManager)
   ↓
CoreDeviceClient (CORE-CLIENT, TCP+TLS, ephemeral session)
   ↓
CORE-HOST
```

CORE tools are also exposed to the LLM as native function definitions
with parameter schemas; native CORE calls travel the identical
ToolRouter/permission/adapter path as explicit `core:` commands.

`CoreClient` defines the contract (legacy `send_message` /
`request_service` / `publish_event` / `get_resource` /
`register_component` / `get_health` plus lifecycle `connect` /
`disconnect` / `is_connected` / `device_status` / `send_request` /
`request`). `RealCoreAdapter` implements it over the real device
client; `MockCoreAdapter` remains the offline stand-in. Configuration:
`ASIS_CORE_*` (see `docs/configuration.md` and `.env.example`);
standalone by default; bounded reconnect; bounded shutdown.
The `asis` and `asis voice` entry points (`asis/cli/main.py:
build_core_manager`) own the single process-wide manager and pass it
to `AssistantApp`, so text, A.S.C.S., and voice share one connection;
the provisioning credential arrives only via the runtime-only
`ASIS_CORE_CREDENTIAL` environment variable.
Physical Windows ↔ Mac LAN validation: NOT PERFORMED.

## Web (implemented)

Basic web access is a separate, CORE-independent capability:

```text
A.S.I.S. (AssistantApp, GENERAL + A.S.C.S. modes, voice)
   ↓  ToolRouter / PermissionManager / ToolExecutor
web_search / web_fetch (shared registry, LOW permission)
   ↓
WebProvider ABC  asis/web/provider.py (DuckDuckGo HTTP backend, no key)
   ↓
Internet
```

Web traffic is never routed through CORE, and CORE code is never
touched by web changes. Configuration: `ASIS_WEB_*` (see
`docs/configuration.md` and `.env.example`); optional and off-switchable
via `ASIS_WEB_ENABLED`; bounded and shutdown-safe. Retrieved pages are
untrusted data (see `docs/tools-permissions.md`). Live internet
validation: PERFORMED (2026-09-17, `ASIS_WEB_LIVE=1`: real fetch of a
public page + real search query, both passing).

## R.E.S.C.S. (future)

Intended relationship:

```text
A.S.I.S.
   ↓
MemoryProvider / StorageProvider   (local SQLite today)
   ↓
Future RESCS Adapter               asis/integrations/rescs/adapter.py (placeholder)
   ↓
C.O.R.E.
   ↓
R.E.S.C.S.
```

`StorageClient` defines the contract (`store/retrieve/search/delete`).
The shipped adapter reports unavailable and raises `MemoryError`
directing callers to local memory. Rules: no direct cloud-DB coupling
in A.S.I.S., no fake cloud integration, integration arrives through
these abstractions.
