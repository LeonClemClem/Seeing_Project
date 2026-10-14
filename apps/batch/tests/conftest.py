"""Persistence tests run against a real Postgres given by DATABASE_URL (see `make test-batch`).

The schema is reset to `alembic upgrade head` (which seeds the curated sites) for each test.
"""

import os

import pytest
from alembic import command
from sqlalchemy import text

from seeing_db import make_engine, make_session_factory
from seeing_db.migrate import alembic_config


def pytest_collection_modifyitems(config, items):
    if "DATABASE_URL" in os.environ:
        return
    skip = pytest.mark.skip(reason="needs a Postgres DATABASE_URL")
    for item in items:
        if "db" in item.fixturenames:
            item.add_marker(skip)


@pytest.fixture
def db():
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield make_session_factory(engine)
    engine.dispose()
