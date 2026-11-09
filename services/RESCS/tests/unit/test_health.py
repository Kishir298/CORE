"""Health service unit tests."""

from __future__ import annotations

from rescs.health import DOWN, OK, HealthService


def _ok() -> str:
    return OK


def _down() -> str:
    return DOWN


def test_no_checks_is_ok():
    service = HealthService()
    assert service.report() == {"status": OK, "checks": {}}


def test_all_ok():
    service = HealthService()
    service.register("db", _ok)
    service.register("storage", _ok)
    report = service.report()
    assert report["status"] == OK
    assert report["checks"] == {"db": OK, "storage": OK}


def test_any_down_dominates():
    service = HealthService()
    service.register("db", _ok)
    service.register("storage", _down)
    assert service.report()["status"] == DOWN


def test_raising_check_counts_as_down():
    def boom() -> str:
        raise RuntimeError("nope")

    service = HealthService()
    service.register("db", boom)
    report = service.report()
    assert report["status"] == DOWN
    assert report["checks"]["db"] == DOWN
