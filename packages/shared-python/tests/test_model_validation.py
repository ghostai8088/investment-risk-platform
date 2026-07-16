"""VW-1 model-validation workflow unit/behavior tests (ENT-037, SR 11-7 / P7).

SQLite has no RLS; tenant-isolation + the P0001 append-only triggers are proven in
``test_model_validation_pg.py``. Here we prove the fail-closed guards (vocab / blur / actor /
non-REGISTERED target / evidence-run refusal), the ``MODEL.VALIDATE`` emission + its ``after_value``
shape (plus the OD-G no-lineage/no-DQ conventions), latest-wins recency, the ORM append-only guard
on all three tables, and — the load-bearing OD-B behavior — that a latest-outcome ``REJECTED`` at
the shared ``assert_model_version_of`` seam refuses a new run while every other outcome (incl.
UNVALIDATED and APPROVED_WITH_CONDITIONS) binds. That ONE seam is called pre-create by every one of
the 12 model-bound governed-number binders, so the seam test is the universal proof.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.models import DataQualityResult
from irp_shared.lineage.models import LineageEdge
from irp_shared.model.models import (
    ModelValidation,
    ModelValidationEvidence,
    ModelValidationFinding,
    ModelVersion,
)
from irp_shared.model.service import (
    RejectedModelVersionError,
    assert_model_version_of,
    register_model,
    register_model_version,
)
from irp_shared.model.validation import (
    MODEL_VALIDATE_EVENT,
    ModelValidationActor,
    ModelValidationValueError,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    latest_validation,
    list_validations,
    record_validation,
)
from irp_shared.models import Base

_MODEL_CODE = "risk.var.parametric"
_T0 = datetime(2026, 6, 1, tzinfo=UTC)
# MG-1 (OD-MG-1-D): next_review_due must sit within the tier ceiling of the record's OWN
# timestamp (untiered => the TIER_1 365-day fail-safe). The suite injects `now` as early as
# 2026-01-01, so the shared fixture date must be <= 2026-12-31.
_DUE = date(2026, 12, 1)


@pytest.fixture
def session() -> Iterator[Session]:
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


def _registered_version(session: Session, tenant: str, *, code: str = _MODEL_CODE) -> ModelVersion:
    model = register_model(
        session, tenant_id=tenant, code=code, name="m", model_type="VAR", actor_id="dev"
    )
    version = register_model_version(
        session, model=model, version_label="1.0.0", actor_id="dev", status="REGISTERED"
    )
    session.flush()
    return version


def _actor() -> ModelValidationActor:
    return ModelValidationActor(actor_id="validator-2l")


def _request(version_id: str, **over: object) -> RecordValidationRequest:
    base: dict[str, object] = dict(
        model_version_id=version_id,
        validation_type="INITIAL",
        outcome="APPROVED",
        scope_summary="Reviewed conceptual soundness, implementation, and outcomes.",
        next_review_due=_DUE,
    )
    base.update(over)
    return RecordValidationRequest(**base)  # type: ignore[arg-type]


def _completed_run(session: Session, tenant: str, run_type: str = "VAR_BACKTEST") -> str:
    run = CalculationRun(
        tenant_id=tenant,
        run_type=run_type,
        status=RunStatus.COMPLETED.value,
        initiated_by="a",
    )
    session.add(run)
    session.flush()
    return str(run.run_id)


# ---------- happy path + audit ----------


def test_record_validation_persists_and_emits(session: Session) -> None:
    tenant = str(uuid.uuid4())
    version = _registered_version(session, tenant)
    run_id = _completed_run(session, tenant)
    record = record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(
            version.id,
            findings=(ValidationFindingInput(finding_text="minor doc gap", severity="LOW"),),
            evidence=(ValidationEvidenceInput(evidence_type="CALCULATION_RUN", run_id=run_id),),
        ),
        now=_T0,
    )
    assert record.outcome == "APPROVED"
    assert session.get(ModelValidation, record.id) is not None
    assert (
        session.execute(select(func.count()).select_from(ModelValidationFinding)).scalar_one() == 1
    )
    ev = session.execute(select(ModelValidationEvidence)).scalar_one()
    assert ev.run_id == run_id  # the cited run id was stamped

    # MODEL.VALIDATE emitted exactly once, with the ratified after_value shape.
    events = (
        session.execute(select(AuditEvent).where(AuditEvent.event_type == MODEL_VALIDATE_EVENT))
        .scalars()
        .all()
    )
    assert len(events) == 1
    after = events[0].after_value
    assert after["model_version_id"] == version.id
    assert after["outcome"] == "APPROVED"
    assert after["validation_type"] == "INITIAL"
    assert after["finding_count"] == 1
    assert after["evidence_count"] == 1
    assert after["next_review_due"] == _DUE.isoformat()
    # OD-G: registry-sibling convention — no lineage edge AND no DQ row from a validation write.
    assert session.execute(select(func.count()).select_from(LineageEdge)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(DataQualityResult)).scalar_one() == 0


# ---------- vocab guards ----------


def test_bad_validation_type_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="validation_type"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, validation_type="WHENEVER"),
        )


def test_bad_outcome_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="outcome"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, outcome="MAYBE"),
        )


def test_bad_finding_severity_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="severity"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(
                v.id, findings=(ValidationFindingInput(finding_text="x", severity="CRITICAL"),)
            ),
        )


def test_bad_evidence_type_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="evidence_type"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, evidence=(ValidationEvidenceInput(evidence_type="VIBES"),)),
        )


# ---------- blur guards ----------


def test_conditions_required_for_approved_with_conditions(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="requires conditions"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, outcome="APPROVED_WITH_CONDITIONS"),
        )


def test_conditions_refused_without_awc(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="only valid with"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, outcome="APPROVED", conditions="cap notional"),
        )


def test_next_review_due_required_for_approving(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="requires a next_review_due"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, next_review_due=None),
        )


def test_next_review_due_refused_for_rejected(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="must not carry a next_review_due"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, outcome="REJECTED", next_review_due=_DUE),
        )


def test_rejected_needs_no_review_date(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    record = record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, outcome="REJECTED", next_review_due=None),
    )
    assert record.outcome == "REJECTED" and record.next_review_due is None


# ---------- actor + target guards ----------


def test_ai_actor_refused_human_only(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="human-only"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=ModelValidationActor(actor_id="bot", actor_type="agent"),
            request=_request(v.id),
        )


def test_non_registered_version_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    model = register_model(
        session, tenant_id=tenant, code=_MODEL_CODE, name="m", model_type="VAR", actor_id="dev"
    )
    draft = register_model_version(
        session, model=model, version_label="0.9.0", actor_id="dev", status=None
    )
    session.flush()
    with pytest.raises(ModelValidationValueError, match="not REGISTERED"):
        record_validation(session, acting_tenant=tenant, actor=_actor(), request=_request(draft.id))


def test_cross_tenant_version_refused(session: Session) -> None:
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    v = _registered_version(session, tenant_a)
    with pytest.raises(ModelValidationValueError, match="not visible"):
        record_validation(session, acting_tenant=tenant_b, actor=_actor(), request=_request(v.id))


# ---------- evidence-run guards ----------


def test_evidence_run_missing_id_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="requires a run_id"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(
                v.id, evidence=(ValidationEvidenceInput(evidence_type="CALCULATION_RUN"),)
            ),
        )


def test_document_evidence_missing_reference_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    with pytest.raises(ModelValidationValueError, match="requires a reference"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, evidence=(ValidationEvidenceInput(evidence_type="DOCUMENT"),)),
        )


def test_calculation_run_evidence_with_reference_refused(session: Session) -> None:
    """Symmetric evidence blur: a CALCULATION_RUN row points at a run, not a document."""
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    run_id = _completed_run(session, tenant)
    with pytest.raises(ModelValidationValueError, match="must not carry a reference"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(
                v.id,
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="CALCULATION_RUN", run_id=run_id, reference="stray"
                    ),
                ),
            ),
        )


def test_document_evidence_with_run_id_refused(session: Session) -> None:
    """Symmetric evidence blur: a DOCUMENT row points at a reference, not a run."""
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    run_id = _completed_run(session, tenant)
    with pytest.raises(ModelValidationValueError, match="must not carry a run_id"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(
                v.id,
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="DOCUMENT", reference="r.pdf", run_id=run_id
                    ),
                ),
            ),
        )


def test_evidence_run_cross_tenant_refused(session: Session) -> None:
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    v = _registered_version(session, tenant_a)
    foreign_run = _completed_run(session, tenant_b)
    with pytest.raises(ModelValidationValueError, match="not visible"):
        record_validation(
            session,
            acting_tenant=tenant_a,
            actor=_actor(),
            request=_request(
                v.id,
                evidence=(
                    ValidationEvidenceInput(evidence_type="CALCULATION_RUN", run_id=foreign_run),
                ),
            ),
        )


def test_evidence_run_not_completed_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    run = CalculationRun(
        tenant_id=tenant, run_type="VAR", status=RunStatus.RUNNING.value, initiated_by="a"
    )
    session.add(run)
    session.flush()
    with pytest.raises(ModelValidationValueError, match="!= COMPLETED"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(
                v.id,
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="CALCULATION_RUN", run_id=str(run.run_id)
                    ),
                ),
            ),
        )


# ---------- recency + the OD-B gate ----------


def test_latest_validation_is_most_recent(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, outcome="REJECTED", next_review_due=None),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, outcome="APPROVED"),
        now=datetime(2026, 2, 1, tzinfo=UTC),
    )
    latest = latest_validation(session, v.id, acting_tenant=tenant)
    assert latest is not None and latest.outcome == "APPROVED"
    assert len(list_validations(session, v.id, acting_tenant=tenant)) == 2


def test_latest_uses_system_from_not_id(session: Session) -> None:
    """Anti-correlate system_from with id: the later-system_from record carries a LEXICALLY-SMALLER
    id than the earlier one. `latest_validation` must still pick the later-system_from record — a
    regression to id-only ordering would pick the wrong one (finder fold: proves the system_from
    leg is load-bearing, not just the id tiebreaker)."""
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    # Directly build two records with controlled (system_from, id) so the axes disagree.
    older = ModelValidation(
        id="ffffffff-ffff-4fff-8fff-ffffffffffff",  # LARGE id
        tenant_id=tenant,
        model_version_id=v.id,
        validation_type="INITIAL",
        outcome="REJECTED",
        scope_summary="s",
        validated_by="x",
        system_from=datetime(2026, 1, 1, tzinfo=UTC),  # EARLIER
    )
    newer = ModelValidation(
        id="00000000-0000-4000-8000-000000000000",  # SMALL id
        tenant_id=tenant,
        model_version_id=v.id,
        validation_type="PERIODIC",
        outcome="APPROVED",
        scope_summary="s",
        validated_by="x",
        system_from=datetime(2026, 2, 1, tzinfo=UTC),  # LATER (should win)
    )
    session.add_all([older, newer])
    session.flush()
    latest = latest_validation(session, v.id, acting_tenant=tenant)
    assert latest is not None and latest.outcome == "APPROVED"  # later system_from, smaller id


def test_unvalidated_version_binds(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    # No validation record → binds normally (the SR 26-2 use-before-validation posture).
    assert (
        assert_model_version_of(session, v.id, tenant_id=tenant, expected_model_code=_MODEL_CODE).id
        == v.id
    )


def test_rejected_version_refuses_new_run(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, outcome="REJECTED", next_review_due=None),
    )
    with pytest.raises(RejectedModelVersionError):
        assert_model_version_of(session, v.id, tenant_id=tenant, expected_model_code=_MODEL_CODE)


def test_approved_after_rejected_unblocks(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, outcome="REJECTED", next_review_due=None),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, outcome="APPROVED"),
        now=datetime(2026, 3, 1, tzinfo=UTC),
    )
    # Recency: the later APPROVED clears the block.
    assert (
        assert_model_version_of(session, v.id, tenant_id=tenant, expected_model_code=_MODEL_CODE).id
        == v.id
    )


def test_approved_with_conditions_binds(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, outcome="APPROVED_WITH_CONDITIONS", conditions="cap gross notional"),
    )
    assert (
        assert_model_version_of(session, v.id, tenant_id=tenant, expected_model_code=_MODEL_CODE).id
        == v.id
    )


# ---------- append-only ORM guard ----------


def test_validation_tables_are_append_only(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant)
    record = record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(
            v.id,
            findings=(ValidationFindingInput(finding_text="f"),),
            evidence=(ValidationEvidenceInput(evidence_type="DOCUMENT", reference="report.pdf"),),
        ),
    )
    session.flush()
    finding = session.execute(select(ModelValidationFinding)).scalar_one()
    evidence = session.execute(select(ModelValidationEvidence)).scalar_one()
    for mutate in (
        lambda: setattr(record, "outcome", "REJECTED"),
        lambda: setattr(finding, "finding_text", "changed"),
        lambda: setattr(evidence, "reference", "changed"),
    ):
        mutate()
        with pytest.raises(AppendOnlyViolation):
            session.flush()
        session.rollback()


# ---------- MG-1 (OD-MG-1-D): the tier-bounded cadence ceiling ----------


def _tiered_version(session: Session, tenant: str, *, materiality: str, code: str) -> ModelVersion:
    from irp_shared.model.service import assign_model_tier

    version = _registered_version(session, tenant, code=code)
    assign_model_tier(
        session,
        acting_tenant=tenant,
        model_id=version.model_id,
        materiality_rating=materiality,
        complexity_rating="MEDIUM",
        rationale="cadence fixture",
        actor_id="validator-2l",
    )
    return version


def test_cadence_ceiling_tier1_boundary(session: Session) -> None:
    # due == now+365 PASSES; +366 refuses (the ceiling is a <= bound on the record's OWN clock).
    tenant = str(uuid.uuid4())
    v = _tiered_version(session, tenant, materiality="HIGH", code="risk.cad.t1")
    now = datetime(2026, 7, 1, tzinfo=UTC)
    ok = record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, next_review_due=now.date() + timedelta(days=365)),
        now=now,
    )
    assert ok.next_review_due == date(2027, 7, 1)
    v2 = _tiered_version(session, tenant, materiality="HIGH", code="risk.cad.t1b")
    with pytest.raises(ModelValidationValueError, match="TIER_1 review ceiling"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v2.id, next_review_due=now.date() + timedelta(days=366)),
            now=now,
        )


def test_cadence_ceiling_tier2_boundary(session: Session) -> None:
    # 730 passes, 731 refuses (the middle-tier boundary the campaign only exercises at equality).
    tenant = str(uuid.uuid4())
    now = datetime(2026, 7, 1, tzinfo=UTC)
    v = _tiered_version(session, tenant, materiality="MEDIUM", code="risk.cad.t2")
    ok = record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v.id, next_review_due=now.date() + timedelta(days=730)),
        now=now,
    )
    assert ok.next_review_due == now.date() + timedelta(days=730)
    v2 = _tiered_version(session, tenant, materiality="MEDIUM", code="risk.cad.t2b")
    with pytest.raises(ModelValidationValueError, match="TIER_2 review ceiling"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v2.id, next_review_due=now.date() + timedelta(days=731)),
            now=now,
        )


def test_cadence_ceiling_untiered_gets_tier1_bound_and_tier3_gets_1095(session: Session) -> None:
    # The fail-safe (VW-1's ratified posture, continued): an UNTIERED model is bounded like
    # TIER_1. A TIER_3 model may declare out to 1095 days.
    tenant = str(uuid.uuid4())
    untiered = _registered_version(session, tenant, code="risk.cad.none")
    now = datetime(2026, 7, 1, tzinfo=UTC)
    with pytest.raises(ModelValidationValueError, match="untiered fail-safe"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(untiered.id, next_review_due=now.date() + timedelta(days=366)),
            now=now,
        )
    t3 = _tiered_version(session, tenant, materiality="LOW", code="risk.cad.t3")
    ok = record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(t3.id, next_review_due=now.date() + timedelta(days=1095)),
        now=now,
    )
    assert ok.next_review_due == now.date() + timedelta(days=1095)
    t3b = _tiered_version(session, tenant, materiality="LOW", code="risk.cad.t3b")
    with pytest.raises(ModelValidationValueError, match="TIER_3 review ceiling"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(t3b.id, next_review_due=now.date() + timedelta(days=1096)),
            now=now,
        )


# ---------- MG-1 (OD-MG-1-E): the EXCEPTION type's shape + substitution guards ----------


def test_exception_must_be_awc_with_expiry(session: Session) -> None:
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant, code="risk.exc.shape")
    with pytest.raises(ModelValidationValueError, match="EXCEPTION must be APPROVED_WITH_COND"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(v.id, validation_type="EXCEPTION", outcome="APPROVED"),
        )
    # The compliant shape: AWC + conditions + expiry (the existing blur rules supply the
    # required-ness of both — OD-E's "for free" claim, pinned).
    record = record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(
            v.id,
            validation_type="EXCEPTION",
            outcome="APPROVED_WITH_CONDITIONS",
            conditions="POC sequencing (urgent-need analogue); controls: registered limitations "
            "+ backtest monitoring. Person-level independence disclosure applies.",
        ),
    )
    assert record.validation_type == "EXCEPTION" and record.next_review_due == _DUE


def test_exception_cannot_substitute_for_validation_or_unreject(session: Session) -> None:
    tenant = str(uuid.uuid4())
    # (1) prior REAL validation ⇒ EXCEPTION refused (a validated model revalidates, never excepts)
    v = _registered_version(session, tenant, code="risk.exc.sub")
    record_validation(session, acting_tenant=tenant, actor=_actor(), request=_request(v.id))
    with pytest.raises(ModelValidationValueError, match="cannot be filed for a version that has"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(
                v.id,
                validation_type="EXCEPTION",
                outcome="APPROVED_WITH_CONDITIONS",
                conditions="x",
            ),
        )
    # (2) latest-REJECTED ⇒ EXCEPTION refused by the SAME single guard (a REJECTED row is a
    # non-EXCEPTION row — the impl review proved the separate un-reject guard unreachable, so it
    # was removed; the un-reject protection is the "no prior non-EXCEPTION row" guard, verified
    # here to cover the REJECTED case too).
    v2 = _registered_version(session, tenant, code="risk.exc.rej")
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(v2.id, outcome="REJECTED", next_review_due=None),
    )
    with pytest.raises(ModelValidationValueError, match="validated or rejected"):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(
                v2.id,
                validation_type="EXCEPTION",
                outcome="APPROVED_WITH_CONDITIONS",
                conditions="x",
            ),
        )


def test_exception_renewal_is_the_permitted_regrant_path(session: Session) -> None:
    # The DISCLOSED semantics (OD-E, a planning-verifier fold): a fresh EXCEPTION after an
    # earlier one is ALLOWED — the audited re-grant ceremony; the count is unbounded (recorded
    # limitation; the bound is the named MG-2 candidate).
    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant, code="risk.exc.renew")
    for i in range(2):
        record_validation(
            session,
            acting_tenant=tenant,
            actor=_actor(),
            request=_request(
                v.id,
                validation_type="EXCEPTION",
                outcome="APPROVED_WITH_CONDITIONS",
                conditions=f"grant {i}",
            ),
        )
    assert len(list_validations(session, v.id, acting_tenant=tenant)) == 2


# ---------- MG-1 (OD-MG-1-F): the seam teeth — an EXPIRED exception refuses new binds ----------


def test_expired_exception_refuses_bind_and_discharges(session: Session) -> None:
    from irp_shared.model.service import ExpiredModelExceptionError, assert_model_version_of

    tenant = str(uuid.uuid4())
    v = _registered_version(session, tenant, code="risk.exc.teeth")
    # An exception granted in the past whose expiry has passed (the injectable `now` makes the
    # backdated grant cadence-compliant at ITS OWN clock — expiry now+180 <= now+365).
    past = datetime(2025, 1, 1, tzinfo=UTC)
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(
            v.id,
            validation_type="EXCEPTION",
            outcome="APPROVED_WITH_CONDITIONS",
            conditions="grant 0",
            next_review_due=past.date() + timedelta(days=180),  # expired 2025-06-30
        ),
        now=past,
    )
    with pytest.raises(ExpiredModelExceptionError):
        assert_model_version_of(
            session, v.id, tenant_id=tenant, expected_model_code="risk.exc.teeth"
        )
    # Discharge path 1 (the refusal message's own advice): a FRESH exception ⇒ binds again.
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(
            v.id,
            validation_type="EXCEPTION",
            outcome="APPROVED_WITH_CONDITIONS",
            conditions="re-grant",
            next_review_due=_DUE,
        ),
    )
    assert (
        assert_model_version_of(
            session, v.id, tenant_id=tenant, expected_model_code="risk.exc.teeth"
        ).id
        == v.id
    )
    # Discharge path 2: a REAL validation on a separately-expired version ⇒ binds again.
    v2 = _registered_version(session, tenant, code="risk.exc.teeth2")
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(
            v2.id,
            validation_type="EXCEPTION",
            outcome="APPROVED_WITH_CONDITIONS",
            conditions="grant",
            next_review_due=past.date() + timedelta(days=180),
        ),
        now=past,
    )
    with pytest.raises(ExpiredModelExceptionError):
        assert_model_version_of(
            session, v2.id, tenant_id=tenant, expected_model_code="risk.exc.teeth2"
        )
    record_validation(
        session, acting_tenant=tenant, actor=_actor(), request=_request(v2.id)
    )  # INITIAL APPROVED — wait: guard 1 refuses EXCEPTION after a real validation, not the
    # reverse; a real validation AFTER exceptions is the intended graduation.
    assert (
        assert_model_version_of(
            session, v2.id, tenant_id=tenant, expected_model_code="risk.exc.teeth2"
        ).id
        == v2.id
    )


def test_unexpired_exception_and_no_rows_both_bind(session: Session) -> None:
    # The corpus-safety invariant (OD-MG-1-F): versions with NO validation rows keep binding —
    # the disclosed SR 26-2 default; filing an exception is what ARMS its own expiry.
    from irp_shared.model.service import assert_model_version_of

    tenant = str(uuid.uuid4())
    bare = _registered_version(session, tenant, code="risk.exc.bare")
    assert (
        assert_model_version_of(
            session, bare.id, tenant_id=tenant, expected_model_code="risk.exc.bare"
        ).id
        == bare.id
    )
    granted = _registered_version(session, tenant, code="risk.exc.live")
    record_validation(
        session,
        acting_tenant=tenant,
        actor=_actor(),
        request=_request(
            granted.id,
            validation_type="EXCEPTION",
            outcome="APPROVED_WITH_CONDITIONS",
            conditions="grant",
        ),
    )
    assert (
        assert_model_version_of(
            session, granted.id, tenant_id=tenant, expected_model_code="risk.exc.live"
        ).id
        == granted.id
    )
