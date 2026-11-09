#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo 'Run with sudo after reviewing this installer.' >&2; exit 1; fi
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
command -v python3 >/dev/null || { echo 'Install python3 and python3-venv first.' >&2; exit 1; }
command -v systemctl >/dev/null || { echo 'This installer needs a systemd distribution.' >&2; exit 1; }
if ! id core >/dev/null 2>&1; then useradd --system --home-dir /var/lib/core --shell /usr/sbin/nologin core; fi
install -d -m 0755 /opt/core /etc/core
install -d -m 0700 -o core -g core /var/lib/core
if [[ ! -x /opt/core/venv/bin/python ]]; then python3 -m venv /opt/core/venv; fi
/opt/core/venv/bin/python -m pip install "$SOURCE"
install -m 0644 "$SOURCE/deploy/linux/core.service" /etc/systemd/system/core.service
if [[ ! -f /etc/core/core.env ]]; then install -m 0600 "$SOURCE/deploy/linux/core.env.example" /etc/core/core.env; fi
systemctl daemon-reload
printf '%s\n' 'Installed. Edit /etc/core/core.env and configure your HTTPS proxy.' 'Then run: sudo systemctl enable --now core' 'Read first-owner setup key: sudo journalctl -u core -b --no-pager'
