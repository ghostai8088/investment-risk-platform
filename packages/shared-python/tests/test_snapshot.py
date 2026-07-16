"""SQLite-local unit/behavior tests for P2-1 dataset_snapshot (reproducible input snapshot).

RLS is a no-op on SQLite (FORCE-RLS tenant isolation + the P0001 trigger live in
``test_snapshot_pg.py``); here we prove: canonical serialization determinism + close-out-marker
exclusion; physical-version pinning + ``captured_content``/``content_hash``; the ``manifest_hash``;
the governed ``build_snapshot`` (lineage edge per component, one ``SNAPSHOT.CREATE`` audit event);
the temporal-reproducibility mutation test (a bound FR valuation correction leaves the snapshot
byte-stable) and the EV portfolio drift detection; cross-tenant binding fail-closed (explicit
predicate); the completeness gate (gap + empty-scope fail closed, whole-unit rollback); the
append-only ORM guard; and the load-bearing scope fences (no quantity x mark, no ``calc`` import,
nothing imports ``snapshot``). Entitlement parity + the migration head are also pinned.
"""

from __future__ import annotations

import ast
import json
import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES
from irp_shared.lineage.models import SOURCE_TYPE_DATA_SNAPSHOT, LineageEdge
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio, update_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import (
    DatasetSnapshot,
    DatasetSnapshotComponent,
    EmptySnapshotError,
    SnapshotActor,
    SnapshotNotFound,
    SnapshotPurposeError,
    build_snapshot,
    verify_snapshot,
)
from irp_shared.snapshot import serialize as ser
from irp_shared.snapshot import service as snapshot_service
from irp_shared.valuation import correct_valuation, create_valuation, reconstruct_valuation_as_of
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
# A fixed FUTURE knowledge cutoff: deterministic (manifest stability) AND always >= the wall-clock
# ``system_from`` the binders stamp at seed time, so the as-known reconstruction sees the rows.
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 3, 31)
ACTOR = SnapshotActor(actor_id="steward")


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


def _inst(db: Session, tenant: str, code: str) -> str:
    return create_instrument(
        db,
        tenant_id=tenant,
        code=code,
        name="i",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="steward"),
    ).id


def _pf(db: Session, tenant: str, code: str, parent: str | None = None) -> str:
    return create_portfolio(
        db,
        tenant_id=tenant,
        code=code,
        name=code.lower(),
        node_type="ACCOUNT",
        parent_portfolio_id=parent,
        actor=PortfolioActor(actor_id="steward"),
    ).id


def _pos(db: Session, tenant: str, pf: str, inst: str, qty: str):  # noqa: ANN202
    return create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="steward"),
        quantity=Decimal(qty),
        valid_from=T0,
    )


def _val(db: Session, tenant: str, pf: str, inst: str, mark: str):  # noqa: ANN202
    return create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="steward"),
        mark_value=Decimal(mark),
        valid_from=T0,
    )


def _seed_complete(db: Session) -> tuple[str, str]:
    """A complete tenant: 1 portfolio, 2 instruments, 2 positions, 2 valuations (all marked).
    Returns ``(tenant_id, portfolio_id)``."""
    tenant = str(uuid.uuid4())
    pf = _pf(db, tenant, "ACCT-1")
    for n, (qty, mark) in enumerate([("100", "12.50"), ("-200", "7.00")]):
        inst = _inst(db, tenant, f"INST-{n}")
        _pos(db, tenant, pf, inst, qty)
        _val(db, tenant, pf, inst, mark)
    db.flush()
    return tenant, pf


# ---------- canonical serialization ----------


