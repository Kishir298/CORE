"""Fail closed instead of creating a new database on an unmounted SD card."""
from pathlib import Path
import os
from sqlalchemy.engine import make_url


def check_mount(settings):
    if not settings.required_mount:
        return
    root = Path(settings.required_mount).resolve()
    if not os.path.ismount(root):
        raise OSError('Required mount is unavailable')
    if settings.storage_backend != 'local':
        raise ValueError('SSD deployment requires explicit local object storage')
    url = make_url(settings.database_url)
    if url.get_backend_name() != 'sqlite' or not url.database or url.database == ':memory:':
        raise ValueError('SSD deployment requires a persistent SQLite database')
    for path in (Path(settings.storage_dir), Path(url.database)):
        if not path.is_absolute() or not path.resolve().is_relative_to(root):
            raise ValueError('Persistent paths must be inside the required mount')
