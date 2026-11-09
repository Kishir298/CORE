#!/usr/bin/env python3
"""Offline, explicit migration; never formats disks or resets account credentials.

Run only before first Pi start. Keeps original data and an off-filesystem backup.
A failed migration requires inspection; it never retries/cleans data implicitly.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import time

from guard import verify_mount


def sqlite_copy(source,destination):
    with sqlite3.connect(source) as old,sqlite3.connect(destination) as new:
        if old.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Source SQLite integrity check failed.')
        old.backup(new)
        if new.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Copied SQLite integrity check failed.')


def migrate(old_web,db,files,backup_dir,*,apply=False):
    verify_mount()
    for unit in ('risarms-core','risarms-rescs','core'):
        if subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0:
            raise ValueError('Stop all old/new CORE and RESCS writers before migration.')
    old_web,db,files,backup_dir=[Path(p).expanduser().resolve(strict=True) for p in (old_web,db,files,backup_dir)]
    if not (old_web/'accounts.sqlite3').is_file() or not db.is_file() or not files.is_dir():raise ValueError('Expected existing portal accounts, RESCS SQLite database and files directory.')
    if backup_dir.stat().st_dev==Path('/srv/core').stat().st_dev:raise ValueError('Backup destination must be on a separate filesystem, preferably an off-device mounted backup.')
    for tree in (old_web,files):
        if any(p.is_symlink() for p in tree.rglob('*')):raise ValueError('Resolve source symlinks deliberately before migration.')
    target=Path('/srv/core')
    if (target/'core/accounts.sqlite3').exists() or any((target/'rescs/files').iterdir()) or any((target/'rescs/database').iterdir()):
        raise ValueError('Pi destination already contains account or RESCS data; do not overwrite it.')
    config=json.loads((old_web/'gateway.json').read_text())
    key=config.get('rescs_key')
    if not isinstance(key,str) or len(key)<16 or any(c in key for c in '\r\n'):raise ValueError('Source gateway must contain its matching RESCS API key.')
    if not apply:
        print('Preflight passed. No data copied. Stop external writers, then rerun with --apply.');return
    os.umask(0o077)
    stamp=time.strftime('%Y%m%d-%H%M%S')
    archive=backup_dir/('risarms-before-pi-'+stamp+'.tar.gz')
    with tarfile.open(archive,'x:gz') as tar:
        tar.add(old_web,arcname='old-web');tar.add(files,arcname='old-rescs-files')
        for suffix in ('','-wal','-shm'):
            candidate=Path(str(db)+suffix)
            if candidate.exists():tar.add(candidate,arcname='old-rescs-db/'+candidate.name)
        tar.add('/etc/risarms',arcname='pi-configuration')
    archive.chmod(0o600)
    with tarfile.open(archive) as tar:
        for item in tar:
            if item.isfile():
                with tar.extractfile(item) as f:
                    while f.read(1024*1024):pass
    stage=target/('.migration-'+stamp);stage.mkdir(mode=0o700)
    shutil.copytree(old_web,stage/'core',ignore=shutil.ignore_patterns('rescs-files','rescs.sqlite3*','runtime'))
    for suffix in ('','-wal','-shm'):(stage/'core'/('accounts.sqlite3'+suffix)).unlink(missing_ok=True)
    sqlite_copy(old_web/'accounts.sqlite3',stage/'core/accounts.sqlite3')
    for suffix in ('-wal','-shm'):(stage/'core'/('accounts.sqlite3'+suffix)).unlink(missing_ok=True)
    # Other SQLite files copied with their WAL sidecars are retained together.
    config.update(rescs_url='http://127.0.0.1:8081',public_origin='https://core.local',roots={})
    # Empty roots retain catalog defaults after startup.
    config.pop('roots',None)
    (stage/'core/gateway.json').write_text(json.dumps(config,indent=2))
    (stage/'database').mkdir();sqlite_copy(db,stage/'database/rescs.sqlite3')
    shutil.copytree(files,stage/'files')
    # Renames keep the first-install tree as a local rollback staging copy.
    (target/'core').rename(target/('core.before-migration-'+stamp))
    (stage/'core').rename(target/'core')
    (target/'rescs/database').rmdir();(stage/'database').rename(target/'rescs/database')
    (target/'rescs/files').rmdir();(stage/'files').rename(target/'rescs/files')
    env=Path('/etc/risarms/rescs.env');lines=env.read_text().splitlines()
    env.write_text('\n'.join('RESCS_API_KEY='+key if line.startswith('RESCS_API_KEY=') else line for line in lines)+'\n');env.chmod(0o600)
    for tree,account in [(target/'core','risarms-core'),(target/'rescs','risarms-rescs')]:
        subprocess.run(['chown','-R',account+':'+account,str(tree)],check=True)
    print('Migration copied and backed up. Originals remain unchanged. Start services and verify accounts, hashes and records before retiring old data.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--old-web',required=True);p.add_argument('--rescs-db',required=True);p.add_argument('--rescs-files',required=True);p.add_argument('--backup-dir',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    if os.geteuid()!=0:p.error('Run with sudo after stopping source and destination writers.')
    migrate(a.old_web,a.rescs_db,a.rescs_files,a.backup_dir,apply=a.apply)
