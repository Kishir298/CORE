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
risarms_require_commands python3 sv install tar df readlink
SOURCE=${1:-${RISARMS_SOURCE:-}}
[[ -n $SOURCE ]] || risarms_die "Usage: risarms-upgrade <release-source-directory>"
SOURCE=$(readlink -f "$SOURCE")
[[ -r $SOURCE/compatibility.json && -x $SOURCE/deployment/void/install.sh ]] ||
    risarms_die "Not a CORE source tree: $SOURCE"

CURRENT=$(risarms_current_version) || risarms_die "CORE is not installed."
TARGET=$(risarms_version_from_source "$SOURCE")
if [[ $TARGET == "$CURRENT" ]]; then
    printf 'CORE %s is already installed; reinstalling through the installer.\n' "$TARGET"
elif [[ $(printf '%s\n%s\n' "$CURRENT" "$TARGET" | sort -V | tail -n 1) != "$TARGET" ]]; then
    risarms_die "Refusing to upgrade from $CURRENT to older version $TARGET; use risarms-rollback."
fi
risarms_check_free_space "$RISARMS_DATA"

if ! "$SOURCE/deployment/void/install.sh"; then
    printf 'Upgrade to CORE %s failed; previous version links were restored by the installer.\n' "$TARGET" >&2
    exit 1
fi

if risarms_service_up risarms-core; then
    risarms_wait_http http://127.0.0.1:8780/api/health 45 ||
        printf 'CORE upgraded but health check did not pass; run sudo risarms-doctor.\n' >&2
fi
if [[ -r $(risarms_venv_path core "$TARGET")/bin/python ]]; then
    printf 'CORE %s installed from %s\n' "$TARGET" "$SOURCE"
fi
