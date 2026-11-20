#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SOURCE=$(cd -- "$SCRIPT_DIR/../.." && pwd)
# shellcheck source=lib.sh
. "$SCRIPT_DIR/lib.sh"

risarms_require_root
risarms_require_void
risarms_require_commands python3 caddy sv chpst nft useradd install df tar gzip readlink sed ln mv cp find
python3 -m pip --version >/dev/null 2>&1 || risarms_die "python3-pip is required (Void ships python3 without ensurepip)."

VERSION=$(risarms_version_from_source "$SOURCE")
PREVIOUS_VERSION=$(risarms_current_version 2>/dev/null || true)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ORIGIN=${RISARMS_PUBLIC_ORIGIN:-}
if [[ -z $ORIGIN && -r $RISARMS_ETC/core.env ]]; then
    ORIGIN=$(sed -n 's/^CORE_PUBLIC_ORIGIN=//p' "$RISARMS_ETC/core.env" | head -n 1)
fi
ORIGIN=${ORIGIN:-https://core.local}
[[ $ORIGIN =~ ^https://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]{1,5})?$ ]] ||
    risarms_die "RISARMS_PUBLIC_ORIGIN must be an https origin without a path or trailing slash."

CORE_WAS_UP=0
RESCS_WAS_UP=0
CADDY_WAS_UP=0
risarms_service_up risarms-core && CORE_WAS_UP=1
risarms_service_up risarms-rescs && RESCS_WAS_UP=1
risarms_service_up caddy && CADDY_WAS_UP=1
PREVIOUS_CORE_TARGET=$(readlink -f "$RISARMS_APP/core-venv" 2>/dev/null || true)
PREVIOUS_RESCS_TARGET=$(readlink -f "$RISARMS_APP/rescs-venv" 2>/dev/null || true)

restore_previous_links() {
    local status=$?
    if (( status != 0 )); then
        [[ -n $PREVIOUS_CORE_TARGET ]] && risarms_atomic_link "$PREVIOUS_CORE_TARGET" "$RISARMS_APP/core-venv" || true
        [[ -n $PREVIOUS_RESCS_TARGET ]] && risarms_atomic_link "$PREVIOUS_RESCS_TARGET" "$RISARMS_APP/rescs-venv" || true
    fi
    exit "$status"
}
trap restore_previous_links EXIT

if ! id risarms >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$RISARMS_DATA" --shell /usr/sbin/nologin risarms
fi

install -d -m 0755 "$RISARMS_APP" "$RISARMS_APP/venvs" "$RISARMS_ETC" "$RISARMS_LOG"
install -d -m 0700 -o risarms -g risarms "$RISARMS_DATA" "$RISARMS_DATA/core"
install -d -m 0700 -o risarms -g risarms \
    "$RISARMS_DATA/rescs" "$RISARMS_DATA/rescs/database" \
    "$RISARMS_DATA/rescs/files" "$RISARMS_DATA/rescs/tmp" "$RISARMS_DATA/rescs/trash"
install -d -m 0700 -o risarms -g risarms \
    "$RISARMS_LOG/core" "$RISARMS_LOG/rescs" "$RISARMS_DATA/backups" "$RISARMS_STATE"
install -d -m 0700 -o risarms -g risarms /run/risarms-inference
install -d -m 0755 "$RISARMS_DATA/frontend"

risarms_check_free_space "$RISARMS_DATA"
install -m 0644 "$SOURCE/CORE-HOST/core/web/portal.html" "$RISARMS_DATA/frontend/index.html"

build_venv() {
    local name=$1
    local source=$2
    local target
    target=$(risarms_venv_path "$name" "$VERSION")
    local staging="$RISARMS_APP/venvs/$VERSION/.$name.build.$$"
    install -d -m 0755 "$RISARMS_APP/venvs/$VERSION"
    rm -rf "$staging"
    python3 -m venv --without-pip "$staging"
    python3 -m pip --python "$staging/bin/python" install --upgrade pip
    python3 -m pip --python "$staging/bin/python" install "$source"
    "$staging/bin/python" -c "import $3; print('$name ready')"
    rm -rf "$target"
    mv "$staging" "$target"
}

risarms_snapshot_install "$STAMP" >/dev/null
build_venv core "$SOURCE/CORE-HOST" core.version
build_venv rescs "$SOURCE/services/RESCS" rescs

for name in core rescs; do
    link="$RISARMS_APP/$name-venv"
    if [[ -e $link && ! -L $link ]]; then
        mv "$link" "$RISARMS_APP/legacy-$name-venv-$STAMP"
    fi
    risarms_atomic_link "venvs/$VERSION/$name" "$link"
done

if [[ ! -f $RISARMS_ETC/core.env && ! -f $RISARMS_ETC/rescs.env ]]; then
    python3 "$SCRIPT_DIR/configure.py" --origin "$ORIGIN"
elif [[ ! -f $RISARMS_ETC/core.env || ! -f $RISARMS_ETC/rescs.env ]]; then
    risarms_die "Only one environment file exists; repair configuration without regenerating keys."
else
    python3 "$SCRIPT_DIR/configure.py" --reconcile --origin "$ORIGIN"
fi

chown -R risarms:risarms "$RISARMS_DATA/core" "$RISARMS_DATA/rescs" "$RISARMS_LOG"
if [[ -f $RISARMS_DATA/core/gateway.json ]]; then
    chown risarms:risarms "$RISARMS_DATA/core/gateway.json"
fi
chmod 0600 "$RISARMS_ETC"/*.env "$RISARMS_ETC/gateway.json" "$RISARMS_DATA/core/gateway.json"

install -d -m 0755 /etc/sv/risarms-core/log /etc/sv/risarms-rescs/log
install -m 0755 "$SCRIPT_DIR/etc/sv/risarms-core/run" /etc/sv/risarms-core/run
install -m 0755 "$SCRIPT_DIR/etc/sv/risarms-core/log/run" /etc/sv/risarms-core/log/run
install -m 0644 "$SCRIPT_DIR/etc/sv/risarms-core/log/config" /etc/sv/risarms-core/log/config
install -m 0755 "$SCRIPT_DIR/etc/sv/risarms-rescs/run" /etc/sv/risarms-rescs/run
install -m 0755 "$SCRIPT_DIR/etc/sv/risarms-rescs/log/run" /etc/sv/risarms-rescs/log/run
install -m 0644 "$SCRIPT_DIR/etc/sv/risarms-rescs/log/config" /etc/sv/risarms-rescs/log/config

install -d -m 0755 /etc/caddy/risarms
sed "s|https://core.local|$ORIGIN|g" "$SCRIPT_DIR/etc/caddy/portal.caddy" \
    > /etc/caddy/risarms/portal.caddy
chmod 0644 /etc/caddy/risarms/portal.caddy
if [[ ! -f /etc/caddy/Caddyfile ]]; then
    echo 'import /etc/caddy/risarms/*.caddy' > /etc/caddy/Caddyfile
elif ! grep -qxF 'import /etc/caddy/risarms/*.caddy' /etc/caddy/Caddyfile; then
    cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.before-risarms-$STAMP"
    echo 'import /etc/caddy/risarms/*.caddy' >> /etc/caddy/Caddyfile
fi
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

install -d -m 0755 /etc/nftables.d
install -m 0644 "$SCRIPT_DIR/etc/nftables.d/risarms.nft" /etc/nftables.d/risarms.nft
if [[ -f /etc/nftables.conf ]] && ! grep -qF 'include "/etc/nftables.d/*.nft"' /etc/nftables.conf; then
    cp -a /etc/nftables.conf "/etc/nftables.conf.before-risarms-$STAMP"
    printf '\ninclude "/etc/nftables.d/*.nft"\n' >> /etc/nftables.conf
fi
if [[ -f /etc/nftables.conf ]]; then
    nft -c -f /etc/nftables.conf
fi

install -d -m 0755 /etc/elogind/logind.conf.d
install -m 0644 "$SCRIPT_DIR/etc/elogind/logind.conf.d/risarms.conf" /etc/elogind/logind.conf.d/risarms.conf

install -d -m 0755 /usr/local/lib/risarms
install -m 0644 "$SCRIPT_DIR/lib.sh" /usr/local/lib/risarms/common.sh
for script in backup.sh restore.sh upgrade.sh rollback.sh doctor.sh; do
    install -m 0755 "$SCRIPT_DIR/$script" "/usr/local/sbin/risarms-${script%.sh}"
done

risarms_restart_if_up risarms-rescs
risarms_restart_if_up risarms-core
risarms_restart_if_up caddy
risarms_write_state "$VERSION" "$PREVIOUS_VERSION"

trap - EXIT
printf '%s\n' \
    "Installed CORE ${VERSION} for Void x86_64." \
    "Public origin: ${ORIGIN}" \
    "Installed but not enabled." \
    "Review ${RISARMS_ETC}/{core.env,rescs.env} and /etc/caddy/risarms/portal.caddy." \
    "Enable: ln -s /etc/sv/risarms-rescs /var/service/ && ln -s /etc/sv/risarms-core /var/service/ && ln -s /etc/sv/caddy /var/service/" \
    "Then check: sv status risarms-core risarms-rescs caddy" \
    "Diagnose: sudo risarms-doctor" \
    "Backups: sudo risarms-backup" \
    "First-owner setup key: cat ${RISARMS_LOG}/core/current | tail -n 50"