def test_serialize_determinism_and_decimal_scale(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    pos = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    comps = (
        session.execute(
            select(DatasetSnapshotComponent).where(DatasetSnapshotComponent.snapshot_id == pos.id)
        )
        .scalars()
        .all()
    )
    for c in comps:
        # captured_content round-trips to the same hash deterministically.
        assert ser.content_hash(c.captured_content) == c.content_hash
        # close-out markers are excluded from the captured content.
        assert "valid_to" not in c.captured_content and "system_to" not in c.captured_content


def test_decimal_normalization_is_scale_stable() -> None:
    assert ser._norm_decimal(Decimal("100"), 8) == "100.00000000"
    assert ser._norm_decimal(Decimal("100.0"), 8) == "100.00000000"  # 100 and 100.0 alias
    assert ser._norm_decimal(Decimal("-200"), 8) == "-200.00000000"


def test_decimal_normalization_quantizes_half_up() -> None:
    # Sub-scale precision is quantized HALF_UP (matching PG numeric storage), so build-time
    # (in-memory) and verify-time (engine-roundtripped) hash the same value — not Python's default
    # ROUND_HALF_EVEN ("100.00000000" would stay, but a half-way digit must round AWAY from zero).
    assert ser._norm_decimal(Decimal("0.0000005"), 6) == "0.000001"
    assert ser._norm_decimal(Decimal("1.123456785"), 8) == "1.12345679"
    assert ser._norm_decimal(Decimal("-0.0000005"), 6) == "-0.000001"


def test_guid_lowercased_and_datetime_utc() -> None:
    assert ser._norm_guid("ABCDEF") == "abcdef"
    assert ser._norm_datetime(datetime(2026, 1, 1)).endswith("+00:00")  # naive -> UTC


# ---------- build + manifest ----------


def test_build_snapshot_components_and_manifest(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    header = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="EXPOSURE_INPUT",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    session.commit()
    # 2 positions + 2 valuations + 1 portfolio = 5 components.
    assert header.component_count == 5
    assert len(header.manifest_hash) == 64
    kinds = sorted(
        c.component_kind
        for c in session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == header.id
            )
        )
        .scalars()
        .all()
    )
    assert kinds == ["PORTFOLIO", "POSITION", "POSITION", "VALUATION", "VALUATION"]
    # No status / no model_version columns exist on the header.
    assert not hasattr(header, "status") and not hasattr(header, "model_version_id")


def test_manifest_hash_deterministic_on_rebuild(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    kw = dict(
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    h1 = build_snapshot(session, **kw).manifest_hash
    h2 = build_snapshot(session, **kw).manifest_hash  # same pinned cutoffs -> identical
    assert h1 == h2


def test_pinned_system_from_null_for_portfolio(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    header = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    pf_comp = session.execute(
        select(DatasetSnapshotComponent).where(
            DatasetSnapshotComponent.snapshot_id == header.id,
            DatasetSnapshotComponent.component_kind == "PORTFOLIO",
        )
    ).scalar_one()
    assert pf_comp.pinned_system_from is None  # EV has no system axis
    assert pf_comp.pinned_record_version is not None  # the authoritative EV drift discriminator


# ---------- lineage + audit ----------


def test_lineage_edge_per_component(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    header = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    edges = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_DATA_SNAPSHOT,
                LineageEdge.source_id == header.id,
            )
        )
        .scalars()
        .all()
    )
    assert len(edges) == header.component_count
    assert all(e.tenant_id == tenant for e in edges)


def test_one_snapshot_create_audit_event(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    header = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "SNAPSHOT.CREATE", AuditEvent.entity_id == header.id
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    # DC-2 metadata only — the captured payloads are NOT in the audit after_value.
    assert "captured_content" not in str(events[0].after_value)


# ---------- temporal reproducibility (FR) + EV drift ----------


def test_verify_stable_under_fr_correction(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    header = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    session.commit()
    # As-known correct a bound valuation (a NEW version; the OLD row's content is immutable).
    val_comp = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == header.id,
                DatasetSnapshotComponent.component_kind == "VALUATION",
            )
        )
        .scalars()
        .first()
    )
    from irp_shared.valuation import resolve_valuation

    old = resolve_valuation(session, val_comp.target_entity_id, acting_tenant=tenant)
    correct_valuation(
        session,
        old,
        restatement_reason="fix",
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="steward"),
        mark_value=Decimal("999.99"),
    )
    session.commit()
    # The snapshot still pins the ORIGINAL version byte-identically.
    result = verify_snapshot(session, snapshot_id=header.id, acting_tenant=tenant)
    assert result.ok and result.drifted_components == []
    # The live current mark is the corrected value (the contrast).
    live = reconstruct_valuation_as_of(
        session,
        acting_tenant=tenant,
        portfolio_id=old.portfolio_id,
        instrument_id=old.instrument_id,
        valuation_date=VD,
        valid_at=VALID_AT,
    )
    assert live is not None and live.mark_value == Decimal("999.99")


