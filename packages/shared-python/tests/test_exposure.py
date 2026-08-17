"""SQLite-local unit/behavior tests for P2-3 exposure (the first governed derived number, ENT-014).

RLS is a no-op on SQLite (FORCE-RLS isolation + the P0001 trigger live in ``test_exposure_pg.py``);
here we prove: the run-bound + snapshot-gated compute (signed market value v1 = signed qty x
captured
mark x effective captured FX); HALF_UP quantization + the exact-by-construction self-audit; the
effective composite fx_rate + fx_legs evidence (direct/reciprocal/triangulated); snapshot-only input
(no live read; reproducible-under-correction); the failure model (pre-create refusal vs post-create
FAILED); CALC.RUN_* audit (+ NO EXPOSURE.* code); lineage snapshot->run (DEPENDS_ON) + run->result
(ORIGIN, run_id stamped); fail-closed DQ gates; the append-only ORM guard; entitlement parity; the
load-bearing scope fences (snapshot-only/no-risk imports, ast.Mult permitted); and the migration
head.
"""

from __future__ import annotations

import ast
import json
import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.exposure import (
    EXPOSURE_TYPE_MARKET_VALUE,
    ExposureActor,
    ExposureAggregate,
    ExposureInputError,
    run_exposure,
)
from irp_shared.exposure import service as exposure_service
from irp_shared.lineage.models import (
    EDGE_KIND_DEPENDENCY,
    EDGE_KIND_ORIGIN,
    SOURCE_TYPE_CALCULATION_RUN,
    SOURCE_TYPE_DATA_SNAPSHOT,
    LineageEdge,
)
from irp_shared.marketdata import (
    FxRateActor,
    FxRateNotFound,
    capture_fx_rate,
    correct_fx_rate,
    resolve_fx_rate,
)
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, PortfolioNotVisible, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import SnapshotActor, build_snapshot, list_components
from irp_shared.snapshot.models import COMPONENT_KIND_FX, PURPOSE_EXPOSURE_INPUT
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
ACTOR = ExposureActor(actor_id="analyst")
_MONEY_Q = Decimal("0.000001")


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
    from irp_shared.reference.models import Currency

    for code in codes:
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _inst(db: Session, tenant: str, code: str) -> str:
    return create_instrument(
        db,
        tenant_id=tenant,
        code=code,
        name="i",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id


def _pf(db: Session, tenant: str, code: str = "ACCT", base: str | None = None) -> str:
    return create_portfolio(
        db,
        tenant_id=tenant,
        code=code,
        name=code.lower(),
        node_type="ACCOUNT",
        base_currency_code=base,
        actor=PortfolioActor(actor_id="s"),
    ).id


def _pos(db: Session, tenant: str, pf: str, inst: str, qty: str) -> None:
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal(qty),
        valid_from=T0,
    )


def _val(db: Session, tenant: str, pf: str, inst: str, mark: str, ccy: str) -> None:
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


def _fx(db: Session, tenant: str, base: str, quote: str, rate: str) -> str:
    return capture_fx_rate(
        db,
        base_currency=base,
        quote_currency=quote,
        rate_date=VD,
        rate=Decimal(rate),
        acting_tenant=tenant,
        actor=FxRateActor(actor_id="s"),
        valid_from=T0,
    ).id


def _holding(db: Session, tenant: str, pf: str, code: str, qty: str, mark: str, ccy: str) -> str:
    inst = _inst(db, tenant, code)
    _pos(db, tenant, pf, inst, qty)
    _val(db, tenant, pf, inst, mark, ccy)
    return inst


def _run(db: Session, tenant: str, pf: str, base: str | None = "USD", **kw):  # noqa: ANN202
    return run_exposure(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        base_currency=base,
        **kw,
    )


# ---------- positive correctness + determinism ----------


def test_signed_market_value_and_self_audit(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "12.50", "USD")
    _holding(session, tenant, pf, "I1", "-200", "7.00", "EUR")
    _fx(session, tenant, "EUR", "USD", "1.10")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.COMPLETED.value
    by_amt = {r.exposure_amount for r in result.rows}
    assert by_amt == {Decimal("1250.000000"), Decimal("-1540.000000")}
    assert sum(r.exposure_amount for r in result.rows) == Decimal("-290.000000")
    for r in result.rows:
        assert r.exposure_type == EXPOSURE_TYPE_MARKET_VALUE
        # exact-by-construction from the stored, rounded fx_rate.
        assert r.exposure_amount == (r.signed_quantity * r.mark_value * r.fx_rate).quantize(
            _MONEY_Q, rounding=ROUND_HALF_UP
        )


