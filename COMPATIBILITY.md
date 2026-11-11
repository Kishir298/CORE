# CORE Compatibility

Machine-readable source of truth: [`compatibility.json`](compatibility.json).

## Platforms

| OS | Architectures | Minimum | Status |
| --- | --- | --- | --- |
| Windows | x86_64, arm64 | Windows 10 22H2 | CI smoke on windows-latest; Win10 requires hardware validation |
| macOS | x86_64, arm64 | macOS 12 | CI smoke on macos-latest |
| Linux | x86_64, arm64 | glibc 2.28 | CI tests on ubuntu-latest |

PowerShell 5.1 is supported. WSL, Windows Terminal, winget and Bash are not
required to run the installed commands.

## Versions

- Package: `0.5.0` (`core` and `core-client`)
- Wire protocol: `0.4.0`, with `0.3.0` still accepted
- Supported package negotiation: `0.2.0` through `0.5.0`

A component connecting to CORE must confirm the negotiated protocol version
before sending service requests. Protocol `0.4.0` remains backward compatible
with `0.3.0` wire clients.

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
3. Installer: not tested on physical Windows hardware in this workspace.
4. Runtime: host/client tests run on macOS locally and Linux/Windows in CI.
5. Physical hardware: **not verified** for Windows 10, Windows ARM64, Linux
   ARM64 or macOS Intel in this workspace.
