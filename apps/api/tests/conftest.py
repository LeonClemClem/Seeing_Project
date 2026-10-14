"""Tests run against a real, throwaway Postgres: TEST_DATABASE_URL (default: the `web-pg` container on
port 55434, see Makefile `test-api`). The schema is dropped and recreated, so the database name must
contain "test"; DATABASE_URL is deliberately ignored so a dev database is never wiped."""

import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://seeing:seeing@localhost:55434/seeing_test"
)
if "test" not in TEST_DATABASE_URL.rsplit("/", 1)[-1]:
    raise RuntimeError(f"Refusing to run destructive tests on a non-test database: {TEST_DATABASE_URL}")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from collections.abc import Iterator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from seeing_api.db import get_session_factory  # noqa: E402
from seeing_api.main import create_app  # noqa: E402
from seeing_db import Cn2Profile, Forecast, ModelRun, RunStatus, Site  # noqa: E402
from seeing_db.migrate import alembic_config  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    try:
        with get_session_factory()() as s:
            # Start from an empty schema (a downgrade would fail on leftover forecast rows).
            s.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
            s.commit()
    except Exception as exc:  # pragma: no cover - environment problem, not a test failure
        pytest.exit(f"Postgres not reachable at DATABASE_URL ({exc}). Run `make test-api`.", returncode=2)
    command.upgrade(alembic_config(), "head")


@pytest.fixture
def session() -> Iterator[Session]:
    with get_session_factory()() as s:
        s.execute(delete(ModelRun))
        s.commit()
        yield s
        s.rollback()
        s.execute(delete(ModelRun))
        s.commit()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(static_dir="/nonexistent"))


T0 = datetime(2026, 10, 13, 0, tzinfo=UTC)


def add_run(
    session: Session,
    run_time: datetime,
    status: RunStatus = RunStatus.success,
    slug: str = "saint-veran",
    seeing: list[float | None] | None = None,
) -> ModelRun:
    site = session.scalar(select(Site).where(Site.slug == slug))
    assert site is not None
    run = ModelRun(run_time=run_time, status=status, finished_at=run_time + timedelta(hours=3))
    session.add(run)
    session.flush()
    for lead, value in enumerate(seeing if seeing is not None else [1.0, 1.2, 0.8]):
        valid = run_time + timedelta(hours=lead)
        session.add(
            Forecast(
                run_id=run.id, site_id=site.id, valid_time=valid, lead_hour=lead,
                seeing_arcsec=value, r0_m=0.1, integral_cn2=1e-13, h_coulim_m=500.0,
            )
        )
        session.add(
            Cn2Profile(
                run_id=run.id, site_id=site.id, valid_time=valid, lead_hour=lead,
                heights_m=[0.0, 100.0, 200.0][: 2 + lead % 2], cn2=[1e-15, 1e-16, 1e-17][: 2 + lead % 2],
            )
        )
    session.commit()
    return run
