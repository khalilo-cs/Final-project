"""Bring the database schema up to date with Alembic at startup.

Databases created before migrations existed (by `create_all`) have the tables but no
`alembic_version`; they are stamped with the baseline revision, then upgraded.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

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
            command.stamp(config, BASELINE)
        command.upgrade(config, "head")
