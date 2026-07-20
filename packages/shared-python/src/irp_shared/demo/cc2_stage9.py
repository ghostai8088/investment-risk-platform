"""The CC-2 stage-9 demo runner (OD-CC-2-G): the PROJECTION half of the ratified commitment walk.

EXTENDS the living demo tenant a NINTH time (every prior stage byte-untouched) — the governed
projection over the stage-8 captured substrate. **The deliberate contrast with stage 8's
capture-only honesty is the demo's own story**: capture mints nothing (stage 8 held the counts at
19/34/95), a governed projection is a real number that DOES move them — this stage adds the 20th
model code (``pacing.commitment_projection``, the SEVENTEENTH governed number), ONE INITIAL
validation record, and ONE COMPLETED run (20 codes / 35 records / 96 runs, asserted by the
exercising suites). The sequence:

1. Capture ONE **valuation mark** (11.2M USD, 2026-06-30) for ``PE-MERIDIAN-X`` — the NAV anchor
   (a captured input: MANUAL ORIGIN, ``VALUATION.CREATE``, NO run). A funded commitment needs a
   same-currency pinned mark or the projection REFUSES pre-create (no fabricated anchor).
2. **Register** ``pacing.commitment_projection`` v1 with the PE-shaped DECLARED parameters
   (``rc_schedule=0.25,0.333,0.5`` / ``fund_life=12`` / ``bow=2.5`` / ``growth=0.13`` /
   ``yield_floor=0`` — our own declared choices, NOT Takahashi-Alexander's un-routed paper
   examples; only the functional FORM is TA's, NO constant minted).
3. **Build** the ``PACING_INPUT`` snapshot on the stage-8 pair (commitment head + ALL
   call/distribution events + the just-captured mark; ``as_of_valuation_date`` = the mark date =
   the deterministic age anchor) and **run** the projection through the governed-run scaffold —
   the FUTURE-ONLY period rows from the mid-life anchor (unfunded restored to 16.2M via the 1.2M
   recallable; NAV seeded from the mark).
4. Assign the ratified TIER and file the **INITIAL AWC** (``CC2_PACING_TIER`` +
   ``CC2_PACING_INITIAL`` — SEPARATE dossier constants; ``TIER_DOSSIERS`` stays 16-pinned),
   findings resolved against the version's OWN registered ``model_limitation`` rows (from the
   registry, never invented).

Idempotency is REFUSE-NOT-SKIP on this stage's OWN footprint (any ``PACING_PROJECTION`` run in the
demo tenant, probed FIRST). Requires stage 8 (the captured commitment) + the campaign (principals).
The caller owns the ONE commit. The ``stage9`` filename component of the exercising suites is
LOAD-BEARING (alpha-sorts after ``stage8``; **the stage10 zero-pad hazard is recorded for the NEXT
stage author** — ``stage10`` sorts BEFORE ``stage2`` lexically, so a tenth stage must zero-pad).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.demo.dossiers import CC2_PACING_INITIAL, CC2_PACING_TIER
from irp_shared.model.models import VALIDATION_TYPE_INITIAL, ModelLimitation
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)
from irp_shared.pacing import (
    PacingActor,
    register_pacing_projection_model,
    run_pacing_projection,
)
from irp_shared.pacing.events import RUN_TYPE_PACING_PROJECTION
from irp_shared.private_capital.models import Commitment
from irp_shared.snapshot import SnapshotActor, build_pacing_snapshot
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_CODE_VERSION = "demo-cc2"
_ENVIRONMENT_ID = "demo"
_ACTOR_ID = "demo-cc2-runner"
_REPORT_REF = "10_delivery_backlog/cc_2_decision_record.md"

#: The NAV anchor: a TD-1-realistic mark (11.2M against 10M net called + 1.8M distributed) dated
#: exactly one anniversary after the 2025-06-30 vintage — the pin-derived current age is 1, so the
#: projection runs FUTURE-ONLY over ages 2..12.
_MARK_VALUE = Decimal("11200000.000000")
_MARK_DATE = date(2026, 6, 30)
_MARK_VALID_FROM = datetime(2026, 6, 30, tzinfo=UTC)

#: The PE-shaped DECLARED parameters (OD-CC-2-G; OUR choices, not TA's paper examples).
_RC_SCHEDULE = [Decimal("0.25"), Decimal("0.333"), Decimal("0.5")]
_FUND_LIFE = 12
_BOW = Decimal("2.5")
_GROWTH = Decimal("0.13")
_YIELD_FLOOR = Decimal("0")


class DemoCc2Error(RuntimeError):
    """Base class for stage-9 refusals."""


class DemoCc2AlreadySeededError(DemoCc2Error):
    """The stage-9 footprint (any demo-tenant PACING_PROJECTION run) already exists — REFUSE."""


class DemoCc2PrereqError(DemoCc2Error):
    """A stage-9 prerequisite is missing (run stage 8 + the campaign first) or a tripwire fired."""


@dataclass(frozen=True)
class Cc2Stage9Summary:
    tenant_id: str
    pacing_model_version_id: str
    projection_run_id: str
    n_periods: int
    first_period_index: int
    last_period_index: int
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
        raise DemoCc2PrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one from "
            f"the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def _findings_from_registry(
    session: Session, version_id: str, keys: tuple[str, ...]
) -> tuple[ValidationFindingInput, ...]:
    """The campaign's fail-loud key mechanism (the BT-3 precedent, duplicated not shared): each
    dossier finding KEY must match exactly one REGISTERED limitation row, whose text becomes the
    finding."""
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
            raise DemoCc2PrereqError(
                f"dossier finding key {key!r} matched {len(matches)} registered pacing "
                f"limitation row(s) — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


def run_demo_cc2_stage9(session: Session) -> Cc2Stage9Summary:
    """Execute stage 9 (mark → register → build → project → tier + file). The caller owns the
    ONE commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # --- Prereq + footprint probes (refuse-not-skip, BEFORE any write) ---
        commitment = session.execute(
            select(Commitment).where(
                Commitment.tenant_id == DEMO_TENANT_ID,
                Commitment.valid_to.is_(None),
                Commitment.system_to.is_(None),
            )
        ).scalar_one_or_none()
        if commitment is None:
            raise DemoCc2PrereqError(
                "no current commitment in the demo tenant — run the CC-1 stage-8 capture first"
            )
        existing = session.execute(
            select(CalculationRun.run_id).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_type == RUN_TYPE_PACING_PROJECTION,
            )
        ).first()
        if existing is not None:
            raise DemoCc2AlreadySeededError(
                "stage 9 footprint already present (a PACING_PROJECTION run exists) — refusing to "
                "re-seed (refuse-not-skip)"
            )

        portfolio_id = str(commitment.portfolio_id)
        instrument_id = str(commitment.instrument_id)
        registrar = _resolve_principal(session, "risk_analyst_1l", "registrar/1L")
        validator = _resolve_principal(session, "risk_manager_2l", "2L validator")

        # --- 1. The NAV anchor: capture the valuation mark (a captured input, NO run) ---
        create_valuation(
            session,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            valuation_date=_MARK_DATE,
            acting_tenant=DEMO_TENANT_ID,
            actor=ValuationActor(actor_id=registrar),
            mark_value=_MARK_VALUE,
            currency_code=commitment.currency_code,
            valid_from=_MARK_VALID_FROM,
        )

        # --- 2. Register the pacing model (idempotent; a conflict refuses loudly) ---
        version = register_pacing_projection_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=_ACTOR_ID,
            code_version=_CODE_VERSION,
            rc_schedule=_RC_SCHEDULE,
            fund_life=_FUND_LIFE,
            bow=_BOW,
            growth=_GROWTH,
            yield_floor=_YIELD_FLOOR,
        )

        # --- 3. Build the PACING_INPUT snapshot + run the projection ---
        snapshot = build_pacing_snapshot(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=SnapshotActor(actor_id=_ACTOR_ID),
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
        )
        result = run_pacing_projection(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=PacingActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=version.id,
            snapshot_id=snapshot.id,
        )
        if result.status != "COMPLETED":
            raise DemoCc2PrereqError(
                f"the pacing projection did not complete: {result.failure_reason}"
            )
        rows = sorted(result.rows, key=lambda r: r.period_index)
        # Drift tripwire (refuse loudly, never re-derive silently): the mid-life anchor must
        # project FUTURE-ONLY over ages 2..12 (age 1 at the 2026-06-30 mark vs the 2025-06-30
        # vintage). If the seeded dates ever move, this refuses rather than silently reshaping.
        if not rows or rows[0].period_index != 2 or rows[-1].period_index != _FUND_LIFE:
            raise DemoCc2PrereqError(
                "fixture drift: the projection window is not ages 2..12 — the seeded vintage/mark "
                "dates moved; refusing"
            )

        # --- 4. Tier + the INITIAL AWC (NEW code -> SOME record; the MG-1/BT-3 precedent) ---
        assign_model_tier(
            session,
            acting_tenant=DEMO_TENANT_ID,
            model_id=str(version.model_id),
            materiality_rating=CC2_PACING_TIER.materiality_rating,
            complexity_rating=CC2_PACING_TIER.complexity_rating,
            rationale=CC2_PACING_TIER.rationale,
            actor_id=validator,
        )
        findings = _findings_from_registry(
            session, str(version.id), CC2_PACING_INITIAL.finding_keys
        )
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ModelValidationActor(actor_id=validator),
            request=RecordValidationRequest(
                model_version_id=version.id,
                validation_type=VALIDATION_TYPE_INITIAL,
                outcome=CC2_PACING_INITIAL.outcome,
                scope_summary=CC2_PACING_INITIAL.scope_note,
                conditions=CC2_PACING_INITIAL.conditions,
                report_ref=_REPORT_REF,
                next_review_due=date(2026, 7, 20) + timedelta(days=365),
                findings=findings,
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="CALCULATION_RUN", run_id=str(result.run.run_id)
                    ),
                ),
            ),
        )

        return Cc2Stage9Summary(
            tenant_id=DEMO_TENANT_ID,
            pacing_model_version_id=str(version.id),
            projection_run_id=str(result.run.run_id),
            n_periods=len(rows),
            first_period_index=rows[0].period_index,
            last_period_index=rows[-1].period_index,
            initials_filed=1,
        )
    finally:
        detach()
