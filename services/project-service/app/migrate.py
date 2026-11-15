"""Bring the database schema up to date with Alembic at startup.

Databases created before migrations existed (by `create_all`) have the tables but no
`alembic_version`. One that already matches the models is stamped as current; an older
one is stamped with the baseline revision and upgraded from there.
"""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from app.database import Base

BASELINE = "0001"
_SCRIPTS = Path(__file__).parent / "migrations"


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(_SCRIPTS))
    return config


def migrate(engine: Engine) -> None:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if tables and "alembic_version" not in tables:
            context = MigrationContext.configure(connection)
            current = not compare_metadata(context, Base.metadata)
            command.stamp(config, "head" if current else BASELINE)
        command.upgrade(config, "head")