def test_api1b_scope_portfolio_stamped_on_build(session: Session) -> None:
    """API-1b (OD-API-1b-B): the build path stamps ``scope_portfolio_id`` = the ROOT portfolio_id
    (the subtree this exposure run aggregates), so the downstream factor/var/active-risk chain can
    copy it forward and the Class-C 'latest for P' reads resolve. The full copy-forward chain +
    snapshot-consume NULL are proven end-to-end in the risk endpoint + demo-stage9z PG tests."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "12.50", "USD")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.COMPLETED.value
    assert result.run.scope_portfolio_id == pf  # the root is recorded, not NULL


def test_no_portfolio_total_rows(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "12.50", "USD")
    _holding(session, tenant, pf, "I1", "5", "3.00", "USD")
    session.flush()
    result = _run(session, tenant, pf, "USD")
    # One row per (portfolio, instrument) — NO aggregate TOTAL row.
    assert len(result.rows) == 2
    assert all(r.instrument_id for r in result.rows)


def test_half_up_quantization(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    # qty 1 x mark 1.000001 x fx 1.0000005 -> 1.00000150...; HALF_UP @ 6dp = 1.000002.
    _holding(session, tenant, pf, "I0", "1", "1.000001", "EUR")
    _fx(session, tenant, "EUR", "USD", "1.0000005")
    session.flush()
    result = _run(session, tenant, pf, "USD")
    (row,) = result.rows
    assert row.exposure_amount == (row.signed_quantity * row.mark_value * row.fx_rate).quantize(
        _MONEY_Q, rounding=ROUND_HALF_UP
    )


def test_identity_when_mark_is_base(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    result = _run(session, tenant, pf, "USD")
    (row,) = result.rows
    assert row.fx_rate == Decimal("1.000000000000")
    assert json.loads(row.fx_legs) == []  # identity: no legs
    assert row.exposure_amount == Decimal("20.000000")


def test_reciprocal_conversion(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "5.00", "USD")  # USD mark, base EUR
    _fx(session, tenant, "EUR", "USD", "1.25")  # only EUR/USD published
    session.flush()
    result = _run(session, tenant, pf, "EUR")
    (row,) = result.rows
    # USD->EUR reciprocal of 1.25 = 0.8; 100 x 5 x 0.8 = 400.
    assert row.fx_rate == Decimal("0.800000000000")
    assert json.loads(row.fx_legs)[0]["direction"] == "reciprocal"
    assert row.exposure_amount == Decimal("400.000000")


def test_triangulated_conversion(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR", "JPY")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "3.00", "EUR")  # EUR mark, base JPY
    _fx(session, tenant, "EUR", "USD", "1.10")  # EUR->USD
    _fx(session, tenant, "USD", "JPY", "150")  # USD->JPY  (triangulate EUR->USD->JPY)
    session.flush()
    result = _run(session, tenant, pf, "JPY")
    (row,) = result.rows
    # effective EUR->JPY = 1.10 x 150 = 165; 10 x 3 x 165 = 4950.
    assert row.fx_rate == Decimal("165.000000000000")
    assert len(json.loads(row.fx_legs)) == 2
    assert row.exposure_amount == Decimal("4950.000000")


def test_determinism_same_snapshot(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "7.00", "EUR")
    _fx(session, tenant, "EUR", "USD", "1.10")
    session.flush()
    first = _run(session, tenant, pf, "USD")
    snap_id = first.run.input_snapshot_id
    # Re-run over the SAME snapshot.
    second = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        snapshot_id=snap_id,
        base_currency="USD",
        scope_node_id=pf,  # STRUCT-3 (DP-7): a v2-snapshot consume names its node
    )
    assert [r.exposure_amount for r in first.rows] == [r.exposure_amount for r in second.rows]


def test_reproducible_under_fx_correction(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "7.00", "EUR")
    fx_id = _fx(session, tenant, "EUR", "USD", "1.10")
    session.flush()
    first = _run(session, tenant, pf, "USD")
    snap_id = first.run.input_snapshot_id
    before = [r.exposure_amount for r in first.rows]
    # A vendor correction AFTER the run changes the live rate.
    fx_row = resolve_fx_rate(session, fx_id, acting_tenant=tenant)
    correct_fx_rate(
        session,
        fx_row,
        restatement_reason="vendor restatement",
        acting_tenant=tenant,
        actor=FxRateActor(actor_id="s"),
        # a realistic EUR/USD, distinct from the pinned base 1.10 (the correction must NOT leak
        # into the snapshot-reproduced rerun asserted below)
        rate=Decimal("1.25"),
    )
    session.flush()
    # Re-run over the SAME snapshot — the captured FX is reused; exposure is identical.
    again = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        snapshot_id=snap_id,
        base_currency="USD",
        scope_node_id=pf,  # STRUCT-3 (DP-7): a v2-snapshot consume names its node
    )
    assert [r.exposure_amount for r in again.rows] == before


# ---------- snapshot-bound input only ----------


def test_snapshot_pins_fx_components(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "7.00", "EUR")
    _fx(session, tenant, "EUR", "USD", "1.10")
    session.flush()
    snap = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose=PURPOSE_EXPOSURE_INPUT,
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        base_currency="USD",
    )
    comps = list_components(session, snapshot_id=snap.id, acting_tenant=tenant)
    fx_comps = [c for c in comps if c.component_kind == COMPONENT_KIND_FX]
    assert len(fx_comps) == 1  # the EUR/USD leg is pinned


def test_cross_tenant_portfolio_fails_closed_pre_create(session: Session) -> None:
    tenant = str(uuid.uuid4())
    other = str(uuid.uuid4())
    _ccy(session, "USD")
    pf_other = _pf(session, other, code="OTHER")
    _holding(session, other, pf_other, "I0", "10", "2.00", "USD")
    session.flush()
    with pytest.raises(PortfolioNotVisible):
        _run(session, tenant, pf_other, "USD")  # acting as `tenant`, pf belongs to `other`
    assert _count_runs(session, tenant) == 0  # pre-create refusal: no run


# ---------- failure model ----------


def test_pre_create_refusal_missing_code_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    with pytest.raises(ExposureInputError):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="",
            environment_id="ci",
            portfolio_id=pf,
            as_of_valid_at=VALID_AT,
            base_currency="USD",
        )
    assert _count_runs(session, tenant) == 0
    assert _count_exposure(session, tenant) == 0


def test_pre_create_refusal_missing_environment_id(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    with pytest.raises(ExposureInputError):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="v1",
            environment_id="",
            portfolio_id=pf,
            as_of_valid_at=VALID_AT,
            base_currency="USD",
        )
    assert _count_runs(session, tenant) == 0


def test_pre_create_refusal_missing_initiator(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    with pytest.raises(ExposureInputError):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ExposureActor(actor_id=""),
            code_version="v1",
            environment_id="ci",
            portfolio_id=pf,
            as_of_valid_at=VALID_AT,
            base_currency="USD",
        )
    assert _count_runs(session, tenant) == 0


def test_pre_create_refusal_missing_fx_leg(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "7.00", "EUR")  # EUR mark, NO EUR/USD rate
    session.flush()
    with pytest.raises(FxRateNotFound):
        _run(session, tenant, pf, "USD")  # FX-completeness fails closed at build
    assert _count_runs(session, tenant) == 0
    assert _count_exposure(session, tenant) == 0


def test_pre_create_refusal_incomplete_snapshot(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    inst = _inst(session, tenant, "I0")
    _pos(session, tenant, pf, inst, "100")  # a position with NO valuation mark
    session.flush()
    with pytest.raises(DataQualityError):
        _run(session, tenant, pf, "USD")  # snapshot completeness fails closed at build
    assert _count_runs(session, tenant) == 0


def test_post_create_failed_commits_failed_run_zero_rows(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "7.00", "EUR")
    _fx(session, tenant, "EUR", "USD", "1.10")
    session.flush()
    # Build a USD-base snapshot (pins EUR/USD only) ...
    built = _run(session, tenant, pf, "USD")
    snap_id = built.run.input_snapshot_id
    runs_before = _count_runs(session, tenant)
    # ... then CONSUME it requesting base JPY (no JPY legs pinned) -> post-create FAILED.
    result = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        snapshot_id=snap_id,
        base_currency="JPY",
        scope_node_id=pf,  # STRUCT-3 (DP-7)
    )
    assert result.status == RunStatus.FAILED.value
    assert result.rows == []
    assert result.run.status == RunStatus.FAILED.value
    # A FAILED run WAS created (committed evidence); ZERO new exposure rows.
    assert _count_runs(session, tenant) == runs_before + 1
    assert _count_exposure_for_run(session, result.run.run_id) == 0


def test_consume_non_exposure_input_snapshot_refused(session: Session) -> None:
    # Snapshot-gating by CONTRACT: an ADHOC snapshot with all-base-currency marks (FX identity, so
    # the FX-completeness gate cannot catch it) must STILL be refused pre-create.
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    adhoc = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose="ADHOC",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
    )
    with pytest.raises(ExposureInputError):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="v1",
            environment_id="ci",
            snapshot_id=adhoc.id,
            base_currency="USD",
        )
    assert _count_runs(session, tenant) == 0  # pre-create refusal: no run


def test_build_rows_gap_detection_missing_mark() -> None:
    # Defensive unit: a position without a mark is a gap (the gate would fail closed).
    rows, gaps = exposure_service._build_rows(
        inputs=exposure_service._PinnedInputs(
            positions={("p", "i"): Decimal("10")},
            marks={},  # no mark
            rate_map={},
            asset_classes={},
            terms={},
        ),
        base_currency="USD",
        acting_tenant="t",
        run=_FakeRun(),
        snapshot_id="s",
    )
    assert rows == []
    assert any("missing-mark" in g for g in gaps)


class _FakeRun:
    run_id = "00000000-0000-0000-0000-000000000000"


# ---------- audit ----------


def test_audit_calc_run_events_no_exposure_event(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    result = _run(session, tenant, pf, "USD")
    types = [
        e.event_type
        for e in session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == result.run.run_id)
        ).scalars()
    ]
    assert types.count("CALC.RUN_CREATE") == 1
    assert types.count("CALC.RUN_STATUS_CHANGE") == 2  # RUNNING + COMPLETED
    # NO EXPOSURE.* audit code is minted in P2-3.
    all_types = [e.event_type for e in session.execute(select(AuditEvent)).scalars()]
    assert not any(t.startswith("EXPOSURE.") for t in all_types)


def test_failed_run_emits_failure_outcome(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "100", "7.00", "EUR")
    _fx(session, tenant, "EUR", "USD", "1.10")
    session.flush()
    built = _run(session, tenant, pf, "USD")
    result = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        snapshot_id=built.run.input_snapshot_id,
        base_currency="JPY",
        scope_node_id=pf,  # STRUCT-3 (DP-7)
    )
    fail_events = [
        e
        for e in session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == result.run.run_id)
        ).scalars()
        if e.event_type == "CALC.RUN_STATUS_CHANGE" and e.outcome == "failure"
    ]
    assert len(fail_events) == 1


# ---------- lineage ----------


def test_lineage_snapshot_to_run_to_result(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    result = _run(session, tenant, pf, "USD")
    run_id = result.run.run_id
    edges = list(session.execute(select(LineageEdge)).scalars())
    dep = [e for e in edges if e.edge_kind == EDGE_KIND_DEPENDENCY]
    assert len(dep) == 1
    assert dep[0].source_type == SOURCE_TYPE_DATA_SNAPSHOT
    assert dep[0].target_entity_id == run_id
    assert dep[0].run_id == run_id  # run_id stamped on the DEPENDS_ON edge
    origin = [
        e
        for e in edges
        if e.edge_kind == EDGE_KIND_ORIGIN and e.source_type == SOURCE_TYPE_CALCULATION_RUN
    ]
    assert len(origin) == len(result.rows)
    for e in origin:
        assert e.target_entity_type == "exposure_aggregate"
        assert e.run_id == run_id  # run_id stamped on every ORIGIN edge


# ---------- append-only ----------


def test_append_only_orm_guard_blocks_update_delete(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "I0", "10", "2.00", "USD")
    session.flush()
    result = _run(session, tenant, pf, "USD")
    session.commit()
    row = result.rows[0]
    row.exposure_amount = Decimal("1.00")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    with pytest.raises(AppendOnlyViolation):
        session.delete(result.rows[0])
        session.flush()


# ---------- entitlement parity ----------


def test_exposure_permissions_grants_as_ratified() -> None:
    run_holders = {r for r, codes in ROLE_TEMPLATES.items() if "exposure.aggregate.run" in codes}
    view_holders = {r for r, codes in ROLE_TEMPLATES.items() if "exposure.view" in codes}
    assert run_holders == {"platform_admin", "data_steward", "risk_analyst_1l"}
    assert view_holders == {
        "platform_admin",
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "auditor_3l",  # INCLUDED — governed derived-output oversight
    }


# ---------- scope fences (load-bearing) ----------

_EXPOSURE_SERVICE = pathlib.Path(exposure_service.__file__).read_text(encoding="utf-8")


def test_scope_fence_no_live_input_resolvers_in_compute() -> None:
    tree = ast.parse(_EXPOSURE_SERVICE)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    forbidden = {
        "reconstruct_subtree_holdings_as_of",
        "reconstruct_position_as_of",
        "reconstruct_valuation_as_of",
        "reconstruct_fx_rate_as_of",
        "attach_marks_as_of",
        "convert",  # the live convert (compose_effective_rate is the pure path)
    }
    assert not (names & forbidden), names & forbidden
    assert not (attrs & forbidden), attrs & forbidden


def test_scope_fence_no_risk_imports_or_identifiers() -> None:
    tree = ast.parse(_EXPOSURE_SERVICE)
    # (1) No import from a risk / pricing / P3+ analytics package.
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    forbidden_pkgs = ("risk", "factor", "scenario", "pricing", "valuation_model", "stress", "var")
    for mod in imported:
        parts = set(mod.split("."))
        assert not (parts & set(forbidden_pkgs)), f"forbidden import {mod}"
    # (2) No unambiguous risk-analytics identifier (whole tokens; avoids default_factory etc.).
    idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    risk_idents = {
        "value_at_risk",
        "expected_shortfall",
        "covariance",
        "factor_model",
        "factor_return",
        "scenario_result",
        "sensitivity",
        "stress_test",
        "monte_carlo",
        "var_es",
        "pnl",
    }
    assert not (idents & risk_idents), idents & risk_idents


def test_scope_fence_mult_is_permitted() -> None:
    # The signed market-value rollup (qty x mark x fx) — ast.Mult is REQUIRED, not forbidden.
    tree = ast.parse(_EXPOSURE_SERVICE)
    assert any(isinstance(n, ast.Mult) for n in ast.walk(tree))


# ---------- migration head ----------


def test_migration_head_after_curves() -> None:
    # P2-5 advanced the head to 0020_curves (down_revision 0019_price_point); the exposure migration
    # keeps its chain position (0018_exposure_aggregate) and stays reachable in the revision walk.
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_revision("0020_curves").down_revision == "0019_price_point"
    assert "0018_exposure_aggregate" in {r.revision for r in script.walk_revisions()}


# ---------- helpers ----------


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count()).select_from(CalculationRun).where(CalculationRun.tenant_id == tenant)
    ).scalar_one()


def _count_exposure(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(ExposureAggregate)
        .where(ExposureAggregate.tenant_id == tenant)
    ).scalar_one()


def _count_exposure_for_run(db: Session, run_id: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(ExposureAggregate)
        .where(ExposureAggregate.calculation_run_id == run_id)
    ).scalar_one()


# ---------- STRUCT-1 (REQ-PPM-006): two measures, one holding ----------


def _bond(
    db: Session,
    tenant: str,
    code: str,
    *,
    face_value: str | None,
    denomination: str | None = "USD",
) -> str:
    """A bond instrument with (optionally) a terms version carrying its face value."""
    from irp_shared.reference.instrument_terms import create_instrument_terms

    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=code,
        name=code,
        asset_class="BOND",
        actor=ReferenceActor(actor_id="s"),
    ).id
    if face_value is not None or denomination is not None:
        create_instrument_terms(
            db,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=ReferenceActor(actor_id="s"),
            valid_from=T0,
            face_value=(None if face_value is None else Decimal(face_value)),
            denomination_currency=denomination,
            coupon_rate=Decimal("0.0425"),
        )
    return inst


def test_bond_holding_produces_both_measures_from_one_holding_id(session: Session) -> None:
    """THE demonstrating case of the amended row: one bond holding, a NOTIONAL exposure (face x
    qty) AND a MARKET-VALUE exposure (mark x qty), both readable from ONE holding id, both from
    the valuation path (an EXECUTED governed run over pinned components — no fixture rows), and
    the two values DIFFER because the bond is not priced at par."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    inst = _bond(session, tenant, "UST-2031", face_value="1000.0000")
    _pos(session, tenant, pf, inst, "50")
    _val(session, tenant, pf, inst, "985.40", "USD")  # off par
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.COMPLETED.value
    mine = [r for r in result.rows if r.portfolio_id == pf and r.instrument_id == inst]
    by_type = {r.exposure_type: r for r in mine}
    assert set(by_type) == {"MARKET_VALUE", "NOTIONAL"}
    assert by_type["MARKET_VALUE"].exposure_amount == Decimal("49270.000000")
    assert by_type["NOTIONAL"].exposure_amount == Decimal("50000.000000")
    assert by_type["MARKET_VALUE"].exposure_amount != by_type["NOTIONAL"].exposure_amount
    # Both rows are run-bound + snapshot-gated (the valuation path, not a fixture).
    for r in mine:
        assert r.calculation_run_id == result.run.run_id
        assert r.input_snapshot_id is not None
    # The NOTIONAL row's captured inputs keep the self-audit identity: mark_value carries the
    # per-unit FACE VALUE, mark_currency the denomination currency.
    n = by_type["NOTIONAL"]
    assert n.mark_value == Decimal("1000.0000")
    assert n.mark_currency == "USD"
    q = (n.signed_quantity * n.mark_value * n.fx_rate).quantize(_MONEY_Q, rounding=ROUND_HALF_UP)
    assert q == n.exposure_amount


