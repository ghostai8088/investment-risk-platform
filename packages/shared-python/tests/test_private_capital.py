"""SQLite-local unit/behavior tests for CC-1 private capital (ENT-015/016).

RLS is a no-op on SQLite, so symmetric isolation + the P0001 DB triggers live in the PG
file; here we prove the model contracts (temporal classes; the FR manual trio on
``commitment``; NO TimestampMixin on the IA event tables — the transaction precedent;
the ORM append-only guards; the current-row and reversal partial-unique indexes; the
capture-only scope fence: no snapshot/run/model column anywhere), and the service-layer
behavior added at steps 4-5.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.private_capital.models import (
    CALL_TYPES,
    DISTRIBUTION_TYPES,
    CapitalCall,
    Commitment,
    Distribution,
)
from irp_shared.temporal import TemporalClass

# --- temporal classes + column contracts ---


def test_commitment_is_fr_with_manual_trio() -> None:
    assert Commitment.__temporal_class__ == TemporalClass.FULL_REPRODUCIBLE
    for attr in ("valid_from", "valid_to", "system_from", "system_to"):
        assert hasattr(Commitment, attr)
    # The FR manual trio is declared on the model (the mixin supplies only the axes).
    for attr in ("record_version", "supersedes_id", "restatement_reason"):
        assert hasattr(Commitment, attr)


def test_event_tables_are_ia_without_timestamps() -> None:
    for model in (CapitalCall, Distribution):
        assert model.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
        assert hasattr(model, "system_from")
        # No FR/EV axis, no lifecycle, and NO TimestampMixin (updated_* on a
        # P0001-guarded table is dead from birth — the transaction precedent).
        for attr in (
            "valid_from",
            "valid_to",
            "system_to",
            "record_version",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ):
            assert not hasattr(model, attr), f"{model.__name__} must not have {attr}"


def test_capture_only_scope_fence() -> None:
    # Captured inputs bind NO snapshot/run/model (the house contract, OD-CC-1-D/E) and
    # store NO derived economics (funded/unfunded are CC-2's).
    forbidden = {
        "input_snapshot_id",
        "calculation_run_id",
        "model_version_id",
        "funded_amount",
        "unfunded_amount",
        "vintage_year",
    }
    for model in (Commitment, CapitalCall, Distribution):
        cols = set(model.__table__.columns.keys())
        assert not (forbidden & cols), f"{model.__name__} leaks: {forbidden & cols}"


def test_event_tables_key_on_stable_identity_not_version_fk() -> None:
    # The verifier's structural HIGH: events key on (portfolio_id, instrument_id); the
    # commitment_version_id echo is provenance-only and deliberately NOT an FK (an FR
    # version row is not a stable link target).
    for model in (CapitalCall, Distribution):
        cols = model.__table__.columns
        assert not cols["commitment_version_id"].foreign_keys
        assert cols["portfolio_id"].foreign_keys and cols["instrument_id"].foreign_keys


def test_vocab_constants() -> None:
    assert CALL_TYPES == ("DRAWDOWN", "EQUALIZATION", "FEE")
    assert DISTRIBUTION_TYPES == ("RETURN_OF_CAPITAL", "CAPITAL_GAIN", "INCOME")
    assert hasattr(Distribution, "is_recallable")
    assert not hasattr(CapitalCall, "is_recallable")  # distribution-only (OD-CC-1-C)


def test_partial_unique_indexes_declared() -> None:
    def _index(model, name):  # noqa: ANN001, ANN202
        by_name = {ix.name: ix for ix in model.__table__.indexes}
        assert name in by_name, f"{model.__name__} missing index {name}"
        return by_name[name]

    current = _index(Commitment, "uq_commitment_current")
    assert current.unique
    assert [c.name for c in current.columns] == ["tenant_id", "portfolio_id", "instrument_id"]
    for model, name in (
        (CapitalCall, "uq_capital_call_reverses"),
        (Distribution, "uq_distribution_reverses"),
    ):
        ix = _index(model, name)
        assert ix.unique
        assert [c.name for c in ix.columns] == ["reverses_id"]


# --- the ORM append-only guards (the DB trigger halves live in the PG suite) ---


def _minimal_call(session: Session) -> CapitalCall:
    row = CapitalCall(
        tenant_id=str(uuid.uuid4()),
        portfolio_id=None,  # replaced below; FKs unenforced default-off on SQLite
        instrument_id=None,
        commitment_version_id=str(uuid.uuid4()),
        event_date=date(2026, 3, 2),
        amount=Decimal("1000000.000000"),
        currency_code="USD",
        call_type="DRAWDOWN",
    )
    # SQLite in these unit tests doesn't enforce FKs; the service layer (steps 4-5)
    # resolves them fail-closed — here we only exercise the ORM guard mechanics.
    row.portfolio_id = str(uuid.uuid4())
    row.instrument_id = str(uuid.uuid4())
    session.add(row)
    session.flush()
    return row


def test_orm_guard_blocks_update(session: Session) -> None:
    row = _minimal_call(session)
    row.amount = Decimal("2.000000")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_orm_guard_blocks_delete(session: Session) -> None:
    row = _minimal_call(session)
    session.delete(row)
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_distribution_orm_guard_blocks_update(session: Session) -> None:
    row = Distribution(
        tenant_id=str(uuid.uuid4()),
        portfolio_id=str(uuid.uuid4()),
        instrument_id=str(uuid.uuid4()),
        commitment_version_id=str(uuid.uuid4()),
        event_date=date(2026, 3, 2),
        amount=Decimal("500000.000000"),
        currency_code="USD",
        distribution_type="INCOME",
    )
    session.add(row)
    session.flush()
    row.is_recallable = True
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
