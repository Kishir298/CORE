from core.application import CoreApplication
from core.runtime import RuntimeState


def test_application_creates_all_subsystems():
    app = CoreApplication()

    assert app.runtime is not None
    assert app.configuration is not None
    assert app.logger is not None
    assert app.communication is not None
    assert app.resources is not None
    assert app.organization is not None
    assert app.routing is not None
    assert app.events is not None
    assert app.health is not None
    assert app.dependencies is not None
    assert app.security is not None
    assert app.services is not None


def test_application_registers_runtime_components():
    app = CoreApplication()

    assert app.runtime.component_count() == 2


def test_application_starts():
    app = CoreApplication()

    app.start()

    assert app.state == RuntimeState.RUNNING
    assert app.is_running is True


def test_application_stops():
    app = CoreApplication()

    app.start()
    app.stop()

    assert app.state == RuntimeState.STOPPED
    assert app.is_running is False


def test_application_restarts():
    app = CoreApplication()

    app.start()
    app.restart()

    assert app.state == RuntimeState.RUNNING
    assert app.is_running is True


def test_application_event_shutdown():
    app = CoreApplication()

    app.events.subscribe(
        "TEST",
        lambda event: None,
    )

    app.start()
    app.stop()

    assert app.events.subscriber_count() == 0


def test_application_owns_communication():
    app = CoreApplication()

    assert app.communication is not None