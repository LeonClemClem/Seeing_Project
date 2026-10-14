from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_config() -> Config:
    return Config(str(Path(__file__).with_name("alembic.ini")))


def main() -> None:
    """Console script `seeing-migrate`: bring the database schema up to date."""
    command.upgrade(alembic_config(), "head")
