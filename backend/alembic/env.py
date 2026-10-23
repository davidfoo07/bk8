"""Alembic migration environment configuration."""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# Import the Base and all models so metadata is populated
from app.config import sync_database_url
from app.models import tables  # noqa: F401 — imports trigger model registration
from app.models.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# An explicit sqlalchemy.url (e.g. set by the test suite) wins; otherwise use
# the app's DATABASE_URL so migrations always hit the database the app uses.
url = config.get_main_option("sqlalchemy.url") or sync_database_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
