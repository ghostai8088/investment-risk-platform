"""Model-validation workflow (VW-1, ENT-037, SR 11-7 / P7).

A ``model_validation`` is an append-only, CAPTURED governance judgment at ``model_version`` grain —
NOT a governed number (it binds no snapshot / no run / no methodology model_version).
``record_validation`` writes the record + its findings/evidence as ONE unit, fail-closed on every
guard BEFORE any write, and emits the reserved ``MODEL.VALIDATE`` audit code (activated here;
``audit/service.py`` FROZEN). ``latest_validation`` returns the operative (most recent) record per
version — the recency read that ``assert_model_version_of``'s OD-B gate consults so a latest-outcome
``REJECTED`` refuses new runs.

Guards (all pre-write, fail-closed → 422):
- ``validation_type`` / ``outcome`` in vocab; each finding severity + each evidence type in vocab.
- ``conditions`` required IFF ``outcome == APPROVED_WITH_CONDITIONS`` (the PA-3 blur guard).
- ``next_review_due`` required for the two approving outcomes, refused for ``REJECTED`` (symmetric).
- ``actor_type == "user"`` — human-only in v1 (BR-15/MG-07: AI is never the sole approver of a
  potentially-Tier-1 model, and no model carries a tier yet).
- the target ``model_version`` re-resolved tenant-visible AND ``status == "REGISTERED"`` (a
  non-REGISTERED version is refused at every bind — validating it is moot).
- every ``CALCULATION_RUN`` evidence run re-resolved tenant-visible + COMPLETED before its id is
  stamped into the hard FK (PG FK checks bypass RLS — the P3-5/PA-3 precedent); a ``DOCUMENT`` row
  requires a ``reference``, a ``CALCULATION_RUN`` row requires a ``run_id`` (blur guard both ways).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE
from irp_shared.audit.service import record_event
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.mixins import utcnow
from irp_shared.model.models import (
    EVIDENCE_TYPE_CALCULATION_RUN,
    EVIDENCE_TYPE_DOCUMENT,
    EVIDENCE_TYPES,
    FINDING_SEVERITIES,
    MODEL_TIER_1,
    MODEL_TIER_REVIEW_MAX_DAYS,
    VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
    VALIDATION_OUTCOME_REJECTED,
    VALIDATION_OUTCOMES,
    VALIDATION_TYPE_EXCEPTION,
    VALIDATION_TYPES,
    Model,
    ModelValidation,
    ModelValidationEvidence,
    ModelValidationFinding,
    ModelVersion,
)

#: The reserved MODEL audit code, ACTIVATED at VW-1 (audit_event_taxonomy.md MODEL/EVT-050 block).
MODEL_VALIDATE_EVENT = "MODEL.VALIDATE"


class ModelValidationValueError(Exception):
    """A validation record failed a fail-closed guard (vocab / blur / actor / non-REGISTERED
    target / evidence-run refusal) — caught BEFORE any write. Maps to 422."""


class ModelValidationNotVisible(Exception):
    """A ``model_validation`` id is not visible in the acting tenant scope. Maps to an
    indistinguishable 404."""

    def __init__(self, validation_id: str) -> None:
        super().__init__(
            f"model_validation {validation_id} is not visible in the current tenant context"
        )
        self.validation_id = str(validation_id)


@dataclass(frozen=True)
class ModelValidationActor:
    """Actor/correlation context threaded into the MODEL.VALIDATE emission (BR-16 ready). Human-only
    in v1 (``actor_type`` must be ``"user"``; the guard is in ``record_validation``)."""

    actor_id: str
    actor_type: str = "user"
    on_behalf_of: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class ValidationFindingInput:
    """One finding to record with the validation (severity optional — an unranked observation)."""

    finding_text: str
    severity: str | None = None
    authored_by: str | None = None


@dataclass(frozen=True)
class ValidationEvidenceInput:
    """One evidence citation: a governed run (``CALCULATION_RUN`` + ``run_id``) or an external
    ``DOCUMENT`` (+ ``reference``)."""

    evidence_type: str
    run_id: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class RecordValidationRequest:
    """The full validation to record as one unit."""

    model_version_id: str
    validation_type: str
    outcome: str
    scope_summary: str
    conditions: str | None = None
    report_ref: str | None = None
    next_review_due: date | None = None
    findings: tuple[ValidationFindingInput, ...] = field(default_factory=tuple)
    evidence: tuple[ValidationEvidenceInput, ...] = field(default_factory=tuple)


def _validate_vocab(request: RecordValidationRequest) -> None:
    if request.validation_type not in VALIDATION_TYPES:
        raise ModelValidationValueError(
            f"validation_type {request.validation_type!r} not in {sorted(VALIDATION_TYPES)}"
        )
    if request.outcome not in VALIDATION_OUTCOMES:
        raise ModelValidationValueError(
            f"outcome {request.outcome!r} not in {sorted(VALIDATION_OUTCOMES)}"
        )
    if not (request.scope_summary or "").strip():
        raise ModelValidationValueError("scope_summary is required — refused")
    for finding in request.findings:
        if not (finding.finding_text or "").strip():
            raise ModelValidationValueError("a finding_text is required — refused")
        if finding.severity is not None and finding.severity not in FINDING_SEVERITIES:
            raise ModelValidationValueError(
                f"finding severity {finding.severity!r} not in {sorted(FINDING_SEVERITIES)}"
            )
    for ev in request.evidence:
        if ev.evidence_type not in EVIDENCE_TYPES:
            raise ModelValidationValueError(
                f"evidence_type {ev.evidence_type!r} not in {sorted(EVIDENCE_TYPES)}"
            )
        if ev.evidence_type == EVIDENCE_TYPE_CALCULATION_RUN:
            if not ev.run_id:
                raise ModelValidationValueError(
                    "a CALCULATION_RUN evidence row requires a run_id — refused"
                )
            if (ev.reference or "").strip():  # symmetric blur: a run points at a run, not a doc
                raise ModelValidationValueError(
                    "a CALCULATION_RUN evidence row must not carry a reference — refused"
                )
        if ev.evidence_type == EVIDENCE_TYPE_DOCUMENT:
            if not (ev.reference or "").strip():
                raise ModelValidationValueError(
                    "a DOCUMENT evidence row requires a reference — refused"
                )
            if ev.run_id:  # symmetric blur: a document points at a reference, not a run
                raise ModelValidationValueError(
                    "a DOCUMENT evidence row must not carry a run_id — refused"
                )


def _validate_outcome_coupling(request: RecordValidationRequest) -> None:
    """The two symmetric blur guards on ``conditions`` and ``next_review_due`` (OD-A)."""
    is_awc = request.outcome == VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS
    has_conditions = bool((request.conditions or "").strip())
    if is_awc and not has_conditions:
        raise ModelValidationValueError(
            "an APPROVED_WITH_CONDITIONS outcome requires conditions — refused"
        )
    if not is_awc and has_conditions:
        raise ModelValidationValueError(
            "conditions are only valid with an APPROVED_WITH_CONDITIONS outcome — refused"
        )
    is_rejected = request.outcome == VALIDATION_OUTCOME_REJECTED
    if is_rejected and request.next_review_due is not None:
        raise ModelValidationValueError(
            "a REJECTED outcome must not carry a next_review_due (re-validation is TRIGGERED by "
            "remediation) — refused"
        )
    if not is_rejected and request.next_review_due is None:
        raise ModelValidationValueError(
            "an approving outcome requires a next_review_due (the ongoing-monitoring hook) — "
            "refused"
        )


def _resolve_registered_version(
    session: Session, model_version_id: str, *, acting_tenant: str
) -> ModelVersion:
    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.id == str(model_version_id),
            ModelVersion.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if version is None:
        raise ModelValidationValueError(
            f"model_version {model_version_id} is not visible in the acting tenant — refused"
        )
    if version.status != "REGISTERED":
        raise ModelValidationValueError(
            f"model_version {model_version_id} is not REGISTERED (status {version.status!r}); "
            f"only a bindable version can be validated — refused"
        )
    return version


def _resolve_evidence_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Re-resolve a cited run tenant-visible + COMPLETED before its id is stamped into the hard FK
    (PG FK checks bypass RLS — P3-5). A validator cites REAL, finished evidence, never a foreign or
    still-running run."""
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if run is None:
        raise ModelValidationValueError(
            f"evidence run {run_id} is not visible in the acting tenant — refused"
        )
    if run.status != RunStatus.COMPLETED.value:
        raise ModelValidationValueError(
            f"evidence run {run_id} status {run.status!r} != COMPLETED — refused"
        )
    return run


