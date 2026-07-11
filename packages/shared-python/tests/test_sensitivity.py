"""SQLite-local unit/behavior tests for P3-1 sensitivities (the first governed RISK number,
ENT-028).

RLS is a no-op on SQLite (FORCE-RLS isolation + the P0001 trigger live in
``test_sensitivity_pg.py``);
here we prove: the pure analytic kernel (DV01 = -T*DF*1bp; ACT/365F; continuous compounding; 1bp;
HALF_UP@12; PAR_RATE rejected); the model-governance hardening (registered model_version required;
``assert_registered_model_version`` fail-closed pre-create ⇒ zero run/rows; methodology_ref
mandatory;
assumptions/limitations recorded); the curve-snapshot pinning + snapshot-only compute (no live
read;
reproducible-under-correction); CALC.RUN_* audit (+ NO RISK.* code); lineage snapshot->run
(DEPENDS_ON) + run->result (ORIGIN); fail-closed DQ; the append-only ORM guard; entitlement parity;
the methodology doc; the load-bearing scope fences; and the migration head.
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
from irp_shared.lineage.models import (
    EDGE_KIND_DEPENDENCY,
    EDGE_KIND_ORIGIN,
    SOURCE_TYPE_CALCULATION_RUN,
    SOURCE_TYPE_DATA_SNAPSHOT,
    LineageEdge,
)
from irp_shared.marketdata import CurveActor, CurveNode, capture_curve, correct_curve, resolve_curve
from irp_shared.model.models import ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.model.service import UnregisteredModelError
from irp_shared.models import Base
from irp_shared.reference.models import Currency
from irp_shared.risk import (
    SENSITIVITY_TYPE_DV01,
    SENSITIVITY_TYPE_SPREAD_DV01,
    SensitivityActor,
    SensitivityInputError,
    SensitivityResult,
    list_sensitivities,
    register_sensitivity_model,
    run_sensitivities,
)
from irp_shared.risk import kernel as risk_kernel
from irp_shared.risk import service as risk_service
from irp_shared.risk.bootstrap import (
    SENSITIVITY_ASSUMPTIONS,
    SENSITIVITY_LIMITATIONS,
    SENSITIVITY_METHODOLOGY_REF,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_CURVE,
    SNAPSHOT_COMPONENT_KINDS,
    CurveSelector,
    CurveSnapshotError,
    list_components,
)
from irp_shared.snapshot.models import PURPOSE_SENSITIVITY_INPUT

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
CD = date(2026, 6, 1)
ACTOR = SensitivityActor(actor_id="analyst")
SRC = "VENDOR_X"
_Q12 = Decimal("0.000000000001")


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


def _curve(
    db: Session,
    tenant: str,
    *,
    curve_type: str = "SWAP",
    ccy: str = "USD",
    nodes: list[CurveNode],
    reference_key: str = "NONE",
    source: str = SRC,
) -> str:
    return capture_curve(
        db,
        curve_type=curve_type,
        currency_code=ccy,
        curve_date=CD,
        curve_source=source,
        nodes=nodes,
        acting_tenant=tenant,
        actor=CurveActor(actor_id="s"),
        reference_key=reference_key,
        valid_from=T0,
    ).id


def _model(db: Session, tenant: str, code_version: str = "risk-v1") -> str:
    return register_sensitivity_model(
        db, tenant_id=tenant, actor_id="analyst", code_version=code_version
    ).id


def _sel(
    *, curve_type: str = "SWAP", ccy: str = "USD", reference_key: str = "NONE", source: str = SRC
) -> CurveSelector:
    return CurveSelector(
        curve_type=curve_type,
        currency_code=ccy,
        curve_date=CD,
        curve_source=source,
        reference_key=reference_key,
    )


def _zero_nodes() -> list[CurveNode]:
    return [
        CurveNode(
            tenor_label="1Y", tenor_days=365, value_type="ZERO_RATE", point_value=Decimal("0.05")
        ),
        CurveNode(
            tenor_label="2Y", tenor_days=730, value_type="ZERO_RATE", point_value=Decimal("0.06")
        ),
    ]


def _run(db: Session, tenant: str, mv: str, selectors: list[CurveSelector], **kw):  # noqa: ANN202
    return run_sensitivities(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        curve_selectors=selectors,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        **kw,
    )


# ---------- (3) kernel ----------


def test_kernel_zero_rate_dv01() -> None:
    # DV01 = -T * exp(-z*T) * 1bp; 1Y 5% -> -1 * e^-0.05 * 0.0001 = -0.0000951229424...
    val = risk_kernel.node_dv01(365, "ZERO_RATE", Decimal("0.05"))
    assert val == Decimal("-0.000095122942")


def test_kernel_discount_factor_dv01_uses_df_directly() -> None:
    # DF used directly: 2Y DF 0.90 -> -2 * 0.90 * 0.0001 = -0.000180000000 (no implied zero).
    val = risk_kernel.node_dv01(730, "DISCOUNT_FACTOR", Decimal("0.90"))
    assert val == Decimal("-0.000180000000")


def test_kernel_spread_dv01() -> None:
    # 5Y SPREAD 1% -> -5 * e^-0.05 * 0.0001.
    val = risk_kernel.node_spread_dv01(1825, Decimal("0.01"))
    assert val == Decimal("-0.000475614712")


def test_kernel_act365f_year_fraction() -> None:
    # 730 days -> T = 2.0 exactly (ACT/365F): DF curve at DF=1.0 -> -2*1*0.0001 = -0.0002.
    assert risk_kernel.node_dv01(730, "DISCOUNT_FACTOR", Decimal("1")) == Decimal("-0.000200000000")


def test_kernel_par_rate_rejected() -> None:
    with pytest.raises(risk_kernel.SensitivityKernelError):
        risk_kernel.node_dv01(365, "PAR_RATE", Decimal("0.05"))


def test_kernel_non_positive_tenor_rejected() -> None:
    with pytest.raises(risk_kernel.SensitivityKernelError):
        risk_kernel.node_dv01(0, "ZERO_RATE", Decimal("0.05"))


def test_kernel_quantizes_half_up_12dp() -> None:
    val = risk_kernel.node_dv01(365, "ZERO_RATE", Decimal("0.05"))
    assert -val == (-val).quantize(_Q12)  # exactly 12dp, no excess precision


# ---------- (2) model governance ----------


def test_model_and_version_registered_with_methodology(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None
    assert version.methodology_ref == SENSITIVITY_METHODOLOGY_REF  # mandatory, set
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
    assert len(assumptions) == len(SENSITIVITY_ASSUMPTIONS)
    assert len(limitations) == len(SENSITIVITY_LIMITATIONS)


def test_register_is_idempotent(session: Session) -> None:
    tenant = str(uuid.uuid4())
    first = _model(session, tenant)
    second = _model(session, tenant)
    assert first == second  # resolve-or-register; no duplicate inventory


def test_unregistered_model_version_refused_pre_create_zero_run_zero_rows(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    session.flush()
    with pytest.raises(UnregisteredModelError):
        _run(session, tenant, str(uuid.uuid4()), [_sel()])  # a never-registered version id
    assert _count_runs(session, tenant) == 0  # pre-create refusal: no run
    assert _count_results(session, tenant) == 0


def test_missing_model_version_id_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    session.flush()
    with pytest.raises(SensitivityInputError):
        run_sensitivities(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id="",
            curve_selectors=[_sel()],
            as_of_valid_at=VALID_AT,
            as_of_known_at=KNOWN_AT,
        )
    assert _count_runs(session, tenant) == 0


# ---------- (3+) positive correctness via the binder ----------


def test_run_produces_dv01_rows_bound_to_run_snapshot_model(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel()])
    assert result.status == RunStatus.COMPLETED.value
    assert len(result.rows) == 2
    by_tenor = {r.tenor_label: r for r in result.rows}
    assert by_tenor["1Y"].sensitivity_value == Decimal("-0.000095122942")
    for r in result.rows:
        assert r.sensitivity_type == SENSITIVITY_TYPE_DV01
        assert r.calculation_run_id == result.run.run_id
        assert r.input_snapshot_id == result.run.input_snapshot_id
        assert r.model_version_id == mv  # model-bound
        assert r.bump_bps == Decimal("1.0000")


def test_spread_curve_produces_spread_dv01(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(
        session,
        tenant,
        curve_type="CREDIT_SPREAD",
        reference_key="ACME:BBB",
        nodes=[
            CurveNode(
                tenor_label="5Y", tenor_days=1825, value_type="SPREAD", point_value=Decimal("0.01")
            )
        ],
    )
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel(curve_type="CREDIT_SPREAD", reference_key="ACME:BBB")])
    (row,) = result.rows
    assert row.sensitivity_type == SENSITIVITY_TYPE_SPREAD_DV01
    assert row.sensitivity_value == Decimal("-0.000475614712")


# ---------- (4) snapshot pinning + reproducibility ----------


def test_component_kind_curve_minted() -> None:
    assert COMPONENT_KIND_CURVE == "CURVE"
    assert COMPONENT_KIND_CURVE in SNAPSHOT_COMPONENT_KINDS


def test_snapshot_is_sensitivity_input_and_pins_curve(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel()])
    from irp_shared.snapshot import resolve_snapshot

    snap = resolve_snapshot(session, result.run.input_snapshot_id, acting_tenant=tenant)
    assert snap.purpose == PURPOSE_SENSITIVITY_INPUT
    comps = list_components(session, snapshot_id=snap.id, acting_tenant=tenant)
    curve_comps = [c for c in comps if c.component_kind == COMPONENT_KIND_CURVE]
    assert len(curve_comps) == 1
    assert '"nodes"' in curve_comps[0].captured_content  # the node set is captured


def test_reproducible_under_curve_correction(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    cid = _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    first = _run(session, tenant, mv, [_sel()])
    before = [str(r.sensitivity_value) for r in first.rows]
    snap_id = first.run.input_snapshot_id
    # A vendor correction AFTER the run changes the live curve.
    hdr = resolve_curve(session, cid, acting_tenant=tenant)
    correct_curve(
        session,
        hdr,
        restatement_reason="vendor restatement",
        nodes=[
            CurveNode(
                tenor_label="1Y",
                tenor_days=365,
                value_type="ZERO_RATE",
                # a realistic zero rate, distinct from the pinned base 0.05 (the correction must
                # NOT leak into the snapshot-reproduced rerun asserted below)
                point_value=Decimal("0.07"),
            )
        ],
        acting_tenant=tenant,
        actor=CurveActor(actor_id="s"),
    )
    session.flush()
    again = run_sensitivities(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=snap_id,
    )
    assert [str(r.sensitivity_value) for r in again.rows] == before  # captured curve reused


def test_determinism_same_snapshot(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    first = _run(session, tenant, mv, [_sel()])
    second = run_sensitivities(
        session,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=first.run.input_snapshot_id,
    )
    assert [str(r.sensitivity_value) for r in first.rows] == [
        str(r.sensitivity_value) for r in second.rows
    ]


# ---------- (5) calculation_run binding ----------


def test_run_binds_snapshot_model_code_env(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    run = _run(session, tenant, mv, [_sel()]).run
    assert run.input_snapshot_id is not None
    assert run.model_version_id == mv
    assert run.code_version == "risk-v1"
    assert run.environment_id == "ci"
    assert run.run_type == "SENSITIVITY"


# ---------- (6) sensitivity_result IA append-only ----------


def test_sensitivity_result_is_ia_append_only() -> None:
    from irp_shared.temporal import TemporalClass

    assert SensitivityResult.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY


def test_append_only_orm_guard_blocks_update_delete(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel()])
    session.commit()
    row = result.rows[0]
    row.sensitivity_value = Decimal("1.0")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    with pytest.raises(AppendOnlyViolation):
        session.delete(result.rows[0])
        session.flush()


def test_grain_uniqueness_within_run(session: Session) -> None:
    # The 5-tuple grain (run, curve, value_type, tenor_days, sensitivity_type) is unique within a
    # run.
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel()])
    keys = {
        (r.calculation_run_id, r.curve_id, r.value_type, r.tenor_days, r.sensitivity_type)
        for r in result.rows
    }
    assert len(keys) == len(result.rows)


# ---------- (7) DQ fail-closed ----------


def test_par_rate_only_curve_fails_closed_post_create(session: Session) -> None:
    # A PAR_RATE-only curve has NO usable node -> fail-closed -> committed FAILED run + zero rows.
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(
        session,
        tenant,
        nodes=[
            CurveNode(
                tenor_label="1Y", tenor_days=365, value_type="PAR_RATE", point_value=Decimal("0.05")
            )
        ],
    )
    mv = _model(session, tenant)
    session.flush()
    runs_before = _count_runs(session, tenant)
    result = _run(session, tenant, mv, [_sel()])
    assert result.status == RunStatus.FAILED.value
    assert result.rows == []
    assert _count_runs(session, tenant) == runs_before + 1  # committed FAILED run
    assert _count_results_for_run(session, result.run.run_id) == 0


def test_failed_run_keeps_snapshot_dependency_lineage(session: Session) -> None:
    # A committed FAILED run still records the snapshot->run DEPENDS_ON edge (the input-dependency
    # fact is true regardless of outcome — the auditor's refusal evidence has full lineage).
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(
        session,
        tenant,
        nodes=[
            CurveNode(
                tenor_label="1Y", tenor_days=365, value_type="PAR_RATE", point_value=Decimal("0.05")
            )
        ],
    )
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel()])
    assert result.status == RunStatus.FAILED.value
    dep = [
        e
        for e in session.execute(select(LineageEdge)).scalars()
        if e.edge_kind == EDGE_KIND_DEPENDENCY and e.target_entity_id == result.run.run_id
    ]
    assert len(dep) == 1
    assert dep[0].source_type == SOURCE_TYPE_DATA_SNAPSHOT
    assert dep[0].run_id == result.run.run_id
    # ... and ZERO result rows -> ZERO ORIGIN edges for this FAILED run.
    origin = [
        e
        for e in session.execute(select(LineageEdge)).scalars()
        if e.edge_kind == EDGE_KIND_ORIGIN
        and e.target_entity_type == "sensitivity_result"
        and e.run_id == result.run.run_id
    ]
    assert origin == []


def test_missing_curve_selector_fails_closed_pre_create(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    mv = _model(session, tenant)  # no curve captured
    session.flush()
    with pytest.raises(CurveSnapshotError):
        _run(session, tenant, mv, [_sel()])
    assert _count_runs(session, tenant) == 0  # pre-create refusal: no run


def test_cross_tenant_curve_fails_closed_pre_create(session: Session) -> None:
    tenant = str(uuid.uuid4())
    other = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, other, nodes=_zero_nodes())  # belongs to `other`
    mv = _model(session, tenant)
    session.flush()
    with pytest.raises(CurveSnapshotError):
        _run(session, tenant, mv, [_sel()])  # acting as `tenant`, curve is `other`'s
    assert _count_runs(session, tenant) == 0


# ---------- (8) audit ----------


def test_audit_calc_run_events_no_risk_event(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel()])
    types = [
        e.event_type
        for e in session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == result.run.run_id)
        ).scalars()
    ]
    assert types.count("CALC.RUN_CREATE") == 1
    assert types.count("CALC.RUN_STATUS_CHANGE") == 2  # RUNNING + COMPLETED
    # NO RISK.* audit code is minted in P3-1 (reserved-only).
    all_types = [e.event_type for e in session.execute(select(AuditEvent)).scalars()]
    assert not any(t.startswith("RISK.") for t in all_types)


# ---------- (9) lineage ----------


def test_lineage_snapshot_to_run_to_result(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel()])
    run_id = result.run.run_id
    edges = list(session.execute(select(LineageEdge)).scalars())
    dep = [e for e in edges if e.edge_kind == EDGE_KIND_DEPENDENCY and e.target_entity_id == run_id]
    assert len(dep) == 1
    assert dep[0].source_type == SOURCE_TYPE_DATA_SNAPSHOT
    assert dep[0].run_id == run_id
    origin = [
        e
        for e in edges
        if e.edge_kind == EDGE_KIND_ORIGIN
        and e.source_type == SOURCE_TYPE_CALCULATION_RUN
        and e.target_entity_type == "sensitivity_result"
    ]
    assert len(origin) == len(result.rows)
    for e in origin:
        assert e.run_id == run_id


def test_model_version_reference_preserved_on_read(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _curve(session, tenant, nodes=_zero_nodes())
    mv = _model(session, tenant)
    session.flush()
    result = _run(session, tenant, mv, [_sel()])
    session.commit()
    rows = list_sensitivities(session, run_id=result.run.run_id, acting_tenant=tenant)
    assert rows
    assert all(r.model_version_id == mv for r in rows)


# ---------- (10) entitlement parity ----------


def test_risk_permissions_grants_as_ratified() -> None:
    run_holders = {r for r, codes in ROLE_TEMPLATES.items() if "risk.run" in codes}
    view_holders = {r for r, codes in ROLE_TEMPLATES.items() if "risk.view" in codes}
    assert run_holders == {"platform_admin", "data_steward", "risk_analyst_1l"}
    assert view_holders == {
        "platform_admin",
        "data_steward",
        "risk_analyst_1l",
        "risk_manager_2l",
        "auditor_3l",  # INCLUDED — governed risk-output oversight
    }


# ---------- (1) methodology doc ----------

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_METHODOLOGY_DOC = _ROOT / SENSITIVITY_METHODOLOGY_REF


def test_methodology_doc_exists_and_has_required_sections() -> None:
    assert _METHODOLOGY_DOC.is_file()
    text = _METHODOLOGY_DOC.read_text(encoding="utf-8")
    for section in (
        "Purpose & applicability",
        "Inputs & data policy",
        "Formulas & numerical standards",
        "Assumptions",
        "Limitations",
        "Validation / reproduction tests",
        "Known limitations",
    ):
        assert section in text, f"missing methodology section: {section}"


def test_methodology_ref_matches_registered_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None
    assert version.methodology_ref == SENSITIVITY_METHODOLOGY_REF
    assert (_ROOT / version.methodology_ref).is_file()


# ---------- (13) scope fences (load-bearing) ----------

_SERVICE_SRC = pathlib.Path(risk_service.__file__).read_text(encoding="utf-8")
_KERNEL_SRC = pathlib.Path(risk_kernel.__file__).read_text(encoding="utf-8")


def test_scope_fence_no_live_curve_resolver_in_compute() -> None:
    # The compute reads snapshot-pinned content only; the live curve reads belong to build_curve_
    # snapshot (the snapshot package), NEVER to risk/service.py.
    tree = ast.parse(_SERVICE_SRC)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    forbidden = {"reconstruct_curve_as_of", "list_curve_points", "resolve_curve"}
    assert not (names & forbidden), names & forbidden
    assert not (attrs & forbidden), attrs & forbidden


def test_scope_fence_no_future_analytics_imports_or_identifiers() -> None:
    for src in (_SERVICE_SRC, _KERNEL_SRC):
        tree = ast.parse(src)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        forbidden_pkgs = ("factor", "scenario", "pricing", "stress", "var", "covariance")
        for mod in imported:
            parts = set(mod.split("."))
            assert not (parts & set(forbidden_pkgs)), f"forbidden import {mod}"
        idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        forbidden_idents = {
            "value_at_risk",
            "expected_shortfall",
            "covariance",
            "factor_model",
            "factor_return",
            "scenario_result",
            "stress_test",
            "monte_carlo",
            "interpolate",
            "bootstrap_curve",
            "instrument_dv01",
        }
        assert not (idents & forbidden_idents), idents & forbidden_idents


# ---------- (14) migration head ----------


def test_migration_head_is_sensitivity() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0034_proxy_mapping"
    assert script.get_revision("0022_sensitivity").down_revision == "0021_benchmark"


# ---------- helpers ----------


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count()).select_from(CalculationRun).where(CalculationRun.tenant_id == tenant)
    ).scalar_one()


def _count_results(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(SensitivityResult)
        .where(SensitivityResult.tenant_id == tenant)
    ).scalar_one()


def _count_results_for_run(db: Session, run_id: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(SensitivityResult)
        .where(SensitivityResult.calculation_run_id == run_id)
    ).scalar_one()
