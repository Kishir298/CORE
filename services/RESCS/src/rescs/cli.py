"""Installed launcher; uvicorn factory entrypoint stays compatible."""
import argparse
import os
from pathlib import Path
import secrets
import sys


def data_directory():
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'RESCS'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/RESCS'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'rescs'


def main(argv=None):
    parser = argparse.ArgumentParser(prog='rescs')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--allow-remote', action='store_true')
    parser.add_argument('command', nargs='?', choices=['serve', 'setup', 'doctor'], default='serve')
    args = parser.parse_args(argv)
    if args.host not in ('127.0.0.1', '::1', 'localhost') and not args.allow_remote:
        parser.error('Remote listening requires --allow-remote')
    root = data_directory()
    config = args.config or root / 'rescs.env'
    try:
        if args.command == 'setup':
            config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write('RESCS_API_KEY=' + secrets.token_urlsafe(32) + '\n')
                stream.write('RESCS_DATABASE_URL=sqlite:///' + (root / 'rescs.sqlite3').as_posix() + '\n')
                stream.write('RESCS_STORAGE_DIR=' + (root / 'files').as_posix() + '\n')
            print('Private configuration created. Restrict Windows ACLs to your account.')
            return 0
        from rescs.config import Settings
        settings = Settings(_env_file=config)
        from rescs.mounts import check_mount
        check_mount(settings)
        if args.command == 'doctor':
            import uvicorn  # noqa: F401
            print('Configuration, storage guard and server imports passed; no network probes performed.')
            return 0
        from sqlalchemy.engine import make_url
        url = make_url(settings.database_url)
        if url.get_backend_name() == 'sqlite' and url.database != ':memory:':
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        from rescs.main import create_app
        import uvicorn
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return 0
    except FileExistsError:
        print('Configuration already exists; preserved.')
        return 0
    except Exception as exc:
        print(f'RESCS failed ({type(exc).__name__}); check configuration and storage. No fallback used.', file=sys.stderr)
        return 2