def test_verify_stable_under_fr_position_correction(session: Session) -> None:
    # Plan §17 mutation test, POSITION branch (the valuation branch is covered above): an as-known
    # position correction is a NEW physical version; the snapshot pins the ORIGINAL by id, so verify
    # stays byte-stable while the live reconstruct reflects the corrected quantity.
    from irp_shared.position import correct_position, resolve_position

    tenant, pf = _seed_complete(session)
    header = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    session.commit()
    pos_comp = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == header.id,
                DatasetSnapshotComponent.component_kind == "POSITION",
            )
        )
        .scalars()
        .first()
    )
    old = resolve_position(session, pos_comp.target_entity_id, acting_tenant=tenant)
    orig_qty = old.quantity
    assert orig_qty != Decimal("12345")  # the correction genuinely changes the value
    correct_position(
        session,
        old,
        restatement_reason="fix",
        acting_tenant=tenant,
        actor=PositionActor(actor_id="steward"),
        quantity=Decimal("12345"),
    )
    session.commit()
    result = verify_snapshot(session, snapshot_id=header.id, acting_tenant=tenant)
    assert result.ok and result.drifted_components == []  # pinned original version unchanged
    # The OLD physical version's content is immutable (FR close-out, not in-place edit).
    assert resolve_position(session, old.id, acting_tenant=tenant).quantity == orig_qty


def test_verify_reports_ev_portfolio_drift(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    header = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    session.commit()
    from irp_shared.portfolio import resolve_portfolio

    node = resolve_portfolio(session, pf, acting_tenant=tenant)
    update_portfolio(session, node, actor=PortfolioActor(actor_id="steward"), name="renamed")
    session.commit()
    n_before = session.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    result = verify_snapshot(session, snapshot_id=header.id, acting_tenant=tenant)
    assert not result.ok and len(result.drifted_components) == 1  # the portfolio component drifted
    # verify emits ZERO audit events even on the drift branch (OD-023 no-emit-on-read).
    assert session.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == n_before


# ---------- RD-3 OD-A: widened except-tuple regression (drift, not raise) ----------
#
# ``verify_snapshot``'s except-tuple was widened (service.py, ``verify_snapshot``) to additionally
# catch ``ScenarioSnapshotError``/``ProxyWeightSnapshotError`` (a gone pinned row on those
# families) plus ``KeyError``/``TypeError``/``ValueError``/``ArithmeticError`` (a malformed
# ``captured_content`` on any series/composite branch that does ``json.loads`` + keyed access).
# Every test below proves BOTH that ``result.ok is False`` with the component id in
# ``drifted_components`` AND that ``verify_snapshot`` itself does not raise.


def test_verify_reports_drift_on_gone_scenario_shock_row(session: Session) -> None:
    """A gone ``scenario_shock`` row -> ``ScenarioSnapshotError`` inside the SCENARIO branch of
    ``_reresolve_content`` -> the widened except-tuple reports drift, not an unhandled raise."""
    from test_scenario import _run as _scenario_run
    from test_scenario import _scenario as _make_scenario
    from test_scenario import _seed_factor_exposure_run

    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _make_scenario(session, t, fid_usd, fid_eur)
    result = _scenario_run(session, t, fx_run, def_id)
    snap_id = result.run.input_snapshot_id
    session.commit()
    assert verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t).ok is True

    scen_comp = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == snap_id,
                DatasetSnapshotComponent.component_kind == "SCENARIO",
            )
        )
        .scalars()
        .first()
    )
    assert scen_comp is not None
    # A raw-SQL DELETE bypasses the ORM append-only guard (``before_delete`` only fires on an
    # ORM-tracked flush) — simulating the pinned shock row genuinely being gone, not exercising the
    # guard itself (the guard is already covered by ``test_append_only_orm_guard``).
    session.execute(
        text("DELETE FROM scenario_shock WHERE id = :id"), {"id": scen_comp.target_entity_id}
    )
    session.commit()
    session.expire_all()

    result2 = verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t)  # must not raise
    assert result2.ok is False
    assert scen_comp.id in result2.drifted_components


