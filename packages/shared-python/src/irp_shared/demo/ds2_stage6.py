"""The DS-2 stage-6 demo runner (OD-DS-2-E): the estimator conventions live on the living tenant.

EXTENDS the living demo tenant a SIXTH time (every prior stage byte-untouched). NO new model CODE
(two estimator VERSIONS of ``perf.return.desmoothed_geltner`` — the count pins hold; the model
keeps its campaign tier). The sequence:

1. Seed **``PE-HARBORVIEW-IX``** — a NEW private-equity instrument with **16 quarterly marks**
   GENERATED deterministically at a KNOWN true alpha of 0.4 (a declared true-return cycle
   Geltner-smoothed; fixture-searched at planning so ρ̂₁ ≈ 0.50 > 0 AND the OW m=2 discriminants
   are positive — admissible for BOTH conventions).
2. Run the **DECLARED** demo-mg1 v1 (α=0.4 — coincidentally the generator's true alpha) on the
   series — the three-way comparison baseline.
3. Register + run **AR1_ESTIMATED** (min_periods=8): α̂ ≈ 0.50 vs the true 0.40 — the disclosed
   small-sample UPWARD bias visible live, the ~0.26 band persisted; the dossier claims
   **estimation-with-honest-uncertainty, deliberately NOT recovery** (the planning verifier's R1
   reframe).
4. Register + run **OKUNEV_WHITE_ITERATIVE** (m=2): rows with alpha NULL; the deterministic
   two-pass whitening.
5. File the **2 INITIAL AWC dossiers** for the new versions (evidence = their own COMPLETED runs;
   finding keys fail-loud against the NEW registered limitation rows; next_review_due = +365).
   **NO TRIGGERED re-validation** — census-proved: no existing validation condition names the
   declared-alpha rider (the desmoothing versions carry EXCEPTION-form records without closure
   tokens), so there is nothing to close by supersession; forcing one would be the false ceremony
   HG-1's OQ-5 bars (the deliberate, recorded contrast with the MF-1/RS-1 flywheel).

Idempotency is REFUSE-NOT-SKIP on this stage's OWN footprint — ANY non-DECLARED estimator
convention on the desmoothing family, probed FIRST. Requires the campaign (principals + the
demo-mg1 declared version). The caller owns the ONE commit. The ``stage6`` filename component of
the exercising suites is LOAD-BEARING (alpha-sorts after every prior stage's suites).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.demo.dossiers import DS2_AR1_INITIAL, DS2_OW_INITIAL
from irp_shared.entitlement.models import AppUser, Role, UserRole
from irp_shared.model.models import (
    VALIDATION_TYPE_INITIAL,
    Model,
    ModelLimitation,
    ModelVersion,
)
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)
from irp_shared.perf import (
    DESMOOTHED_RETURN_MODEL_CODE,
    DESMOOTHING_DECLARED_CONVENTION,
    DesmoothedReturnActor,
    declared_desmoothing_parameters,
    register_desmoothed_return_estimated_model,
    register_desmoothed_return_okunev_white_model,
    run_desmoothed_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_CODE_VERSION = "demo-ds2"
_ENVIRONMENT_ID = "demo"
_BASE_CODE_VERSION = "demo-mg1"  # the campaign's declared v1 (alpha=0.4) — the baseline
_REPORT_REF = "10_delivery_backlog/ds_2_decision_record.md"
_T0 = datetime(2022, 1, 1, tzinfo=UTC)

# --- The PE-HARBORVIEW-IX fixture (OD-DS-2-E; TD-1-realistic): 16 quarterly marks GENERATED at
# the KNOWN true alpha 0.4 over a declared true-return cycle (fixture-searched at planning:
# rho-hat_1 = 0.5038 => alpha-hat = 0.4962 vs the true 0.40 — the upward bias VISIBLE; OW m=2
# admissible, c = [0.434, 0.317]). The marks are frozen literals so the demo is byte-stable. ---
_DS2_MARK_DATES: tuple[date, ...] = tuple(
    date(2022, 6, 30) + timedelta(days=91 * i) for i in range(16)
)
_DS2_MARK_VALUES: tuple[str, ...] = (
    "250.00", "255.050000", "259.324638", "262.419937", "269.925567", "278.887355",
    "281.375191", "288.193572", "289.501800", "291.147225", "288.262010", "283.676947",
    "283.295818", "284.381940", "285.570750", "292.409655",
)  # fmt: skip
_ALPHA_TRUE = (
    "0.4"  # the generator's declared smoothing (documentation; never asserted as alpha-hat)
)
_WINDOW = (date(2022, 6, 1), date(2026, 4, 30))
_INSTRUMENT_CODE = "PE-HARBORVIEW-IX"
#: The fixture-drift tripwire: the deterministic draw's alpha-hat (0.4962...) must stay in this
#: band; a drifted fixture (regenerated marks) trips loudly instead of silently changing the story.
_ALPHA_HAT_BAND = (Decimal("0.45"), Decimal("0.55"))


class DemoDs2Error(RuntimeError):
    """Stage 6 could not complete against the live tenant state (fail-loud)."""


class DemoDs2PrereqError(DemoDs2Error):
    """Stage 6 extends the LIVING tenant — it requires the MG-1 campaign (principals + the
    demo-mg1 declared desmoothing version) and never bootstraps it. Run the prior stages first."""


class DemoDs2AlreadySeededError(RuntimeError):
    """Refuse-not-skip on stage 6's OWN footprint: a non-DECLARED estimator convention already
    exists on the desmoothing family. Append-only records are never double-filed."""

    def __init__(self) -> None:
        super().__init__(
            f"demo tenant {DEMO_TENANT_ID} already holds a non-DECLARED estimator convention on "
            f"{DESMOOTHED_RETURN_MODEL_CODE!r} — refusing to re-run stage 6 (reset the schema "
            f"and re-run the full six-stage sequence)."
        )


@dataclass(frozen=True)
class Ds2Stage6Summary:
    """Stage 6's end state (the load-bearing ids + the estimation-story numbers)."""

    tenant_id: str
    estimated_version_id: str
    okunev_white_version_id: str
    declared_run_id: str
    estimated_run_id: str
    okunev_white_run_id: str
    alpha_true: Decimal
    alpha_hat: Decimal
    alpha_stderr: Decimal
    initials_filed: int