def record_validation(
    session: Session,
    *,
    acting_tenant: str,
    actor: ModelValidationActor,
    request: RecordValidationRequest,
    now: datetime | None = None,
) -> ModelValidation:
    """Record a validation (+ findings + evidence) as ONE governed unit and emit ``MODEL.VALIDATE``.

    Every guard runs BEFORE any write (fail-closed → 422). Human-only in v1 (BR-15/MG-07). The
    caller owns the commit; ``audit/service.py`` is FROZEN (only the caller-side event constant is
    new). No lineage edge, no DQ rule (the registry-sibling convention — OD-G)."""
    if actor.actor_type != "user":
        raise ModelValidationValueError(
            "model validation is human-only in v1 (BR-15/MG-07: AI is never the sole approver of a "
            "potentially-Tier-1 model) — refused"
        )
    _validate_vocab(request)
    _validate_outcome_coupling(request)
    version = _resolve_registered_version(
        session, request.model_version_id, acting_tenant=acting_tenant
    )
    # --- MG-1 OD-E: the EXCEPTION type's substitution guard ---
    # An EXCEPTION (the per-model, TIME-BOXED use-before-validation grant: SR 26-2 §V supplies the
    # elements — limitations attention, stakeholder notice, controls; SS1/23 P5.3(a)(i) supplies
    # "temporary" and §2.13 the grant semantics) may exist ONLY where NO real validation does — so
    # it can neither substitute for a revalidation NOR un-reject: a REJECTED row is itself a
    # non-EXCEPTION row, so the single "no prior non-EXCEPTION row" guard subsumes the un-reject
    # case entirely. (OD-E ratified a separate second guard for the un-reject case; the impl review
    # proved it unreachable — guard 1 always fires first — so it was removed as dead code and the
    # removal recorded in Part 5.5.) Renewal by a FRESH exception is the intended re-grant path
    # (unbounded — the recorded MG-1 limitation). Version-grain, like the REJECTED gate itself.
    if request.validation_type == VALIDATION_TYPE_EXCEPTION:
        if request.outcome != VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS:
            raise ModelValidationValueError(
                "an EXCEPTION must be APPROVED_WITH_CONDITIONS — the conditions ARE the SR 26-2 §V "
                "controls (limits on use / closer monitoring) + the justification — refused"
            )
        prior_real = session.execute(
            select(ModelValidation.id)
            .where(
                ModelValidation.tenant_id == str(acting_tenant),
                ModelValidation.model_version_id == version.id,
                ModelValidation.validation_type != VALIDATION_TYPE_EXCEPTION,
            )
            .limit(1)
        ).scalar_one_or_none()
        if prior_real is not None:
            raise ModelValidationValueError(
                "a use-before-validation EXCEPTION cannot be filed for a version that has been "
                "validated or rejected — a validated model revalidates (PERIODIC/TRIGGERED) and a "
                "rejected one is remediated + re-validated, never excepted — refused"
            )
    # --- MG-1 OD-D: the tier-bounded cadence ceiling (CLOSES OD-032/OD-033) ---
    # An approving outcome's next_review_due must sit within the model's tier bound; an UNTIERED
    # model gets the TIER_1 bound (VW-1's ratified fail-safe, continued). This costs ONE head
    # SELECT — record_validation's guard path resolves only the version (the MG-1 planning
    # verifier killed the drafted "zero new queries" claim; that fact is true only at the BIND
    # seam, which already reads the head).
    if request.next_review_due is not None:
        head = session.execute(
            select(Model).where(Model.id == version.model_id, Model.tenant_id == str(acting_tenant))
        ).scalar_one_or_none()
        tier = head.tier if head is not None and head.tier in MODEL_TIER_REVIEW_MAX_DAYS else None
        max_days = MODEL_TIER_REVIEW_MAX_DAYS[tier or MODEL_TIER_1]
        today = (now or utcnow()).date()
        bound = today + timedelta(days=max_days)
        tier_label = tier if tier else f"{MODEL_TIER_1} (untiered fail-safe)"
        if request.next_review_due > bound:
            raise ModelValidationValueError(
                f"next_review_due {request.next_review_due.isoformat()} exceeds the {tier_label} "
                f"review ceiling of {max_days} days ({bound.isoformat()}) — OD-MG-1-D; declare a "
                f"date within the bound — refused"
            )
    # Re-resolve every cited run BEFORE any write (nothing is stamped until all evidence is proven).
    resolved_runs: dict[int, str] = {}
    for idx, ev in enumerate(request.evidence):
        if ev.evidence_type == EVIDENCE_TYPE_CALCULATION_RUN:
            run = _resolve_evidence_run(session, str(ev.run_id), acting_tenant=acting_tenant)
            resolved_runs[idx] = str(run.run_id)

    now = now or utcnow()
    record = ModelValidation(
        tenant_id=str(acting_tenant),
        model_version_id=version.id,
        validation_type=request.validation_type,
        outcome=request.outcome,
        scope_summary=request.scope_summary,
        conditions=request.conditions,
        report_ref=request.report_ref,
        next_review_due=request.next_review_due,
        validated_by=actor.actor_id,
        system_from=now,
    )
    session.add(record)
    session.flush()

    for finding in request.findings:
        session.add(
            ModelValidationFinding(
                tenant_id=str(acting_tenant),
                validation_id=record.id,
                finding_text=finding.finding_text,
                severity=finding.severity,
                authored_by=finding.authored_by,
                system_from=now,
            )
        )
    for idx, ev in enumerate(request.evidence):
        session.add(
            ModelValidationEvidence(
                tenant_id=str(acting_tenant),
                validation_id=record.id,
                evidence_type=ev.evidence_type,
                run_id=resolved_runs.get(idx),
                reference=ev.reference,
                system_from=now,
            )
        )
    session.flush()

    record_event(
        session,
        event_type=MODEL_VALIDATE_EVENT,
        tenant_id=str(acting_tenant),
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module="model",
        entity_type="model_validation",
        entity_id=record.id,
        action=ACTION_CREATE,
        after_value={
            "model_version_id": version.id,
            "outcome": request.outcome,
            "validation_type": request.validation_type,
            "finding_count": len(request.findings),
            "evidence_count": len(request.evidence),
            "next_review_due": (
                request.next_review_due.isoformat() if request.next_review_due else None
            ),
        },
        correlation_id=actor.correlation_id,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
    )
    return record


