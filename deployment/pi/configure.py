"""Root-only initial configuration. No shipped shared owner password or API key."""
import argparse
import json
from pathlib import Path
import secrets
import uuid


def configure(base, data, ssd_uuid):
    # A syntactically valid UUID is mandatory, and keys are never regenerated.
    uuid.UUID(ssd_uuid)
    base=Path(base);data=Path(data)
    if any((base/n).exists() for n in ('core.env','rescs.env')):
        raise ValueError('Existing environment files must be preserved.')
    if (data/'core/gateway.json').exists():raise ValueError('Existing gateway data requires deliberate configuration reconciliation.')
    key=secrets.token_urlsafe(48)
    core=f'''CORE_SSD_UUID={ssd_uuid}
CORE_WEB_DATA={data}/core
CORE_PUBLIC_ORIGIN=https://core.local
CORE_EXTERNAL_STORAGE=1
CORE_SAFE_CHAT=1
CORE_MAX_AI_JOBS=1
CORE_AI_CONTEXT_LIMIT=2048
CORE_AI_THREADS=2
RISARMS_INFERENCE_LOCK=/run/risarms-inference/queue.lock
CORE_AI_CGROUP=/sys/fs/cgroup/system.slice/ollama.service
'''
    rescs=f'''CORE_SSD_UUID={ssd_uuid}
RESCS_ENV=production
RESCS_REQUIRE_SIGNED_OWNER=true
RESCS_REQUIRED_MOUNT=/srv/core
TMPDIR=/srv/core/rescs/tmp
RESCS_API_KEY={key}
RESCS_API_KEY_OWNER=
RESCS_DATABASE_URL=sqlite:///{data}/rescs/database/rescs.sqlite3
RESCS_STORAGE_DIR={data}/rescs/files
RESCS_AUTO_CREATE_SCHEMA=true
RESCS_MAX_FILE_SIZE=8388608
RESCS_MAX_BYTES_PER_OWNER=10737418240
RESCS_MAX_FILES_PER_OWNER=10000
RESCS_RATE_LIMIT_ENABLED=true
RESCS_RATE_LIMIT_GENERAL_PER_MINUTE=1200
RESCS_RATE_LIMIT_WRITES_PER_MINUTE=120
RESCS_RATE_LIMIT_UPLOADS_PER_MINUTE=30
'''
    for name,text in [('core.env',core),('rescs.env',rescs)]:
        path=base/name
        with path.open('x') as f:f.write(text)
        path.chmod(0o600)
    config=data/'core/gateway.json'
    if config.exists():
        # Migration must explicitly preserve the corresponding RESCS key.
        raise ValueError('Existing gateway data requires deliberate configuration reconciliation.')
    config.write_text(json.dumps({'rescs_url':'http://127.0.0.1:8081','rescs_key':key,'public_origin':'https://core.local'},indent=2))
    config.chmod(0o600)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ssd-uuid',required=True)
    a=p.parse_args();configure('/etc/risarms','/srv/core',a.ssd_uuid)
