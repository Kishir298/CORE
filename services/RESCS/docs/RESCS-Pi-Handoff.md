# RESCS Raspberry Pi storage update

6 November 2026. RESCS 0.4.0 implements the storage-specific foundation from the latest RISARMS Portal Setup and Changes document, including the added ASIS/ASCS chapter. RESCS needs no AI model, laptop, desktop session or cloud authentication. Raspberry Pi OS Lite 64-bit with Python 3.11+ is the deployment target; only Linux x86_64 Python 3.12 was executed here. This is a source release, not hardware certification or a live deployment.

## What changed

Installed `rescs` command with setup, doctor and loopback startup. Normal startup never publishes a tunnel or downloads models. Packaging declares portable Python dependencies; optional PostgreSQL and S3 remain separate. Existing uvicorn factory startup works.

The Pi installer creates separate `rescs` and `core` service accounts/environments. RESCS files/database/temp spool live on the mounted SSD. Its unit requires and binds to srv-core.mount, limits crash retries and prevents writes outside its private directory. Startup and every HTTP request reject a missing required mount; invalid database/object paths fail rather than silently create microSD storage. Real SSD unplug/cold-boot recovery still requires Pi testing.

Local blob writes fsync content before atomic rename, then fsync the directory on POSIX. Disk-full write failure is tested to leave no successful object or temporary blob. This does not provide a distributed database/blob transaction or a guarantee against all hardware faults.

Signed gateway mode binds each API request to an expiring owner/method/path assertion, plus X-API-Key authentication. CORE derives that owner from its authenticated account UUID. RESCS scopes reads, listings, searches, downloads, deletes, restores, resumable uploads and bulk ownership checks. An owner/admin UI role does not grant another person's content. Global cleanup is disabled through profile assertions. API and gateway secrets stay server-side. The gateway is trusted and can mint assertions; an operator/root compromise is outside this application boundary. Assertions can be replayed briefly and are not a substitute for private transport and gateway session/CSRF controls.

Record PUT and idempotency replays reject different owners. Existing database schema 0.3.0 remains: namespace/key uniqueness is unchanged, so CORE must keep using distinct `personal.profile.UUID.SERVICE` namespaces. This release does not claim identical namespace/key pairs for different owners are supported. No automatic migration of existing private data is performed.

## Included packages

The combined ZIP contains complete RESCS source, the 4 November CORE-HOST release with only its storage adapter patched, and install-pi.sh. The separate RESCS ZIP can be installed independently. CORE-CLIENT, ASIS, ASCS, Our Library and Day Quest are not modified. Earlier CORE model selection remains present; do not use its larger model recommendations as Pi approvals. The added document's AI queue/admission/sandbox work belongs in those service releases.

## Pi installation

Mount the verified SSD at /srv/core first, following the document. No script formats a disk, edits fstab, enables Samba, purchases components or replaces the OS. Install python3, python3-venv and pip using apt first. Review scripts before root installation.

From the combined extracted directory:

```sh
sudo bash install-pi.sh
sudo nano /etc/core/core.env
sudo systemctl enable --now rescs core
sudo systemctl status rescs core
sudo journalctl -u rescs -u core -b --no-pager
```

Set CORE_PUBLIC_ORIGIN to the real HTTPS origin and configure the proxy/private access separately. CORE binds on 8780, RESCS on 127.0.0.1:8081. The installer seeds matching gateway credentials without printing them; do not edit them independently. It installs but does not start/enable services. Readiness checks gate CORE startup. Configure ingress before enabling. Failed mounts may require `systemctl reset-failed rescs core` then an explicit restart after the SSD is mounted.

Existing /var/lib/core data blocks combined installation. Stop both services and take an off-device backup. Copy the CONTENTS of the old web directory to /srv/core/core, retaining gateway.json, accounts, profiles and ownership. Move existing RESCS SQLite database and blobs together to the new paths, retaining originals for rollback; never initialize over them. Reconcile matching API keys in /etc/rescs/rescs.env and gateway.json. Remove/archive the old /var/lib/core content only after verified migration and backup so the installer preflight can proceed. This manual migration requires operator review and has not been run on user data.

## Independent installation on Windows macOS and Linux

Use Python 3.11+ and pipx. Install with `pipx install /absolute/path/to/RESCS`, run `pipx ensurepath` and reopen the terminal. On Windows use the extracted Windows path instead. Then:

```sh
rescs setup
rescs doctor
rescs
rescs --help
```

