"""Unit: upload-session compare_and_set_status (memory + sqlalchemy)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from rescs.domain import UploadSessionData, utcnow
from rescs.errors import ConflictError, NotFoundError
from rescs.repositories.memory import InMemoryUploadSessionRepository
from rescs.repositories.sqlalchemy_ import SQLAlchemyUploadSessionRepository


def _session(**overrides) -> UploadSessionData:
    values = dict(
        id="sess-" + uuid.uuid4().hex[:8],
        owner="system",
        filename="a.bin",
        total_size=10,
        status="active",
        expires_at=utcnow() + timedelta(hours=1),
    )
    values.update(overrides)
    return UploadSessionData(**values)


def _check_repo(repo) -> None:
    created = repo.create(_session())
    assert repo.compare_and_set_status(created.id, "active", "finalizing") is True
    assert repo.get(created.id).status == "finalizing"
    # Loser with stale expectation gets False, state untouched.
    assert repo.compare_and_set_status(created.id, "active", "finalizing") is False
    assert repo.get(created.id).status == "finalizing"
    with pytest.raises(NotFoundError):
        repo.compare_and_set_status("missing-id", "active", "finalizing")


def test_memory_cas_win_lose_missing():
    _check_repo(InMemoryUploadSessionRepository())


def test_sqlalchemy_cas_win_lose_missing(sqlite_session_factory):
    _check_repo(SQLAlchemyUploadSessionRepository(sqlite_session_factory))


def test_memory_cas_concurrent_single_winner():
    import concurrent.futures

    repo = InMemoryUploadSessionRepository()
    created = repo.create(_session())
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: repo.compare_and_set_status(created.id, "active", "finalizing"),
                range(8),
            )
        )
    assert results.count(True) == 1
    assert results.count(False) == 7
    assert repo.get(created.id).status == "finalizing"
    assert ConflictError is not None and NotFoundError is not None

