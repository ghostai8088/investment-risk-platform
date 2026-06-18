"""Portable column types.

``GUID`` stores UUIDs as native ``uuid`` on PostgreSQL (AD-004) and as ``CHAR(36)`` on
other engines (SQLite is used for fast unit tests — see AD-011). Values are always
surfaced to Python as ``str`` so application code and hashing are engine-independent.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator[str]):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(value)
