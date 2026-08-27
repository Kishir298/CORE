import argparse

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


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    runtime = Runtime()

    return execute(args, runtime)


if __name__ == "__main__":
    raise SystemExit(main())
