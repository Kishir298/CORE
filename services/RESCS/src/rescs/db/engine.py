"""SQLAlchemy engine construction and connectivity checks."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from rescs.errors import DependencyUnavailableError


def build_engine(
    database_url: str,
    *,
    echo: bool = False,
    pool_pre_ping: bool | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    connect_timeout: int = 5,
) -> Engine:
    """Create an engine tuned for the ``database_url`` backend.

    SQLite in-memory databases get a static pool (shared connection) so the
    database survives across sessions within a process. Network backends get
    ``pool_pre_ping`` and a bounded connect timeout to surface outages fast.
    """
    url = make_url(database_url)
    backend = url.get_backend_name()

    options: dict = {"echo": echo}
    if backend.startswith("sqlite"):
        if url.database in ("", ":memory:"):
            options["poolclass"] = StaticPool
        connect_args = dict(options.get("connect_args", {}))
        connect_args.setdefault("check_same_thread", False)
        options["connect_args"] = connect_args
    else:
        if pool_pre_ping is not None:
            options["pool_pre_ping"] = pool_pre_ping
        else:
            options["pool_pre_ping"] = True
        if pool_size is not None:
            options["pool_size"] = pool_size
        if max_overflow is not None:
            options["max_overflow"] = max_overflow
        connect_args = dict(options.get("connect_args", {}))
        connect_args.setdefault("connect_timeout", connect_timeout)
        options["connect_args"] = connect_args

    return create_engine(database_url, **options)


def check_connectivity(engine: Engine) -> None:
    """Run ``SELECT 1`` against the engine or raise a domain error."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        cause = str(exc.__cause__ or exc)
        raise DependencyUnavailableError(
            "database is unreachable",
            details={"cause": cause},
        ) from exc