def test_verify_reports_drift_on_gone_desmoothed_return_row(session: Session) -> None:
    """A gone ``desmoothed_return_result`` row -> ``ProxyWeightSnapshotError`` inside the
    DESMOOTHED_RETURN branch of ``_reresolve_content`` (a PROXY_WEIGHT_INPUT snapshot pins the
    consumed desmoothed run's per-period rows) -> drift, not an unhandled raise."""
    from test_proxy_weight import _desmoothed_run, _factor, _factor_returns, _proxy_model

    from irp_shared.risk import ProxyWeightEstimateActor, run_proxy_weight_estimate

    t = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, t)
    fx_usd = _factor(session, t, "FX_USD")
    fx_eur = _factor(session, t, "FX_EUR")
    _factor_returns(session, t, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, t, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    out = run_proxy_weight_estimate(
        session,
        acting_tenant=t,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_proxy_model(session, t),
        desmoothed_run_id=run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    snap_id = out.run.input_snapshot_id
    session.commit()
    assert verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t).ok is True

    dr_comp = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == snap_id,
                DatasetSnapshotComponent.component_kind == "DESMOOTHED_RETURN",
            )
        )
        .scalars()
        .first()
    )
    assert dr_comp is not None
    session.execute(
        text("DELETE FROM desmoothed_return_result WHERE id = :id"),
        {"id": dr_comp.target_entity_id},
    )
    session.commit()
    session.expire_all()

    result2 = verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t)  # must not raise
    assert result2.ok is False
    assert dr_comp.id in result2.drifted_components


def test_verify_reports_drift_on_malformed_scenario_pin(session: Session) -> None:
    """A truncated (non-parseable) ``captured_content`` on a SCENARIO component -> ``json.loads``
    raises ``json.JSONDecodeError`` (a ``ValueError`` subclass) inside ``_reresolve_content`` ->
    drift, not a raw 500. SCENARIO is the newest/highest-risk composite branch (P3-6)."""
    from test_scenario import _run as _scenario_run
    from test_scenario import _scenario as _make_scenario
    from test_scenario import _seed_factor_exposure_run

    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _make_scenario(session, t, fid_usd, fid_eur)
    result = _scenario_run(session, t, fx_run, def_id)
    snap_id = result.run.input_snapshot_id
    session.commit()

    scen_comp = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == snap_id,
                DatasetSnapshotComponent.component_kind == "SCENARIO",
            )
        )
        .scalars()
        .first()
    )
    assert scen_comp is not None
    # A raw-SQL UPDATE bypasses the ORM append-only guard — simulating storage-layer corruption of
    # the pinned JSON blob (truncated mid-object), not exercising the guard itself.
    session.execute(
        text("UPDATE dataset_snapshot_component SET captured_content = :c WHERE id = :id"),
        {"c": '{"scenario_definition_id": "abc", "shock_valu', "id": scen_comp.id},
    )
    session.commit()
    session.expire_all()

    result2 = verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t)  # must not raise
    assert result2.ok is False
    assert scen_comp.id in result2.drifted_components


