from collections.abc import Callable

from core.health.models import HealthResult, HealthStatus


HealthCheck = Callable[[], HealthResult]


class HealthMonitor:
    """Tracks the health of C.O.R.E. components."""

    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck] = {}
        self._results: dict[str, HealthResult] = {}

    def register(
        self,
        component_id: str,
        check: HealthCheck,
    ) -> None:
        self._checks[component_id] = check

        self._results[component_id] = HealthResult(
            component_id=component_id,
            status=HealthStatus.UNKNOWN,
            message="Health check has not run yet.",
        )

    def unregister(self, component_id: str) -> None:
        self._checks.pop(component_id, None)
        self._results.pop(component_id, None)

    def check(self, component_id: str) -> HealthResult:
        check = self._checks.get(component_id)

        if check is None:
            return HealthResult(
                component_id=component_id,
                status=HealthStatus.UNKNOWN,
                message="No health check registered.",
            )

        try:
            result = check()

            if not isinstance(result, HealthResult):
                result = HealthResult(
                    component_id=component_id,
                    status=HealthStatus.UNHEALTHY,
                    message="Health check returned an invalid result.",
                )

        except Exception as exc:
            result = HealthResult(
                component_id=component_id,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {exc}",
            )

        self._results[component_id] = result
        return result

    def check_all(self) -> list[HealthResult]:
        return [
            self.check(component_id)
            for component_id in self._checks
        ]

    def get(self, component_id: str) -> HealthResult:
        return self._results.get(
            component_id,
            HealthResult(
                component_id=component_id,
                status=HealthStatus.UNKNOWN,
                message="Component not registered.",
            ),
        )

    def status(self, component_id: str) -> HealthStatus:
        return self.get(component_id).status

    def overall_status(self) -> HealthStatus:
        if not self._results:
            return HealthStatus.UNKNOWN

        statuses = [
            result.status
            for result in self._results.values()
        ]

        if any(status == HealthStatus.UNHEALTHY for status in statuses):
            return HealthStatus.UNHEALTHY

        if any(status == HealthStatus.DEGRADED for status in statuses):
            return HealthStatus.DEGRADED

        if all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY

        return HealthStatus.UNKNOWN

    def count(self) -> int:
        return len(self._checks)

    def clear(self) -> None:
        self._checks.clear()
        self._results.clear()