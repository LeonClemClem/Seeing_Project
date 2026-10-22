"""Run the Alembic migrations kept in the repository's `database/` folder."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

#: Location of the ini in a repo checkout (path install with `develop = true`): <repo>/database/alembic.ini.
REPO_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "database" / "alembic.ini"


def alembic_ini() -> Path:
    """Path of `alembic.ini`: $ALEMBIC_CONFIG if set (the web image), else the repo checkout's `database/`."""
    env = os.environ.get("ALEMBIC_CONFIG")
    path = Path(env) if env else REPO_ALEMBIC_INI
    if not path.is_file():
        raise RuntimeError(
            f"Alembic config not found at {path}. Set ALEMBIC_CONFIG to the path of database/alembic.ini."
        )
    return path


def alembic_config() -> Config:
    return Config(str(alembic_ini()))


def main() -> None:
    """Console script `seeing-migrate`: bring the database schema up to date."""
    command.upgrade(alembic_config(), "head")
