#!/usr/bin/env bash
# No disk formatting, fstab changes, credential resets, or automatic service enable.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo after mounting the SSD.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
[[ $(uname -m) == aarch64 ]] || { echo 'This Pi installer requires ARM64 Linux. Do not use a 32-bit OS.' >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ is required"'
for tool in systemctl findmnt mountpoint caddy runuser; do command -v "$tool" >/dev/null; done
mountpoint -q /srv/core || { echo 'Mount the selected ext4 SSD at /srv/core first.' >&2; exit 1; }
CORE_SSD_UUID=$(findmnt -n --mountpoint /srv/core -o UUID)
export CORE_SSD_UUID
python3 "$SOURCE/deployment/pi/guard.py"
# Installer never writes into live data or performs an in-place live upgrade.
for unit in risarms-core risarms-rescs; do
    if systemctl is-active --quiet "$unit"; then echo "Stop $unit and take a backup before installation." >&2; exit 1; fi
done
for account in risarms-core risarms-rescs; do
    if ! id "$account" >/dev/null 2>&1; then useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin "$account"; fi
done
install -d -m 0755 /opt/risarms /opt/risarms/deployment /opt/risarms/frontend
install -d -m 0700 /etc/risarms
install -d -m 0700 -o risarms-core -g risarms-core /srv/core/core
install -d -m 0700 -o risarms-rescs -g risarms-rescs /srv/core/rescs /srv/core/rescs/database /srv/core/rescs/files /srv/core/rescs/trash /srv/core/rescs/tmp
install -d -m 0700 /srv/core/backups
for app in our-library day-quest; do install -d -m 0700 "/srv/core/$app"; done
if ! getent group risarms-ai >/dev/null; then groupadd --system risarms-ai; fi
usermod -a -G risarms-ai risarms-core
install -m 0644 "$SOURCE/services/ASCS/deploy/pi/risarms-inference.conf" /etc/tmpfiles.d/risarms-inference.conf
systemd-tmpfiles --create /etc/tmpfiles.d/risarms-inference.conf
python3 -m venv /opt/risarms/core-venv
python3 -m venv /opt/risarms/rescs-venv
/opt/risarms/core-venv/bin/python -m pip install "$SOURCE/CORE-HOST"
/opt/risarms/rescs-venv/bin/python -m pip install -r "$SOURCE/deployment/pi/rescs-requirements.txt" "$SOURCE/services/RESCS"
install -m 0644 "$SOURCE/deployment/pi/guard.py" /opt/risarms/deployment/guard.py
install -m 0644 "$SOURCE/CORE-HOST/core/web/portal.html" /opt/risarms/frontend/index.html
install -m 0644 "$SOURCE/deployment/pi/risarms-core.service" "$SOURCE/deployment/pi/risarms-rescs.service" /etc/systemd/system/
if [[ ! -f /etc/risarms/core.env && ! -f /etc/risarms/rescs.env ]]; then
    python3 "$SOURCE/deployment/pi/configure.py" --ssd-uuid "$CORE_SSD_UUID"
elif [[ ! -f /etc/risarms/core.env || ! -f /etc/risarms/rescs.env ]]; then
    echo 'Only one existing environment file exists; repair configuration without regenerating keys.' >&2; exit 1
fi
chown risarms-core:risarms-core /srv/core/core/gateway.json
chmod 0600 /etc/risarms/*.env /srv/core/core/gateway.json
# Secure existing service trees too; no other application directories are touched.
chown -R risarms-core:risarms-core /srv/core/core
chown -R risarms-rescs:risarms-rescs /srv/core/rescs
install -d -m 0755 /etc/caddy/risarms
install -m 0644 "$SOURCE/deployment/pi/Caddyfile" /etc/caddy/risarms/portal.caddy
if ! grep -qxF 'import /etc/caddy/risarms/*.caddy' /etc/caddy/Caddyfile; then
    cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.before-risarms-$(date +%s)"
    echo 'import /etc/caddy/risarms/*.caddy' >> /etc/caddy/Caddyfile
fi
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# Stable separate CLI commands, without replacing unrelated binaries.
for command in core-host rescs; do
    case "$command" in core-host) target=/opt/risarms/core-venv/bin/core-host;; rescs) target=/opt/risarms/rescs-venv/bin/rescs;; esac
    if [[ -e /usr/local/bin/$command && $(readlink /usr/local/bin/$command || true) != "$target" ]]; then
        echo "Preserving existing $command; use $target explicitly."
    else ln -sfn "$target" "/usr/local/bin/$command"; fi
done
if [[ -e /usr/local/bin/risarms-admin ]]; then
    echo 'Existing risarms-admin preserved; review the new helper before replacing it.'
else install -m 0755 "$SOURCE/deployment/pi/risarms-admin" /usr/local/bin/risarms-admin; fi
systemctl daemon-reload
printf '%s\n' 'Installed without enabling services. Review configuration and migrate old data before starting.' \
  'sudo systemctl enable --now risarms-rescs risarms-core' \
  'sudo systemctl reload caddy' \
  'Get first-owner setup key: sudo journalctl -u risarms-core -b --no-pager' \
  'Trust the Caddy root certificate on each client before entering credentials at https://core.local.'
