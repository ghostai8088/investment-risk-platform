"""SQLite-local unit/behavior tests for P3-3 factor exposures (the second governed RISK number,
ENT-028 family — allocation v1).

RLS is a no-op on SQLite (FORCE-RLS isolation + the P0001 trigger live in
``test_factor_exposure_pg.py``); here we prove: the pure allocation kernel (indicator loading = 1;
exact ``mark_currency`` match; HALF_UP@6; duplicate/NULL-scope factor sets rejected; signs
preserved); **contributions sum to the pinned input total EXACTLY (ε = 0 — REQ-MKT-003)**; the
model-governance hardening (registered model_version required; ``assert_registered_model_version``
fail-closed pre-create ⇒ zero run/rows; methodology_ref mandatory; assumptions/limitations
recorded); the atoms+factors snapshot pinning (the IA + EV pin flavors) + snapshot-only compute
(reproducible under a later factor amend AND a later exposure re-run); the pre-create refusals
(non-COMPLETED/foreign/empty exposure run; empty/non-CURRENCY/NULL-scope/duplicate-currency factor
set); the post-create FAILED unmapped-atom gate (zero rows, DEPENDS_ON kept); CALC.RUN_* audit
(+ NO RISK.* code); lineage; the append-only ORM guard; entitlement REUSE parity (no new
permission); the methodology doc; the load-bearing scope fences; and the migration head.
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.lineage.models import (
    EDGE_KIND_DEPENDENCY,
    EDGE_KIND_ORIGIN,
    SOURCE_TYPE_CALCULATION_RUN,
    SOURCE_TYPE_DATA_SNAPSHOT,
    LineageEdge,
)
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.marketdata.factor import (
    FactorActor,
    FactorNotVisible,
    capture_factor,
    update_factor,
)
from irp_shared.model.models import ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.model.service import UnregisteredModelError
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    FactorExposureActor,
    FactorExposureInputError,
    FactorExposureResult,
    FactorKernelError,
    ModelVersionConflictError,
    WrongModelVersionError,
    factor_kernel,
    list_factor_exposures,
    register_factor_exposure_model,
    register_sensitivity_model,
    run_factor_exposure,
)
from irp_shared.risk.bootstrap import (
    FACTOR_EXPOSURE_ASSUMPTIONS,
    FACTOR_EXPOSURE_LIMITATIONS,
    FACTOR_EXPOSURE_METHODOLOGY_REF,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_EXPOSURE,
    COMPONENT_KIND_FACTOR,
    PURPOSE_FACTOR_EXPOSURE_INPUT,
    SNAPSHOT_COMPONENT_KINDS,
    list_components,
    verify_snapshot,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
ACTOR = FactorExposureActor(actor_id="analyst")
_Q6 = Decimal("0.000001")


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _ccy(db: Session, *codes: str) -> None:
    for code in codes:
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _holding(db: Session, tenant: str, pf: str, code: str, qty: str, mark: str, ccy: str) -> str:
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=code,
        name="i",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal(qty),
        valid_from=T0,
    )
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal(mark),
        currency_code=ccy,
        valid_from=T0,
    )
    return inst


def _exposure_run(
    db: Session,
    tenant: str,
    holdings: list[tuple[str, str, str]],  # (qty, mark, ccy)
    *,
    fx: tuple[tuple[str, str, str], ...] = (),  # (base, quote, rate)
) -> str:
    """A COMPLETED governed exposure run over the given holdings -> its run_id (the atoms)."""
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    for i, (qty, mark, ccy) in enumerate(holdings):
        _holding(db, tenant, pf, f"I{i}-{uuid.uuid4().hex[:6]}", qty, mark, ccy)
    for base, quote, rate in fx:
        capture_fx_rate(
            db,
            base_currency=base,
            quote_currency=quote,
            rate_date=VD,
            rate=Decimal(rate),
            acting_tenant=tenant,
            actor=FxRateActor(actor_id="s"),
            valid_from=T0,
        )
    result = run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="analyst"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        base_currency="USD",
    )
    assert result.status == RunStatus.COMPLETED.value
    return result.run.run_id


def _factor(db: Session, tenant: str, code: str, ccy: str | None, family: str = "CURRENCY") -> str:
    return capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family=family,
        currency_code=ccy,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id


def _model(db: Session, tenant: str, code_version: str = "risk-v1") -> str:
    return register_factor_exposure_model(
        db, tenant_id=tenant, actor_id="analyst", code_version=code_version
    ).id


def _run(db: Session, tenant: str, mv: str, exposure_run_id: str, factor_ids: list[str], **kw):  # noqa: ANN202
    return run_factor_exposure(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        exposure_run_id=exposure_run_id,
        factor_ids=factor_ids,
        **kw,
    )


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == tenant,
            CalculationRun.run_type == "FACTOR_EXPOSURE",
        )
    ).scalar_one()


def _count_results(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(FactorExposureResult)
        .where(FactorExposureResult.tenant_id == tenant)
    ).scalar_one()


# ---------- (1) pure kernel ----------


def test_kernel_indicator_allocation_exact() -> None:
    f = factor_kernel.FactorPin(
        id="f1", factor_code="FX_USD", factor_family="CURRENCY", currency_code="USD"
    )
    index = factor_kernel.build_factor_index([f])
    atom = factor_kernel.AtomPin(
        id="a1",
        portfolio_id="p",
        instrument_id="i",
        base_currency="USD",
        mark_currency="USD",
        exposure_amount=Decimal("1250.000000"),
    )
    out = factor_kernel.allocate_atom(atom, index)
    assert out is not None
    assert out.loading == Decimal(1)
    assert out.exposure_amount == Decimal("1250.000000")
    assert out.exposure_amount == out.exposure_amount.quantize(_Q6)  # exactly 6dp


def test_kernel_sign_preserved_for_short_atom() -> None:
    f = factor_kernel.FactorPin(
        id="f1", factor_code="FX_USD", factor_family="CURRENCY", currency_code="USD"
    )
    index = factor_kernel.build_factor_index([f])
    atom = factor_kernel.AtomPin(
        id="a1",
        portfolio_id="p",
        instrument_id="i",
        base_currency="USD",
        mark_currency="USD",
        exposure_amount=Decimal("-2500.000000"),
    )
    out = factor_kernel.allocate_atom(atom, index)
    assert out is not None and out.exposure_amount == Decimal("-2500.000000")


def test_kernel_unmapped_atom_returns_none() -> None:
    f = factor_kernel.FactorPin(
        id="f1", factor_code="FX_USD", factor_family="CURRENCY", currency_code="USD"
    )
    index = factor_kernel.build_factor_index([f])
    atom = factor_kernel.AtomPin(
        id="a1",
        portfolio_id="p",
        instrument_id="i",
        base_currency="USD",
        mark_currency="JPY",
        exposure_amount=Decimal("1.000000"),
    )
    assert factor_kernel.allocate_atom(atom, index) is None


def test_kernel_duplicate_currency_rejected() -> None:
    f1 = factor_kernel.FactorPin(
        id="f1", factor_code="A", factor_family="CURRENCY", currency_code="USD"
    )
    f2 = factor_kernel.FactorPin(
        id="f2", factor_code="B", factor_family="CURRENCY", currency_code="USD"
    )
    with pytest.raises(FactorKernelError):
        factor_kernel.build_factor_index([f1, f2])


def test_kernel_null_scope_rejected() -> None:
    f = factor_kernel.FactorPin(
        id="f1", factor_code="A", factor_family="CURRENCY", currency_code=None
    )
    with pytest.raises(FactorKernelError):
        factor_kernel.build_factor_index([f])


# ---------- (2) model governance ----------


def test_model_and_version_registered_with_methodology(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None
    assert version.methodology_ref == FACTOR_EXPOSURE_METHODOLOGY_REF  # mandatory, set
    assert version.status == "REGISTERED"


def test_assumptions_and_limitations_recorded(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    assumptions = (
        session.execute(select(ModelAssumption).where(ModelAssumption.model_version_id == mv_id))
        .scalars()
        .all()
    )
    limitations = (
        session.execute(select(ModelLimitation).where(ModelLimitation.model_version_id == mv_id))
        .scalars()
        .all()
    )
    assert len(assumptions) == len(FACTOR_EXPOSURE_ASSUMPTIONS)
    assert len(limitations) == len(FACTOR_EXPOSURE_LIMITATIONS)


def test_register_is_idempotent(session: Session) -> None:
    tenant = str(uuid.uuid4())
    assert _model(session, tenant) == _model(session, tenant)


def test_unregistered_model_version_refused_pre_create_zero_run_zero_rows(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    with pytest.raises(UnregisteredModelError):
        _run(session, tenant, str(uuid.uuid4()), exp_run, [fac])
    assert _count_runs(session, tenant) == 0
    assert _count_results(session, tenant) == 0


# ---------- (3) positive correctness + the REQ-MKT-003 sum-to-total acceptance ----------


def test_allocation_rows_bound_to_run_snapshot_model(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "12.50", "USD"), ("-40", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    assert result.status == RunStatus.COMPLETED.value
    assert len(result.rows) == 2
    for row in result.rows:
        assert row.calculation_run_id == result.run.run_id
        assert row.input_snapshot_id == result.run.input_snapshot_id
        assert row.model_version_id == mv
        assert row.factor_id == fac
        assert row.factor_family == "CURRENCY"
        assert row.loading == Decimal(1)
        assert row.base_currency == "USD" and row.mark_currency == "USD"
    amounts = sorted(r.exposure_amount for r in result.rows)
    assert amounts == [Decimal("-400.000000"), Decimal("1250.000000")]  # signed, exact


def test_contributions_sum_to_total_exactly_multi_currency(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR", "GBP")
    exp_run = _exposure_run(
        session,
        tenant,
        [("100", "10.00", "USD"), ("50", "20.00", "EUR"), ("-30", "5.00", "GBP")],
        fx=[("EUR", "USD", "1.10"), ("GBP", "USD", "1.25")],
    )
    factors = [
        _factor(session, tenant, "FX_USD", "USD"),
        _factor(session, tenant, "FX_EUR", "EUR"),
        _factor(session, tenant, "FX_GBP", "GBP"),
    ]
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, factors)
    assert result.status == RunStatus.COMPLETED.value
    assert len(result.rows) == 3
    # ε = 0: the allocation total equals the pinned atom total EXACTLY (REQ-MKT-003).
    from irp_shared.exposure import ExposureAggregate

    atom_total = sum(
        r.exposure_amount
        for r in session.execute(
            select(ExposureAggregate).where(ExposureAggregate.calculation_run_id == exp_run)
        ).scalars()
    )
    assert sum(r.exposure_amount for r in result.rows) == atom_total
    # Per-factor totals are the atoms partitioned by mark currency (signed).
    by_factor = {r.factor_code: r.exposure_amount for r in result.rows}
    assert by_factor["FX_USD"] == Decimal("1000.000000")
    assert by_factor["FX_EUR"] == Decimal("1100.000000")  # 50 x 20.00 x 1.10
    assert by_factor["FX_GBP"] == Decimal("-187.500000")  # -30 x 5.00 x 1.25


# ---------- (4) snapshot pinning + reproducibility ----------


def test_component_kinds_minted() -> None:
    assert COMPONENT_KIND_EXPOSURE in SNAPSHOT_COMPONENT_KINDS
    assert COMPONENT_KIND_FACTOR in SNAPSHOT_COMPONENT_KINDS


def test_snapshot_pins_atoms_ia_flavor_and_factors_ev_flavor(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    snapshot_id = result.run.input_snapshot_id
    comps = list_components(session, snapshot_id=snapshot_id, acting_tenant=tenant)
    kinds = {c.component_kind for c in comps}
    assert kinds == {COMPONENT_KIND_EXPOSURE, COMPONENT_KIND_FACTOR}
    for c in comps:
        if c.component_kind == COMPONENT_KIND_EXPOSURE:
            # The IA pin flavor: system axis only (immutable row; drift impossible).
            assert c.pinned_valid_from is None
            assert c.pinned_record_version is None
            assert c.pinned_system_from is not None
            assert c.target_entity_type == "exposure_aggregate"
        else:
            # The EV pin flavor: record_version discriminates drift; no system axis.
            assert c.pinned_record_version is not None
            assert c.pinned_system_from is None
            assert c.target_entity_type == "factor"
    from irp_shared.snapshot import resolve_snapshot

    header = resolve_snapshot(session, snapshot_id, acting_tenant=tenant)
    assert header.purpose == PURPOSE_FACTOR_EXPOSURE_INPUT


def test_reproducible_under_factor_amend(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    first = _run(session, tenant, mv, exp_run, [fac])
    snapshot_id = first.run.input_snapshot_id
    # A later EV amend of the factor definition must NOT change a re-run over the SAME snapshot.
    from irp_shared.marketdata.factor import resolve_factor

    update_factor(
        session,
        resolve_factor(session, fac, acting_tenant=tenant),
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        description="amended after the run",
    )
    session.flush()
    second = run_factor_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=snapshot_id,
    )
    assert second.status == RunStatus.COMPLETED.value
    assert sorted([(r.factor_code, r.loading, r.exposure_amount) for r in first.rows]) == sorted(
        [(r.factor_code, r.loading, r.exposure_amount) for r in second.rows]
    )
    # The amend IS visible as drift on the FACTOR component (the EXPOSURE pin stays byte-stable).
    v = verify_snapshot(session, snapshot_id=snapshot_id, acting_tenant=tenant)
    assert not v.ok
    comps = {
        c.id: c for c in list_components(session, snapshot_id=snapshot_id, acting_tenant=tenant)
    }
    for cid in v.drifted_components:
        assert comps[cid].component_kind == COMPONENT_KIND_FACTOR


def test_reproducible_under_later_exposure_rerun(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    first = _run(session, tenant, mv, exp_run, [fac])
    # A LATER exposure run (new atoms) must not touch the pinned snapshot or a same-snapshot rerun.
    _exposure_run(session, tenant, [("999", "99.00", "USD")])
    second = run_factor_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=first.run.input_snapshot_id,
    )
    assert [r.exposure_amount for r in second.rows] == [r.exposure_amount for r in first.rows]


def test_determinism_same_snapshot(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD"), ("7", "3.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    first = _run(session, tenant, mv, exp_run, [fac])
    second = run_factor_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=first.run.input_snapshot_id,
    )
    assert [
        (r.portfolio_id, r.instrument_id, r.factor_id, r.loading, r.exposure_amount)
        for r in first.rows
    ] == [
        (r.portfolio_id, r.instrument_id, r.factor_id, r.loading, r.exposure_amount)
        for r in second.rows
    ]


# ---------- (5) pre-create refusals (zero run / zero rows / zero audit) ----------


def test_missing_inputs_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(FactorExposureInputError):
        run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv,
        )  # neither snapshot_id nor exposure_run_id+factor_ids
    with pytest.raises(FactorExposureInputError):
        run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="",
            environment_id="ci",
            model_version_id=mv,
            exposure_run_id=str(uuid.uuid4()),
            factor_ids=[str(uuid.uuid4())],
        )
    assert _count_runs(session, tenant) == 0


def test_foreign_or_unknown_exposure_run_refused(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    _ccy(session, "USD")
    foreign_run = _exposure_run(session, other, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    from irp_shared.exposure.service import ExposureRunNotVisible

    with pytest.raises(ExposureRunNotVisible):
        _run(session, tenant, mv, foreign_run, [fac])
    assert _count_runs(session, tenant) == 0


def test_non_completed_exposure_run_refused(session: Session) -> None:
    # A REAL non-COMPLETED exposure run (status CREATED via the calc rails): the consume guard
    # must refuse it pre-create — NOT a vacuous unknown-id proxy (the 2026-07 review finding).
    from irp_shared.calc.service import create_run

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    stale_run = create_run(
        session, tenant_id=tenant, run_type="EXPOSURE_AGGREGATE", initiated_by="s"
    )
    session.flush()
    with pytest.raises(FactorExposureInputError, match="COMPLETED"):
        _run(session, tenant, mv, stale_run.run_id, [fac])
    assert _count_runs(session, tenant) == 0


def test_unknown_exposure_run_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    from irp_shared.exposure.service import ExposureRunNotVisible

    with pytest.raises(ExposureRunNotVisible):
        _run(session, tenant, mv, str(uuid.uuid4()), [fac])  # unknown run id
    assert _count_runs(session, tenant) == 0


def test_non_currency_family_factor_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    style = _factor(session, tenant, "MOMENTUM", None, family="STYLE")
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(FactorExposureInputError):
        _run(session, tenant, mv, exp_run, [style])
    assert _count_runs(session, tenant) == 0


def test_null_scope_currency_factor_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    scopeless = _factor(session, tenant, "FX_ANY", None, family="CURRENCY")
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(FactorExposureInputError):
        _run(session, tenant, mv, exp_run, [scopeless])
    assert _count_runs(session, tenant) == 0


def test_duplicate_currency_factor_set_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    f1 = _factor(session, tenant, "FX_USD_A", "USD")
    f2 = _factor(session, tenant, "FX_USD_B", "USD")
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(FactorExposureInputError):
        _run(session, tenant, mv, exp_run, [f1, f2])
    assert _count_runs(session, tenant) == 0  # the ambiguous partition never produced a run


def test_cross_tenant_factor_refused(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    foreign_factor = _factor(session, other, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(FactorNotVisible):
        _run(session, tenant, mv, exp_run, [foreign_factor])
    assert _count_runs(session, tenant) == 0


def _mint_fe_snapshot(session: Session, tenant: str, atoms: list[dict], factors: list[dict]):  # noqa: ANN202
    """Hand-mint a FACTOR_EXPOSURE_INPUT snapshot with ARBITRARY pinned content (bypassing the
    governed builder) — the adjudication-gate probe vehicle (the test_var precedent)."""
    from types import SimpleNamespace

    from irp_shared.snapshot import (
        COMPONENT_KIND_EXPOSURE,
        COMPONENT_KIND_FACTOR,
        PURPOSE_FACTOR_EXPOSURE_INPUT,
        SnapshotActor,
    )
    from irp_shared.snapshot.service import _append_spec, _persist_snapshot

    specs: list = []
    for kind, ent, rows in (
        (COMPONENT_KIND_EXPOSURE, "exposure_aggregate", atoms),
        (COMPONENT_KIND_FACTOR, "factor", factors),
    ):
        for content in rows:
            content = dict(content)
            anchor = SimpleNamespace(
                id=content["id"], valid_from=None, system_from=T0, record_version=None
            )
            _append_spec(specs, kind, ent, anchor, content)
    header = _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        specs=specs,
        label="",
        purpose=PURPOSE_FACTOR_EXPOSURE_INPUT,
        as_of_valid_at=VALID_AT,
        as_of_known_at=VALID_AT,
        as_of_valuation_date=VD,
        binding_predicate_version="test:hand-minted",
    )
    session.flush()
    return header


def _atom(base: str | None = "USD", amount: str = "10.000000") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "portfolio_id": str(uuid.uuid4()),
        "instrument_id": str(uuid.uuid4()),
        "base_currency": base,
        "mark_currency": "USD",
        "exposure_amount": amount,
    }


def _fac(code: str = "FX_USD", ccy: str = "USD") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "factor_code": code,
        "factor_family": "CURRENCY",
        "currency_code": ccy,
    }


def test_p3c3_null_base_currency_and_malformed_pin_refused(session: Session) -> None:
    # P3-C3 binder-consistency pass (the active-risk/VaR twins): factor_service pins a hand-mintable
    # atom whose base_currency reaches the NOT-NULL varchar(3) result column, and it was the one
    # binder with NO malformed-pin wrapper at all (OD-A Part 3, folded on discovery). A
    # uniformly-NULL/>3-char base_currency refuses PRE-create; a JSON-null exposure_amount
    # (Decimal(None) -> TypeError) is a governed 422, not a raw parse 500.
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    mv = _model(session, tenant)
    session.flush()

    def consume(snapshot_id: str):  # noqa: ANN202
        return run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=FactorExposureActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv,
            snapshot_id=snapshot_id,
        )

    for bad in (None, "USDX"):
        snap = _mint_fe_snapshot(session, tenant, [_atom(base=bad)], [_fac()])
        with pytest.raises(FactorExposureInputError, match="base_currency is not a 3-letter code"):
            consume(snap.id)
    malformed = _atom()
    malformed["exposure_amount"] = None  # JSON-null numeric -> TypeError -> governed 422
    snap = _mint_fe_snapshot(session, tenant, [malformed], [_fac()])
    with pytest.raises(FactorExposureInputError, match="not a well-formed v1 input"):
        consume(snap.id)
    assert _count_runs(session, tenant) == 0


# ---------- (6) post-create FAILED (fail-closed DQ; zero rows; durable evidence) ----------


def test_unmapped_atom_fails_closed_post_create(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    exp_run = _exposure_run(
        session,
        tenant,
        [("100", "10.00", "USD"), ("50", "20.00", "EUR")],
        fx=[("EUR", "USD", "1.10")],
    )
    fac = _factor(session, tenant, "FX_USD", "USD")  # no EUR factor -> the EUR atom is unmapped
    mv = _model(session, tenant)
    session.flush()
    runs_before = _count_runs(session, tenant)
    result = _run(session, tenant, mv, exp_run, [fac])
    assert result.status == RunStatus.FAILED.value
    assert result.rows == [] and result.failure_reason
    assert _count_runs(session, tenant) == runs_before + 1  # committed FAILED run
    assert _count_results(session, tenant) == 0  # zero result rows — no silent residual bucket


def test_failed_run_keeps_snapshot_dependency_lineage(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    exp_run = _exposure_run(session, tenant, [("50", "20.00", "EUR")], fx=[("EUR", "USD", "1.10")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    assert result.status == RunStatus.FAILED.value
    edges = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.target_entity_type == "calculation_run",
                LineageEdge.target_entity_id == result.run.run_id,
                LineageEdge.edge_kind == EDGE_KIND_DEPENDENCY,
            )
        )
        .scalars()
        .all()
    )
    assert len(edges) == 1  # the FAILED run keeps its input link (durable refusal evidence)
    assert edges[0].source_type == SOURCE_TYPE_DATA_SNAPSHOT


# ---------- (7) output contract / audit / lineage / append-only / grain ----------


def test_output_contract_bindings(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    run = result.run
    assert run.input_snapshot_id and run.model_version_id == mv
    assert run.code_version == "risk-v1" and run.environment_id == "ci"
    for row in result.rows:
        assert row.input_snapshot_id == run.input_snapshot_id
        assert row.calculation_run_id == run.run_id
        assert row.model_version_id == mv


def test_audit_calc_run_events_no_risk_event(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_type == "calculation_run",
                AuditEvent.entity_id == result.run.run_id,
            )
        )
        .scalars()
        .all()
    )
    types = [e.event_type for e in events]
    assert "CALC.RUN_CREATE" in types and "CALC.RUN_STATUS_CHANGE" in types
    risk_events = (
        session.execute(select(AuditEvent).where(AuditEvent.event_type.like("RISK.%")))
        .scalars()
        .all()
    )
    assert risk_events == []  # RISK.FACTOR_EXPOSURE_CREATE stays reserved-not-emitted


def test_lineage_snapshot_to_run_to_result(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    origin = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_CALCULATION_RUN,
                LineageEdge.target_entity_type == "factor_exposure_result",
                LineageEdge.edge_kind == EDGE_KIND_ORIGIN,
            )
        )
        .scalars()
        .all()
    )
    assert {e.target_entity_id for e in origin} == {r.id for r in result.rows}
    assert all(e.run_id == result.run.run_id for e in origin)


def test_factor_exposure_result_is_ia_append_only(session: Session) -> None:
    from irp_shared.temporal import TemporalClass

    assert FactorExposureResult.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    session.commit()
    row = result.rows[0]
    row.exposure_amount = Decimal("999.000000")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    with pytest.raises(AppendOnlyViolation):
        session.delete(result.rows[0])
        session.flush()


def test_grain_uniqueness_within_run(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    keys = {
        (r.calculation_run_id, r.portfolio_id, r.instrument_id, r.factor_id) for r in result.rows
    }
    assert len(keys) == len(result.rows)  # the 4-tuple grain is unique within the run
    listed = list_factor_exposures(session, run_id=result.run.run_id, acting_tenant=tenant)
    assert len(listed) == len(result.rows)


# ---------- (8) entitlement REUSE parity (no new permission — OD-P3-3-L) ----------


def test_risk_permissions_reused_no_new_codes() -> None:
    run_roles = {r for r, perms in ROLE_TEMPLATES.items() if "risk.run" in perms}
    view_roles = {r for r, perms in ROLE_TEMPLATES.items() if "risk.view" in perms}
    assert run_roles == {"data_steward", "risk_analyst_1l", "platform_admin"}
    assert view_roles == {
        "risk_analyst_1l",
        "risk_manager_2l",
        "data_steward",
        "auditor_3l",
        "platform_admin",
    }
    # NO factor-exposure-specific permission exists anywhere in the templates (pure reuse).
    all_codes = {code for perms in ROLE_TEMPLATES.values() for code in perms}
    assert not {c for c in all_codes if "factor_exposure" in c or "factor." in c}


# ---------- (9) methodology doc ----------

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_FACTOR_SERVICE_SRC = (
    _ROOT / "packages/shared-python/src/irp_shared/risk/factor_service.py"
).read_text()
_FACTOR_KERNEL_SRC = (
    _ROOT / "packages/shared-python/src/irp_shared/risk/factor_kernel.py"
).read_text()


def test_methodology_doc_exists_and_has_required_sections() -> None:
    doc = (_ROOT / FACTOR_EXPOSURE_METHODOLOGY_REF).read_text()
    for section in (
        "## Purpose & applicability",
        "## Inputs & data policy",
        "## Formulas & numerical standards",
        "## Assumptions",
        "## Limitations",
        "## Validation / reproduction tests",
        "## Known limitations",
    ):
        assert section in doc, section


def test_methodology_ref_matches_registered_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == FACTOR_EXPOSURE_METHODOLOGY_REF
    assert (_ROOT / version.methodology_ref).exists()


# ---------- (10) load-bearing scope fences ----------


def test_scope_fence_no_live_reads_in_compute_path() -> None:
    # The COMPUTE path (_parse_pins/_build_rows) reads snapshot-pinned content ONLY; the live
    # exposure/factor reads belong to the PRE-CREATE gate + the snapshot builder.
    tree = ast.parse(_FACTOR_SERVICE_SRC)
    forbidden = {"resolve_factor", "list_exposure_atoms", "resolve_exposure_run", "list_exposure"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("_parse_pins", "_build_rows"):
            found.add(node.name)
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            assert not (names & forbidden), (node.name, names & forbidden)
            assert not (attrs & forbidden), (node.name, attrs & forbidden)
    # The fence must never pass vacuously (2026-07 review finding): both compute helpers exist.
    assert found == {"_parse_pins", "_build_rows"}, found


def test_scope_fence_no_future_analytics_imports_or_identifiers() -> None:
    for src in (_FACTOR_SERVICE_SRC, _FACTOR_KERNEL_SRC):
        tree = ast.parse(src)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for mod in imported:
            parts = set(mod.split("."))
            assert not (
                parts & {"scenario", "pricing", "stress", "var", "covariance", "benchmark"}
            ), f"forbidden import {mod}"
        idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        forbidden_idents = {
            "value_at_risk",
            "expected_shortfall",
            "covariance",
            "regression",
            "beta",
            "scenario_result",
            "stress_test",
            "monte_carlo",
            "tracking_error",
            "attribution",
            "factor_return",
            "reconstruct_factor_return_as_of",
            "list_factor_returns",
        }
        assert not (idents & forbidden_idents), idents & forbidden_idents


def test_scope_fence_no_factor_return_component_kind() -> None:
    # P3-3 v1 consumes NO factor return. The FACTOR_RETURN kind WAS minted at P3-4 (its designed
    # first consumer — covariance; the no-status-decay flip); the load-bearing fence is that the
    # FACTOR-EXPOSURE sources still never reference it (the covariance slice does).
    assert "FACTOR_RETURN" in SNAPSHOT_COMPONENT_KINDS  # minted at P3-4, not here
    assert "FACTOR_RETURN" not in _FACTOR_SERVICE_SRC
    assert "FACTOR_RETURN" not in _FACTOR_KERNEL_SRC


# ---------- (10b) the 2026-07 adversarial-review regression tests ----------


def test_wrong_flavor_snapshot_refused_pre_create(session: Session) -> None:
    # Review finding: a FACTOR_EXPOSURE_INPUT-purposed snapshot with ZERO EXPOSURE/FACTOR
    # components (mintable via the generic build_snapshot) must be a pre-create refusal —
    # NOT a COMPLETED zero-row governed run.
    from irp_shared.snapshot import SnapshotActor, build_snapshot

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = create_portfolio(
        session,
        tenant_id=tenant,
        code="WF",
        name="wf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    _holding(session, tenant, pf, "WF-I0", "100", "10.00", "USD")
    wrong = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose=PURPOSE_FACTOR_EXPOSURE_INPUT,  # in-vocab, but the WRONG flavor
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
    )
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(FactorExposureInputError, match="pins no exposure atoms"):
        run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv,
            snapshot_id=wrong.id,
        )
    assert _count_runs(session, tenant) == 0
    assert _count_results(session, tenant) == 0


def test_non_currency_factor_refused_on_consume_path(session: Session) -> None:
    # Review finding: the family gate must hold on the consume-existing path too — a pinned
    # STYLE factor with a currency_code scope must refuse pre-create, never COMPLETE.
    from irp_shared.snapshot import SnapshotActor, build_factor_exposure_snapshot

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    style = capture_factor(
        session,
        factor_code="MOMENTUM_USD",
        factor_source="VENDOR_F",
        factor_family="STYLE",
        currency_code="USD",  # legal capture: scope is family-independent
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    pinned = build_factor_exposure_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        exposure_run_id=exp_run,
        factor_ids=[style],
    )
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(FactorExposureInputError, match="not supported"):
        run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv,
            snapshot_id=pinned.id,
        )
    assert _count_runs(session, tenant) == 0


def test_duplicate_currency_refused_on_consume_path(session: Session) -> None:
    # Review finding: an ambiguous partition pinned into a snapshot must refuse PRE-create on the
    # consume path (previously a committed FAILED run without DQ evidence).
    from irp_shared.snapshot import SnapshotActor, build_factor_exposure_snapshot

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    f1 = _factor(session, tenant, "FX_USD_A", "USD")
    f2 = _factor(session, tenant, "FX_USD_B", "USD")
    pinned = build_factor_exposure_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        exposure_run_id=exp_run,
        factor_ids=[f1, f2],
    )
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(FactorExposureInputError, match="duplicate currency_code"):
        run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv,
            snapshot_id=pinned.id,
        )
    assert _count_runs(session, tenant) == 0


def test_wrong_model_family_version_refused(session: Session) -> None:
    # Review finding: a registered SENSITIVITY model_version must not drive a factor-exposure
    # run (CTRL-003 model identity; reachable once two model families exist).
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _factor(session, tenant, "FX_USD", "USD")
    sensitivity_mv = register_sensitivity_model(
        session, tenant_id=tenant, actor_id="analyst", code_version="risk-v1"
    ).id
    session.flush()
    with pytest.raises(WrongModelVersionError):
        _run(session, tenant, sensitivity_mv, exp_run, [fac])
    assert _count_runs(session, tenant) == 0
    assert _count_results(session, tenant) == 0


def test_register_conflict_on_new_code_version(session: Session) -> None:
    # Review finding: re-registering v1 with a DIFFERENT code_version must be a governed 409
    # conflict, never an IntegrityError 500.
    tenant = str(uuid.uuid4())
    first = _model(session, tenant, code_version="risk-v1")
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, code_version="risk-v2")
    assert _model(session, tenant, code_version="risk-v1") == first  # idempotent path intact


def test_builder_refuses_empty_factor_ids(session: Session) -> None:
    # Review finding: a factor-less FACTOR_EXPOSURE_INPUT snapshot must be refused at build.
    from irp_shared.snapshot import (
        FactorExposureSnapshotError,
        SnapshotActor,
        build_factor_exposure_snapshot,
    )

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    exp_run = _exposure_run(session, tenant, [("100", "10.00", "USD")])
    with pytest.raises(FactorExposureSnapshotError, match="no factor ids"):
        build_factor_exposure_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="s"),
            exposure_run_id=exp_run,
            factor_ids=[],
        )


def test_failed_run_reason_names_unmapped_atoms(session: Session) -> None:
    # Review finding: the FAILED failure_reason must name the unmapped atoms/currencies, and the
    # DQ gate must leave a persisted data_quality_result for the run.
    from irp_shared.dq.models import DataQualityResult

    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    exp_run = _exposure_run(
        session,
        tenant,
        [("100", "10.00", "USD"), ("50", "20.00", "EUR")],
        fx=[("EUR", "USD", "1.10")],
    )
    fac = _factor(session, tenant, "FX_USD", "USD")
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, exp_run, [fac])
    assert result.status == RunStatus.FAILED.value
    assert result.failure_reason is not None
    assert "unmapped-atom:" in result.failure_reason and ":EUR" in result.failure_reason
    dq_rows = (
        session.execute(
            select(DataQualityResult).where(DataQualityResult.target_entity_id == result.run.run_id)
        )
        .scalars()
        .all()
    )
    assert dq_rows, "the fail-closed gate must persist DQ evidence for the FAILED run"


# ---------- (11) migration head ----------


def test_migration_head_is_factor_exposure() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0040_var_estimate_age"
    assert script.get_revision("0024_factor_exposure").down_revision == "0023_factor_return"
