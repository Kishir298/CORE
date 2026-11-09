"""Health reporting foundation.

Components register a named check callable returning a status string.
The aggregate report reflects the worst observed status. Only later phases
wire real dependency checks (database, object store); a process with no
registered checks is by definition healthy/ready.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

ComponentStatus = str  # "ok" | "degraded" | "down"

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_CHECK = Callable[[], ComponentStatus]


class HealthService:
    def __init__(self) -> None:
        self._checks: dict[str, _CHECK] = {}

    def register(self, name: str, check: _CHECK) -> None:
        self._checks[name] = check

    def report(self) -> dict[str, Any]:
        results: dict[str, ComponentStatus] = {}
        for name, check in self._checks.items():
            try:
                results[name] = check()
            except Exception:
                results[name] = DOWN
        if DOWN in results.values():
            overall = DOWN
        elif DEGRADED in results.values():
            overall = DEGRADED
        else:
            overall = OK
        return {"status": overall, "checks": results}
