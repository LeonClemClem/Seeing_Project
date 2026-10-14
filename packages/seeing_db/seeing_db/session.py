from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeing_db.config import database_url


def make_engine(url: str | None = None, **kwargs) -> Engine:
    # Small pool: the DB is an e2-micro shared by both environments.
    kwargs.setdefault("pool_size", 2)
    kwargs.setdefault("max_overflow", 2)
    kwargs.setdefault("pool_pre_ping", True)
    return create_engine(url or database_url(), **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