def test_producer_census_exact_set_equality(session: Session) -> None:
    """REQ-PPM-006: 'checked against the producers'. EXACT set equality between the producer
    registry, the vocabulary, and the DISTINCT measures an EXECUTED run emitted — never an
    assertion over the vocabulary tuple alone."""
    from irp_shared.exposure.models import EXPOSURE_TYPES
    from irp_shared.exposure.service import EXPOSURE_PRODUCERS

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    inst = _bond(session, tenant, "CORP-2029", face_value="1000.0000")
    _pos(session, tenant, pf, inst, "25")
    _val(session, tenant, pf, inst, "1012.75", "USD")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.COMPLETED.value
    emitted = {r.exposure_type for r in result.rows}
    assert emitted == set(EXPOSURE_PRODUCERS)
    assert emitted == set(EXPOSURE_TYPES)


def test_bond_without_face_value_fails_closed(session: Session) -> None:
    """DP-4: a BOND with no face value is a DATA DEFECT — a committed FAILED run naming the gap,
    never a silent skip. (The positive control is the COMPLETED bond run above: the same book
    WITH a face value completes — P18 clause 1.)"""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    inst = create_instrument(
        session,
        tenant_id=tenant,
        code="MYSTERY-BOND",
        name="bond with no terms",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="s"),
    ).id
    _pos(session, tenant, pf, inst, "10")
    _val(session, tenant, pf, inst, "990.00", "USD")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.FAILED.value
    assert result.failure_reason and "missing-face-value" in result.failure_reason
    assert result.rows == []


