"""SQLite engine, session factory and the declarative Base."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for every Orbit table."""


_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    # SQLite only: the webhook background task and the request handler share the engine.
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create any missing tables. Orbit has no migrations; the schema is created on startup."""
    from app import models  # noqa: F401  (registers the mappers)

    Base.metadata.create_all(engine)