Alternatively install into a venv with `python -m pip install /path/to/RESCS`; activate that venv before using `rescs` or add its Scripts (Windows) or bin (POSIX) directory to persistent user PATH. `where rescs` on Windows or `command -v rescs` on POSIX diagnoses PATH. Setup creates a private per-user env file; Windows users must restrict its ACL. Existing configs are preserved. Explicit configs use `rescs --config /path/to/rescs.env doctor` or `serve`. Environment values override env-file settings. Raw `python -m uvicorn rescs.main:create_app --factory --host 127.0.0.1 --port 8081` remains supported using RESCS environment configuration.

Standalone per-user data: LOCALAPPDATA/RESCS on Windows, ~/Library/Application Support/RESCS on macOS, XDG_DATA_HOME/rescs or ~/.local/share/rescs on Linux. Setup writes durable paths there. Remote backends are never silently replaced by local storage.

## Configuration and limits

Pi: RESCS_DATABASE_URL=sqlite:////srv/core/rescs/database/rescs.sqlite3; RESCS_STORAGE_DIR=/srv/core/rescs/files; RESCS_REQUIRED_MOUNT=/srv/core; RESCS_REQUIRE_SIGNED_OWNER=true; RESCS_ENV=production; TMPDIR=/srv/core/rescs/tmp. RESCS_API_KEY is generated privately; RESCS_API_KEY_OWNER is empty because the gateway supplies authenticated scope per request. RESCS_AUTO_CREATE_SCHEMA defaults true. Installer caps files at 8 MiB, bytes at 250 MiB per owner and records at 2000 total per owner; CORE additionally retains its 1000-per-service scope cap. Quota changes require coordinated CORE changes. Trash retains bytes in the object store with metadata tombstones, not a separate moved copy; the reserved trash directory is not an implemented recycle-bin filesystem. See existing quotas/backups docs for accounting details.

## File behavior and remaining document requirements

Existing file APIs list metadata without downloading content. Actual downloads verify ownership and CORE validates SHA-256. Uploads are durable server objects independent of the laptop. Soft delete, restore and permanent purge exist in RESCS; CORE's UI does not yet expose all recovery actions. The existing portal supports flat personal files, not an implemented folder/Family Shared/project ACL interface. Sharing is denied by default; no broad admin bypass or Samba access is added. Folder destinations, explicit sharing ACLs and browser preview UI remain future CORE/RESCS work. This package is not a claim that every acceptance item in the document is finished.

Gateway login, session revocation, password re-entry, UI layout and chat privacy remain CORE responsibilities and were not re-certified here. ASCS must not run as rescs/root or receive /srv/core/rescs access. Root can read plaintext; client-side encryption is deferred. Keep raw database/model/storage ports private.

## Offline preparation backup and rollback

Local files/records, loopback HTTP, Trash and setup/doctor work without internet after dependencies are installed. Remote clients need LAN/Tailscale connectivity; remote S3/PostgreSQL need their networks. Package downloads and updates need internet. RESCS itself uses no model.

Prepare wheels on the SAME target Python/OS/architecture with `python -m pip wheel /path/to/RESCS -w wheelhouse`. Copy the source and wheelhouse to the target; install with `python -m pip install --no-index --find-links wheelhouse /path/to/RESCS`. Optional providers need their own prepared wheels. No ARM64 wheelhouse or model weights are bundled. A built universal RESCS wheel is supplied; transitive wheels remain target-specific.

Stop CORE and RESCS before a coordinated backup. Back up all /srv/core/core and /srv/core/rescs plus protected configs to a separate encrypted destination. Existing scripts/rescs_backup.py supports SQLite/blob copies with SHA-256 manifest verification; staging under /srv/core/backups is on the same SSD and is not disaster protection. Restore matching database/blobs/configs while stopped, fix service ownership, verify manifest hashes and test a download before enabling traffic. To roll back, stop services, reinstall the previous source packages/units and restore matching data/config backups. Never delete data during uninstall. Live user-data migration and off-device restore were not executed.

## Validation

RESCS full suite: 312 passed, four live PostgreSQL/S3 tests skipped. New real in-process API tests cover account isolation, Trash/restart persistence and invalid/expired signatures. Mount absence/path checks and disk-full use controlled OS failures. Real uvicorn loopback with the patched CORE adapter passed record save/list, file upload/download, cross-user rejection and delete. Ruff F checks passed; shell syntax checks passed; universal wheel built; installed rescs help runs outside source directory. Linux x86_64 Python 3.12 only. No real Pi/ARM64, Windows/macOS, root install, systemd boot, physical SSD loss, public TLS, AI inference, sharing UI or full CORE suite executed. GitHub was read only and no public deployment was performed.
