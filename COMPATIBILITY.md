# CORE Compatibility

Machine-readable source of truth: [`compatibility.json`](compatibility.json).

## Platforms

| Role | OS | Architectures | Minimum | Status |
| --- | --- | --- | --- | --- |
| Server | Void Linux (glibc, runit) | x86_64 | glibc 2.28 | Release target; booted HP 14 validation pending |
| Legacy client | Windows | x86_64, arm64 | Windows 10 22H2 | CORE-CLIENT only; not a 0.6.0 server target |
| Legacy client | macOS | x86_64, arm64 | macOS 12 | CORE-CLIENT only; RISARMS-ui delivers the desktop app |
| Legacy client | Linux | x86_64, arm64 | glibc 2.28 | CORE-CLIENT only; not a 0.6.0 server target |

CORE 0.6.0 server releases are source archives for Void Linux x86_64 with glibc
and runit. Raspberry Pi/ARM64, Windows-host and macOS-host server deployments
are historical or unsupported. PowerShell 5.1 is supported for the legacy
Windows client; WSL, Windows Terminal, winget and Bash are not required.

## Versions

- Package: `0.6.0` (`core` and `core-client`)
- Bundled RESCS: `0.4.0`
- Wire protocol: `0.4.0`, with `0.3.0` still accepted
- Supported package negotiation: `0.2.0` through `0.6.0`
- Release channel: `beta`

A component connecting to CORE must confirm the negotiated protocol version
before sending service requests. Protocol `0.4.0` remains backward compatible
with `0.3.0` wire clients. The release workflow rejects a stable tag while the
manifest channel is `beta`.

## Integration status

| Component | Integration | Status |
| --- | --- | --- |
| RESCS | HTTP API via `X-API-Key` | IMPLEMENTED |
| ASIS | CORE-CLIENT adapter | IMPLEMENTED, optional |
| ASCS | CORE-CLIENT adapter | IMPLEMENTED, optional |
| TIVISS | device registration | IMPLEMENTED |

CORE remains fully usable when an integration is offline.

## Validation levels

1. Source compilation: verified locally and in CI.
2. Package generation: exercised by the release workflow.
3. Installer: static tests only; no booted Void install yet.
4. Runtime: host/client tests run on macOS locally and Linux/Windows in CI.
5. Physical hardware: **not verified** for the HP 14/Void target, Raspberry Pi,
   or any desktop platform in this workspace.
