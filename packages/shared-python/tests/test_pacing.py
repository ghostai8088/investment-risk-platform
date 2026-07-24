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


def test_migration_head_and_chain() -> None:
    import pathlib

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0051_breach_action"  # MG-2
    assert script.get_revision("0045_pacing_projection").down_revision == "0044_private_capital"


# --- step 5: the registrar + declared-param parse-back ---

from irp_shared.model.service import ModelVersionConflictError, WrongModelVersionError  # noqa: E402
from irp_shared.pacing.bootstrap import (  # noqa: E402
    PACING_MODEL_CODE,
    declared_pacing_parameters,
    register_pacing_projection_model,
)


def _register(session: Session, tenant: str, **kw):  # noqa: ANN003, ANN202
    base = dict(
        rc_schedule=[Decimal("0.25"), Decimal("0.333"), Decimal("0.5")],
        fund_life=12,
        bow=Decimal("2.5"),
        growth=Decimal("0.13"),
        yield_floor=Decimal("0"),
    )
    base.update(kw)
    return register_pacing_projection_model(
        session, tenant_id=tenant, actor_id="a", code_version="cc2-v1", **base
    )


def test_register_and_parse_back_roundtrip(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv = _register(session, tenant)
    session.flush()
    assert mv.status == "REGISTERED"
    params = declared_pacing_parameters(session, mv)
    assert params.rc_schedule == (Decimal("0.250000"), Decimal("0.333000"), Decimal("0.500000"))
    assert params.fund_life == 12
    assert params.bow == Decimal("2.5")
    assert params.growth == Decimal("0.13")
    assert params.yield_floor == Decimal("0.000000")


def test_register_is_idempotent(session: Session) -> None:
    tenant = str(uuid.uuid4())
    a = _register(session, tenant)
    session.flush()
    b = _register(session, tenant)
    assert a.id == b.id  # resolve-or-register


def test_register_conflict_on_changed_declaration(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _register(session, tenant)
    session.flush()
    # Same label + code_version but a DIFFERENT bow -> the assumption set differs -> conflict.
    with pytest.raises(ModelVersionConflictError):
        _register(session, tenant, bow=Decimal("3.0"))


def test_register_canonicalizes_rate_identity(session: Session) -> None:
    tenant = str(uuid.uuid4())
    a = _register(session, tenant, rc_schedule=[Decimal("0.25"), Decimal("0.5")])
    session.flush()
    # 0.250 vs 0.25 must NOT mint a distinct identity (same canonical 6dp form).
    b = _register(session, tenant, rc_schedule=[Decimal("0.250"), Decimal("0.500")])
    assert a.id == b.id


def test_register_rejects_out_of_domain(session: Session) -> None:
    tenant = str(uuid.uuid4())
    for bad in (
        dict(bow=Decimal("0")),
        dict(growth=Decimal("-1")),
        dict(yield_floor=Decimal("1.5")),
        dict(rc_schedule=[Decimal("1.5")]),
        dict(fund_life=0),
        dict(rc_schedule=[Decimal("0.1")] * 13, fund_life=12),  # length > L
    ):
        with pytest.raises(ValueError):
            _register(session, tenant, **bad)


def test_register_refuses_unbindable_magnitude(session: Session) -> None:
    """Register/bind symmetry: values the strict parse-back would reject (fund_life > 9999; a
    bow/growth integer part > 4 digits; > 12 dp) are refused AT REGISTRATION — never a version that
    registers 201 yet can never bind."""
    for bad in (
        dict(fund_life=10000),  # _INT_PATTERN caps at 9999
        dict(bow=Decimal("12345")),  # _SIGNED_DECIMAL integer part <= 4 digits
        dict(growth=Decimal("0.1234567890123")),  # > 12 dp
    ):
        with pytest.raises(ValueError):
            _register(session, tenant=str(uuid.uuid4()), **bad)


def test_register_negative_zero_growth_is_one_identity(session: Session) -> None:
    """A ``-0`` growth is value-identical to ``0`` and MUST NOT mint a distinct version identity
    (nor trip a spurious same-label conflict) — the canonicalization folds the sign of zero."""
    tenant = str(uuid.uuid4())
    a = _register(session, tenant, growth=Decimal("0"))
    session.flush()
    b = _register(session, tenant, growth=Decimal("-0"))  # same label, code_version
    assert a.id == b.id  # resolve-or-register, not a 409


def test_parse_back_fails_closed_on_missing_form_marker(session: Session) -> None:
    # A version minted WITHOUT the functional_form marker (e.g. via the generic endpoint) must
    # fail closed at parse-back, not silently project.
    from irp_shared.model.service import register_model_version, resolve_or_register_model

    tenant = str(uuid.uuid4())
    model = resolve_or_register_model(
        session,
        tenant_id=tenant,
        code=PACING_MODEL_CODE,
        name="x",
        model_type="PACING_PROJECTION",
        actor_id="a",
        description="d",
    )
    mv = register_model_version(
        session,
        model=model,
        version_label="rogue",
        actor_id="a",
        methodology_ref="m",
        code_version="x",
        status="REGISTERED",
        assumptions=("rc_schedule=0.5", "fund_life=4", "bow=2", "growth=0", "yield_floor=0"),
        limitations=("l",),
    )
    session.flush()
    with pytest.raises(WrongModelVersionError):
        declared_pacing_parameters(session, mv)