def test_face_value_without_denomination_fails_closed(session: Session) -> None:
    """DP-4's missing-input case: a face value with no denomination currency cannot be converted
    — fail-closed gap, never a guessed currency."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    inst = _bond(session, tenant, "NODENOM-2030", face_value="1000.0000", denomination=None)
    _pos(session, tenant, pf, inst, "10")
    _val(session, tenant, pf, inst, "1001.00", "USD")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.FAILED.value
    assert result.failure_reason and "missing-denomination-currency" in result.failure_reason


def test_equity_without_terms_skips_notional(session: Session) -> None:
    """DP-4: NOTIONAL is defined only where a face value exists — a non-bond without terms is a
    SKIP (market value only), not a gap."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "EQ-1", "100", "12.50", "USD")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.COMPLETED.value
    assert {r.exposure_type for r in result.rows} == {"MARKET_VALUE"}


def test_notional_converts_from_denomination_currency(session: Session) -> None:
    """DP-4: the NOTIONAL leg converts from the DENOMINATION currency — exercised where the
    denomination is NOT any mark's currency (review fold F-5: a EUR-denominated bond MARKED in
    USD), so the leg is pinned ONLY because the binder unions denomination currencies into the
    FX-completeness set. Reverting that union makes this book gap missing-fx."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    inst = _bond(session, tenant, "BUND-2032", face_value="1000.0000", denomination="EUR")
    _pos(session, tenant, pf, inst, "30")
    _val(session, tenant, pf, inst, "1071.50", "USD")  # marked in USD; EUR appears ONLY via terms
    _fx(session, tenant, "EUR", "USD", "1.10")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.COMPLETED.value
    by_type = {r.exposure_type: r for r in result.rows}
    # 30 x 1000 x 1.10 = 33,000 USD (hand-derived, not a re-run of the code).
    assert by_type["NOTIONAL"].exposure_amount == Decimal("33000.000000")
    assert by_type["NOTIONAL"].mark_currency == "EUR"
    # 30 x 1071.50 = 32,145 USD — no FX leg on the mark side.
    assert by_type["MARKET_VALUE"].exposure_amount == Decimal("32145.000000")


def test_missing_denomination_fx_refuses_at_build(session: Session) -> None:
    """The P18 positive control of the union: the SAME book WITHOUT the EUR rate refuses at the
    snapshot build (FxRateNotFound, pre-create — zero run), proving the pinned leg above arrived
    because the binder demanded it, not by coincidence."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    inst = _bond(session, tenant, "BUND-2033", face_value="1000.0000", denomination="EUR")
    _pos(session, tenant, pf, inst, "30")
    _val(session, tenant, pf, inst, "1071.50", "USD")
    session.flush()  # NO EUR->USD rate captured

    with pytest.raises(FxRateNotFound):
        _run(session, tenant, pf, "USD")
    assert (
        session.execute(select(func.count()).select_from(CalculationRun)).scalar_one() == 0
    )  # pre-create refusal: zero runs


