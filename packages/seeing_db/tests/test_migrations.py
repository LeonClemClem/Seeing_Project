import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from seeing_db import Base, Site, User, UserRole, make_engine, make_session_factory
from seeing_db.migrate import alembic_config

pytestmark = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="needs a Postgres DATABASE_URL")


def _enum_exists(engine, name: str) -> bool:
    with engine.connect() as conn:
        return conn.execute(text("SELECT 1 FROM pg_type WHERE typname = :n"), {"n": name}).first() is not None


def test_upgrade_downgrade_roundtrip():
    cfg = alembic_config()
    command.upgrade(cfg, "head")
    engine = make_engine()
    session = make_session_factory(engine)()
    slugs = set(session.scalars(select(Site.slug)))
    session.close()
    assert {"saint-veran", "copernic-gap", "pic-du-midi"} <= slugs
    assert {"users", "user_sessions"} <= set(inspect(engine).get_table_names())

    command.downgrade(cfg, "0002")
    assert "users" not in inspect(engine).get_table_names()
    assert not _enum_exists(engine, "user_role")

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine.dispose()


def test_models_match_migrations():
    """The models and the migration history describe the same schema (nothing left to autogenerate)."""
    command.upgrade(alembic_config(), "head")
    engine = make_engine()
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []


def test_user_email_must_be_lowercase():
    command.upgrade(alembic_config(), "head")
    engine = make_engine()
    session = make_session_factory(engine)()
    session.add(User(email="Someone@Example.org", password_hash="x", role=UserRole.user))
    with pytest.raises(IntegrityError):
        session.commit()
    session.close()
    engine.dispose()
