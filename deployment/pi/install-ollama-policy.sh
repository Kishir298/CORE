#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo after installing Ollama.' >&2; exit 1; }
command -v ollama >/dev/null
id ollama >/dev/null
[[ $(systemctl show ollama -p User --value) == ollama ]] || { echo 'Review the Ollama runtime account before applying this policy.' >&2; exit 1; }
# Refuse to change a running model workload implicitly.
if systemctl is-active --quiet ollama; then echo 'Stop Ollama deliberately before applying its SSD/resource policy.' >&2; exit 1; fi
set -a
source /etc/risarms/core.env
set +a
python3 /opt/risarms/deployment/guard.py
install -d -m 0700 -o ollama -g ollama /srv/core/models
install -d -m 0755 /etc/systemd/system/ollama.service.d
install -m 0644 "$(dirname -- "${BASH_SOURCE[0]}")/ollama-pi.conf" /etc/systemd/system/ollama.service.d/risarms-pi.conf
# Non-secret UUID file is readable by the Ollama service, unlike root-only core.env.
printf 'CORE_SSD_UUID=%s\n' "$CORE_SSD_UUID" > /etc/risarms/ollama.env
chmod 0600 /etc/risarms/ollama.env
systemctl daemon-reload
printf '%s\n' 'Policy installed; enable/start Ollama explicitly after review. No weights downloaded.'
