"""The PPF-2 stage-12 demo runner (OD-PPF-2-F): the private covariance block Ω_pp slice.

EXTENDS the living demo tenant a TWELFTH time (every prior stage byte-untouched) — the governed
private covariance over the ALREADY-SEEDED pure-private substrate (ZERO new book data, the verifier
census): both PRIVATE segments already carry a COMPLETED PPF-1 ``risk.factor_return.pure_private``
run over the identical quarterly appraisal grid.

- **PPF_PRIVATE_EQUITY_GLOBAL** (PE-HARBOR-IV) and **PPF_PRIVATE_CREDIT_GLOBAL** (PC-BRIDGEWATER-II)
  → ONE ``risk.covariance.private`` run over their COMMON appraisal periods.

This is a GOVERNED-NUMBER stage (the CC-2 shape): it mints the 22nd model code
(``risk.covariance.private``, the NINETEENTH governed number), files ONE INITIAL validation record,
and completes ONE governed run (a covariance run IS the matrix identity — one run over both
segments). The counts MOVE 21/36/103 → **22/37/104** (asserted by the exercising suites). The
sequence:

1. Resolve the two seeded PRIVATE segments by code + their latest COMPLETED pure-private runs
   (refuse if the substrate is missing — no fabrication).
2. Compute the COMMON appraisal-period window ``N`` (the interval intersection; assert N >= 2) and
   **register** ``risk.covariance.private`` v1 with that declared window.
3. **Run** the Ω_pp estimation over the two segments (build-in-request; the run resolves each
   segment's latest pure-private run and pins their common series).
4. Assign the ratified TIER and file the **INITIAL AWC** (``PPF2_PRIVATE_COVARIANCE_TIER`` +
   ``PPF2_PRIVATE_COVARIANCE_INITIAL``), findings resolved against the version's OWN registered
   ``model_limitation`` rows.

Idempotency is REFUSE-NOT-SKIP on this stage's OWN footprint (any ``COVARIANCE_PRIVATE`` run in the
demo tenant, probed FIRST). Requires PPF-1 (the seeded pure-private segments). The caller owns the
ONE commit. **The ``stage9zzz`` filename component of the exercising suites is LOAD-BEARING**
(alpha-sorts AFTER ``stage9zz`` — the stage-10 zero-pad hazard; the PPF-1 ``stage9zz`` workaround
extended one more ``z``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.demo.dossiers import PPF2_PRIVATE_COVARIANCE_INITIAL, PPF2_PRIVATE_COVARIANCE_TIER
from irp_shared.marketdata.models import Factor
from irp_shared.model.models import VALIDATION_TYPE_INITIAL, ModelLimitation
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)
from irp_shared.risk import (
    METRIC_TYPE_PURE_PRIVATE_PERIOD,
    PurePrivateCovarianceActor,
    latest_pure_private_factor_for_segment,
    register_private_covariance_model,
    run_private_covariance,
)
from irp_shared.risk.events import RUN_TYPE_COVARIANCE_PRIVATE

_CODE_VERSION = "demo-ppf2"
_ENVIRONMENT_ID = "demo"
_ACTOR_ID = "demo-ppf2-runner"
_REPORT_REF = "10_delivery_backlog/ppf_2_decision_record.md"

#: The two seeded PRIVATE segments (created by PPF-1 stage 11), by factor_code.
_SEGMENT_CODES: tuple[str, ...] = ("PPF_PRIVATE_EQUITY_GLOBAL", "PPF_PRIVATE_CREDIT_GLOBAL")


class DemoPpf2Error(RuntimeError):
    """Base class for stage-12 refusals."""


class DemoPpf2AlreadySeededError(DemoPpf2Error):
    """The stage-12 footprint (any demo-tenant COVARIANCE_PRIVATE run) already exists — REFUSE."""


class DemoPpf2PrereqError(DemoPpf2Error):
    """A stage-12 prerequisite is missing (run PPF-1 first) or a tripwire fired."""


@dataclass(frozen=True)
class Ppf2Stage12Summary:
    tenant_id: str
    private_covariance_model_version_id: str
    run_id: str
    segment_factor_ids: tuple[str, ...]
    window_observations: int
    matrix_rows: int
    initials_filed: int


def _resolve_principal(session: Session, role_code: str, label: str) -> str:
    from irp_shared.entitlement.models import AppUser, Role, UserRole

    rows = session.execute(
        select(AppUser.id)
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(AppUser.tenant_id == DEMO_TENANT_ID, Role.code == role_code)
    ).all()
    if len(rows) != 1:
        raise DemoPpf2PrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one from "
            f"the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def _resolve_segment(session: Session, factor_code: str) -> str:
    """Resolve a seeded PRIVATE segment factor by code (refuse if absent — no fabrication)."""
    seg_id = session.execute(
        select(Factor.id).where(
            Factor.tenant_id == DEMO_TENANT_ID,
            Factor.factor_code == factor_code,
            Factor.factor_family == "PRIVATE",
            Factor.valid_to.is_(None),  # the EV active window
        )
    ).scalar_one_or_none()
    if seg_id is None:
        raise DemoPpf2PrereqError(
            f"PRIVATE segment {factor_code!r} is not seeded in the demo tenant — run PPF-1 first"
        )
    return str(seg_id)


def _common_window(session: Session, segment_ids: list[str]) -> int:
    """The count of common ``(period_start, period_end)`` appraisal periods across the segments'
    latest pure-private runs (the declared covariance window; refuse below 2)."""
    per_segment: list[set[tuple[date, date]]] = []
    for seg_id in segment_ids:
        rows = latest_pure_private_factor_for_segment(
            session, acting_tenant=DEMO_TENANT_ID, segment_factor_id=seg_id
        )
        intervals = {
            (r.period_start, r.period_end)
            for r in rows
            if r.metric_type == METRIC_TYPE_PURE_PRIVATE_PERIOD
        }
        if not intervals:
            raise DemoPpf2PrereqError(
                f"segment {seg_id} has no pure-private series — run PPF-1 first"
            )
        per_segment.append(intervals)
    common = set.intersection(*per_segment)
    if len(common) < 2:
        raise DemoPpf2PrereqError(
            f"the seeded segments share only {len(common)} common appraisal period(s) — Ω_pp needs "
            f">= 2; refusing"
        )
    return len(common)


def _findings_from_registry(
    session: Session, version_id: str, keys: tuple[str, ...]
) -> tuple[ValidationFindingInput, ...]:
    """The campaign's fail-loud key mechanism (the CC-2/PPF-1 precedent): each dossier finding KEY
    must match exactly one REGISTERED limitation row, whose text becomes the finding."""
    texts = [
        r[0]
        for r in session.execute(
            select(ModelLimitation.limitation_text).where(
                ModelLimitation.model_version_id == version_id
            )
        ).all()
    ]
    findings: list[ValidationFindingInput] = []
    for key in keys:
        matches = [t for t in texts if key in t]
        if len(matches) != 1:
            raise DemoPpf2PrereqError(
                f"dossier finding key {key!r} matched {len(matches)} registered private-covariance "
                f"limitation row(s) — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


def run_demo_ppf2_stage12(session: Session) -> Ppf2Stage12Summary:
    """Execute stage 12 (resolve segments → compute window → register → run Ω_pp → tier + file). The
    caller owns the ONE commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # --- Footprint probe (refuse-not-skip, BEFORE any write) ---
        existing = session.execute(
            select(CalculationRun.run_id).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_type == RUN_TYPE_COVARIANCE_PRIVATE,
            )
        ).first()
        if existing is not None:
            raise DemoPpf2AlreadySeededError(
                "stage 12 footprint already present (a COVARIANCE_PRIVATE run exists) — refusing "
                "to re-seed (refuse-not-skip)"
            )

        registrar = _resolve_principal(session, "risk_analyst_1l", "registrar/1L")
        validator = _resolve_principal(session, "risk_manager_2l", "2L validator")

        segment_ids = [_resolve_segment(session, code) for code in _SEGMENT_CODES]
        window = _common_window(session, segment_ids)

        # --- Register the private-covariance model ONCE (idempotent; a conflict refuses loudly) ---
        version = register_private_covariance_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=registrar,
            code_version=_CODE_VERSION,
            window_observations=window,
        )

        # --- Run Ω_pp over the two segments (one run IS the matrix identity) ---
        result = run_private_covariance(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=PurePrivateCovarianceActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=version.id,
            segment_factor_ids=segment_ids,
        )
        if result.status != "COMPLETED":
            raise DemoPpf2PrereqError(
                f"the private covariance run did not complete: {result.failure_reason}"
            )

        # --- Tier + the INITIAL AWC (NEW code -> SOME record; the MG-1/CC-2/PPF-1 precedent) ---
        assign_model_tier(
            session,
            acting_tenant=DEMO_TENANT_ID,
            model_id=str(version.model_id),
            materiality_rating=PPF2_PRIVATE_COVARIANCE_TIER.materiality_rating,
            complexity_rating=PPF2_PRIVATE_COVARIANCE_TIER.complexity_rating,
            rationale=PPF2_PRIVATE_COVARIANCE_TIER.rationale,
            actor_id=validator,
        )
        findings = _findings_from_registry(
            session, str(version.id), PPF2_PRIVATE_COVARIANCE_INITIAL.finding_keys
        )
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ModelValidationActor(actor_id=validator),
            request=RecordValidationRequest(
                model_version_id=version.id,
                validation_type=VALIDATION_TYPE_INITIAL,
                outcome=PPF2_PRIVATE_COVARIANCE_INITIAL.outcome,
                scope_summary=PPF2_PRIVATE_COVARIANCE_INITIAL.scope_note,
                conditions=PPF2_PRIVATE_COVARIANCE_INITIAL.conditions,
                report_ref=_REPORT_REF,
                next_review_due=date(2026, 7, 22) + timedelta(days=365),
                findings=findings,
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="CALCULATION_RUN", run_id=str(result.run.run_id)
                    ),
                ),
            ),
        )

        return Ppf2Stage12Summary(
            tenant_id=DEMO_TENANT_ID,
            private_covariance_model_version_id=str(version.id),
            run_id=str(result.run.run_id),
            segment_factor_ids=tuple(segment_ids),
            window_observations=window,
            matrix_rows=len(result.rows),
            initials_filed=1,
        )
    finally:
        detach()
