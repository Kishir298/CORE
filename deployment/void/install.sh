#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run with sudo after reviewing this installer.' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { echo 'This installer targets the HP 14 Void Linux x86_64 host.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
for tool in python3 caddy sv chpst nft; do
    command -v "$tool" >/dev/null || { echo "Install $tool first (Void: sudo xbps-install -S caddy runit-void nftables)." >&2; exit 1; }
done
if ! id risarms >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/risarms --shell /usr/sbin/nologin risarms
fi
install -d -m 0755 /opt/risarms /etc/risarms /var/log/risarms
install -d -m 0755 /opt/risarms/deployment
install -d -m 0700 -o risarms -g risarms /var/lib/risarms /var/lib/risarms/core
install -d -m 0700 -o risarms -g risarms /var/lib/risarms/rescs /var/lib/risarms/rescs/database /var/lib/risarms/rescs/files /var/lib/risarms/rescs/tmp /var/lib/risarms/rescs/trash
install -d -m 0700 -o risarms -g risarms /var/log/risarms/core /var/log/risarms/rescs /var/lib/risarms/backups
install -d -m 0755 /var/lib/risarms/frontend
install -m 0644 "$SOURCE/CORE-HOST/core/web/portal.html" /var/lib/risarms/frontend/index.html
python3 -m venv /opt/risarms/core-venv
python3 -m venv /opt/risarms/rescs-venv
/opt/risarms/core-venv/bin/python -m pip install --upgrade pip
/opt/risarms/rescs-venv/bin/python -m pip install --upgrade pip
/opt/risarms/core-venv/bin/python -m pip install "$SOURCE/CORE-HOST"
/opt/risarms/rescs-venv/bin/python -m pip install "$SOURCE/services/RESCS"
if [[ ! -f /etc/risarms/core.env && ! -f /etc/risarms/rescs.env ]]; then
    python3 "$SOURCE/deployment/void/configure.py"
elif [[ ! -f /etc/risarms/core.env || ! -f /etc/risarms/rescs.env ]]; then
    echo 'Only one environment file exists; repair configuration without regenerating keys.' >&2
    exit 1
fi
chown -R risarms:risarms /var/lib/risarms/core /var/lib/risarms/rescs /var/log/risarms
chmod 0600 /etc/risarms/*.env /etc/risarms/gateway.json
install -d -m 0755 /etc/sv/risarms-core/log /etc/sv/risarms-rescs/log
install -m 0755 "$SOURCE/deployment/void/etc/sv/risarms-core/run" /etc/sv/risarms-core/run
install -m 0755 "$SOURCE/deployment/void/etc/sv/risarms-core/log/run" /etc/sv/risarms-core/log/run
install -m 0755 "$SOURCE/deployment/void/etc/sv/risarms-rescs/run" /etc/sv/risarms-rescs/run
install -m 0755 "$SOURCE/deployment/void/etc/sv/risarms-rescs/log/run" /etc/sv/risarms-rescs/log/run
install -d -m 0755 /etc/caddy/risarms
install -m 0644 "$SOURCE/deployment/void/etc/caddy/portal.caddy" /etc/caddy/risarms/portal.caddy
if [[ -f /etc/caddy/Caddyfile ]] && ! grep -qxF 'import /etc/caddy/risarms/*.caddy' /etc/caddy/Caddyfile; then
    cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.before-risarms-$(date +%s)"
    echo 'import /etc/caddy/risarms/*.caddy' >> /etc/caddy/Caddyfile
fi
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
install -m 0644 "$SOURCE/deployment/void/etc/nftables.d/risarms.nft" /etc/nftables.d/risarms.nft 2>/dev/null || true
install -d -m 0755 /etc/elogind/logind.conf.d
install -m 0644 "$SOURCE/deployment/void/etc/elogind/logind.conf.d/risarms.conf" /etc/elogind/logind.conf.d/risarms.conf
install -m 0755 "$SOURCE/deployment/void/backup.sh" /usr/local/sbin/risarms-backup
printf '%s\n' \
  'Installed but not enabled.' \
  'Review /etc/risarms/{core.env,rescs.env} and /etc/caddy/risarms/portal.caddy.' \
  'Enable: ln -s /etc/sv/risarms-rescs /var/service/ && ln -s /etc/sv/risarms-core /var/service/ && ln -s /etc/sv/caddy /var/service/' \
  'Then check: sv status risarms-core risarms-rescs caddy' \
  'First-owner setup key: cat /var/log/risarms/core/current | tail -n 50'
