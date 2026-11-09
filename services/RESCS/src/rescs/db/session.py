"""SQLAlchemy session management and transactional scope."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from rescs.errors import (
    ConflictError,
    DependencyUnavailableError,
    RESCSError,
    StorageError,
)

SessionFactory = Callable[[], Session]


def create_session_factory(engine: Engine) -> SessionFactory:
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
    )
    return factory


def _cause(exc: BaseException) -> str:
    return str(exc.__cause__ or exc)


@contextmanager
def session_scope(
    session_factory: SessionFactory,
    action: str = "database operation",
    *,
    conflict: Callable[[], RESCSError] | None = None,
) -> Iterator[Session]:
    """Run a unit of work in its own transaction.

    Commits on success and rolls back on failure. Integrity violations raise
    ``conflict()`` when provided or a generic :class:`ConflictError`;
    connectivity failures become :class:`DependencyUnavailableError`; other
    database failures become :class:`StorageError`. Callers never observe raw
    database exceptions.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if conflict is not None:
            raise conflict() from exc
        raise ConflictError(
            "integrity constraint violation", details={"action": action}
        ) from exc
    except OperationalError as exc:
        session.rollback()
        raise DependencyUnavailableError(
            "database unavailable", details={"action": action, "cause": _cause(exc)}
        ) from exc
    except RESCSError:
        session.rollback()
        raise
    except SQLAlchemyError as exc:
        session.rollback()
        raise StorageError(
            "database failure", details={"action": action, "cause": _cause(exc)}
        ) from exc
    finally:
        session.close()
