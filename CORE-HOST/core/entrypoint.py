"""Installed Linux server and Windows-compatible host command with a stable per-user data directory."""
import argparse
import os
from pathlib import Path


def default_data():
    if os.environ.get("CORE_WEB_DATA"):
        return Path(os.environ["CORE_WEB_DATA"]).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))
    return base / "RISARMS" / "CORE" / "web"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="core-host", description="Run the C.O.R.E. host and authenticated portal.")
    parser.add_argument("command", nargs="?", choices=("start", "doctor", "model-check", "model-download", "init-owner", "pi-check", "pi-benchmark"), default="start")
    parser.add_argument("--data", type=Path, default=None, help="Persistent portal data directory.")
    parser.add_argument("--config", type=Path, help="Optional native CORE YAML configuration.")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--no-browser", action="store_true", help="Compatibility flag; server is headless by default.")
    parser.add_argument("--open", action="store_true", help="Open a browser on this server device.")
    parser.add_argument("--gateway-only", action="store_true", help="Run the authenticated API and service jobs without native TCP runtime.")
    parser.add_argument("--owner-seed", type=Path, help="Private salted initial-owner verifier; only used by init-owner.")
    parser.add_argument("--with-storage", action="store_true", help="Start and supervise the bundled local RESCS backend.")
    parser.add_argument('--model', help='Explicit installed model tag for Pi benchmark.')
    parser.add_argument('--service', choices=('asis','ascs'), default='asis')
    parser.add_argument('--approve', action='store_true',help='Explicitly approve the measured Pi model digest/context.')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    data = (args.data or default_data()).expanduser().resolve()
    if args.command in ('pi-check','pi-benchmark') or (args.command in ('model-check','model-download') and os.environ.get('CORE_SAFE_CHAT')=='1'):
        import json
        from core.pi_resources import PiPolicy, benchmark
        data.mkdir(parents=True,exist_ok=True)
        if args.command=='model-download':parser.error('Pi models are never automatically downloaded. Pull an explicit allowed Q4 tag with Ollama, then run pi-benchmark.')
        if args.command=='pi-benchmark':
            if not args.model:parser.error('pi-benchmark requires --model.')
            try:print(json.dumps(benchmark(data,args.model,args.service,args.approve),indent=2))
            except (OSError,ValueError,RuntimeError) as exc:parser.error(str(exc))
        else:
            policy=PiPolicy(data)
            try:
                import time
                while len(policy.samples)<10:time.sleep(.2)
                print(json.dumps(policy.evaluate(args.model or '',args.service),indent=2))
            finally:policy.close()
        return 0
    if args.command == "init-owner":
        import json
        from core.web.accounts import Accounts
        if args.owner_seed is None: parser.error("init-owner requires --owner-seed.")
        accounts = Accounts(data)
        try:
            created=accounts.bootstrap_owner(json.loads(args.owner_seed.read_text()))
            print("Initial owner created; password change required at first login." if created else "Existing accounts preserved; bootstrap skipped.")
        finally: accounts.close()
        return 0
    if args.command in ("model-check", "model-download"):
        import json
        from core.model_support import system_report, download_recommended
        report = system_report(data.parent)
        print(json.dumps(report, indent=2))
        if args.command == "model-download":
            try:
                model = download_recommended(report)
                from core.web.gateway import Gateway
                gateway = Gateway(directory=data)
                gateway.config["models"].update(asis=model, tiviss=model)
                gateway.save_config(); gateway.close()
                print("Default ASIS/TIVISS model configured:", model)
            except (OSError, ValueError, RuntimeError) as exc: parser.error(str(exc))
        return 0
    if args.command == "doctor":
        print("C.O.R.E. host command is installed.")
        print("Portal data:", data)
        print("Portal settings:", "present" if (data / "gateway.json").is_file() else "first-run setup required")
        print("Local URL:", f"http://127.0.0.1:{args.port}")
        print("External service dependencies and models require separate verification.")
        return 0
    from core.application import CoreApplication
    from core.web.gateway import serve
    # Do not implicitly load config from whichever directory the terminal uses.
    config = args.config.expanduser().resolve() if args.config else None
    runtime = data / "runtime" if args.gateway_only else data.parent / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    try:
        os.chdir(runtime)
        app = None if args.gateway_only else CoreApplication(config_path=config, discover_config=False)
        serve(app, directory=data, port=args.port, open_browser=args.open and not args.no_browser, **({"start_storage":True} if args.with_storage else {}))
    finally:
        os.chdir(previous)
    return 0
