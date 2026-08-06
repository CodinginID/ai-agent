from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine with production-ready connection pooling.

    Configuration:
        - pool_size=10: Base number of connections kept in the pool.
        - max_overflow=20: Up to 20 extra connections may be created
          beyond pool_size under high load (total max = 30).
        - pool_pre_ping=True: Verify each connection before use to
          detect stale or broken connections from the database server.
        - pool_timeout=30: Seconds to wait for a connection from the
          pool before raising TimeoutError.
        - pool_recycle=3600: Recycle connections after 1 hour to
          prevent database-side connection limits from being hit.

    SQLite special handling:
        - check_same_thread=False: Allows connections to be used from
          any thread (SQLAlchemy's queue pool manages thread safety).
        - connect_args={"timeout": 30}: Waits up to 30 seconds for a
          write lock before raising OperationalError.
    """
    kwargs: dict = dict(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_timeout=30,
        pool_recycle=3600,
    )

    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 30}

    return create_engine(database_url, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
