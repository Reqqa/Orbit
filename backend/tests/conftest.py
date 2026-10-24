"""Test fixtures: a throwaway database per test.

The environment variables are set before anything from `app` is imported, because
`app.db` builds the engine at import time and `app.config.get_settings` is cached
on first call. An env var outranks the .env file, so the developer's real database
and real secrets are never touched by the test suite.
"""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP_DB = Path(tempfile.gettempdir()) / "orbit_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["PHONE_HMAC_KEY"] = "test-phone-hmac-key"

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402,F401  (registers the mappers)


@pytest.fixture
def session() -> Iterator[Session]:
    """A Session on an empty database; every table is dropped afterwards."""
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def tenants(session: Session) -> tuple[models.Tenant, models.Tenant]:
    """Two tenants, so tests can show one tenant's data cannot affect the other's."""
    a = models.Tenant(name="Tenant A", whatsapp_number="+60100000001")
    b = models.Tenant(name="Tenant B", whatsapp_number="+60100000002")
    session.add_all([a, b])
    session.commit()
    return a, b
