"""Alembic environment: uses the Flask app config for the DB URL and the
SQLAlchemy metadata from app.models."""
from __future__ import annotations

import os
from logging.config import fileConfig
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer the app's DATABASE_URL; fall back to alembic.ini.
db_url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))


from app import create_app  # noqa: E402

flask_app = create_app()
with flask_app.app_context():
    from app.models import Base  # noqa: E402

    target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
