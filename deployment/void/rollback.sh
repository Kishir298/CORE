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
risarms_require_commands install sv readlink

CURRENT=$(risarms_current_version) || risarms_die "CORE is not installed."
TARGET=${1:-$(risarms_previous_version)} || risarms_die "No previous version recorded."
[[ -n $TARGET ]] || risarms_die "Usage: risarms-rollback [version]"
CORE_VENV=$(risarms_venv_path core "$TARGET")
RESCS_VENV=$(risarms_venv_path rescs "$TARGET")
[[ -x $CORE_VENV/bin/core-host && -x $RESCS_VENV/bin/rescs ]] ||
    risarms_die "CORE $TARGET is not available under $RISARMS_APP/venvs."
[[ $TARGET != "$CURRENT" ]] || risarms_die "CORE $TARGET is already active."

install -d -m 0700 "$RISARMS_STATE"
risarms_atomic_link "venvs/$TARGET/core" "$RISARMS_APP/core-venv"
risarms_atomic_link "venvs/$TARGET/rescs" "$RISARMS_APP/rescs-venv"
risarms_write_state "$TARGET" "$CURRENT"
risarms_restart_if_up risarms-rescs
risarms_restart_if_up risarms-core
if risarms_service_up risarms-core; then
    risarms_wait_http http://127.0.0.1:8780/api/health 45 ||
        printf 'Rollback completed but health check did not pass; run sudo risarms-doctor.\n' >&2
fi
printf 'Rolled back CORE from %s to %s.\n' "$CURRENT" "$TARGET"
printf 'Configuration snapshots: %s/snapshots\n' "$RISARMS_STATE"
