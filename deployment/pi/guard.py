#!/usr/bin/env python3
"""Fail closed unless /srv/core is the configured SSD filesystem."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import ProxyHandler, build_opener


def verify_mount(path='/srv/core', expected_uuid=None):
    path=Path(path)
    if not path.is_mount():raise RuntimeError('Storage unavailable: /srv/core must be a mounted SSD, not a microSD directory.')
    result=subprocess.run(['findmnt','--json','--mountpoint',str(path),'-o','UUID,FSTYPE,OPTIONS'],check=True,capture_output=True,text=True)
    rows=json.loads(result.stdout)['filesystems']
    if len(rows)!=1 or rows[0]['fstype']!='ext4':raise RuntimeError('Expected one ext4 data filesystem.')
    if rows[0].get('uuid')!=(expected_uuid or os.environ.get('CORE_SSD_UUID')):raise RuntimeError('The mounted SSD UUID does not match this installation.')
    if 'rw' not in rows[0]['options'].split(','):raise RuntimeError('The SSD is read-only.')
    return rows[0]


def wait_ready(url):
    opener=build_opener(ProxyHandler({}));deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            with opener.open(url,timeout=1) as response:
                if response.status==200 and json.loads(response.read(65536)).get('status') in ('ready','ok'):return
        except (OSError,ValueError):pass
        time.sleep(.5)
    raise RuntimeError('Backend readiness deadline exceeded.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--ready')
    args=parser.parse_args()
    verify_mount()
    if args.ready:wait_ready(args.ready)