def test_terms_without_face_value_do_not_demand_fx(session: Session) -> None:
    """Review fold F-0: a terms row carrying a denomination but NO face value produces no
    NOTIONAL (DP-4 SKIP) — so its currency must NOT join the FX demand. This book has no EUR
    rate and must still COMPLETE, market-value only."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    pf = _pf(session, tenant)
    inst = _inst(session, tenant, "EQ-DEN")  # EQUITY
    from irp_shared.reference.instrument_terms import create_instrument_terms

    create_instrument_terms(
        session,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=ReferenceActor(actor_id="s"),
        valid_from=T0,
        denomination_currency="EUR",  # noted, but face_value is NULL
    )
    _pos(session, tenant, pf, inst, "100")
    _val(session, tenant, pf, inst, "12.50", "USD")
    session.flush()  # NO EUR rate exists

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.COMPLETED.value
    assert {r.exposure_type for r in result.rows} == {"MARKET_VALUE"}


def test_bond_vocabulary_variant_still_gaps(session: Session) -> None:
    """Review fold F-3: the bond-gap predicate is containment, not exact-string equality — a
    CORP_BOND without a face value fails closed rather than silently skipping."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    inst = create_instrument(
        session,
        tenant_id=tenant,
        code="CORP-VAR",
        name="corporate bond, variant vocab",
        asset_class="CORP_BOND",
        actor=ReferenceActor(actor_id="s"),
    ).id
    _pos(session, tenant, pf, inst, "10")
    _val(session, tenant, pf, inst, "990.00", "USD")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.FAILED.value
    assert result.failure_reason and "missing-face-value" in result.failure_reason


