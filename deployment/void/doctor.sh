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
FAILURES=0
WARNINGS=0
pass() { printf '  ok    %s\n' "$*"; }
warn() { printf '  warn  %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '  FAIL  %s\n' "$*"; FAILURES=$((FAILURES + 1)); }

printf 'CORE Void diagnostics\n'
if id risarms >/dev/null 2>&1; then pass "service account risarms exists"; else fail "service account risarms is missing"; fi
for path in "$RISARMS_APP" "$RISARMS_ETC" "$RISARMS_DATA" "$RISARMS_LOG"; do
    if [[ -d $path ]]; then pass "$path exists"; else fail "$path is missing"; fi
done
if [[ -f $RISARMS_ETC/core.env && -f $RISARMS_ETC/rescs.env && -f $RISARMS_ETC/gateway.json ]]; then
    pass "configuration files exist"
    permissions=$(stat -c '%a' "$RISARMS_ETC"/*.env "$RISARMS_ETC/gateway.json" | sort -u | tr '\n' ' ')
    if [[ $permissions == "600 " ]]; then pass "configuration permissions are 0600"; else fail "configuration permissions: $permissions"; fi
else
    fail "one or more configuration files are missing"
fi
if python3 - "$RISARMS_ETC" "$RISARMS_DATA" <<'PY'
import json
import sys
from pathlib import Path

base, data = Path(sys.argv[1]), Path(sys.argv[2])
key = ""
for line in (base / "rescs.env").read_text().splitlines():
    name, separator, value = line.partition("=")
    if separator and name == "RESCS_API_KEY":
        key = value
        break
if not key:
    raise SystemExit(1)
for path in (base / "gateway.json", data / "core" / "gateway.json"):
    if json.loads(path.read_text()).get("rescs_key") != key:
        raise SystemExit(1)
PY
then
    pass "RESCS key matches both gateway files"
else
    fail "RESCS key does not match both gateway files"
fi

INSTALLED=$(risarms_current_version 2>/dev/null || true)
if [[ -n $INSTALLED ]]; then pass "installed version: $INSTALLED"; else fail "install-state version is missing"; fi
CORE_RUNTIME=$("$RISARMS_APP/core-venv/bin/python" -c 'from core.version import __version__; print(__version__)' 2>/dev/null || true)
if [[ -n $CORE_RUNTIME && $CORE_RUNTIME == "$INSTALLED" ]]; then
    pass "core-venv reports $CORE_RUNTIME"
else
    fail "core-venv reports ${CORE_RUNTIME:-nothing}, expected ${INSTALLED:-unknown}"
fi
if "$RISARMS_APP/rescs-venv/bin/python" -c 'import rescs' >/dev/null 2>&1; then
    pass "rescs-venv imports"
else
    fail "rescs-venv cannot import rescs"
fi

if risarms_check_free_space "$RISARMS_DATA" >/dev/null 2>&1; then
    pass "at least ${RISARMS_MIN_FREE_GIB} GiB free"
else
    fail "less than ${RISARMS_MIN_FREE_GIB} GiB free under $RISARMS_DATA"
fi

for service in risarms-core risarms-rescs caddy; do
    status=$(sv status "$service" 2>/dev/null | head -n 1 || true)
    if [[ $status == run:* ]]; then
        pass "$service is up"
    elif [[ $service == caddy ]]; then
        warn "$service is not running"
    else
        fail "$service is not running"
    fi
done

if risarms_service_up risarms-core; then
    if risarms_wait_http http://127.0.0.1:8780/api/health 5 >/dev/null 2>&1; then
        pass "CORE health endpoint responds"
    else
        fail "CORE health endpoint does not respond"
    fi
fi
if risarms_service_up risarms-rescs; then
    if risarms_wait_http http://127.0.0.1:8081/health/ready 5 >/dev/null 2>&1; then
        pass "RESCS readiness endpoint responds"
    else
        fail "RESCS readiness endpoint does not respond"
    fi
fi
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    pass "Caddy configuration is valid"
else
    fail "Caddy configuration is invalid"
fi
if nft list table inet risarms >/dev/null 2>&1; then
    pass "risarms nftables table is loaded"
else
    warn "risarms nftables table is not loaded"
fi
if compgen -G "$RISARMS_DATA/backups/risarms-*.tar.gz" >/dev/null; then
    pass "backups are present"
else
    warn "no backups found; run sudo risarms-backup"
fi
printf 'Result: %d failure(s), %d warning(s)\n' "$FAILURES" "$WARNINGS"
(( FAILURES == 0 ))
