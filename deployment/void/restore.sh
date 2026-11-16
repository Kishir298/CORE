#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -r $SCRIPT_DIR/lib.sh ]]; then
    # shellcheck source=lib.sh
    . "$SCRIPT_DIR/lib.sh"
else
    # shellcheck source=/dev/null
    . /usr/local/lib/risarms/common.sh
fi

risarms_require_root
risarms_require_void
risarms_require_commands tar gzip python3

if [[ $# -gt 0 && $1 == "--yes" ]]; then
    shift
    ASSUME_YES=1
else
    ASSUME_YES=0
fi
ARCHIVE=${1:-}
if [[ -z $ARCHIVE ]]; then
    ARCHIVE=$(find "$RISARMS_DATA/backups" -maxdepth 1 -name 'risarms-*.tar.gz' -print 2>/dev/null | sort | tail -n 1)
fi
[[ -n $ARCHIVE && -f $ARCHIVE ]] || risarms_die "Usage: risarms-restore [--yes] <backup.tar.gz>"
ARCHIVE=$(readlink -f "$ARCHIVE")

if [[ -f $ARCHIVE.sha256 ]]; then
    (cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256")
fi

listing=$(mktemp)
trap 'rm -f "$listing"' EXIT
tar -tzf "$ARCHIVE" > "$listing"
if grep -Eq '(^/|(^|/)\.\.(/|$))' "$listing"; then
    risarms_die "Backup contains unsafe paths."
fi
allowed='^(etc/risarms|etc/caddy/risarms|etc/nftables\.d/risarms\.nft|etc/elogind/logind\.conf\.d/risarms\.conf|etc/sv/risarms-(core|rescs)|var/lib/risarms/(core|rescs|frontend|install-state))(/|$)'
if grep -Evq "$allowed" "$listing"; then
    risarms_die "Backup contains paths outside the RISARMS deployment."
fi
if tar -tvzf "$ARCHIVE" | awk '$1 ~ /^l/ {found=1} END {exit found ? 0 : 1}'; then
    risarms_die "Backup contains symbolic links; refusing to restore."
fi

if (( ASSUME_YES == 0 )); then
    printf 'Restore %s over %s? [y/N] ' "$ARCHIVE" "$RISARMS_DATA"
    read -r answer
    [[ $answer == y || $answer == Y ]] || risarms_die "Restore cancelled."
fi

CORE_WAS_UP=0
RESCS_WAS_UP=0
CADDY_WAS_UP=0
risarms_service_up risarms-core && CORE_WAS_UP=1
risarms_service_up risarms-rescs && RESCS_WAS_UP=1
risarms_service_up caddy && CADDY_WAS_UP=1
if (( CORE_WAS_UP == 1 )); then sv down risarms-core; fi
if (( RESCS_WAS_UP == 1 )); then sv down risarms-rescs; fi
restore_services() {
    if (( RESCS_WAS_UP == 1 )); then sv up risarms-rescs 2>/dev/null || true; fi
    if (( CORE_WAS_UP == 1 )); then sv up risarms-core 2>/dev/null || true; fi
}
trap 'rm -f "$listing"; restore_services' EXIT INT TERM

tar -C / -xzpf "$ARCHIVE"
chown -R risarms:risarms \
    "$RISARMS_DATA/core" "$RISARMS_DATA/rescs" "$RISARMS_LOG" 2>/dev/null || true
chmod 0600 "$RISARMS_ETC"/*.env "$RISARMS_ETC/gateway.json" 2>/dev/null || true
if [[ -f $RISARMS_DATA/core/gateway.json ]]; then
    chown risarms:risarms "$RISARMS_DATA/core/gateway.json"
    chmod 0600 "$RISARMS_DATA/core/gateway.json"
fi
if (( CADDY_WAS_UP == 1 )); then sv restart caddy 2>/dev/null || true; fi
printf 'Restored %s\n' "$ARCHIVE"