def test_verify_reports_drift_on_malformed_factor_return_pin(session: Session) -> None:
    """A well-formed JSON object MISSING the required ``"rows"`` key on a FACTOR_RETURN component
    (the proxy-weight candidate-factor return window) -> ``KeyError`` on ``pinned["rows"]`` inside
    ``_reresolve_content`` -> drift, not a raw 500. Proves the except-tuple widening generalizes
    beyond the two new exception classes to malformed ``captured_content`` on a DIFFERENT composite
    branch than SCENARIO."""
    from test_proxy_weight import _desmoothed_run, _factor, _factor_returns, _proxy_model

    from irp_shared.risk import ProxyWeightEstimateActor, run_proxy_weight_estimate

    t = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, t)
    fx_usd = _factor(session, t, "FX_USD")
    fx_eur = _factor(session, t, "FX_EUR")
    _factor_returns(session, t, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, t, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    out = run_proxy_weight_estimate(
        session,
        acting_tenant=t,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_proxy_model(session, t),
        desmoothed_run_id=run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    snap_id = out.run.input_snapshot_id
    session.commit()

    fr_comp = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == snap_id,
                DatasetSnapshotComponent.component_kind == "FACTOR_RETURN",
            )
        )
        .scalars()
        .first()
    )
    assert fr_comp is not None
    pinned = json.loads(fr_comp.captured_content)
    del pinned["rows"]  # syntactically valid JSON, missing the key ``_reresolve_content`` needs
    session.execute(
        text("UPDATE dataset_snapshot_component SET captured_content = :c WHERE id = :id"),
        {"c": json.dumps(pinned), "id": fr_comp.id},
    )
    session.commit()
    session.expire_all()

    result2 = verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t)  # must not raise
    assert result2.ok is False
    assert fr_comp.id in result2.drifted_components


def test_verify_reports_drift_on_non_object_scenario_pin(session: Session) -> None:
    """A syntactically valid but non-object ``captured_content`` (a JSON array) on a SCENARIO
    component -> ``pinned["scenario_definition_id"]`` raises ``TypeError`` (list indices must be
    integers, not str) inside ``_parsed_pin`` -> drift, not a raw 500. The "non-object" malformed
    shape named in the decision record (rd_3_decision_record.md Part 3 step 1), distinct from the
    truncated-JSON and missing-key shapes already covered above."""
    from test_scenario import _run as _scenario_run
    from test_scenario import _scenario as _make_scenario
    from test_scenario import _seed_factor_exposure_run

    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _make_scenario(session, t, fid_usd, fid_eur)
    result = _scenario_run(session, t, fx_run, def_id)
    snap_id = result.run.input_snapshot_id
    session.commit()

    scen_comp = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == snap_id,
                DatasetSnapshotComponent.component_kind == "SCENARIO",
            )
        )
        .scalars()
        .first()
    )
    assert scen_comp is not None
    session.execute(
        text("UPDATE dataset_snapshot_component SET captured_content = :c WHERE id = :id"),
        {"c": "[1, 2, 3]", "id": scen_comp.id},
    )
    session.commit()
    session.expire_all()

    result2 = verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t)  # must not raise
    assert result2.ok is False
    assert scen_comp.id in result2.drifted_components


def test_verify_reports_drift_on_malformed_benchmark_return_pin(session: Session) -> None:
    """A well-formed JSON object MISSING the required ``"rows"`` key on a BENCHMARK_RETURN
    component -> ``KeyError`` inside ``_parsed_pin`` -> drift, not a raw 500. BENCHMARK_RETURN is
    the fourth (and last untested) composite branch that parses ``captured_content``."""
    from test_benchmark_relative import D0, D1, D2, TENANT, _return_run
    from test_benchmark_relative import _bench_return as _bm_return
    from test_benchmark_relative import _benchmark as _make_benchmark
    from test_benchmark_relative import _model as _br_model
    from test_benchmark_relative import _run as _br_run

    run_id, _pf = _return_run(session, [(D0, "1000000"), (D1, "1030000"), (D2, "1019700")])
    bm = _make_benchmark(session)
    _bm_return(session, bm, D1, "0.025")
    _bm_return(session, bm, D2, "0.005")
    mv = _br_model(session)
    result = _br_run(session, run_id, bm.id, mv)
    snap_id = result.run.input_snapshot_id
    session.commit()

    br_comp = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == snap_id,
                DatasetSnapshotComponent.component_kind == "BENCHMARK_RETURN",
            )
        )
        .scalars()
        .first()
    )
    assert br_comp is not None
    pinned = json.loads(br_comp.captured_content)
    del pinned["rows"]
    session.execute(
        text("UPDATE dataset_snapshot_component SET captured_content = :c WHERE id = :id"),
        {"c": json.dumps(pinned), "id": br_comp.id},
    )
    session.commit()
    session.expire_all()

    result2 = verify_snapshot(session, snapshot_id=snap_id, acting_tenant=TENANT)  # must not raise
    assert result2.ok is False
    assert br_comp.id in result2.drifted_components


