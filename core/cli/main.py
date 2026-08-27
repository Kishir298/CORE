import argparse
import time

from core.application import CoreApplication
from core.runtime import Runtime


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core",
        description="C.O.R.E. control interface.",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "status",
        help="Show C.O.R.E. runtime status.",
    )

    subparsers.add_parser(
        "start",
        help="Start C.O.R.E.",
    )

    subparsers.add_parser(
        "stop",
        help="Stop C.O.R.E.",
    )

    subparsers.add_parser(
        "services",
        help="Show C.O.R.E. services.",
    )

    subparsers.add_parser(
        "resources",
        help="Show registered resources.",
    )

    subparsers.add_parser(
        "connections",
        help="Show active connections.",
    )

    subparsers.add_parser(
        "health",
        help="Show C.O.R.E. health.",
    )

    return parser


def execute(
    args: argparse.Namespace,
    runtime: Runtime,
) -> int:
    """
    Execute a single CLI command.

    This function intentionally does not block. Long-running process
    behavior belongs to main().
    """

    if args.command == "start":
        runtime.start()
        print("C.O.R.E. started.")
        return 0

    if args.command == "stop":
        runtime.stop()
        print("C.O.R.E. stopped.")
        return 0

    if args.command == "status":
        print(f"Runtime: {runtime.state.value.upper()}")
        return 0

    if args.command == "services":
        print("Services:")
        print("  Service management available through C.O.R.E.")
        return 0

    if args.command == "resources":
        print("Resources:")
        print("  Resource registry available through C.O.R.E.")
        return 0

    if args.command == "connections":
        print("Connections:")
        print("  Connection management available through C.O.R.E.")
        return 0

    if args.command == "health":
        print("Health:")
        print("  C.O.R.E. health monitoring available.")
        return 0

    return 0


def run_application(app: CoreApplication) -> int:
    """
    Start the real C.O.R.E. application and keep the process alive.
    """

    try:
        app.start()

        print("C.O.R.E. v0.1")
        print("────────────────────────")
        print(f"Runtime: {app.state.value.upper()}")
        print()
        print("C.O.R.E. is running.")
        print("Press Ctrl+C to shut down.")

        while app.is_running:
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print("C.O.R.E. shutting down...")

    finally:
        app.stop()

    print("C.O.R.E. stopped.")

    return 0


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "start":
        app = CoreApplication()
        return run_application(app)

    app = CoreApplication()

    return execute(args, app)


if __name__ == "__main__":
    raise SystemExit(main())