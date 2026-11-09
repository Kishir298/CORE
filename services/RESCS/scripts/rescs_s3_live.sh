#!/usr/bin/env bash
# RESCS live S3 gated runner (MinIO-local preferred, zero code secrets).
# Skips cleanly without RESCS_LIVE_S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY.
# Daemon hosting (minio server/docker/brew) and bucket creation stay manual.
set -u
PYBIN="python3"
[ -x ".venv/bin/python" ] && PYBIN=".venv/bin/python"
if [ -z "${RESCS_LIVE_S3_ENDPOINT:-}" ] || [ -z "${RESCS_LIVE_S3_BUCKET:-}" ] \
  || [ -z "${RESCS_LIVE_S3_ACCESS_KEY:-}" ] || [ -z "${RESCS_LIVE_S3_SECRET_KEY:-}" ]; then
  echo "SKIPPED-unconfigured: set RESCS_LIVE_S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY for live run"
  exec "$PYBIN" -m pytest tests/integration/test_s3_live.py -q -rs -p no:cacheprovider
fi
export RESCS_LIVE_S3_PREFIX="${RESCS_LIVE_S3_PREFIX:-test-$("$PYBIN" -c 'import uuid;print(uuid.uuid4().hex[:8])')}"
"$PYBIN" -m pytest tests/integration/test_s3_live.py -q -rs -p no:cacheprovider
rc=$?
echo "LIVE-DONE rc=$rc prefix=${RESCS_LIVE_S3_PREFIX} (keys self-deleted in test finally)"
unset RESCS_LIVE_S3_ENDPOINT RESCS_LIVE_S3_BUCKET RESCS_LIVE_S3_REGION RESCS_LIVE_S3_ACCESS_KEY RESCS_LIVE_S3_SECRET_KEY RESCS_LIVE_S3_PREFIX
exit $rc