def test_face_value_over_envelope_is_a_governed_gap(session: Session) -> None:
    """Review fold F-2: instrument_terms lawfully stores 16 integer digits, mark_value holds 14 —
    an over-envelope face value must be a named governed gap, never a numeric-overflow 500."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    inst = _bond(session, tenant, "JUMBO-2040", face_value="100000000000000.0000")  # 1E14
    _pos(session, tenant, pf, inst, "1")
    _val(session, tenant, pf, inst, "990.00", "USD")
    session.flush()

    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.FAILED.value
    assert result.failure_reason and "face-value-exceeds-envelope" in result.failure_reason


def test_pre_struct1_snapshot_emits_no_notional_and_no_gap() -> None:
    """A pre-STRUCT-1 snapshot has no INSTRUMENT/INSTRUMENT_TERMS pins: the NOTIONAL measure is
    definitionally absent from its pinned inputs — the producer emits nothing and gaps nothing
    (old-run reproduction stays byte-identical; never fabricate, never refuse retroactively)."""
    rows, gaps = exposure_service._build_rows(
        inputs=exposure_service._PinnedInputs(
            positions={("p", "i"): Decimal("10")},
            marks={("p", "i"): (Decimal("99.50"), "USD")},
            rate_map={},
            asset_classes={},  # the pre-STRUCT-1 shape
            terms={},
        ),
        base_currency="USD",
        acting_tenant="t",
        run=_FakeRun(),
        snapshot_id="s",
    )
    assert gaps == []
    assert [r.exposure_type for r in rows] == ["MARKET_VALUE"]


def test_unknown_exposure_type_read_refused(session: Session) -> None:
    """The read surface refuses an unknown measure (a vocabulary error is a caller defect, not an
    empty book)."""
    from irp_shared.exposure import list_exposure_by_entity

    with pytest.raises(ExposureInputError, match="unknown exposure_type"):
        list_exposure_by_entity(
            session, acting_tenant=str(uuid.uuid4()), exposure_type="GROSS_DELTA"
        )


# ---------- STRUCT-3 (REQ-PPM-008 / DP-7 / DP-10): the node-scoped consume path ----------


def _three_level_book(db: Session, tenant: str) -> tuple[str, str, str, str]:
    """FUND -> STRATEGY -> two ACCOUNTs, positions on the leaves only. Returns
    (fund, strategy, account_a, account_b)."""
    from irp_shared.portfolio import create_portfolio

    actor = PortfolioActor(actor_id="s")
    fund = create_portfolio(
        db, tenant_id=tenant, code="FUND", name="fund", node_type="FUND", actor=actor
    ).id
    strat = create_portfolio(
        db,
        tenant_id=tenant,
        code="STRAT",
        name="strategy",
        node_type="STRATEGY",
        actor=actor,
        parent_portfolio_id=fund,
    ).id
    a = create_portfolio(
        db,
        tenant_id=tenant,
        code="ACCT-A",
        name="account a",
        node_type="ACCOUNT",
        actor=actor,
        parent_portfolio_id=strat,
    ).id
    b = create_portfolio(
        db,
        tenant_id=tenant,
        code="ACCT-B",
        name="account b",
        node_type="ACCOUNT",
        actor=actor,
        parent_portfolio_id=strat,
    ).id
    ia = _inst(db, tenant, "3L-I0")
    ib = _inst(db, tenant, "3L-I1")
    _pos(db, tenant, a, ia, "100")
    _val(db, tenant, a, ia, "12.50", "USD")
    _pos(db, tenant, b, ib, "40")
    _val(db, tenant, b, ib, "25.00", "USD")
    db.flush()
    return fund, strat, a, b


def test_full_subtree_pin_stores_the_tree_and_survives_a_middle_reparent(
    session: Session,
) -> None:
    """The run's STORED view is the pinned PORTFOLIO components: re-parent the MIDDLE node after
    the run and the captured parent map is UNCHANGED (leaf-only re-parents are explicitly
    insufficient — the row's own amendment); the grouping nodes are pinned even with no
    positions."""
    from irp_shared.portfolio import resolve_portfolio, update_portfolio
    from irp_shared.snapshot import NODE_FX_BINDING_PREDICATE, resolve_snapshot
    from irp_shared.snapshot.models import COMPONENT_KIND_PORTFOLIO

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    fund, strat, a, b = _three_level_book(session, tenant)
    other = create_portfolio(
        session,
        tenant_id=tenant,
        code="STRAT2",
        name="second strategy",
        node_type="STRATEGY",
        actor=PortfolioActor(actor_id="s"),
        parent_portfolio_id=fund,
    ).id
    session.flush()

    result = _run(session, tenant, fund, "USD")
    assert result.status == RunStatus.COMPLETED.value
    snap = resolve_snapshot(session, result.run.input_snapshot_id, acting_tenant=tenant)
    # STRUCT-4: the default EXPOSURE_INPUT predicate advanced to v3 (node-fx); the
    # full-subtree pin this test proves is carried forward unchanged.
    assert snap.binding_predicate_version == NODE_FX_BINDING_PREDICATE

    def _pinned_parents() -> dict[str, str | None]:
        comps = list_components(session, snapshot_id=snap.id, acting_tenant=tenant)
        out = {}
        for c in comps:
            if c.component_kind == COMPONENT_KIND_PORTFOLIO:
                data = json.loads(c.captured_content)
                out[data["id"]] = data["parent_portfolio_id"]
        return out

    before = _pinned_parents()
    # Grouping nodes with no positions ARE pinned: fund, strat, AND the empty second strategy.
    assert set(before) >= {str(fund).lower(), str(strat).lower(), str(other).lower()}

    # Re-parent the MIDDLE node (strategy under the other strategy) AFTER the run.
    update_portfolio(
        session,
        resolve_portfolio(session, strat, acting_tenant=tenant),
        actor=PortfolioActor(actor_id="s"),
        parent_portfolio_id=other,
    )
    session.flush()
    assert _pinned_parents() == before  # the run's stored view of the tree did not change


def test_v2_consume_without_node_refuses_and_with_node_scopes(session: Session) -> None:
    """DP-7 executed: a node-less consume on a full-subtree snapshot REFUSES (the shipped NULL
    stamp failed the node-id clause silently); a consume AT the strategy node computes ONLY its
    sub-holdings and stamps the node on the run."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    fund, strat, a, b = _three_level_book(session, tenant)
    built = _run(session, tenant, fund, "USD")
    snap_id = built.run.input_snapshot_id

    with pytest.raises(ExposureInputError, match="must name its node"):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="v1",
            environment_id="ci",
            snapshot_id=snap_id,
            base_currency="USD",
        )

    at_strat = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        snapshot_id=snap_id,
        base_currency="USD",
        scope_node_id=strat,
    )
    assert at_strat.status == RunStatus.COMPLETED.value
    assert at_strat.run.scope_portfolio_id == str(strat)  # the node id carried on the run
    # Both accounts sit under the strategy: 100x12.50 + 40x25.00, market value.
    mv = [r for r in at_strat.rows if r.exposure_type == "MARKET_VALUE"]
    assert sum(r.exposure_amount for r in mv) == Decimal("2250.000000")

    at_a = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        snapshot_id=snap_id,
        base_currency="USD",
        scope_node_id=a,
    )
    mv_a = [r for r in at_a.rows if r.exposure_type == "MARKET_VALUE"]
    assert sum(r.exposure_amount for r in mv_a) == Decimal("1250.000000")  # account A only
    # Two runs at different nodes are distinguishable from run rows alone.
    assert at_strat.run.scope_portfolio_id != at_a.run.scope_portfolio_id


