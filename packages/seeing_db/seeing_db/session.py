import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeing_db.config import database_url


def make_engine(url: str | None = None, **kwargs) -> Engine:
    # The DB is an e2-micro shared by both environments (max_connections 40): up to 2 web instances per environment
    # x (DB_POOL_SIZE + DB_MAX_OVERFLOW) = 16 per environment, plus the jobs. A page of the site sends ~10 requests at
    # once (forecast, Cn2, history, measurements, skill...): with 2 + 2 connections the slow ones held them all and the
    # others failed after 30 s (500 on every panel, 2/11 15h41-15h50 UTC).
    kwargs.setdefault("pool_size", int(os.environ.get("DB_POOL_SIZE", "4")))
    kwargs.setdefault("max_overflow", int(os.environ.get("DB_MAX_OVERFLOW", "4")))
    kwargs.setdefault("pool_pre_ping", True)
    return create_engine(url or database_url(), **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