def latest_validation(
    session: Session, model_version_id: str, *, acting_tenant: str
) -> ModelValidation | None:
    """The operative (most recent) validation record for a version, or ``None`` if never validated.
    Ordered ``(system_from DESC, id DESC)``. The ``id`` leg makes the read DETERMINISTIC (a stable,
    query-plan-independent result) — NOT write-order recency: two validations of ONE version with
    an IDENTICAL ``system_from`` resolve by UUID order, not insertion order, so equal-timestamp
    validations of one version are OUT OF CONTRACT (the human-only, non-injected-clock path can't
    produce a same-microsecond tie; a coarse-granularity backfill could — no such path exists
    today, and there is no sequence column on these IA tables to order by instead — finder note)."""
    return session.execute(
        select(ModelValidation)
        .where(
            ModelValidation.model_version_id == str(model_version_id),
            ModelValidation.tenant_id == str(acting_tenant),
        )
        .order_by(ModelValidation.system_from.desc(), ModelValidation.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_validations(
    session: Session, model_version_id: str, *, acting_tenant: str
) -> list[ModelValidation]:
    """All validation records for a version, most-recent first (the same deterministic order)."""
    return list(
        session.execute(
            select(ModelValidation)
            .where(
                ModelValidation.model_version_id == str(model_version_id),
                ModelValidation.tenant_id == str(acting_tenant),
            )
            .order_by(ModelValidation.system_from.desc(), ModelValidation.id.desc())
        )
        .scalars()
        .all()
    )


def list_findings(
    session: Session, validation_id: str, *, acting_tenant: str
) -> list[ModelValidationFinding]:
    return list(
        session.execute(
            select(ModelValidationFinding)
            .where(
                ModelValidationFinding.validation_id == str(validation_id),
                ModelValidationFinding.tenant_id == str(acting_tenant),
            )
            .order_by(ModelValidationFinding.system_from, ModelValidationFinding.id)
        )
        .scalars()
        .all()
    )


def list_evidence(
    session: Session, validation_id: str, *, acting_tenant: str
) -> list[ModelValidationEvidence]:
    return list(
        session.execute(
            select(ModelValidationEvidence)
            .where(
                ModelValidationEvidence.validation_id == str(validation_id),
                ModelValidationEvidence.tenant_id == str(acting_tenant),
            )
            .order_by(ModelValidationEvidence.system_from, ModelValidationEvidence.id)
        )
        .scalars()
        .all()
    )