def test_consume_node_refusals_fire(session: Session) -> None:
    """P9 for the two new refusals: a node OUTSIDE the pinned subtree refuses; a pinned grouping
    node with NO positions beneath refuses (DP-10 — never a zero total)."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    fund, strat, a, b = _three_level_book(session, tenant)
    empty = create_portfolio(
        session,
        tenant_id=tenant,
        code="EMPTY-S",
        name="empty strategy",
        node_type="STRATEGY",
        actor=PortfolioActor(actor_id="s"),
        parent_portfolio_id=fund,
    ).id
    session.flush()
    built = _run(session, tenant, fund, "USD")
    snap_id = built.run.input_snapshot_id

    with pytest.raises(ExposureInputError, match="not a node of the snapshot's pinned"):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="v1",
            environment_id="ci",
            snapshot_id=snap_id,
            base_currency="USD",
            scope_node_id=str(uuid.uuid4()),
        )
    with pytest.raises(ExposureInputError, match="empty (subtree|.*holds no positions)"):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="v1",
            environment_id="ci",
            snapshot_id=snap_id,
            base_currency="USD",
            scope_node_id=empty,
        )


def test_shallow_trees_run_normally(session: Session) -> None:
    """Minimum depth is a property of the TEST, never a rule applied to data: a single flat node
    with positions runs exactly as before."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    pf = _pf(session, tenant)
    _holding(session, tenant, pf, "FLAT-I", "10", "5.00", "USD")
    session.flush()
    result = _run(session, tenant, pf, "USD")
    assert result.status == RunStatus.COMPLETED.value


