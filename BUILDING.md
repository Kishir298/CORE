# Building CORE

## Prerequisites

- Python 3.10+ (3.12 is used in CI)
- `python -m pip install build pyinstaller`
- Windows: PowerShell 5.1 is sufficient; Git Bash is used by CI for packaging
  commands, but is not required to build wheels.

## Python wheels

```bash
python -m build --wheel --sdist CORE-HOST
python -m build --wheel --sdist CORE-CLIENT
```

Artifacts land in `CORE-HOST/dist/` and `CORE-CLIENT/dist/`.

## Standalone executables

```bash
python -m pip install -e CORE-HOST -e CORE-CLIENT
python -m PyInstaller --onefile --name core-host \
  --collect-submodules core --collect-data core \
  --distpath dist/host scripts/standalone_host.py
python -m PyInstaller --onefile --name core-client \
  --collect-submodules client --collect-data client \
  --distpath dist/client scripts/standalone_client.py
```

Each executable must be built on its target operating system and
architecture. Cross-compilation is not supported for the bundled runtime.

## Linux server bundle

```bash
python -m build --wheel CORE-HOST
mkdir -p server
cp CORE-HOST/dist/*.whl server/
cp CORE-HOST/deploy/linux/install-server.sh CORE-HOST/deploy/linux/core.service server/
tar -czf CORE-Server-$(python -c "import tomllib;print(tomllib.load(open('CORE-HOST/pyproject.toml','rb'))['project']['version'])")-linux-x64.tar.gz -C server .
```

## Automated releases

`.github/workflows/release.yml` builds Python wheels, standalone executables
for Windows x64/ARM64, macOS Intel/ARM64 and Linux x64/ARM64, plus the Linux
server bundle. Every artifact gets a SHA-256 checksum and the release includes
a CycloneDX SBOM.

A version tag `vX.Y.Z` must match both `pyproject.toml` files,
`compatibility.json` and `CORE-HOST/core/version.py`; the workflow fails
otherwise. Workflow-dispatch runs build artifacts without publishing a GitHub
Release.

## Tests

```bash
(cd CORE-HOST && python -m pytest -q)
(cd CORE-CLIENT && python -m pytest -q)
ruff check --select F CORE-HOST/core CORE-CLIENT/client
```
