"""Portable column types.

``GUID`` stores UUIDs as native ``uuid`` on PostgreSQL (AD-004) and as ``CHAR(36)`` on
other engines (SQLite is used for fast unit tests — see AD-011). Values are always
surfaced to Python as ``str`` so application code and hashing are engine-independent.

``PreciseDecimal`` stores a high-scale exact decimal as native ``NUMERIC(precision, scale)`` on
PostgreSQL and as a fixed-scale TEXT string on other engines. SQLite has no exact numeric —
SQLAlchemy roundtrips ``Numeric`` through binary float there, which corrupts the 17th+
significant digit; a 20dp value (the P3-4 ``covariance_value`` scale) does NOT survive. Values
are surfaced as ``Decimal`` on both engines and quantized HALF_UP to the declared scale at bind
(the same rounding PG ``numeric`` applies to a sub-scale value — see
``snapshot.serialize._norm_decimal``), so both engines store and return the identical exact
value (AD-011).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, Numeric, String, TypeDecorator


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


class PreciseDecimal(TypeDecorator[Decimal]):
    impl = String
    cache_ok = True

    def __init__(self, precision: int = 38, scale: int = 20) -> None:
        super().__init__()
        self.precision = precision
        self.scale = scale
        self._quantum = Decimal(1).scaleb(-scale)

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Numeric(self.precision, self.scale))
        # precision digits + sign + decimal point headroom.
        return dialect.type_descriptor(String(self.precision + 4))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        # Quantize inside a context wide enough for the full column (precision integer digits +
        # scale) — the DEFAULT context is prec 28, which raises InvalidOperation for a value
        # Numeric(38,20) legitimately holds (> 8 integer digits at scale 20).
        with localcontext() as ctx:
            ctx.prec = self.precision + self.scale
            quantized = Decimal(value).quantize(self._quantum, rounding=ROUND_HALF_UP)
        if quantized == 0:
            quantized = abs(quantized)  # -0 -> +0: PG numeric drops the sign; keep engines equal
        if dialect.name == "postgresql":
            return quantized
        return f"{quantized:f}"

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)
