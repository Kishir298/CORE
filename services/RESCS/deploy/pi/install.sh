#!/bin/bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
mountpoint -q /srv/core || { echo 'Mount the verified SSD at /srv/core first'; exit 1; }
[[ $(uname -m) == aarch64 || $(uname -m) == x86_64 ]] || { echo '64-bit Linux required'; exit 1; }
source_dir=$(cd "$(dirname "$0")/../.." && pwd)
id rescs >/dev/null 2>&1 || useradd --system --home /srv/core/rescs --shell /usr/sbin/nologin rescs
install -d -o rescs -g rescs -m 700 /srv/core/rescs/{files,database,trash,tmp}
install -d -m 700 /etc/rescs
python3 -m venv /opt/rescs/venv
/opt/rescs/venv/bin/python -m pip install "$source_dir"
if [[ ! -f /etc/rescs/rescs.env ]]; then
 umask 077
 /opt/rescs/venv/bin/python - <<'PYCODE' > /etc/rescs/rescs.env
import secrets
print('RESCS_API_KEY=' + secrets.token_urlsafe(48))
print('RESCS_ENV=production\nRESCS_REQUIRED_MOUNT=/srv/core\nRESCS_REQUIRE_SIGNED_OWNER=true')
print('RESCS_DATABASE_URL=sqlite:////srv/core/rescs/database/rescs.sqlite3')
print('RESCS_STORAGE_DIR=/srv/core/rescs/files\nRESCS_MAX_FILE_SIZE=8388608\nRESCS_MAX_BYTES_PER_OWNER=262144000')
print('RESCS_MAX_RECORDS_PER_OWNER=2000\nTMPDIR=/srv/core/rescs/tmp')
PYCODE
fi
chown root:rescs /etc/rescs/rescs.env
chmod 640 /etc/rescs/rescs.env
install -m 644 "$source_dir/deploy/pi/rescs.service" /etc/systemd/system/rescs.service
systemctl daemon-reload
echo 'Installed, not started. Configure the patched CORE gateway with the same API key, then enable rescs.'
