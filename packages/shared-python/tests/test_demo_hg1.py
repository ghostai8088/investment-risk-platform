"""Unit-tier (SQLite) probes for HG-1: the promote age gate + stage 3's refusal guards + the
constants conformance rules (OD-HG-1-A/C/D).

The gate probes use controlled dates by monkeypatching ``proxy_weight_service.utcnow`` (the
promote-day is the ratified anchor — never ``valid_from``); the conformance test works per
SEARCHED SET (dossier code → its registered limitation row set), making the finding-key and
'FL-1'-token rules executable at unit tier (the two re-seeding PG suites remain the
fail-loud proof in CI).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from irp_shared.audit.models import AuditEvent
from irp_shared.calc.models import RunStatus
from irp_shared.demo import (
    DemoHg1AlreadySeededError,
    DemoHg1PrereqError,
    run_demo_hg1_private,
)
from irp_shared.demo.dossiers import (
    FLAGSHIP_DOSSIERS,
    MF1_LOADINGS_INITIAL,
    MF1_TRIGGERED_DOSSIERS,
)
from irp_shared.models import Base
from irp_shared.risk import (
    ProxyWeightInputError,
    ProxyWeightStaleEstimateError,
    promote_proxy_weight_estimate,
    register_factor_exposure_loadings_model,
)
from irp_shared.risk.bootstrap import (
    ES_ASSUMPTIONS_BASE,
    ES_LIMITATIONS,
    ES_TOTAL_LIMITATIONS,
    FACTOR_EXPOSURE_LIMITATIONS,
    FACTOR_EXPOSURE_LOADINGS_LIMITATIONS,
    FACTOR_EXPOSURE_PROXY_LIMITATIONS,
    PROXY_WEIGHT_LIMITATIONS,
    SCENARIO_ASSUMPTIONS,
    VAR_ASSUMPTIONS_BASE,
    VAR_BACKTEST_LIMITATIONS,
    VAR_HS_LIMITATIONS,
    VAR_LIMITATIONS,
    VAR_TOTAL_ASSUMPTIONS_BASE,
    VAR_TOTAL_LIMITATIONS,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


# --- Stage-3 refusal guards (the MF-1 unit-tier pattern; both fire before any PG-specific
# work — set_tenant_context is a no-op off PostgreSQL). ---


def test_stage3_prereq_refusal_on_an_unseeded_tenant(session: Session) -> None:
    with pytest.raises(DemoHg1PrereqError, match="never bootstraps"):
        run_demo_hg1_private(session)


def test_stage3_requires_the_extension_not_just_the_campaign(session: Session) -> None:
    # A tenant with SOME model rows but no loadings code refuses on the missing second stage.
    from irp_shared.demo.campaign import DEMO_TENANT_ID
    from irp_shared.risk import register_var_model

    register_var_model(
        session,
        tenant_id=DEMO_TENANT_ID,
        actor_id="probe",
        code_version="probe",
        confidence_level="0.99",
    )
    session.flush()
    with pytest.raises(DemoHg1PrereqError, match="MF-1 extension"):
        run_demo_hg1_private(session)


def test_stage3_own_footprint_refusal(session: Session) -> None:
    # Loadings model + the instrument present => the footprint probe fires (refuse-not-skip).
    from irp_shared.demo.campaign import DEMO_TENANT_ID
    from irp_shared.demo.hg1_private import _INSTRUMENT_CODE
    from irp_shared.reference.instrument import create_instrument
    from irp_shared.reference.service import ReferenceActor

    register_factor_exposure_loadings_model(
        session, tenant_id=DEMO_TENANT_ID, actor_id="probe", code_version="probe"
    )
    create_instrument(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_INSTRUMENT_CODE,
        name="probe twin",
        asset_class="PRIVATE_CREDIT",
        actor=ReferenceActor(actor_id="probe"),
    )
    session.flush()
    with pytest.raises(DemoHg1AlreadySeededError):
        run_demo_hg1_private(session)


# --- The promote age gate (OD-HG-1-A). Fixture: a real estimate-run + snapshot shape is heavy;
# the gate reads ONLY run.input_snapshot_id -> the snapshot header, so the probes mint a
# COMPLETED PROXY_WEIGHT_ESTIMATE run directly (the calc-service shape every var_total test
# uses) with a hand-built snapshot header where needed. ---

_TENANT = str(uuid.uuid4())
_PROMOTE_DAY = datetime(2026, 7, 1, tzinfo=UTC)


def _mint_instrument_and_factor(s: Session) -> tuple[str, str]:
    from irp_shared.marketdata import FactorActor, capture_factor
    from irp_shared.reference.instrument import create_instrument
    from irp_shared.reference.models import Currency
    from irp_shared.reference.service import ReferenceActor

    s.add(Currency(tenant_id=_TENANT, code="USD", name="USD", valid_from=_PROMOTE_DAY))
    s.flush()
    inst = create_instrument(
        s,
        tenant_id=_TENANT,
        code=f"I-{uuid.uuid4().hex[:6]}",
        name="inst",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    fid = capture_factor(
        s,
        factor_code=f"F-{uuid.uuid4().hex[:6]}",
        factor_source="T",
        factor_family="MARKET",
        acting_tenant=_TENANT,
        actor=FactorActor(actor_id="s"),
        valid_from=_PROMOTE_DAY,
    ).id
    return str(inst), str(fid)


def _mint_estimate_run(s: Session, snapshot_id: str | None) -> str:
    from irp_shared.calc.service import create_run, update_run_status
    from irp_shared.risk.events import RUN_TYPE_PROXY_WEIGHT_ESTIMATE

    run = create_run(
        s,
        tenant_id=_TENANT,
        run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
        initiated_by="probe",
        code_version="probe",
        environment_id="ci",
        input_snapshot_id=snapshot_id,
    )
    update_run_status(s, run, RunStatus.RUNNING)
    update_run_status(s, run, RunStatus.COMPLETED)
    s.flush()
    return str(run.run_id)


def _mint_snapshot(s: Session, *, purpose: str, span_end: date) -> str:
    from irp_shared.snapshot.models import DatasetSnapshot

    snap = DatasetSnapshot(
        tenant_id=_TENANT,
        label="probe",
        purpose=purpose,
        as_of_valuation_date=span_end,
        as_of_valid_at=_PROMOTE_DAY,
        as_of_known_at=_PROMOTE_DAY,
        binding_predicate_version="v1:probe",
        component_count=0,
        manifest_hash="0" * 64,
        created_by="probe",
    )
    s.add(snap)
    s.flush()
    return str(snap.id)


@pytest.fixture()
def frozen_day(monkeypatch: pytest.MonkeyPatch) -> datetime:
    import irp_shared.risk.proxy_weight_service as svc

    monkeypatch.setattr(svc, "utcnow", lambda: _PROMOTE_DAY)
    return _PROMOTE_DAY


def _promote(s: Session, inst: str, fid: str, run_id: str, bound: int | None):
    from irp_shared.marketdata import ProxyMappingActor

    return promote_proxy_weight_estimate(
        s,
        private_instrument_id=inst,
        factor_id=fid,
        weight=Decimal("0.5"),
        acting_tenant=_TENANT,
        actor=ProxyMappingActor(actor_id="analyst"),
        source_calculation_run_id=run_id,
        max_promotion_age_days=bound,
    )


def test_bounded_promote_passes_and_audits_the_age(session: Session, frozen_day) -> None:
    from irp_shared.snapshot import PURPOSE_PROXY_WEIGHT_INPUT

    inst, fid = _mint_instrument_and_factor(session)
    snap = _mint_snapshot(
        session, purpose=PURPOSE_PROXY_WEIGHT_INPUT, span_end=date(2026, 5, 22)
    )  # age = 40 days on the frozen promote-day
    run_id = _mint_estimate_run(session, snap)
    row = _promote(session, inst, fid, run_id, bound=60)
    assert row.mapping_method == "REGRESSION"
    event = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_id == str(row.id), AuditEvent.action == "create")
            .order_by(AuditEvent.event_time.desc())
        )
        .scalars()
        .first()
    )
    assert event is not None and event.after_value.get("promotion_age_days") == 40


def test_bounded_promote_refuses_a_stale_estimate(session: Session, frozen_day) -> None:
    from irp_shared.snapshot import PURPOSE_PROXY_WEIGHT_INPUT

    inst, fid = _mint_instrument_and_factor(session)
    snap = _mint_snapshot(
        session, purpose=PURPOSE_PROXY_WEIGHT_INPUT, span_end=date(2026, 1, 2)
    )  # age = 180 days
    run_id = _mint_estimate_run(session, snap)
    with pytest.raises(ProxyWeightStaleEstimateError, match=r"180 day\(s\) old"):
        _promote(session, inst, fid, run_id, bound=90)


@pytest.mark.parametrize("shape", ["null", "dangling", "wrong_purpose"])
def test_the_three_unmeasurable_shapes(session: Session, frozen_day, shape: str) -> None:
    inst, fid = _mint_instrument_and_factor(session)
    if shape == "null":
        snap = None
    elif shape == "dangling":
        snap = str(uuid.uuid4())  # bare non-FK column — resolves to nothing
    else:
        snap = _mint_snapshot(session, purpose="VAR_INPUT", span_end=date(2026, 5, 22))
    run_id = _mint_estimate_run(session, snap)
    # Bounded => fail CLOSED (the BT-2 gated-implies-closed shape).
    with pytest.raises(ProxyWeightStaleEstimateError, match="UNMEASURABLE"):
        _promote(session, inst, fid, run_id, bound=400)
    # Ungated => the status quo: promotes cleanly, and the audit payload omits the key.
    row = _promote(session, inst, fid, run_id, bound=None)
    event = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_id == str(row.id), AuditEvent.action == "create")
            .order_by(AuditEvent.event_time.desc())
        )
        .scalars()
        .first()
    )
    assert event is not None and "promotion_age_days" not in event.after_value


def test_the_bound_floor_refuses_below_one(session: Session, frozen_day) -> None:
    inst, fid = _mint_instrument_and_factor(session)
    run_id = _mint_estimate_run(session, None)
    with pytest.raises(ProxyWeightInputError, match="must be >= 1"):
        _promote(session, inst, fid, run_id, bound=0)


def test_manual_capture_audit_omits_the_promotion_key(session: Session) -> None:
    from irp_shared.marketdata import ProxyMappingActor, capture_proxy_mapping

    inst, fid = _mint_instrument_and_factor(session)
    row = capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=fid,
        weight=Decimal("1.0"),
        acting_tenant=_TENANT,
        actor=ProxyMappingActor(actor_id="s"),
    )
    event = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(row.id), AuditEvent.action == "create"
            )
        )
        .scalars()
        .first()
    )
    assert event is not None and "promotion_age_days" not in event.after_value


# --- The constants conformance rules (OD-HG-1-C), per SEARCHED SET. ---

_SEARCHED_SETS: dict[str, tuple[str, ...]] = {
    "risk.var.parametric": VAR_LIMITATIONS,
    "risk.var.historical": VAR_HS_LIMITATIONS,
    "risk.var.parametric_total": VAR_TOTAL_LIMITATIONS,
    "risk.var.parametric_es": ES_LIMITATIONS,
    "risk.var.parametric_es_total": ES_TOTAL_LIMITATIONS,
    "risk.var_backtest": VAR_BACKTEST_LIMITATIONS,
}
#: ALL twelve HG-1-edited tuples (the review's three-finder convergence: the fence must cover
#: every edited set, not just the key-carrying ones — C3, the headline correction, especially).
_EDITED_ROWS: tuple[tuple[str, ...], ...] = (
    VAR_LIMITATIONS,
    VAR_HS_LIMITATIONS,
    VAR_TOTAL_LIMITATIONS,
    ES_LIMITATIONS,
    ES_TOTAL_LIMITATIONS,
    PROXY_WEIGHT_LIMITATIONS,
    VAR_ASSUMPTIONS_BASE,
    ES_ASSUMPTIONS_BASE,
    VAR_TOTAL_ASSUMPTIONS_BASE,
    SCENARIO_ASSUMPTIONS,
    FACTOR_EXPOSURE_LIMITATIONS,
    FACTOR_EXPOSURE_PROXY_LIMITATIONS,
)


def _keys_for(code: str) -> tuple[str, ...]:
    if code in MF1_TRIGGERED_DOSSIERS:
        return MF1_TRIGGERED_DOSSIERS[code].finding_keys
    return FLAGSHIP_DOSSIERS[code].finding_keys


def test_every_finding_key_resolves_exactly_once_per_searched_set() -> None:
    for code, rows in _SEARCHED_SETS.items():
        for key in _keys_for(code):
            matches = [t for t in rows if key in t]
            assert len(matches) == 1, (code, key, len(matches))
    # The loadings INITIAL's keys against its own set.
    for key in MF1_LOADINGS_INITIAL.finding_keys:
        matches = [t for t in FACTOR_EXPOSURE_LOADINGS_LIMITATIONS if key in t]
        assert len(matches) == 1, ("loadings", key, len(matches))


def test_no_edited_constant_carries_the_flywheel_token() -> None:
    for rows in _EDITED_ROWS:
        for t in rows:
            assert "FL-1" not in t
