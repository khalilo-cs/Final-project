from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

import app.main  # noqa: F401  (registers every model)
from app.database import Base
from app.migrate import migrate


def test_migrations_build_exactly_the_models(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    migrate(engine)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []
    migrate(engine)  # running again is a no-op
    engine.dispose()


def test_database_created_before_migrations_is_adopted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(engine)
    migrate(engine)
    with engine.connect() as connection:
        assert "alembic_version" in inspect(connection).get_table_names()
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version is not None
    engine.dispose()
