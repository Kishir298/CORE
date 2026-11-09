import pytest

from tiviss.conversation import (
    Request,
    RequestValidationError,
    Response,
    ResponseStatus,
)


def test_request_creation_defaults():
    request = Request.create(source="owner", content="hello")
    assert request.source == "owner"
    assert request.content == "hello"
    assert request.request_id
    assert request.timestamp.tzinfo is not None
    assert request.metadata == {}


def test_request_explicit_id():
    request = Request.create(source="owner", content="hello", request_id="req-1")
    assert request.request_id == "req-1"


def test_request_empty_source_rejected():
    with pytest.raises(RequestValidationError):
        Request.create(source="", content="hello")


def test_request_empty_content_rejected():
    with pytest.raises(RequestValidationError):
        Request.create(source="owner", content="   ")


def test_response_creation_and_defaults():
    response = Response.create(
        request_id="req-1", agent_id="tiviss-1", content="ack", status=ResponseStatus.OK
    )
    assert response.request_id == "req-1"
    assert response.agent_id == "tiviss-1"
    assert response.ok


def test_response_status_values():
    assert ResponseStatus.OK.value == "ok"
    assert ResponseStatus.DENIED.value == "denied"
    assert ResponseStatus.FAILED.value == "failed"
    assert ResponseStatus.ERROR.value == "error"


def test_response_not_ok_when_denied():
    response = Response.create(
        request_id="req-1",
        agent_id="tiviss-1",
        content="no",
        status=ResponseStatus.DENIED,
    )
    assert response.ok is False


def test_request_is_immutable():
    request = Request.create(source="owner", content="x")
    with pytest.raises(AttributeError):
        request.content = "y"  # type: ignore[misc]
