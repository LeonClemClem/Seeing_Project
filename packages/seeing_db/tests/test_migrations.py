import os

import pytest
from alembic import command
from sqlalchemy import select

from seeing_db import Site, make_engine, make_session_factory
from seeing_db.migrate import alembic_config

pytestmark = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="needs a Postgres DATABASE_URL")


def test_upgrade_downgrade_roundtrip():
    cfg = alembic_config()
    command.upgrade(cfg, "head")
    session = make_session_factory(make_engine())()
    slugs = set(session.scalars(select(Site.slug)))
    session.close()
    assert {"saint-veran", "copernic-gap", "pic-du-midi"} <= slugs
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
