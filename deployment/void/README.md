# CORE Void Linux deployment

This directory is the release-grade CORE 0.6.0 deployment for Void Linux x86_64 glibc with runit. The target is the HP 14-dq1037wm. ARM64, Raspberry Pi, systemd, Windows-host, and macOS-host server deployments are not supported by this release.

## Prerequisites

```bash
sudo xbps-install -S python3 python3-pip caddy runit-void nftables elogind
```

The installer requires root, x86_64, Void Linux, glibc, and at least 5 GiB free under `/var/lib/risarms`. It does not partition or format storage.

## First install

```bash
sudo ./install.sh
sudo tail -n 50 /var/log/risarms/core/current
```

The installer creates:

- `/opt/risarms/venvs/<version>/{core,rescs}` plus stable `core-venv` and `rescs-venv` links.
- `/etc/risarms/{core.env,rescs.env,gateway.json}`.
- `/var/lib/risarms/{core,rescs,frontend,backups,install-state}`.
- `/var/log/risarms/{core,rescs}` with svlogd rotation.
- `/etc/sv/risarms-{core,rescs}` with runit log services.
- `/etc/caddy/risarms/portal.caddy` for the configured HTTPS origin.
- `/etc/nftables.d/risarms.nft`, `/etc/elogind/logind.conf.d/risarms.conf`, and operator scripts.

Services are installed but not enabled. Review configuration first, then enable:

```bash
sudo ln -s /etc/sv/risarms-rescs /var/service/
sudo ln -s /etc/sv/risarms-core /var/service/
sudo ln -s /etc/sv/caddy /var/service/
sudo sv status risarms-core risarms-rescs caddy
sudo risarms-doctor
```

The default origin is `https://core.local`. To change it safely without rotating keys:

```bash
sudo RISARMS_PUBLIC_ORIGIN=https://core.example.test ./install.sh
```

## Logs and diagnostics

```bash
sudo tail -n 100 /var/log/risarms/core/current
sudo tail -n 100 /var/log/risarms/rescs/current
sudo sv status risarms-core risarms-rescs caddy
sudo risarms-doctor
```

svlogd rotates at 1 MiB, keeps 10 archives, and rotates daily.

## Backup and restore

```bash
sudo risarms-backup
sudo risarms-restore --yes /var/lib/risarms/backups/risarms-<stamp>.tar.gz
```

Backups include CORE data, RESCS data, frontend files, `/etc/risarms`, Caddy/nftables/elogind configuration, and runit service definitions. They contain secrets, are mode `0600`, and are not encrypted by the installer. Default retention is 14 days; set `RISARMS_BACKUP_RETENTION_DAYS` to change it.

## Upgrade and rollback

```bash
sudo ./upgrade.sh /path/to/new/CORE-Server-<version>-void-x86_64
sudo risarms-rollback
```

Each release gets its own virtual environments. Upgrade builds the new environments before switching stable symlinks and records the previous version. Rollback switches back to the previous environments. Restore configuration and data with `risarms-restore` when required.

## Storage and failure behavior

The installer refuses to run below the configured free-space floor. It does not claim external-SSD, power-loss, or filesystem-failure protection. SQLite and RESCS files stay on the internal disk. Back up both CORE and RESCS together while services are stopped.

## Known pending gates

- Booted Void installation and reboot test on the HP.
- Real runit service start/stop, Caddy trust, and nftables load.
- Upgrade, rollback, backup, restore, and storage-failure drills.
- Physical HP firmware, thermal, and memory-upgrade validation.
- The 2 x 8 GB Samsung DDR4-2666 upgrade is planned, not installed or verified.
