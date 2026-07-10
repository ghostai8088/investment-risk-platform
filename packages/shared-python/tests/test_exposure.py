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
        asset_class="BOND",
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
        positions={("p", "i"): Decimal("10")},
        marks={},  # no mark
        rate_map={},
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
    assert script.get_current_head() == "0031_portfolio_return"
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
