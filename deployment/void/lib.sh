#!/usr/bin/env bash
set -euo pipefail

RISARMS_APP="${RISARMS_APP:-/opt/risarms}"
RISARMS_ETC="${RISARMS_ETC:-/etc/risarms}"
RISARMS_DATA="${RISARMS_DATA:-/var/lib/risarms}"
RISARMS_LOG="${RISARMS_LOG:-/var/log/risarms}"
RISARMS_STATE="${RISARMS_STATE:-$RISARMS_DATA/install-state}"
RISARMS_MIN_FREE_GIB="${RISARMS_MIN_FREE_GIB:-5}"

risarms_log() { printf '[risarms] %s\n' "$*"; }
risarms_die() { printf '[risarms] ERROR: %s\n' "$*" >&2; exit 1; }

risarms_require_root() {
    [[ ${EUID} -eq 0 ]] || risarms_die "Run with sudo after reviewing the script."
}

risarms_require_void() {
    [[ -r /etc/os-release ]] || risarms_die "Cannot identify the operating system."
    # shellcheck disable=SC1091
    . /etc/os-release
    [[ ${ID:-} == void ]] || risarms_die "CORE server releases support Void Linux only."
    [[ $(uname -m) == x86_64 ]] || risarms_die "CORE server releases support x86_64 only."
    ldd --version 2>/dev/null | grep -qi glibc || risarms_die "glibc is required."
}

risarms_require_commands() {
    local tool
    for tool in "$@"; do
        command -v "$tool" >/dev/null 2>&1 || risarms_die "Missing required command: $tool"
    done
}

risarms_version_from_source() {
    local source=${1:?source tree required}
    python3 - "$source/compatibility.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
version = data.get("version")
if not isinstance(version, str) or not version:
    raise SystemExit(f"{path} has no version")
print(version)
PY
}

risarms_current_version() {
    local path="$RISARMS_STATE/version"
    [[ -r $path ]] || return 1
    tr -d '[:space:]' < "$path"
}

risarms_previous_version() {
    local path="$RISARMS_STATE/previous-version"
    [[ -r $path ]] || return 1
    tr -d '[:space:]' < "$path"
}

risarms_check_free_space() {
    local path=${1:-$RISARMS_DATA}
    local required_kib=$((RISARMS_MIN_FREE_GIB * 1024 * 1024))
    local available_kib
    available_kib=$(df -Pk "$path" | awk 'NR == 2 {print $4}')
    [[ $available_kib =~ ^[0-9]+$ ]] || risarms_die "Cannot determine free space for $path."
    (( available_kib >= required_kib )) || risarms_die \
        "Need at least ${RISARMS_MIN_FREE_GIB} GiB free on $path (${available_kib} KiB available)."
}

risarms_atomic_link() {
    local target=${1:?target required}
    local link=${2:?link required}
    local temporary="${link}.new.$$"
    rm -f "$temporary"
    ln -s "$target" "$temporary"
    mv -Tf "$temporary" "$link"
}

risarms_venv_path() {
    local name=${1:?name required}
    local version=${2:?version required}
    printf '%s/venvs/%s/%s\n' "$RISARMS_APP" "$version" "$name"
}

risarms_service_up() {
    sv status "$1" 2>/dev/null | grep -q '^run:'
}

risarms_wait_http() {
    local url=${1:?url required}
    local timeout=${2:-30}
    python3 - "$url" "$timeout" <<'PY'
import sys
import time
import urllib.error
import urllib.request

url, timeout = sys.argv[1], int(sys.argv[2])
deadline = time.monotonic() + timeout
last = "no response"
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status < 500:
                raise SystemExit(0)
            last = f"HTTP {response.status}"
    except (OSError, urllib.error.URLError) as exc:
        last = str(exc)
    time.sleep(1)
raise SystemExit(f"Timed out waiting for {url}: {last}")
PY
}

risarms_snapshot_install() {
    local stamp=${1:?stamp required}
    local snapshot="$RISARMS_STATE/snapshots/$stamp"
    install -d -m 0700 "$snapshot"
    if [[ -d $RISARMS_ETC ]]; then
        cp -a "$RISARMS_ETC" "$snapshot/etc-risarms"
    fi
    if [[ -e $RISARMS_APP/core-venv || -L $RISARMS_APP/core-venv ]]; then
        readlink -f "$RISARMS_APP/core-venv" > "$snapshot/core-venv-target" || true
    fi
    if [[ -e $RISARMS_APP/rescs-venv || -L $RISARMS_APP/rescs-venv ]]; then
        readlink -f "$RISARMS_APP/rescs-venv" > "$snapshot/rescs-venv-target" || true
    fi
    risarms_current_version > "$snapshot/version" 2>/dev/null || true
    find "$RISARMS_STATE/snapshots" -mindepth 1 -maxdepth 1 -type d \
        -printf '%T@ %p\n' 2>/dev/null | sort -rn | tail -n +6 | cut -d' ' -f2- |
        while IFS= read -r old; do rm -rf -- "$old"; done
    printf '%s\n' "$snapshot"
}

risarms_write_state() {
    local version=${1:?version required}
    local previous=${2:-}
    install -d -m 0700 "$RISARMS_STATE"
    printf '%s\n' "$version" > "$RISARMS_STATE/version"
    if [[ -n $previous ]]; then
        printf '%s\n' "$previous" > "$RISARMS_STATE/previous-version"
    fi
}

risarms_restart_if_up() {
    local service=$1
    if risarms_service_up "$service"; then
        sv restart "$service"
    fi
}
