# CORE Releases

CORE follows independent semantic versioning (`MAJOR.MINOR.PATCH`). The
current package version is declared in `CORE-HOST/pyproject.toml`,
`CORE-CLIENT/pyproject.toml`, `CORE-HOST/core/version.py` and
`compatibility.json`; the release workflow refuses to build if they differ.

The **wire protocol** has its own version (`0.4.0` in
`CORE-HOST/core/communication/protocol.py`). It is intentionally decoupled
from the package version, so a package release does not silently change the
protocol.

## Target

CORE 0.6.0 server releases target **Void Linux x86_64 glibc with runit** only.
The release archive is a source tree plus the Void installer and deployment
assets; it is not a portable server binary.

## Channels

| Channel | Trigger | GitHub Release |
| --- | --- | --- |
| Stable | tag `vX.Y.Z` | draft release, not prerelease; requires manifest channel `stable` |
| Beta | tag `vX.Y.Z-beta.N` | draft prerelease |
| Development | `workflow_dispatch` | artifacts only, no Release |

The manifest currently declares `release_channel: beta`, so the workflow
rejects a stable tag until that field is changed intentionally. Releases are
created with `--draft`; nothing is published automatically.

## Artifacts

- `CORE-Server-<version>-void-x86_64.tar.gz`
- `SHA256SUMS`
- `sbom-<name>.cdx.json`

The archive contains `CORE-HOST/`, `CORE-CLIENT/`, `services/`, `deployment/`,
`install/`, `validation/`, the compatibility manifest and the release docs.
The protected paths, checksum file and SBOM are not nested inside it.

## Process

1. Update the version in both `pyproject.toml` files, `core/version.py`,
   `compatibility.json` and `CHANGELOG.md`; set `release_channel` deliberately.
2. Run the full host and client test suites and the deployment static tests.
3. Commit, then create and push an annotated tag: `git tag -a vX.Y.Z-beta.N -m "CORE X.Y.Z-beta.N"`.
4. The workflow validates tag/version/channel/manifest agreement, tests, builds
   the Void archive, writes checksums and the SBOM, and creates a draft release.
5. A human reviews the draft, records the pending hardware validation, and
   publishes it only when authorized.

Never create a tag or release as part of an ordinary commit/push.

## Signing

CORE server archives are not code-signed and CORE has no signed server updater.
Do not label the release as hardware-certified or signed.
