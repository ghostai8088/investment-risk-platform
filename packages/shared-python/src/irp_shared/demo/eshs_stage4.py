"""The ES-HS-1 stage-4 demo runner (OD-ES-HS-1-F): the 18th registered code and its INITIAL.

EXTENDS the living demo tenant a FOURTH time (campaign + multifamily + stage 3 stay
byte-untouched): registers ``risk.var.historical_es`` v1 (21/0.95 — the flagship HS twin's
declaration, so n·a = 1.05 and the FRACTIONAL Prop-4.1 boundary weight is APPLIED in the
flagship demo; the seeded window's worst two scenarios happen to TIE, so the pair lands on the
recorded tied-tail equality case — ES = VaR exactly, disclosed in the dossier; the weight's
numeric effect is exercised by the kernel suite's untied fixtures), runs the empirical ES bound
to the SAME pinned snapshot as the campaign's LATEST flagship
historical-VaR forecast (the coherent (VaR, ES) pair over one scenario set — the BT-3
shared-``input_snapshot_id`` pairing design input, demonstrated in the living tenant), then
tier-assigns the new head (ES_HS_TIER: HIGH/MEDIUM ⇒ TIER_1 under the MG-1 matrix — the 2L verb
BEFORE filing, the MF-1 V8 ordering) and files the INITIAL AWC dossier (ES_HS_INITIAL;
``next_review_due`` = filing-day + 365, the TIER_1 strict ceiling; finding keys fail-loud
against the NEW code's registered limitation rows; evidence = this model's OWN COMPLETED run).

A genuinely NEW code requires SOME record (the MF-1 loadings-INITIAL precedent; the naked
use-before-validation default is the regime hole MF-1's V4 closed) — HG-1's OQ-5 false-ceremony
bar does not apply because everything here IS new.

Idempotency is REFUSE-NOT-SKIP on this stage's OWN footprint — the ES-HS model code, probed
FIRST (the registration is the first write, so any partially-committed state contains the
probe); refuses without the campaign. The caller owns the ONE commit. The flywheel grep token
appears in nothing this module writes.

The filename leg of the ordering discipline (the planning verifier's catch): the suites that
exercise this module are named ``test_demo_stage4_eshs*`` so a single-invocation local battery
collects them AFTER the campaign/hg1/multifamily suites — an earlier-sorting name would seed
the 18th code before the multifamily suite asserts its EXACTLY-17 pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.demo.dossiers import ES_HS_INITIAL, ES_HS_TIER
from irp_shared.model.models import (
    VALIDATION_TYPE_INITIAL,
    Model,
    ModelLimitation,
    ModelVersion,
)
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)
from irp_shared.risk import (
    ES_HS_MODEL_CODE,
    VAR_HS_MODEL_CODE,
    VarActor,
    VarResult,
    register_historical_var_es_model,
    run_var_historical,
)

_CODE_VERSION = "demo-eshs1"
_BASE_CODE_VERSION = "demo-mg1"  # the campaign's flagship HS registration this stage pairs with
_REPORT_REF = "10_delivery_backlog/es_hs_1_decision_record.md"


class DemoEshsError(RuntimeError):
    """Stage 4 could not complete against the live tenant state."""


class DemoEshsPrereqError(DemoEshsError):
    """Stage 4 extends the LIVING tenant — it requires the MG-1 campaign (the flagship HS
    forecast series it pairs with) and never bootstraps it. Run the prior stages first."""


class DemoEshsAlreadySeededError(RuntimeError):
    """Refuse-not-skip on stage 4's OWN footprint: the ES-HS model code already exists.
    Append-only records are never double-filed; reset the schema and re-run all four stages."""

    def __init__(self) -> None:
        super().__init__(
            f"demo tenant {DEMO_TENANT_ID} already holds model {ES_HS_MODEL_CODE!r} — refusing "
            f"to re-run stage 4 (reset the schema and re-run campaign + extension + stage 3 + "
            f"stage 4)."
        )


@dataclass(frozen=True)
class EshsStage4Summary:
    """Stage 4's end state (the load-bearing ids + the paired numbers)."""

    tenant_id: str
    model_version_id: str
    es_run_id: str
    shared_snapshot_id: str
    es_value: Decimal
    paired_var_value: Decimal
    tier: str
    initials_filed: int


# Small helpers DUPLICATED from the prior stages, not imported — those modules are byte-frozen
# fences and the raising helpers must raise stage-4-typed errors (the recorded MF-1
# adjudication, applied again at HG-1 and here).
def _resolve_principal(session: Session, role_code: str, label: str) -> str:
    from irp_shared.entitlement.models import AppUser, Role, UserRole

    rows = session.execute(
        select(AppUser.id)
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(AppUser.tenant_id == DEMO_TENANT_ID, Role.code == role_code)
    ).all()
    if len(rows) != 1:
        raise DemoEshsPrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one "
            f"from the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def _registered_limitations(session: Session, version_id: str) -> list[str]:
    return [
        r[0]
        for r in session.execute(
            select(ModelLimitation.limitation_text).where(
                ModelLimitation.model_version_id == version_id
            )
        ).all()
    ]


