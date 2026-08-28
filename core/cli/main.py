import argparse
import time

from core.application import CoreApplication
from core.runtime import Runtime


def create_parser() -> argparse.ArgumentParser:
    """Create the C.O.R.E. command-line interface parser."""

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
        help="Show registered C.O.R.E. services.",
    )

    subparsers.add_parser(
        "resources",
        help="Show registered C.O.R.E. resources.",
    )

    subparsers.add_parser(
        "connections",
        help="Show active communication endpoints.",
    )

    subparsers.add_parser(
        "health",
        help="Show C.O.R.E. health status.",
    )

    return parser


def _print_services(app: CoreApplication) -> None:
    """Print registered services and their lifecycle state."""

    print("Services:")

    services = app.services.list_services()

    if not services:
        print("  No services registered.")
        return

    for service in services:
        service_id = getattr(service, "service_id", str(service))
        name = getattr(service, "name", service_id)
        version = getattr(service, "version", "unknown")

        print(
            f"  {service_id} | {name} | v{version}"
        )


def _print_resources(app: CoreApplication) -> None:
    """Print registered resources."""

    print("Resources:")

    resources = app.resources.list_resources()

    if not resources:
        print("  No resources registered.")
        return

    for resource in resources:
        resource_id = getattr(
            resource,
            "resource_id",
            getattr(resource, "id", str(resource)),
        )

        resource_type = getattr(
            resource,
            "resource_type",
            getattr(resource, "type", "unknown"),
        )

        print(
            f"  {resource_id} | {resource_type}"
        )


def _print_connections(app: CoreApplication) -> None:
    """Print communication endpoint information."""

    print("Connections:")

    count = app.communication.count()

    print(
        f"  Registered endpoints: {count}"
    )

    if not app.communication.is_running:
        print("  Communication: STOPPED")
        return

    print("  Communication: RUNNING")


def _print_health(app: CoreApplication) -> None:
    """Run and print the current C.O.R.E. health state."""

    print("Health:")

    if not app.is_running:
        print("  Overall: NOT RUNNING")
        return

    results = app.health_check()
    overall = app.health.overall_status()

    print(
        f"  Overall: {overall.value.upper()}"
    )

    for result in results:
        print(
            f"  {result.component_id}: "
            f"{result.status.value.upper()} - "
            f"{result.message}"
        )


def execute(
    args: argparse.Namespace,
    runtime: Runtime,
) -> int:
    """
    Execute a CLI command against a Runtime.

    This compatibility interface is retained for direct runtime tests and
    low-level usage. The full application-aware CLI path is handled by
    execute_application().
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
        print(
            f"Runtime: {runtime.state.value.upper()}"
        )
        return 0

    if args.command == "services":
        print("Services:")
        print(
            "  Service information requires CoreApplication."
        )
        return 0

    if args.command == "resources":
        print("Resources:")
        print(
            "  Resource information requires CoreApplication."
        )
        return 0

    if args.command == "connections":
        print("Connections:")
        print(
            "  Connection information requires CoreApplication."
        )
        return 0

    if args.command == "health":
        print("Health:")
        print(
            "  Health information requires CoreApplication."
        )
        return 0

    return 0


def execute_application(
    args: argparse.Namespace,
    app: CoreApplication,
) -> int:
    """
    Execute a CLI command against the complete C.O.R.E. application.
    """

    if args.command == "start":
        app.start()
        print("C.O.R.E. started.")
        return 0

    if args.command == "stop":
        app.stop()
        print("C.O.R.E. stopped.")
        return 0

    if args.command == "status":
        print(
            f"Runtime: {app.state.value.upper()}"
        )
        return 0

    if args.command == "services":
        _print_services(app)
        return 0

    if args.command == "resources":
        _print_resources(app)
        return 0

    if args.command == "connections":
        _print_connections(app)
        return 0

    if args.command == "health":
        _print_health(app)
        return 0

    return 0


def run_application(app: CoreApplication) -> int:
    """Run the real C.O.R.E. application until interrupted."""

    try:
        app.start()

        print("C.O.R.E. v0.2")
        print("────────────────────────")
        print(
            f"Runtime: {app.state.value.upper()}"
        )
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
    """CLI entry point."""

    parser = create_parser()
    args = parser.parse_args()

    app = CoreApplication()

    if args.command == "start":
        return run_application(app)

    return execute_application(args, app)


if __name__ == "__main__":
    raise SystemExit(main())