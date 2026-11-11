# Changelog

All notable changes to CORE are documented here.

## [0.5.0] — 2026-11-11

### Added

- `core-host setup` command: prepares the private portal data directory and
  default configuration without binding a socket.
- Cross-platform GitHub Actions release pipeline for host, client and the
  Linux server bundle (Windows x64/ARM64, macOS Intel/ARM64, Linux x64/ARM64).
- SHA-256 checksums, CycloneDX SBOM and stable/beta/development channels.
- Machine-readable `compatibility.json` with platform, runtime and protocol
  declarations.
- Platform smoke job in CI (Ubuntu, Windows, macOS) that verifies the installed
  commands from an unrelated working directory.
- Documentation set: installation, building, releases, security and
  compatibility.

### Changed

- `core/version.py` now reports the package version `0.5.0` (previously stale
  at `0.4.0` while `pyproject.toml` shipped 0.5.0). `0.5.0` is added to the
  negotiated package versions.
- The wire protocol version is explicitly decoupled from the package version;
  protocol remains `0.4.0`.

### Fixed

- Version drift between package metadata and runtime version reporting.
- `core-host doctor` now reports platform and machine architecture.

## [0.4.0]

- Portal, TLS client and RESCS integration release. See the previous
  `CORE-HOST/README.md` release notes.
