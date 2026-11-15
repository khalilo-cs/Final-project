from alembic import context

import app.main  # noqa: F401  (imports every model so the metadata is complete)
from app.database import Base, engine

target_metadata = Base.metadata


def run() -> None:
    connection = context.config.attributes.get("connection")
    if connection is None:  # `alembic` command line: use the configured database
        with engine.begin() as connection:
            _run(connection)
    else:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite cannot ALTER most columns in place
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run()