def _findings_from_registry(
    session: Session, version_id: str, keys: tuple[str, ...], code: str
) -> tuple[ValidationFindingInput, ...]:
    """The campaign's fail-loud key mechanism (the multifamily duplication precedent — NOT
    shared machinery): each dossier finding KEY must match exactly one REGISTERED limitation
    row, whose text becomes the finding."""
    texts = _registered_limitations(session, version_id)
    findings: list[ValidationFindingInput] = []
    for key in keys:
        matches = [t for t in texts if key in t]
        if len(matches) != 1:
            raise DemoEshsError(
                f"dossier finding key {key!r} matched {len(matches)} registered limitation "
                f"row(s) of {code} — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


def _latest_flagship_hs_row(session: Session) -> VarResult:
    """The campaign's LATEST flagship historical-VaR forecast row (deterministic: max
    window_end, then run id) — its pinned snapshot is the one this stage's ES run binds."""
    rows = (
        session.execute(
            select(VarResult)
            .join(ModelVersion, ModelVersion.id == VarResult.model_version_id)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(
                VarResult.tenant_id == DEMO_TENANT_ID,
                VarResult.metric_type == "VAR_HISTORICAL",
                Model.code == VAR_HS_MODEL_CODE,
                ModelVersion.code_version == _BASE_CODE_VERSION,
            )
            .order_by(VarResult.window_end.desc(), VarResult.calculation_run_id.desc())
        )
        .scalars()
        .all()
    )
    if not rows:
        raise DemoEshsPrereqError(
            "the demo tenant holds no flagship VAR_HISTORICAL forecast rows — the MG-1 "
            "campaign has not run; run the prior stages first"
        )
    return rows[0]


def run_demo_eshs_stage4(session: Session) -> EshsStage4Summary:
    """Execute stage 4 (register → run-on-the-shared-snapshot → tier-assign → file). The
    caller owns the ONE commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # --- Prereq + footprint probes (refuse-not-skip, BEFORE any write) ---
        model_count = session.execute(
            select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
        ).scalar_one()
        if model_count == 0:
            raise DemoEshsPrereqError(
                f"demo tenant {DEMO_TENANT_ID} holds no model rows — the MG-1 campaign has "
                f"not run; run the prior stages first"
            )
        already = session.execute(
            select(Model).where(Model.tenant_id == DEMO_TENANT_ID, Model.code == ES_HS_MODEL_CODE)
        ).scalar_one_or_none()
        if already is not None:
            raise DemoEshsAlreadySeededError()

        hs_row = _latest_flagship_hs_row(session)
        registrar_id = _resolve_principal(session, "risk_analyst_1l", "1L registrar")
        validator_id = _resolve_principal(session, "risk_manager_2l", "2L validator")

        # --- The 18th code, minted FIRST (the footprint probe's own write) ---
        version = register_historical_var_es_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=registrar_id,
            code_version=_CODE_VERSION,
            confidence_level="0.95",
            window_observations=21,
        )

        # --- The flagship ES run on the SHARED snapshot (the coherent (VaR, ES) pair) ---
        result = run_var_historical(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=VarActor(actor_id=registrar_id),
            code_version=_CODE_VERSION,
            environment_id="demo",
            model_version_id=str(version.id),
            snapshot_id=hs_row.input_snapshot_id,
        )
        if result.status != "COMPLETED":
            raise DemoEshsError(
                f"the stage-4 ES run did not COMPLETE (status={result.status!r}, "
                f"reason={result.failure_reason!r})"
            )
        (es_row,) = result.rows
        if es_row.var_value < hs_row.var_value:
            # ES >= VaR on the shared window is theorem-true — a violation means the tenant
            # state drifted (a different snapshot/window than the pair assumes); refuse loudly.
            raise DemoEshsError(
                f"ES {es_row.var_value} < paired VaR {hs_row.var_value} on the shared "
                f"snapshot — the pairing invariant failed; refusing"
            )

        # --- Tier BEFORE filing (the MF-1 V8 ordering); HIGH/MEDIUM ⇒ TIER_1 ---
        head = assign_model_tier(
            session,
            acting_tenant=DEMO_TENANT_ID,
            model_id=str(version.model_id),
            materiality_rating=ES_HS_TIER.materiality_rating,
            complexity_rating=ES_HS_TIER.complexity_rating,
            rationale=ES_HS_TIER.rationale,
            actor_id=validator_id,
        )
        if head.tier is None:  # narrow for typing; assign_model_tier always stamps it
            raise DemoEshsError("tier assignment left the head untiered — refusing")

        # --- The INITIAL AWC (the genuinely-new-code record; next_review_due = +365) ---
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ModelValidationActor(actor_id=validator_id),
            request=RecordValidationRequest(
                model_version_id=version.id,
                validation_type=VALIDATION_TYPE_INITIAL,
                outcome=ES_HS_INITIAL.outcome,
                scope_summary=ES_HS_INITIAL.scope_note,
                conditions=ES_HS_INITIAL.conditions,
                report_ref=_REPORT_REF,
                next_review_due=utcnow().date() + timedelta(days=365),  # the TIER_1 ceiling
                findings=_findings_from_registry(
                    session, version.id, ES_HS_INITIAL.finding_keys, ES_HS_MODEL_CODE
                ),
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="CALCULATION_RUN", run_id=result.run.run_id
                    ),
                    ValidationEvidenceInput(
                        evidence_type="DOCUMENT",
                        reference=f"{_REPORT_REF} (OD-ES-HS-1-F: the ratified stage-4 dossier "
                        f"this record transcribes)",
                    ),
                ),
            ),
        )

        return EshsStage4Summary(
            tenant_id=DEMO_TENANT_ID,
            model_version_id=str(version.id),
            es_run_id=result.run.run_id,
            shared_snapshot_id=hs_row.input_snapshot_id,
            es_value=es_row.var_value,
            paired_var_value=hs_row.var_value,
            tier=head.tier,
            initials_filed=1,
        )
    finally:
        detach()
