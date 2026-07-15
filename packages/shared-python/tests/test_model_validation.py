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
from datetime import UTC, date, datetime

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
_DUE = date(2027, 6, 1)


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
