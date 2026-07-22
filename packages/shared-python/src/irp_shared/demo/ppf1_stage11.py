"""The PPF-1 stage-11 demo runner (OD-PPF-1-F): the pure-private factor-return slice.

EXTENDS the living demo tenant an ELEVENTH time (every prior stage byte-untouched) — the governed
pooling over the ALREADY-SEEDED private substrate (ZERO new book data, the verifier census): both
qualified private instruments already carry a COMPLETED ``perf.return.desmoothed_geltner`` run and a
current-head REGRESSION proxy blend.

- **PE-HARBOR-IV** (PRIVATE_EQUITY, campaign; blend → FX_USD) → ``PPF_PRIVATE_EQUITY_GLOBAL``.
- **PC-BRIDGEWATER-II** (PRIVATE_CREDIT, HG-1; blend → MF_RATES_GOV + MF_CRSPD_IG) → segment
  ``PPF_PRIVATE_CREDIT_GLOBAL``.

This is a GOVERNED-NUMBER stage (the CC-2 contrast with stage-10's runs-only): it mints the 21st
model code (``risk.factor_return.pure_private``, the EIGHTEENTH governed number), files ONE INITIAL
validation record, and completes TWO governed runs (one per single-member segment). The counts MOVE
20/35/101 → **21/36/103** (asserted by the exercising suites). The sequence:

1. Resolve the two seeded members by code + their sole COMPLETED desmoothing runs (refuse if the
   substrate is missing — no fabrication).
2. **Register** ``risk.factor_return.pure_private`` v1 (declared pooling=EQUAL_WEIGHT /
   intercept=RETAIN_ALPHA / min_members=1 — the ratified OQ-PPF-1-2/3/5).
3. Per segment: create the PRIVATE segment ``factor`` (APPRAISAL frequency) + a weight-1 MANUAL
   membership row onto it, then **run** the pooled pure-private factor return (min_members=1,
   member count disclosed).
4. Assign the ratified TIER and file the **INITIAL AWC** (``PPF1_PURE_PRIVATE_TIER`` +
   ``PPF1_PURE_PRIVATE_INITIAL`` — SEPARATE dossier constants; ``TIER_DOSSIERS`` stays 16-pinned),
   findings resolved against the version's OWN registered ``model_limitation`` rows.

Idempotency is REFUSE-NOT-SKIP on this stage's OWN footprint (any ``PURE_PRIVATE_FACTOR`` run in the
demo tenant, probed FIRST). Requires the campaign + HG-1 (the seeded members). The caller owns the
ONE commit. **The ``stage9zz`` filename component of the exercising suites is LOAD-BEARING**
(alpha-sorts AFTER ``stage9z`` — the stage-10 zero-pad hazard: ``stage11`` sorts BEFORE ``stage2``;
the API-1 ``stage9z`` workaround extended one more ``z``).
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
from irp_shared.demo.dossiers import PPF1_PURE_PRIVATE_INITIAL, PPF1_PURE_PRIVATE_TIER
from irp_shared.marketdata import (
    FactorActor,
    ProxyMappingActor,
    capture_factor,
    capture_proxy_mapping,
)
from irp_shared.model.models import VALIDATION_TYPE_INITIAL, ModelLimitation
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)
from irp_shared.perf.events import RUN_TYPE_DESMOOTHED_RETURN
from irp_shared.perf.models import DesmoothedReturnResult
from irp_shared.reference.models import Instrument
from irp_shared.risk import (
    PurePrivateFactorActor,
    register_pure_private_factor_model,
    run_pure_private_factor_return,
)
from irp_shared.risk.events import RUN_TYPE_PURE_PRIVATE_FACTOR

_CODE_VERSION = "demo-ppf1"
_ENVIRONMENT_ID = "demo"
_ACTOR_ID = "demo-ppf1-runner"
_REPORT_REF = "10_delivery_backlog/ppf_1_decision_record.md"
_VALID_FROM = datetime(2026, 6, 30, tzinfo=UTC)

#: The two seeded single-member segments: (segment factor_code, member instrument_code).
_SEGMENTS: tuple[tuple[str, str], ...] = (
    ("PPF_PRIVATE_EQUITY_GLOBAL", "PE-HARBOR-IV"),
    ("PPF_PRIVATE_CREDIT_GLOBAL", "PC-BRIDGEWATER-II"),
)


class DemoPpf1Error(RuntimeError):
    """Base class for stage-11 refusals."""


class DemoPpf1AlreadySeededError(DemoPpf1Error):
    """The stage-11 footprint (any demo-tenant PURE_PRIVATE_FACTOR run) already exists — REFUSE."""


class DemoPpf1PrereqError(DemoPpf1Error):
    """A stage-11 prerequisite is missing (run the campaign + HG-1 first) or a tripwire fired."""


@dataclass(frozen=True)
class Ppf1Stage11Summary:
    tenant_id: str
    pure_private_model_version_id: str
    run_ids: tuple[str, ...]
    segment_factor_ids: tuple[str, ...]
    total_period_rows: int
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
        raise DemoPpf1PrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one from "
            f"the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def _resolve_member(session: Session, instrument_code: str) -> tuple[str, str]:
    """Resolve the seeded member instrument by code + its sole COMPLETED desmoothing run (refuse if
    absent — no fabrication). Returns (instrument_id, desmoothed_run_id)."""
    instrument = session.execute(
        select(Instrument).where(
            Instrument.tenant_id == DEMO_TENANT_ID,
            Instrument.code == instrument_code,
            Instrument.valid_to.is_(None),  # the EV active window (versioned in place)
        )
    ).scalar_one_or_none()
    if instrument is None:
        raise DemoPpf1PrereqError(
            f"instrument {instrument_code!r} is not seeded in the demo tenant — run the campaign + "
            f"HG-1 first"
        )
    run_ids = (
        session.execute(
            select(DesmoothedReturnResult.calculation_run_id)
            .join(
                CalculationRun,
                CalculationRun.run_id == DesmoothedReturnResult.calculation_run_id,
            )
            .where(
                DesmoothedReturnResult.tenant_id == DEMO_TENANT_ID,
                DesmoothedReturnResult.instrument_id == instrument.id,
                CalculationRun.run_type == RUN_TYPE_DESMOOTHED_RETURN,
                CalculationRun.status == "COMPLETED",
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    if len(run_ids) != 1:
        raise DemoPpf1PrereqError(
            f"member {instrument_code!r} has {len(run_ids)} COMPLETED desmoothing run(s) — need "
            f"exactly one from the seed; refusing"
        )
    return str(instrument.id), str(run_ids[0])


def _findings_from_registry(
    session: Session, version_id: str, keys: tuple[str, ...]
) -> tuple[ValidationFindingInput, ...]:
    """The campaign's fail-loud key mechanism (the CC-2 precedent, duplicated not shared): each
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
            raise DemoPpf1PrereqError(
                f"dossier finding key {key!r} matched {len(matches)} registered pure-private "
                f"limitation row(s) — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


def run_demo_ppf1_stage11(session: Session) -> Ppf1Stage11Summary:
    """Execute stage 11 (resolve members → register → per segment: segment+membership+run → tier +
    file). The caller owns the ONE commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # --- Footprint probe (refuse-not-skip, BEFORE any write) ---
        existing = session.execute(
            select(CalculationRun.run_id).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_type == RUN_TYPE_PURE_PRIVATE_FACTOR,
            )
        ).first()
        if existing is not None:
            raise DemoPpf1AlreadySeededError(
                "stage 11 footprint already present (a PURE_PRIVATE_FACTOR run exists) — refusing "
                "to re-seed (refuse-not-skip)"
            )

        registrar = _resolve_principal(session, "risk_analyst_1l", "registrar/1L")
        validator = _resolve_principal(session, "risk_manager_2l", "2L validator")

        # --- Register the pure-private model ONCE (idempotent; a conflict refuses loudly) ---
        version = register_pure_private_factor_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=_ACTOR_ID,
            code_version=_CODE_VERSION,
            min_members=1,
        )

        # --- Per segment: the PRIVATE factor + a MANUAL membership row + the pooled run ---
        run_ids: list[str] = []
        segment_ids: list[str] = []
        total_rows = 0
        for factor_code, instrument_code in _SEGMENTS:
            instrument_id, desmoothed_run_id = _resolve_member(session, instrument_code)
            segment = capture_factor(
                session,
                factor_code=factor_code,
                factor_source="PPF",
                factor_family="PRIVATE",
                frequency="APPRAISAL",
                acting_tenant=DEMO_TENANT_ID,
                actor=FactorActor(actor_id=registrar),
                valid_from=_VALID_FROM,
            )
            capture_proxy_mapping(
                session,
                private_instrument_id=instrument_id,
                factor_id=segment.id,
                weight=Decimal("1"),
                acting_tenant=DEMO_TENANT_ID,
                actor=ProxyMappingActor(actor_id=registrar),
                valid_from=_VALID_FROM,
            )
            result = run_pure_private_factor_return(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=PurePrivateFactorActor(actor_id=_ACTOR_ID),
                code_version=_CODE_VERSION,
                environment_id=_ENVIRONMENT_ID,
                model_version_id=version.id,
                segment_factor_id=segment.id,
                member_desmoothed_run_ids=[desmoothed_run_id],
            )
            if result.status != "COMPLETED":
                raise DemoPpf1PrereqError(
                    f"the pure-private run for {factor_code!r} did not complete: "
                    f"{result.failure_reason}"
                )
            run_ids.append(str(result.run.run_id))
            segment_ids.append(str(segment.id))
            total_rows += len(result.rows)

        # --- Tier + the INITIAL AWC (NEW code -> SOME record; the MG-1/CC-2 precedent) ---
        assign_model_tier(
            session,
            acting_tenant=DEMO_TENANT_ID,
            model_id=str(version.model_id),
            materiality_rating=PPF1_PURE_PRIVATE_TIER.materiality_rating,
            complexity_rating=PPF1_PURE_PRIVATE_TIER.complexity_rating,
            rationale=PPF1_PURE_PRIVATE_TIER.rationale,
            actor_id=validator,
        )
        findings = _findings_from_registry(
            session, str(version.id), PPF1_PURE_PRIVATE_INITIAL.finding_keys
        )
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ModelValidationActor(actor_id=validator),
            request=RecordValidationRequest(
                model_version_id=version.id,
                validation_type=VALIDATION_TYPE_INITIAL,
                outcome=PPF1_PURE_PRIVATE_INITIAL.outcome,
                scope_summary=PPF1_PURE_PRIVATE_INITIAL.scope_note,
                conditions=PPF1_PURE_PRIVATE_INITIAL.conditions,
                report_ref=_REPORT_REF,
                next_review_due=date(2026, 7, 22) + timedelta(days=365),
                findings=findings,
                evidence=tuple(
                    ValidationEvidenceInput(evidence_type="CALCULATION_RUN", run_id=rid)
                    for rid in run_ids
                ),
            ),
        )

        return Ppf1Stage11Summary(
            tenant_id=DEMO_TENANT_ID,
            pure_private_model_version_id=str(version.id),
            run_ids=tuple(run_ids),
            segment_factor_ids=tuple(segment_ids),
            total_period_rows=total_rows,
            initials_filed=1,
        )
    finally:
        detach()
