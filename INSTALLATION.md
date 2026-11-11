# CORE Installation

C.O.R.E. ships as two installable commands plus an optional Linux server bundle.
Both commands run on Windows 10 22H2+, Windows 11, macOS (Intel/Apple Silicon)
and Linux (x86_64/ARM64). Python 3.10+ is required.

## Install from source

```bash
python -m pip install -e CORE-HOST
python -m pip install -e CORE-CLIENT
```

This installs `core-host` and `core-client` into the active environment's
`Scripts/` (Windows) or `bin/` (macOS/Linux) directory. Use `pipx install` if
you want the commands isolated from your project environments.

## Verify the commands resolve globally

`core-host` and `core-client` work from any terminal directory because they
store data in per-user locations, never in the current directory.

```bash
cd /
core-host --help
core-client --help
core-host doctor
core-client doctor
```

If the commands are not found on macOS/Linux, add the interpreter's `bin`
directory to `PATH` (for example `~/.local/bin`). On Windows with PowerShell
5.1, the `Scripts` directory is normally added by the Python installer; if it
is missing, add it to the user `PATH` through *System Properties → Environment
Variables*.

## Host setup

```bash
core-host setup
core-host init-owner --owner-seed owner-seed.json
core-host start
```

`setup` creates the private portal data directory and default
`gateway.json`. It never binds a socket. `init-owner` requires a private,
salted owner-verifier file and is only needed once.

Data locations:

- Windows: `%LOCALAPPDATA%\RISARMS\CORE\web`
- macOS: `~/.local/share/RISARMS/CORE/web` (unless `XDG_DATA_HOME` is set)
- Linux: `$XDG_DATA_HOME/RISARMS/CORE/web` or `~/.local/share/RISARMS/CORE/web`

Override with `--data` or `CORE_WEB_DATA`.

## Client setup

```bash
core-client setup --url https://core.example.com
core-client doctor
core-client            # desktop interface
core-client browser    # browser portal
core-client native --help
```

The saved portal URL is per-user and can be overridden with `--url` or
`CORE_PORTAL_URL`.

## Linux server deployment

Download `CORE-Server-VERSION-linux-x64.tar.gz` from the release page. It
contains the `core` wheel, `install-server.sh` and `core.service`.

```bash
tar -xzf CORE-Server-*-linux-x64.tar.gz -C /tmp/core-server
sudo /tmp/core-server/install-server.sh
sudo systemctl enable --now core
```

The server bundle is Linux-only by design; Windows and macOS run
`core-host start` as a user process.

## Updating

Reinstall the wheel or rerun `pip install -e`. User data under the portal data
directory and the saved client URL are preserved. Configuration files are
never overwritten by an update.

## Uninstall

```bash
python -m pip uninstall core core-client
```

Uninstalling does not delete portal data, user accounts, device records,
credentials or the saved client URL. Remove the data directory manually only
if you intend to erase them.

## Platform notes

- Windows 10 22H2 is validated independently from Windows 11; PowerShell 5.1
  is supported and WSL is not required.
- macOS builds are unsigned unless release signing secrets are configured;
  Gatekeeper may require *Open Anyway* for unsigned local builds.
- SSH/headless Linux hosts should use `--no-browser`; the server is headless
  by default.
