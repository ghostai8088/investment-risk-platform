"""Alembic environment.

The database URL is read from the ``DATABASE_URL`` environment variable at runtime
(no secrets in source — BR-10). ``target_metadata`` is the foundation metadata (audit,
entitlement, calculation-run). The CI ``migration`` job runs ``alembic upgrade head`` and
``alembic check`` (schema-drift gate, OD-052) against PostgreSQL.
"""

from __future__ import annotations

import os

from alembic import context

config = context.config

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Foundation metadata (audit, entitlement, calculation-run). Domain models are added later.
from irp_shared.models import metadata as target_metadata  # noqa: E402


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Drift check (P0.5 / OD-052): flag structural drift (added/removed tables and
            # columns). Type and server-default comparison is intentionally disabled to avoid
            # false positives from custom types (GUID) and dialect variants (JSON vs JSONB).
            compare_type=False,
            compare_server_default=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