def _resolve_principal(session: Session, role_code: str, label: str) -> str:
    rows = session.execute(
        select(AppUser.id)
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(AppUser.tenant_id == DEMO_TENANT_ID, Role.code == role_code)
    ).all()
    if len(rows) != 1:
        raise DemoDs2PrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one "
            f"from the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def _resolve_declared_version(session: Session) -> ModelVersion:
    versions = (
        session.execute(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(
                Model.tenant_id == DEMO_TENANT_ID,
                Model.code == DESMOOTHED_RETURN_MODEL_CODE,
                ModelVersion.code_version == _BASE_CODE_VERSION,
            )
        )
        .scalars()
        .all()
    )
    if len(versions) != 1:
        raise DemoDs2PrereqError(
            f"the demo tenant holds {len(versions)} {_BASE_CODE_VERSION!r} desmoothing "
            f"version(s) — the MG-1 campaign has not run (or drifted); refusing"
        )
    return versions[0]


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
    """The campaign's fail-loud key mechanism (the per-stage duplication precedent — NOT shared
    machinery): each dossier finding KEY must match exactly one REGISTERED limitation row."""
    texts = _registered_limitations(session, version_id)
    findings: list[ValidationFindingInput] = []
    for key in keys:
        matches = [t for t in texts if key in t]
        if len(matches) != 1:
            raise DemoDs2Error(
                f"dossier finding key {key!r} matched {len(matches)} registered limitation "
                f"row(s) of {code} — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


def _require_completed(result: object, label: str) -> None:
    status = getattr(result, "status", None)
    if status != "COMPLETED":
        reason = getattr(result, "failure_reason", None)
        raise DemoDs2Error(f"the {label} did not COMPLETE (status={status!r}, reason={reason!r})")


def run_demo_ds2_stage6(session: Session) -> Ds2Stage6Summary:
    """Execute stage 6 (seed → declared baseline → estimate → whiten → file). The caller owns
    the ONE commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # --- Prereq + footprint probes (refuse-not-skip, BEFORE any write) ---
        model_count = session.execute(
            select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
        ).scalar_one()
        if model_count == 0:
            raise DemoDs2PrereqError(
                f"demo tenant {DEMO_TENANT_ID} holds no model rows — the MG-1 campaign has "
                f"not run; run the prior stages first"
            )
        dm_versions = (
            session.execute(
                select(ModelVersion)
                .join(Model, Model.id == ModelVersion.model_id)
                .where(
                    Model.tenant_id == DEMO_TENANT_ID,
                    Model.code == DESMOOTHED_RETURN_MODEL_CODE,
                )
            )
            .scalars()
            .all()
        )
        if not dm_versions:
            raise DemoDs2PrereqError(
                "the demo tenant holds no desmoothing versions — the MG-1 campaign has not "
                "run; run the prior stages first"
            )
        for existing in dm_versions:
            if (
                declared_desmoothing_parameters(session, existing).estimator_convention
                != DESMOOTHING_DECLARED_CONVENTION
            ):
                raise DemoDs2AlreadySeededError()

        registrar_id = _resolve_principal(session, "risk_analyst_1l", "1L registrar")
        validator_id = _resolve_principal(session, "risk_manager_2l", "2L validator")
        declared_version = _resolve_declared_version(session)

        # --- 1: seed PE-HARBORVIEW-IX (its own portfolio; marks only — desmoothing reads
        # valuations, no position needed) ---
        pf = create_portfolio(
            session,
            tenant_id=DEMO_TENANT_ID,
            code="DEMO-PRIVATE-DS2",
            name="Demo private-asset estimation book (DS-2)",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id=registrar_id),
        ).id
        inst = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=_INSTRUMENT_CODE,
            name="Harborview Capital Partners IX LP",
            asset_class="PRIVATE_EQUITY",
            actor=ReferenceActor(actor_id=registrar_id),
        ).id
        for on, mark in zip(_DS2_MARK_DATES, _DS2_MARK_VALUES, strict=True):
            create_valuation(
                session,
                portfolio_id=pf,
                instrument_id=inst,
                valuation_date=on,
                acting_tenant=DEMO_TENANT_ID,
                actor=ValuationActor(actor_id=registrar_id),
                mark_value=Decimal(mark),
                currency_code="USD",
                valid_from=_T0,
            )
        session.flush()

        def _run(version_id: str, label: str):  # noqa: ANN202
            result = run_desmoothed_return(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=DesmoothedReturnActor(actor_id=registrar_id),
                code_version=_CODE_VERSION,
                environment_id=_ENVIRONMENT_ID,
                model_version_id=version_id,
                portfolio_id=pf,
                instrument_id=inst,
                window_start=_WINDOW[0],
                window_end=_WINDOW[1],
            )
            _require_completed(result, label)
            return result

        # --- 2: the DECLARED baseline (demo-mg1 v1, alpha=0.4 — the generator's true alpha) ---
        declared_run = _run(str(declared_version.id), "DECLARED baseline desmoothing run")

        # --- 3: AR1_ESTIMATED — the estimation with its honest uncertainty, live ---
        est_version = register_desmoothed_return_estimated_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=registrar_id,
            code_version=_CODE_VERSION,
            min_periods=8,
        )
        est_run = _run(str(est_version.id), "AR1_ESTIMATED desmoothing run")
        est_summary = next(r for r in est_run.rows if r.metric_type == "DESMOOTHING_SUMMARY")
        alpha_hat = est_summary.alpha
        alpha_stderr = est_summary.alpha_stderr
        if alpha_hat is None or alpha_stderr is None:
            raise DemoDs2Error("the estimated run's summary lacks alpha-hat/stderr — refusing")
        lo, hi = _ALPHA_HAT_BAND
        if not lo < alpha_hat < hi:
            # The fixture-drift tripwire: the deterministic draw's alpha-hat moved — the
            # generated marks changed; the dossier's numbers would silently lie. Refuse loudly.
            raise DemoDs2Error(
                f"alpha-hat {alpha_hat} outside the fixture band ({lo}, {hi}) — the "
                f"PE-HARBORVIEW-IX marks drifted; refusing"
            )

        # --- 4: OKUNEV_WHITE_ITERATIVE — the deterministic whitening ---
        ow_version = register_desmoothed_return_okunev_white_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=registrar_id,
            code_version=_CODE_VERSION,
            ow_max_order=2,
        )
        ow_run = _run(str(ow_version.id), "OKUNEV_WHITE_ITERATIVE desmoothing run")
        if any(r.alpha is not None for r in ow_run.rows):
            raise DemoDs2Error("an OW row carries a non-NULL alpha — refusing")

        # --- 5: the 2 INITIAL AWCs (NO TRIGGERED — the recorded no-closable-condition honesty;
        # see the module docstring) ---
        today = utcnow().date()
        v_actor = ModelValidationActor(actor_id=validator_id)
        document = ValidationEvidenceInput(
            evidence_type="DOCUMENT",
            reference=f"{_REPORT_REF} (OD-DS-2-E: the ratified stage-6 shape this record "
            f"transcribes)",
        )
        initials = 0
        for version_obj, dossier, run_id in (
            (est_version, DS2_AR1_INITIAL, est_run.run.run_id),
            (ow_version, DS2_OW_INITIAL, ow_run.run.run_id),
        ):
            record_validation(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=v_actor,
                request=RecordValidationRequest(
                    model_version_id=version_obj.id,
                    validation_type=VALIDATION_TYPE_INITIAL,
                    outcome=dossier.outcome,
                    scope_summary=dossier.scope_note,
                    conditions=dossier.conditions,
                    report_ref=_REPORT_REF,
                    next_review_due=today + timedelta(days=365),
                    findings=_findings_from_registry(
                        session,
                        str(version_obj.id),
                        dossier.finding_keys,
                        DESMOOTHED_RETURN_MODEL_CODE,
                    ),
                    evidence=(
                        ValidationEvidenceInput(
                            evidence_type="CALCULATION_RUN", run_id=str(run_id)
                        ),
                        document,
                    ),
                ),
            )
            initials += 1

        return Ds2Stage6Summary(
            tenant_id=DEMO_TENANT_ID,
            estimated_version_id=str(est_version.id),
            okunev_white_version_id=str(ow_version.id),
            declared_run_id=str(declared_run.run.run_id),
            estimated_run_id=str(est_run.run.run_id),
            okunev_white_run_id=str(ow_run.run.run_id),
            alpha_true=Decimal(_ALPHA_TRUE),
            alpha_hat=alpha_hat,
            alpha_stderr=alpha_stderr,
            initials_filed=initials,
        )
    finally:
        detach()
