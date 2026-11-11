# CORE Releases

CORE follows independent semantic versioning (`MAJOR.MINOR.PATCH`). The
current package version is declared in `CORE-HOST/pyproject.toml`,
`CORE-CLIENT/pyproject.toml`, `CORE-HOST/core/version.py` and
`compatibility.json`; the release workflow refuses to publish if they differ.

The **wire protocol** has its own version (`0.4.0` in
`CORE-HOST/core/communication/protocol.py`). It is intentionally decoupled
from the package version, so a package release does not silently change the
protocol.

## Channels

| Channel | Trigger | GitHub Release |
| --- | --- | --- |
| Stable | tag `vX.Y.Z` | published, not prerelease |
| Beta | tag `vX.Y.Z-beta.N` | published as prerelease |
| Development | `workflow_dispatch` | artifacts only, no Release |

Ordinary commits to `main` never publish a stable release; they only run CI.

## Artifacts

Naming: `CORE-<component>-<version>-<os>-<arch>-<format>`.

- `CORE-Host-<v>-windows-x64.zip`, `CORE-Host-<v>-windows-arm64.zip`
- `CORE-Client-<v>-windows-x64.zip`, `CORE-Client-<v>-windows-arm64.zip`
- `CORE-Host|Client-<v>-macos-x86_64.tar.gz`
- `CORE-Host|Client-<v>-macos-arm64.tar.gz`
- `CORE-Host|Client-<v>-linux-x64.tar.gz`
- `CORE-Host|Client-<v>-linux-arm64.tar.gz`
- `CORE-Server-<v>-linux-x64.tar.gz`
- `CORE-Host|Client-<v>-python-wheel.whl` and `-python-sdist.tar.gz`
- `SHA256SUMS`, `sbom.cdx.json`

## Process

1. Update the version in both `pyproject.toml` files, `core/version.py`,
   `compatibility.json` and `CHANGELOG.md`.
2. Run the full host and client test suites.
3. Commit, then create and push an annotated tag: `git tag -a vX.Y.Z -m "CORE X.Y.Z"`.
4. The release workflow validates, tests, builds all targets, verifies
   artifacts, writes checksums and the SBOM, and publishes the Release.
5. If any required matrix job fails, the publish job does not run.

Windows ARM64 is marked experimental because dependency availability differs
from x64; experimental failures are visible in the run summary and do not
silently disappear.

## Signing

macOS signing/notarization is only attempted when configured secrets exist.
Unsigned builds are labelled as such; they are never presented as notarized.
