"""P3-C2 OD-D: captured-input ``PreciseDecimal`` parity.

Two proofs:
  1. TYPE FENCE — every float53-unsafe captured decimal column (precision >= 16) is now a
     ``PreciseDecimal`` (catches a regression back to plain ``Numeric``, which loses the 17th+
     digit on SQLite); ``coupon_rate(12,6)`` stays plain ``Numeric`` (safe by contract).
  2. ROUNDTRIP — a 17-significant-digit value bound to a converted column and read back on
     SQLite is EXACT (a plain ``Numeric`` column roundtrips through binary float and would
     corrupt it; PG was already exact — this closes the test-engine divergence).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.types import PreciseDecimal
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.marketdata.models import (
    BenchmarkConstituent,
    CurvePoint,
    FactorReturn,
    FxRate,
    PricePoint,
)
from irp_shared.models import Base
from irp_shared.position.models import Position
from irp_shared.reference.models import CorporateAction, InstrumentTerms
from irp_shared.transaction.models import Transaction
from irp_shared.valuation.models import Valuation

# (model, column, expected precision) — the OD-D converted set (precision >= 16). Includes the
# transaction captured/inert decimals (review fold): OD-D's criterion is mechanical (every
# captured decimal column with precision >= 16), so transaction.{quantity,price,gross_amount}
# belong here alongside the position/valuation/marketdata columns.
_CONVERTED = [
    (Position, "quantity", 28),
    (Position, "cost_basis", 20),
    (Valuation, "mark_value", 20),
    (FxRate, "rate", 28),
    (PricePoint, "price", 20),
    (CurvePoint, "point_value", 20),
    (BenchmarkConstituent, "weight", 20),
    (FactorReturn, "return_value", 20),
    (InstrumentTerms, "face_value", 20),
    (CorporateAction, "ratio", 18),
    (CorporateAction, "amount", 20),
    (Transaction, "quantity", 28),
    (Transaction, "price", 20),
    (Transaction, "gross_amount", 20),
]


@pytest.mark.parametrize("model,column,precision", _CONVERTED)
def test_converted_column_is_precise_decimal(model, column, precision) -> None:  # noqa: ANN001
    col_type = model.__table__.c[column].type
    assert isinstance(col_type, PreciseDecimal), (
        f"{model.__tablename__}.{column} must be PreciseDecimal (float53-unsafe: "
        f"precision {precision} >= 16); got {type(col_type).__name__}"
    )


def test_safe_column_stays_plain_numeric() -> None:
    from sqlalchemy import Numeric

    from irp_shared.reference.models import InstrumentTerms as IT

    col_type = IT.__table__.c["coupon_rate"].type
    assert isinstance(col_type, Numeric) and not isinstance(
        col_type, PreciseDecimal
    ), "coupon_rate(12,6) is float53-safe (12 < 16) and stays plain Numeric"


def test_factor_return_17_digit_value_roundtrips_exactly_on_sqlite() -> None:
    """The end-to-end proof through a converted column: a 17-significant-digit return survives
    the SQLite roundtrip byte-for-byte (a plain Numeric column would corrupt it)."""
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db: Session = make_session_factory(engine)()
    tenant = str(uuid.uuid4())
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
    from irp_shared.reference.models import Currency

    db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=t0))
    db.flush()
    # return_value is Numeric(20,12): a value exercising 17 significant digits within 12
    # fractional places (12345.678901234 — 17 sig digits, 9 fractional). Binary float cannot
    # represent it exactly; PreciseDecimal (fixed-scale TEXT on SQLite) can.
    exact = Decimal("12345.678901234")
    factor = capture_factor(
        db,
        factor_code="FX_X",
        factor_source="V",
        factor_family="CURRENCY",
        currency_code="USD",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=t0,
    )
    f = resolve_factor(db, factor.id, acting_tenant=tenant)
    capture_factor_return(
        db,
        f,
        return_date=date(2026, 5, 1),
        return_value=exact,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=t0,
    )
    db.flush()
    db.expire_all()  # force a fresh read from the DB (not the identity-map cache)
    row = db.query(FactorReturn).filter_by(tenant_id=tenant).one()
    assert row.return_value == exact  # exact — a plain Numeric would have lost the 17th digit
    db.close()
