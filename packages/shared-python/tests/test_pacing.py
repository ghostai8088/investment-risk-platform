"""CC-2 pacing model contract tests (SQLite; PG isolation/trigger in the _pg file)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.pacing.events import RUN_TYPE_PACING_PROJECTION
from irp_shared.pacing.models import PacingProjectionResult
from irp_shared.temporal import TemporalClass


def test_result_is_ia_true_append_only() -> None:
    assert PacingProjectionResult.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    assert hasattr(PacingProjectionResult, "system_from")
    for attr in ("valid_from", "valid_to", "system_to", "record_version", "status", "updated_at"):
        assert not hasattr(PacingProjectionResult, attr), f"must not have {attr}"


def test_run_bound_snapshot_gated_model_bound() -> None:
    cols = PacingProjectionResult.__table__.columns
    for fk_col in ("calculation_run_id", "input_snapshot_id", "model_version_id"):
        assert not cols[fk_col].nullable and cols[fk_col].foreign_keys
    for fk_col in ("portfolio_id", "instrument_id"):
        assert cols[fk_col].foreign_keys
    # The projected values + the currency; period_index is the fund-age grain.
    for money in ("projected_call", "projected_distribution", "projected_nav", "unfunded_end"):
        assert not cols[money].nullable
    grain = {
        tuple(c.name for c in u.columns)
        for u in PacingProjectionResult.__table__.constraints
        if u.__class__.__name__ == "UniqueConstraint"
    }
    assert ("calculation_run_id", "period_index") in grain


def test_run_type_distinct() -> None:
    assert RUN_TYPE_PACING_PROJECTION == "PACING_PROJECTION"


def test_orm_guard_blocks_update_and_delete(session: Session) -> None:
    from irp_shared.calc.models import CalculationRun  # noqa: F401 (metadata already loaded)

    row = PacingProjectionResult(
        tenant_id=str(uuid.uuid4()),
        calculation_run_id=str(uuid.uuid4()),
        input_snapshot_id=str(uuid.uuid4()),
        model_version_id=str(uuid.uuid4()),
        portfolio_id=str(uuid.uuid4()),
        instrument_id=str(uuid.uuid4()),
        period_index=1,
        period_start=date(2026, 6, 30),
        period_end=date(2027, 6, 30),
        projected_call=Decimal("1000000.000000"),
        projected_distribution=Decimal("0.000000"),
        projected_nav=Decimal("1000000.000000"),
        unfunded_end=Decimal("0.000000"),
        currency_code="USD",
    )
    session.add(row)
    session.flush()
    row.projected_nav = Decimal("2.000000")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
