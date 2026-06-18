"""Declarative base with a stable naming convention (helps Alembic and migrations)."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base for all ORM models.

    Every mapped model MUST declare ``__temporal_class__`` (FR / IA / EV) per the
    temporal reproducibility standard (BR-19). This is asserted by a test.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