# ---------- fail-closed gates ----------


def test_completeness_gap_fails_closed_no_partial(session: Session) -> None:
    tenant = str(uuid.uuid4())
    pf = _pf(session, tenant, "ACCT-1")
    inst = _inst(session, tenant, "INST-0")
    _pos(session, tenant, pf, inst, "100")  # a non-zero position with NO mark -> a gap
    session.flush()
    with pytest.raises(DataQualityError):
        build_snapshot(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            purpose="TEST",
            portfolio_id=pf,
            as_of_valid_at=VALID_AT,
            as_of_known_at=KNOWN_AT,
            as_of_valuation_date=VD,
        )
    session.rollback()
    # Whole-unit rollback (CTRL-032): NO snapshot, NO component, NO snapshot-sourced lineage edge,
    # NO SNAPSHOT.CREATE event. The lineage assertion is the load-bearing one — edges are FLUSHED
    # (step 6) BEFORE the completeness gate raises (step 7), so this proves they rolled back (not
    # merely that they were never written, which is the case for the post-gate audit event).
    assert session.execute(select(DatasetSnapshot)).first() is None
    assert session.execute(select(DatasetSnapshotComponent)).first() is None
    assert (
        session.execute(
            select(LineageEdge).where(LineageEdge.source_type == SOURCE_TYPE_DATA_SNAPSHOT)
        ).first()
        is None
    )
    assert (
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == "SNAPSHOT.CREATE")
        ).first()
        is None
    )


def test_empty_scope_fails_closed(session: Session) -> None:
    tenant = str(uuid.uuid4())
    pf = _pf(session, tenant, "EMPTY")  # a portfolio with no positions
    session.flush()
    with pytest.raises(EmptySnapshotError):
        build_snapshot(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            purpose="TEST",
            portfolio_id=pf,
            as_of_valid_at=VALID_AT,
            as_of_known_at=KNOWN_AT,
            as_of_valuation_date=VD,
        )


def test_cross_tenant_binding_fails_closed(session: Session) -> None:
    from irp_shared.portfolio import PortfolioNotVisible

    _t, pf = _seed_complete(session)
    foreign = str(uuid.uuid4())  # a different tenant cannot bind tenant A's portfolio
    with pytest.raises(PortfolioNotVisible):
        build_snapshot(
            session,
            acting_tenant=foreign,
            actor=ACTOR,
            purpose="TEST",
            portfolio_id=pf,
            as_of_valid_at=VALID_AT,
            as_of_known_at=KNOWN_AT,
            as_of_valuation_date=VD,
        )


def test_invalid_purpose_rejected(session: Session) -> None:
    _t, pf = _seed_complete(session)
    with pytest.raises(SnapshotPurposeError):
        build_snapshot(
            session,
            acting_tenant=_t,
            actor=ACTOR,
            purpose="BOGUS",
            portfolio_id=pf,
            as_of_valid_at=VALID_AT,
        )


def test_unknown_snapshot_not_found(session: Session) -> None:
    with pytest.raises(SnapshotNotFound):
        verify_snapshot(session, snapshot_id=str(uuid.uuid4()), acting_tenant=str(uuid.uuid4()))


# ---------- append-only ----------


def test_append_only_orm_guard(session: Session) -> None:
    tenant, pf = _seed_complete(session)
    header = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        purpose="TEST",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    session.commit()
    header.label = "mutated"
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    comp = session.execute(select(DatasetSnapshotComponent)).scalars().first()
    session.delete(comp)
    with pytest.raises(AppendOnlyViolation):
        session.flush()


# ---------- scope fences ----------

_SNAPSHOT_SRC = pathlib.Path(snapshot_service.__file__).parent


