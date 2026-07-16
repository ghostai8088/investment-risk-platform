"""PostgreSQL end-state test for the MG-1 demo validation campaign (OD-MG-1-G, plan Step 5).

Gated on ``IRP_TEST_DATABASE_URL``. Runs the campaign ONCE (module-scoped) as the OWNER engine —
the runner writes across the whole governed surface (reference, market data, entitlement wiring,
sixteen model registrations, ~40 governed runs, validations), so the per-suite ``irp_app``
grant-list pattern does not fit; FORCE RLS still applies to the owner, and every session here
scopes itself to the DEMO tenant via the tenant context. The end state asserted is the ratified
one: 16 registered codes, every head tiered, 16 hash-chained ``MODEL.TIER_ASSIGN`` events carrying
the dual ratings + rationale (the ratings' ONLY durable home), 6 INITIAL validations with the
dossier outcomes (the 5 AWC conditions carrying the 'FL-1' flywheel hook the MF-1 TRIGGERED
re-validation greps for), 10 unexpired EXCEPTION records, every CALCULATION_RUN evidence row
resolving to a COMPLETED in-tenant run, and refuse-not-skip on a second invocation.

Dirty double-run safety: the module fixture tolerates an ALREADY-SEEDED demo tenant (the campaign
itself refuses — proven by ``test_second_run_refuses``) and every assertion reads the DB, not the
first run's return value.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from irp_shared.audit.models import AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.mixins import utcnow
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import (
    DEMO_TENANT_ID,
    DemoCampaignAlreadySeededError,
    run_demo_campaign,
)
from irp_shared.demo.dossiers import FLAGSHIP_CODES, FLAGSHIP_DOSSIERS, TIER_DOSSIERS
from irp_shared.model.models import (
    Model,
    ModelValidation,
    ModelValidationEvidence,
    ModelVersion,
)
from irp_shared.model.service import MODEL_TIER_ASSIGN_EVENT

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

#: The ratified 16-code end state (grep '_MODEL_CODE =' over risk/perf bootstrap).
_ALL_CODES = frozenset(TIER_DOSSIERS)
_EXCEPTION_CODES = _ALL_CODES - frozenset(FLAGSHIP_CODES)


@pytest.fixture(scope="module")
def factory():  # noqa: ANN201
    """Owner-engine session factory with the campaign executed once. An already-seeded demo
    tenant (the local dirty double-run mode) is tolerated here — the refusal semantics get their
    own test — and every test below asserts against the DB, never the summary object."""
    engine = make_engine(URL, poolclass=NullPool)
    session_factory = make_session_factory(engine)
    session = session_factory()
    seeded_by_this_run = False
    try:
        try:
            run_demo_campaign(session)
            session.commit()
            seeded_by_this_run = True
        except DemoCampaignAlreadySeededError:
            session.rollback()  # dirty double-run: the end state already exists; assert it
    finally:
        session.close()
    yield session_factory
    # Teardown: drop the demo tenant's role->permission WIRING rows (EV entitlement plumbing,
    # not the governed end state — models/tiers/validations/runs all stay). The campaign is the
    # FIRST PG suite to wire RolePermission onto the migration-seeded permission catalog, and
    # CI's final `alembic downgrade base` smoke deletes that catalog — rows still referencing it
    # would fail the 0002 downgrade with an FK violation.
    #
    # CLEAN UP ONLY WHAT THIS RUN SEEDED (the MG-1-review fold): when the demo tenant was ALREADY
    # seeded (the CLI-created living tenant, or an earlier double-run), those role_permission rows
    # are not ours to delete — stripping them would break the living tenant's 1L/2L wiring for the
    # next endpoint-driven act. In CI the schema is fresh so this run always seeds; only the local
    # dirty double-run hits the skip.
    if not seeded_by_this_run:
        engine.dispose()
        return
    cleanup = session_factory()
    try:
        persistent_tenant_context(cleanup, DEMO_TENANT_ID)
        cleanup.execute(
            text(
                "DELETE FROM role_permission WHERE role_id IN "
                "(SELECT id FROM role WHERE tenant_id = :tenant)"
            ),
            {"tenant": DEMO_TENANT_ID},
        )
        cleanup.commit()
    finally:
        cleanup.close()
    engine.dispose()


@pytest.fixture()
def db(factory) -> Session:  # noqa: ANN001
    session = factory()
    persistent_tenant_context(session, DEMO_TENANT_ID)
    yield session
    session.close()


def _models_by_code(db: Session) -> dict[str, Model]:
    rows = db.execute(select(Model).where(Model.tenant_id == DEMO_TENANT_ID)).scalars().all()
    return {m.code: m for m in rows}


def _validations_by_code(db: Session) -> dict[str, list[ModelValidation]]:
    """All demo-tenant validation records keyed by their model CODE (via the version join)."""
    rows = db.execute(
        select(Model.code, ModelValidation)
        .join(ModelVersion, ModelVersion.model_id == Model.id)
        .join(ModelValidation, ModelValidation.model_version_id == ModelVersion.id)
        .where(Model.tenant_id == DEMO_TENANT_ID)
    ).all()
    out: dict[str, list[ModelValidation]] = {}
    for code, validation in rows:
        out.setdefault(code, []).append(validation)
    return out


def test_sixteen_codes_registered_and_all_tiered(db: Session) -> None:
    models = _models_by_code(db)
    assert set(models) == _ALL_CODES  # exactly the 16 ratified codes, nothing else
    untiered = sorted(code for code, m in models.items() if m.tier is None)
    assert untiered == []  # every head carries its derived tier (OD-MG-1-A/B)
    assert {m.tier for m in models.values()} <= {"TIER_1", "TIER_2", "TIER_3"}


def test_tier_assign_events_carry_the_ratings_payload(db: Session) -> None:
    """16 ``MODEL.TIER_ASSIGN`` events, one per head, each carrying the dual ratings + rationale
    with before/after — the audit payload is the ratings' ONLY durable home (OQ-MG-1-1 sub-fork
    (i)), so this assertion is load-bearing, not cosmetic."""
    models = _models_by_code(db)
    events = (
        db.execute(
            select(AuditEvent).where(
                AuditEvent.tenant_id == DEMO_TENANT_ID,
                AuditEvent.event_type == MODEL_TIER_ASSIGN_EVENT,
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 16
    assert {e.entity_id for e in events} == {m.id for m in models.values()}
    for event in events:
        assert event.before_value == {"tier": None}  # every head registered untiered (OD-B)
        after = event.after_value
        assert set(after) == {"tier", "materiality_rating", "complexity_rating", "rationale"}
        assert after["materiality_rating"] in {"HIGH", "MEDIUM", "LOW"}
        assert after["complexity_rating"] in {"HIGH", "MEDIUM", "LOW"}
        assert after["rationale"].strip()
        assert after["tier"] in {"TIER_1", "TIER_2", "TIER_3"}


def test_six_initial_validations_with_the_dossier_outcomes(db: Session) -> None:
    by_code = _validations_by_code(db)
    initials = {
        code: [v for v in validations if v.validation_type == "INITIAL"]
        for code, validations in by_code.items()
        if any(v.validation_type == "INITIAL" for v in validations)
    }
    assert set(initials) == set(FLAGSHIP_CODES)  # exactly the 6 flagship codes
    for code, records in initials.items():
        assert len(records) == 1, code
        record = records[0]
        assert record.outcome == FLAGSHIP_DOSSIERS[code].outcome, code
        assert record.next_review_due is not None
        assert record.validated_by  # the 2L principal of record


def test_the_five_awc_conditions_carry_the_fl1_flywheel_hook(db: Session) -> None:
    """The ratified flywheel: the CURRENCY-only condition names FL-1/MF-1 as remediation — the
    MF-1 TRIGGERED re-validation later greps conditions for 'FL-1' to find what it closes."""
    by_code = _validations_by_code(db)
    awc_initials = [
        (code, v)
        for code, validations in by_code.items()
        for v in validations
        if v.validation_type == "INITIAL" and v.outcome == "APPROVED_WITH_CONDITIONS"
    ]
    assert len(awc_initials) == 5
    for code, record in awc_initials:
        assert record.conditions and "FL-1" in record.conditions, code
    # ... and ONLY those five carry the hook (the EXCEPTION conditions deliberately avoid the
    # token so the later grep finds exactly the flagship conditions).
    non_awc_initial = [
        v
        for validations in by_code.values()
        for v in validations
        if not (v.validation_type == "INITIAL" and v.outcome == "APPROVED_WITH_CONDITIONS")
    ]
    for record in non_awc_initial:
        assert not (record.conditions and "FL-1" in record.conditions)


def test_ten_exceptions_time_boxed_and_unexpired(db: Session) -> None:
    by_code = _validations_by_code(db)
    exceptions = {
        code: [v for v in validations if v.validation_type == "EXCEPTION"]
        for code, validations in by_code.items()
        if any(v.validation_type == "EXCEPTION" for v in validations)
    }
    assert set(exceptions) == _EXCEPTION_CODES  # exactly the 10 non-flagship codes
    today = utcnow().date()
    for code, records in exceptions.items():
        assert len(records) == 1, code
        record = records[0]
        assert record.outcome == "APPROVED_WITH_CONDITIONS"  # the mandatory EXCEPTION shape
        assert record.conditions and "POC sequencing" in record.conditions
        assert record.next_review_due is not None and record.next_review_due > today  # unexpired
    # Person-level non-independence is disclosed on EVERY campaign record (Part 3 item 1).
    for validations in by_code.values():
        for record in validations:
            assert "PERSON-LEVEL INDEPENDENCE DISCLOSURE" in record.scope_summary


def test_every_run_evidence_row_resolves_completed_in_tenant(db: Session) -> None:
    rows = (
        db.execute(
            select(ModelValidationEvidence).where(
                ModelValidationEvidence.tenant_id == DEMO_TENANT_ID,
                ModelValidationEvidence.evidence_type == "CALCULATION_RUN",
            )
        )
        .scalars()
        .all()
    )
    assert rows  # the flagship dossiers cite their own runs — the chain really ran
    for evidence in rows:
        run = db.execute(
            select(CalculationRun).where(CalculationRun.run_id == evidence.run_id)
        ).scalar_one()
        assert run.tenant_id == DEMO_TENANT_ID
        assert run.status == RunStatus.COMPLETED.value
    # The two REAL backtest runs (BT-1 over the plain series, BT-2 over the total series) are
    # among the cited evidence — the honest-evidence-chain requirement, not a registration stub.
    backtests = (
        db.execute(
            select(CalculationRun).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_type == "VAR_BACKTEST",
            )
        )
        .scalars()
        .all()
    )
    assert len(backtests) == 2
    assert all(r.status == RunStatus.COMPLETED.value for r in backtests)
    cited = {str(e.run_id) for e in rows}
    assert {str(r.run_id) for r in backtests} <= cited


def test_second_run_refuses_not_skips(factory) -> None:  # noqa: ANN001
    """Refuse-not-skip (OD-MG-1-G): a demo tenant already holding model rows refuses re-seeding
    outright — no partial re-runs, no silent convergence (the RD-3 lesson, inverted)."""
    session = factory()
    try:
        with pytest.raises(DemoCampaignAlreadySeededError, match="refusing"):
            run_demo_campaign(session)
        session.rollback()
    finally:
        session.close()
