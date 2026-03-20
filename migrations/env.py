import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Load .env ────────────────────────────────────────
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url from DATABASE_URL environment variable
database_url = (os.environ.get("DATABASE_URL") or "").strip()
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is required for Alembic migrations. "
        "Set DATABASE_URL to a valid SQLAlchemy URL, for example: "
        "postgresql+psycopg2://rfq_user:changeme@localhost:5432/rfq_manager_db"
    )
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all models so Base.metadata is populated ──
from src.database import Base  # noqa: E402
from src.models import rfq, workflow, rfq_stage, subtask, reminder  # noqa: E402, F401
from src.models import rfq_note, rfq_file, rfq_stage_field_value, rfq_history  # noqa: E402, F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata
            )

            with context.begin_transaction():
                context.run_migrations()
    except Exception as exc:
        raise RuntimeError(
            "Alembic could not connect using DATABASE_URL. "
            "Verify host/user/password/database and SQLAlchemy driver format, for example: "
            "postgresql+psycopg2://rfq_user:changeme@localhost:5432/rfq_manager_db"
        ) from exc


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
