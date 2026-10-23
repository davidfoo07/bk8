"""Pytest configuration and shared fixtures.

Tests always run against a throwaway local database — TEST_DATABASE_URL, or
``<dev db>_test`` next to a local dev database, or the local Docker Postgres
when .env points at a hosted one (Supabase): the suite drops and recreates its
database, which must never happen remotely.  The URL is swapped on the
settings singleton here, before any test module imports app.models.database
and builds the engine.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings, sync_database_url

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_LOCAL_TEST_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/courtedge_test"

_dev_url = make_url(settings.database_url)
if os.environ.get("TEST_DATABASE_URL"):
    _test_url = make_url(os.environ["TEST_DATABASE_URL"])
elif _dev_url.host in _LOCAL_HOSTS:
    _test_url = _dev_url.set(database=f"{_dev_url.database}_test")
else:
    _test_url = make_url(_LOCAL_TEST_URL)
if _test_url.host not in _LOCAL_HOSTS:
    raise RuntimeError(f"Refusing to run tests against non-local database host {_test_url.host!r}")
if (_test_url.host, _test_url.port, _test_url.database) == (
    _dev_url.host, _dev_url.port, _dev_url.database
):
    raise RuntimeError(f"Test database must differ from dev database {_dev_url.database!r}")

settings.database_url = _test_url.set(drivername="postgresql+asyncpg").render_as_string(
    hide_password=False
)
settings.database_url_sync = sync_database_url(settings.database_url)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_db_ready = False


def _psycopg2_url():
    # SQLAlchemy 2.1 maps bare postgresql:// to psycopg 3, which isn't installed.
    return make_url(sync_database_url(settings.database_url))


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Recreate the test database and migrate it to head once per session."""
    global _db_ready
    from alembic import command
    from alembic.config import Config

    sync_url = _psycopg2_url()
    admin = create_engine(sync_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{sync_url.database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{sync_url.database}"'))
    except Exception as e:  # Postgres not running: non-DB tests still run
        print(f"\n[conftest] test database unavailable, DB tests will fail: {e}")
        yield
        return
    finally:
        admin.dispose()

    # No ini file: alembic.ini hardcodes a stale URL and its logging config
    # would clobber pytest's log capture.
    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url.render_as_string(hide_password=False))
    command.upgrade(cfg, "head")
    _db_ready = True
    yield


@pytest.fixture(autouse=True)
def _truncate_tables():
    """Empty every table after each test so tests don't see each other's rows."""
    yield
    if not _db_ready:
        return
    from app.models.database import Base
    from app.models import tables  # noqa: F401 — registers models on Base

    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    eng = create_engine(_psycopg2_url())
    try:
        with eng.begin() as conn:
            conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    finally:
        eng.dispose()


@pytest.fixture
def sample_player_absence():
    """Sample player absence for testing."""
    from app.schemas.team import PlayerAbsence
    return PlayerAbsence(
        player_id="1630595",
        name="Cade Cunningham",
        status="OUT",
        reason="Knee - Injury Management",
        ortg_impact=-3.5,
        drtg_impact=1.2,
        nrtg_impact=-4.7,
        minutes_share=0.38,
    )


@pytest.fixture
def sample_player_absences():
    """Multiple player absences for multi-player testing."""
    from app.schemas.team import PlayerAbsence
    return [
        PlayerAbsence(
            player_id="1630595",
            name="Cade Cunningham",
            status="OUT",
            ortg_impact=-3.5,
            drtg_impact=1.2,
            nrtg_impact=-4.7,
            minutes_share=0.38,
        ),
        PlayerAbsence(
            player_id="203999",
            name="Jalen Duren",
            status="OUT",
            ortg_impact=-1.5,
            drtg_impact=0.8,
            nrtg_impact=-2.3,
            minutes_share=0.30,
        ),
    ]


@pytest.fixture(autouse=True)
def _reset_db_pool():
    """Drop pooled asyncpg connections after each test.

    The module-level TestClient runs every request on a fresh event loop, so a
    connection pooled by one request is bound to a loop that is already closed
    by the next one ("attached to a different loop").
    """
    yield
    from app.models.database import engine
    engine.sync_engine.dispose(close=False)
