"""Domain error foundation tests."""

from __future__ import annotations

from rescs.errors import (
    ConflictError,
    DependencyUnavailableError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
    StorageError,
    UnauthorizedError,
)


def test_defaults():
    err = InvalidRequestError()
    assert err.code == "INVALID_REQUEST"
    assert err.status_code == 400
    assert err.details is None
    assert str(err) == "InvalidRequestError"


def test_custom_message_and_details():
    err = NotFoundError("record missing", details={"id": "abc"})
    assert err.message == "record missing"
    assert err.details == {"id": "abc"}


def test_to_dict_shape():
    err = ForbiddenError("nope", details={"owner": "other"})
    payload = err.to_dict()
    assert payload == {
        "code": "FORBIDDEN",
        "message": "nope",
        "details": {"owner": "other"},
    }


def test_status_codes():
    assert InvalidRequestError().status_code == 400
    assert UnauthorizedError().status_code == 401
    assert ForbiddenError().status_code == 403
    assert NotFoundError().status_code == 404
    assert ConflictError().status_code == 409
    assert StorageError().status_code == 500
    assert DependencyUnavailableError().status_code == 503