def test_snapshot_computes_no_product_no_calc_import() -> None:
    """The snapshot package multiplies nothing (no quantity x mark) and imports no ``calc`` symbol —
    readiness never becomes wiring; reproducibility infrastructure, not analytics."""
    for path in (_SNAPSHOT_SRC / "service.py", _SNAPSHOT_SRC / "serialize.py"):
        tree = ast.parse(path.read_text())
        mults = [
            n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult)
        ]
        assert not mults, f"{path.name} multiplies (possible quantity x mark)"
    for path in _SNAPSHOT_SRC.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "calc" not in node.module.split("."), f"{path.name} imports calc"
                # P3-3: the ONLY sanctioned exposure import is the FUNCTION-LOCAL, models-only
                # atom read in service.py (module-level would be a circular import — the exposure
                # SERVICE imports snapshot; empirically verified in the 2026-07 review).
                if "exposure" in node.module.split("."):
                    assert (
                        path.name == "service.py"
                        and node.module == "irp_shared.exposure.models"
                        and node.col_offset > 0
                    ), (
                        f"{path.name} imports {node.module} — only a function-local "
                        f"irp_shared.exposure.models import in service.py is sanctioned"
                    )
                # PM-1: the ONLY sanctioned transaction import is the same function-local,
                # models-only read in service.py (build_return_snapshot pins in-window txns; the
                # transaction SERVICE is never imported — the exposure.models precedent).
                if "transaction" in node.module.split("."):
                    assert (
                        path.name == "service.py"
                        and node.module == "irp_shared.transaction.models"
                        and node.col_offset > 0
                    ), (
                        f"{path.name} imports {node.module} — only a function-local "
                        f"irp_shared.transaction.models import in service.py is sanctioned"
                    )
            if isinstance(node, ast.Import):
                assert all("calc" not in a.name.split(".") for a in node.names)
                assert all(
                    "exposure" not in a.name.split(".") for a in node.names
                ), f"{path.name} imports an exposure module wholesale"
                assert all(
                    "transaction" not in a.name.split(".") for a in node.names
                ), f"{path.name} imports a transaction module wholesale"


def test_nothing_imports_snapshot() -> None:
    """``snapshot`` is a leaf: no other ``irp_shared`` package imports it at runtime, EXCEPT the
    central ``models.py`` aggregator (every model) and the run consumers ``exposure`` (P2-3) +
    ``risk`` (P3-1) + ``perf`` (PM-1 — builds the RETURN_INPUT snapshot + reads its pinned
    components) — which read the bound snapshot's pinned components + build the curve snapshot
    (the AD-014 single-bind) — and ``demo`` (MG-1: the campaign runner orchestrates the real
    consume-existing paths from ABOVE every domain, like the apps layer; nothing imports it)."""
    root = pathlib.Path(snapshot_service.__file__).parents[1]
    for path in root.rglob("*.py"):
        if (
            "snapshot" in path.parts
            or "exposure" in path.parts
            or "risk" in path.parts
            or "perf" in path.parts
            or "demo" in path.parts
            or path.name == "models.py"
        ):
            continue
        text = path.read_text()
        assert "import irp_shared.snapshot" not in text, path
        assert "from irp_shared.snapshot" not in text, path


# ---------- entitlement parity ----------


def test_snapshot_permissions_grants_as_ratified() -> None:
    view_holders = {r for r, codes in ROLE_TEMPLATES.items() if "snapshot.view" in codes}
    create_holders = {r for r, codes in ROLE_TEMPLATES.items() if "snapshot.create" in codes}
    assert view_holders == {"data_steward", "risk_analyst_1l", "risk_manager_2l", "platform_admin"}
    assert create_holders == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in view_holders and "auditor_3l" not in create_holders


# ---------- migration head ----------


def test_migration_0016_chain_position() -> None:
    # 0016 (dataset_snapshot) sits immediately above 0015; the HEAD advances each slice (P2-2 added
    # 0017_fx_rate), so this guards 0016's fixed chain position, not that it is still the head.
    from alembic.script import ScriptDirectory

    root = pathlib.Path(snapshot_service.__file__)
    while not (root / "alembic.ini").exists():  # walk up to the repo root (CWD-independent)
        assert root != root.parent, "alembic.ini not found"
        root = root.parent
    script = ScriptDirectory(str(root / "migrations"))
    rev = script.get_revision("0016_dataset_snapshot")
    assert rev.down_revision == "0015_valuation"
    assert "0016_dataset_snapshot" in {r.revision for r in script.walk_revisions()}
