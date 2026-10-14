"""Lazily created engine/session so that importing the app (and /healthz) never touches the DB."""

from collections.abc import Iterator
from functools import cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from seeing_db import make_engine, make_session_factory


@cache
def get_engine() -> Engine:
    return make_engine()


@cache
def get_session_factory() -> sessionmaker[Session]:
    return make_session_factory(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one read-only session per request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