# ---------- STRUCT-3 (REQ-PPM-008): the rollup identity ----------


def _rollup_totals(db: Session, tenant: str, run_id: str, node: str) -> dict[str, Decimal]:
    from irp_shared.exposure.service import rollup_exposure

    return {
        r.exposure_type: r.total
        for r in rollup_exposure(db, acting_tenant=tenant, run_id=run_id, node_id=node)
    }


def test_rollup_identity_three_levels_two_node_types_per_measure(session: Session) -> None:
    """THE identity, on a tree at least three levels deep with two node types and BOTH measures
    live: the top total equals the sum of the level below it, AND the sum of the level below
    that — per exposure_type, to the last decimal (leaf rows quantized once; composition exact
    by construction)."""
    from irp_shared.portfolio import create_portfolio

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    fund, strat, a, b = _three_level_book(session, tenant)
    # A second strategy holding a BOND leaf so the NOTIONAL measure joins the identity.
    strat2 = create_portfolio(
        session,
        tenant_id=tenant,
        code="STRAT-FI",
        name="fixed income strategy",
        node_type="STRATEGY",
        actor=PortfolioActor(actor_id="s"),
        parent_portfolio_id=fund,
    ).id
    acct_c = create_portfolio(
        session,
        tenant_id=tenant,
        code="ACCT-C",
        name="account c",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
        parent_portfolio_id=strat2,
    ).id
    bond = _bond(session, tenant, "3L-UST", face_value="1000.0000")
    _pos(session, tenant, acct_c, bond, "5")
    _val(session, tenant, acct_c, bond, "985.40", "USD")
    session.flush()

    run = _run(session, tenant, fund, "USD")
    assert run.status == RunStatus.COMPLETED.value
    rid = run.run.run_id

    top = _rollup_totals(session, tenant, rid, fund)
    level1 = [_rollup_totals(session, tenant, rid, n) for n in (strat, strat2)]
    level2 = [_rollup_totals(session, tenant, rid, n) for n in (a, b, acct_c)]

    for measure in top:
        l1 = sum((d.get(measure, Decimal(0)) for d in level1), Decimal(0))
        l2 = sum((d.get(measure, Decimal(0)) for d in level2), Decimal(0))
        assert top[measure] == l1 == l2, measure
    # Both measures were genuinely in the identity (the bond emitted NOTIONAL).
    assert set(top) == {"MARKET_VALUE", "NOTIONAL"}
    assert top["NOTIONAL"] == Decimal("5000.000000")  # 5 x 1000, hand-derived
    assert top["MARKET_VALUE"] == Decimal("2250.000000") + Decimal("4927.000000")


def test_middle_node_insertion_changes_no_additive_total(session: Session) -> None:
    """Insert a NEW grouping node between the strategy and its accounts, change no holding,
    re-RUN — every contract-declared-additive total is unchanged (ratios are excluded by the
    CONTRACT: this read composes only what the operator declaration admits)."""
    from irp_shared.portfolio import create_portfolio, resolve_portfolio, update_portfolio

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    fund, strat, a, b = _three_level_book(session, tenant)
    session.flush()
    before_run = _run(session, tenant, fund, "USD")
    before = _rollup_totals(session, tenant, before_run.run.run_id, fund)

    middle = create_portfolio(
        session,
        tenant_id=tenant,
        code="MID",
        name="inserted grouping node",
        node_type="STRATEGY",
        actor=PortfolioActor(actor_id="s"),
        parent_portfolio_id=strat,
    ).id
    for leaf in (a, b):
        update_portfolio(
            session,
            resolve_portfolio(session, leaf, acting_tenant=tenant),
            actor=PortfolioActor(actor_id="s"),
            parent_portfolio_id=middle,
        )
    session.flush()

    after_run = _run(session, tenant, fund, "USD")
    after = _rollup_totals(session, tenant, after_run.run.run_id, fund)
    assert after == before  # the top's additive totals are invariant under regrouping
    # And the inserted node composes the SAME totals as its parent chain (4 levels deep now).
    at_middle = _rollup_totals(session, tenant, after_run.run.run_id, middle)
    assert at_middle == after


def test_rollup_refusals_fire(session: Session) -> None:
    """P9: a node outside the pinned subtree refuses; the contract governs the read (flip the
    operator and the rollup refuses — result obedience for the composition)."""
    from irp_shared.aggregation.contracts import (
        AGGREGATION_CONTRACTS,
        OPERATOR_NOT_AGGREGATABLE,
        NotAggregatableError,
    )
    from irp_shared.exposure.service import rollup_exposure

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    fund, strat, a, b = _three_level_book(session, tenant)
    session.flush()
    run = _run(session, tenant, fund, "USD")
    rid = run.run.run_id

    with pytest.raises(ExposureInputError, match="not in the run's pinned subtree"):
        rollup_exposure(session, acting_tenant=tenant, run_id=rid, node_id=str(uuid.uuid4()))

    import pytest as _pytest

    mp = _pytest.MonkeyPatch()
    try:
        mp.setitem(
            AGGREGATION_CONTRACTS["EXPOSURE_AGGREGATE"],
            "exposure_amount",
            OPERATOR_NOT_AGGREGATABLE,
        )
        with pytest.raises(NotAggregatableError):
            rollup_exposure(session, acting_tenant=tenant, run_id=rid, node_id=fund)
    finally:
        mp.undo()
