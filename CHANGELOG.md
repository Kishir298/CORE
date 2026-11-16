# Changelog

All notable changes to CORE are documented here.

## [0.6.0] — 2026-11-16

### Added

- Void Linux x86_64 glibc/runit server release target for the HP 14.
- Release-grade installer with root/platform checks, a 5 GiB free-space guard,
  versioned virtual environments, stable symlinks, atomic install-state
  snapshots and rollback on failure.
- Caddy site, nftables include, elogind lid-ignore configuration and svlogd
  rotation (1 MiB, 10 archives, daily).
- Backup, restore, upgrade, rollback and `risarms-doctor` operators installed to
  `/usr/local/sbin`.
- Desktop control channel, per-profile service grants, registered owner-device
  binding and queued owner actions (from the feature branch).
- Static deployment tests, compatibility-manifest checks and a Void-only draft
  release workflow.

### Changed

- Package version is `0.6.0`; `core/version.py` reports `0.6.0` and the wire
  protocol remains `0.4.0` with `0.3.0` accepted.
- Server releases ship `CORE-Server-<version>-void-x86_64.tar.gz` only.
- Raspberry Pi/ARM64, systemd, Windows-host and macOS-host server deployments
  are historical for this release.
- Releases are created as drafts and are never published automatically.

### Fixed

- Gateway origin reconciliation no longer rotates the RESCS key.
- Service logs rotate predictably instead of growing without bound.

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
