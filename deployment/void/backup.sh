#!/bin/sh
set -eu
[[ $(id -u) -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DEST=/var/lib/risarms/backups
install -d -m 0700 "$DEST"
sv down risarms-core 2>/dev/null || true
sv down risarms-rescs 2>/dev/null || true
trap 'sv up risarms-rescs 2>/dev/null || true; sv up risarms-core 2>/dev/null || true' EXIT INT TERM
tar -C /var/lib/risarms --exclude=backups -czf "$DEST/risarms-$STAMP.tar.gz" core rescs
find "$DEST" -name 'risarms-*.tar.gz' -mtime +14 -delete
echo "Backup written to $DEST/risarms-$STAMP.tar.gz"
