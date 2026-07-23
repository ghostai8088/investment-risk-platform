"""The PPF-3 stage-13 demo runner: the UNIFIED public+private parametric VaR — the §2.1 arc's
CAPSTONE (``risk.var.parametric_unified``, the TWENTIETH governed number, OD-PPF-3).

EXTENDS the living demo tenant a THIRTEENTH time (every prior stage byte-untouched). Unlike the
PPF-2 stage (one covariance run over existing segments), this stage stands up a fresh two-fund book
and a whole public chain, then contrasts the total and unified numbers.

- Seeds ONE new portfolio ``DEMO-UNIFIED-PPF3`` holding BOTH existing demo private funds —
  **PE-HARBOR-IV** (PRIVATE_EQUITY, proxied to FX_USD) + **PC-BRIDGEWATER-II** (PRIVATE_CREDIT,
  proxied to MF_RATES_GOV + MF_CRSPD_IG) — with boundary valuations under the new ``portfolio_id``
  (ZERO new instruments / segments / Ω_pp — all reused, the OQ-3=B two-fund book).
- Runs a fresh public chain over the UNION factor set {FX_USD, MF_RATES_GOV, MF_CRSPD_IG}: exposure
  → LOADINGS factor-exposure (the multi-family projection; PPF-1 guard 1 keeps the PRIVATE segment
  memberships OUT of the public snapshot) → the campaign's window-30 DAILY covariance (REUSED — its
  ``version_label`` is fixed "v1", so a smaller window cannot be minted; the stage instead extends
  FX_USD's daily returns 5 days so the FX×MF overlap reaches the 30 aligned obs the window needs).
- Runs BOTH ``risk.var.parametric_total`` (the PA-4 contrast) AND ``run_var_unified`` (consuming the
  tenant-wide Ω_pp), and asserts **σ_unified ≠ σ_total** — they differ by exactly the cross-segment
  pure-private co-movement ``2·p_PE·p_PC·Ω_pp[PE,PC]/d_t`` (the headline; the correlated private
  risk that independent-diagonal total VaR misses — non-trivial ONLY with ≥2 private segments).

GOVERNED-NUMBER stage (the CC-2 / PPF-2 shape): it mints the 23rd model code
(``risk.var.parametric_unified``, the 20th governed number), files ONE INITIAL AWC, and completes
the chain's runs. Counts move **22/37/104 → 23/38/109** (the chain fires exposure + factor-exposure
+ covariance + total-VaR + unified-VaR = 5 runs; the exercising ``_pg`` suite pins the exact total).
The loadings/covariance/total models are RESOLVED (reused — one fixed-"v1" version each); ONLY the
unified CODE is new ⇒ +1 code, and only it is tiered + carries the INITIAL AWC ⇒ +1 record.

Idempotency is REFUSE-NOT-SKIP on this stage's OWN footprint (the ``DEMO-UNIFIED-PPF3`` portfolio,
probed FIRST). Requires PPF-1 (the seeded pure-private segments + fund proxies) and PPF-2 (the
tenant-wide Ω_pp). The caller owns the ONE commit. **The ``stage9zzzz`` filename component of the
exercising suites is LOAD-BEARING** (alpha-sorts AFTER ``stage9zzz`` — the stage-10 zero-pad hazard;
one more ``z`` than PPF-2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.demo.dossiers import PPF3_UNIFIED_VAR_INITIAL, PPF3_UNIFIED_VAR_TIER
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import FactorActor, capture_factor_return, resolve_factor
from irp_shared.marketdata.models import Factor
from irp_shared.model.models import VALIDATION_TYPE_INITIAL, Model, ModelLimitation, ModelVersion
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.portfolio.models import Portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.models import Instrument
from irp_shared.risk import (
    COVARIANCE_MODEL_CODE,
    FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    VAR_TOTAL_MODEL_CODE,
    CovarianceActor,
    FactorExposureActor,
    VarActor,
    register_var_parametric_unified_model,
    run_covariance,
    run_factor_exposure,
    run_var,
    run_var_unified,
)
from irp_shared.risk.events import RUN_TYPE_COVARIANCE_PRIVATE
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_CODE_VERSION = "demo-ppf3"
_ENVIRONMENT_ID = "demo"
_ACTOR_ID = "demo-ppf3-runner"
_REPORT_REF = "10_delivery_backlog/ppf_3_decision_record.md"

_PORTFOLIO_CODE = "DEMO-UNIFIED-PPF3"
#: The union DAILY covariance reuses the campaign's window-30 ``risk.covariance.sample`` (its
#: version_label is fixed "v1" — a smaller window cannot be minted). The campaign's FX_USD daily
#: returns end 2026-05-25 while the MF factors span 2026-05-01…06-20 — only a 25-obs overlap. So
#: this stage extends FX_USD forward 5 days (continuing the campaign cycle) to make
#: {FX_USD} ∩ {MF_*} = 2026-05-01…05-30 = 30 aligned obs, and runs the covariance as-of 05-30.
_AS_OF = date(2026, 5, 30)
_FX_USD_EXTENSION: tuple[tuple[date, str], ...] = (
    (date(2026, 5, 26), "0.0007"),
    (date(2026, 5, 27), "-0.0015"),
    (date(2026, 5, 28), "0.0038"),
    (date(2026, 5, 29), "-0.0042"),
    (date(2026, 5, 30), "0.0019"),
)
_CONFIDENCE = "0.99"  # the demo VaR confidence (no new confidence vocabulary minted)
_APPRAISAL_DAYS = 91  # quarterly — the Ω_pp appraisal→daily de-scale (d_t = 91·252/365)
_MAX_ESTIMATE_AGE_DAYS = 400
_UNION_FACTOR_CODES: tuple[str, ...] = ("FX_USD", "MF_RATES_GOV", "MF_CRSPD_IG")
#: (instrument_code, quantity, USD boundary mark) for the two EXISTING demo private funds.
_FUNDS: tuple[tuple[str, str, str], ...] = (
    ("PE-HARBOR-IV", "50", "1080.00"),
    ("PC-BRIDGEWATER-II", "60", "1000.00"),
)
_T0 = datetime(2024, 6, 1, tzinfo=UTC)


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


class DemoPpf3Error(RuntimeError):
    """Base class for stage-13 refusals."""


class DemoPpf3AlreadySeededError(DemoPpf3Error):
    """The stage-13 footprint (the ``DEMO-UNIFIED-PPF3`` portfolio) already exists — REFUSE."""


class DemoPpf3PrereqError(DemoPpf3Error):
    """A stage-13 prerequisite is missing (run PPF-1 + PPF-2 first) or a tripwire fired."""


@dataclass(frozen=True)
class Ppf3Stage13Summary:
    tenant_id: str
    portfolio_id: str
    unified_model_version_id: str
    unified_run_id: str
    total_run_id: str
    exposure_run_id: str
    factor_exposure_run_id: str
    covariance_run_id: str
    private_covariance_run_id: str
    sigma_unified: Decimal
    sigma_total: Decimal
    private_variance: Decimal
    #: σ²_unified − σ²_total — the cross-segment pure-private co-movement headline (signed).
    variance_delta: Decimal
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
        raise DemoPpf3PrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one from "
            f"the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def _resolve_instrument(session: Session, code: str) -> str:
    inst_id = session.execute(
        select(Instrument.id).where(Instrument.tenant_id == DEMO_TENANT_ID, Instrument.code == code)
    ).scalar_one_or_none()
    if inst_id is None:
        raise DemoPpf3PrereqError(f"instrument {code!r} is not seeded — run the campaign first")
    return str(inst_id)


def _resolve_factor(session: Session, code: str) -> str:
    fid = session.execute(
        select(Factor.id).where(
            Factor.tenant_id == DEMO_TENANT_ID,
            Factor.factor_code == code,
            Factor.valid_to.is_(None),  # the EV active window
        )
    ).scalar_one_or_none()
    if fid is None:
        raise DemoPpf3PrereqError(f"factor {code!r} is not seeded — run the campaign first")
    return str(fid)


def _resolve_version_by_code(session: Session, code: str) -> str:
    """The single REGISTERED ``model_version`` for a demo model code. These families fix their
    ``version_label`` at "v1", so there is exactly one version per code — RESOLVE it (a new
    ``code_version`` cannot mint a second, and this stage adds no new supporting codes)."""
    vid = session.execute(
        select(ModelVersion.id)
        .join(Model, Model.id == ModelVersion.model_id)
        .where(Model.tenant_id == DEMO_TENANT_ID, Model.code == code)
    ).scalar_one_or_none()
    if vid is None:
        raise DemoPpf3PrereqError(f"model code {code!r} is not registered — run the campaign first")
    return str(vid)


def _resolve_omega_pp_run(session: Session) -> str:
    """The tenant-wide Ω_pp run (PPF-2 stage 12; exactly one COMPLETED ``COVARIANCE_PRIVATE``)."""
    run_id = session.execute(
        select(CalculationRun.run_id).where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == RUN_TYPE_COVARIANCE_PRIVATE,
            CalculationRun.status == RunStatus.COMPLETED.value,
        )
    ).scalar_one_or_none()
    if run_id is None:
        raise DemoPpf3PrereqError(
            "no COMPLETED private covariance (Ω_pp) run in the demo tenant — run PPF-2 first"
        )
    return str(run_id)


def _findings_from_registry(
    session: Session, version_id: str, keys: tuple[str, ...]
) -> tuple[ValidationFindingInput, ...]:
    """The campaign's fail-loud key mechanism (the CC-2/PPF-1/PPF-2 precedent): each dossier finding
    KEY must match exactly one REGISTERED limitation row, whose text becomes the finding."""
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
            raise DemoPpf3PrereqError(
                f"dossier finding key {key!r} matched {len(matches)} registered unified-VaR "
                f"limitation row(s) — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


def _require_completed(result: object, label: str) -> None:
    status = getattr(result, "status", None)
    if status != RunStatus.COMPLETED.value:
        reason = getattr(result, "failure_reason", None)
        raise DemoPpf3PrereqError(f"{label} did not complete: {reason}")


def run_demo_ppf3_stage13(session: Session) -> Ppf3Stage13Summary:
    """Execute stage 13 (seed the two-fund book → public chain → total + unified → assert the
    cross-segment headline → tier + file the INITIAL AWC). The caller owns the ONE commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # --- Footprint probe (refuse-not-skip, BEFORE any write) ---
        existing = session.execute(
            select(Portfolio.id).where(
                Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _PORTFOLIO_CODE
            )
        ).first()
        if existing is not None:
            raise DemoPpf3AlreadySeededError(
                f"stage 13 footprint already present (the {_PORTFOLIO_CODE} portfolio exists) — "
                f"refusing to re-seed (refuse-not-skip)"
            )

        registrar = _resolve_principal(session, "risk_analyst_1l", "registrar/1L")
        validator = _resolve_principal(session, "risk_manager_2l", "2L validator")

        # --- Resolve the reused substrate (funds + union factors + Ω_pp) ---
        fund_ids = {code: _resolve_instrument(session, code) for code, _q, _m in _FUNDS}
        factor_ids = [_resolve_factor(session, code) for code in _UNION_FACTOR_CODES]
        omega_pp_run_id = _resolve_omega_pp_run(session)

        # --- Seed the two-fund book: ONE new portfolio + positions + boundary marks (USD) ---
        portfolio_id = create_portfolio(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=_PORTFOLIO_CODE,
            name="Unified public+private VaR demo book (PPF-3)",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id=registrar),
        ).id
        for code, qty, mark in _FUNDS:
            create_position(
                session,
                portfolio_id=portfolio_id,
                instrument_id=fund_ids[code],
                acting_tenant=DEMO_TENANT_ID,
                actor=PositionActor(actor_id=registrar),
                quantity=Decimal(qty),
                valid_from=_T0,
            )
            create_valuation(
                session,
                portfolio_id=portfolio_id,
                instrument_id=fund_ids[code],
                valuation_date=_AS_OF,
                acting_tenant=DEMO_TENANT_ID,
                actor=ValuationActor(actor_id=registrar),
                mark_value=Decimal(mark),
                currency_code="USD",
                valid_from=_T0,
            )
        session.flush()

        # Extend FX_USD's daily returns 5 days forward so {FX_USD} ∩ {MF_*} = 30 aligned obs at
        # as-of 05-30 (the reused window-30 covariance needs them; captured input, not a governed
        # run — the count is unaffected). The MF factors already span this range.
        fx_usd_factor = resolve_factor(session, factor_ids[0], acting_tenant=DEMO_TENANT_ID)
        for on, value in _FX_USD_EXTENSION:
            capture_factor_return(
                session,
                fx_usd_factor,
                return_date=on,
                return_value=Decimal(value),
                acting_tenant=DEMO_TENANT_ID,
                actor=FactorActor(actor_id=_ACTOR_ID),
                valid_from=_T0,
            )
        session.flush()

        # --- The public chain over the UNION factor set (reused loadings/covariance/total models;
        # only the unified CODE is new) ---
        exposure = run_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ExposureActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            portfolio_id=portfolio_id,
            as_of_valid_at=_dt(_AS_OF),
            base_currency="USD",
        )
        _require_completed(exposure, "stage-13 exposure run")

        loadings = run_factor_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=FactorExposureActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=_resolve_version_by_code(session, FACTOR_EXPOSURE_LOADINGS_MODEL_CODE),
            exposure_run_id=exposure.run.run_id,
            factor_ids=factor_ids,
        )
        _require_completed(loadings, "stage-13 loadings factor-exposure run")

        covariance = run_covariance(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=CovarianceActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=_resolve_version_by_code(session, COVARIANCE_MODEL_CODE),
            factor_ids=factor_ids,
            as_of_valid_at=_dt(_AS_OF),
        )
        _require_completed(covariance, "stage-13 union covariance run")

        # --- The PA-4 total-VaR contrast (residual leg over BOTH proxied funds) ---
        total = run_var(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=VarActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=_resolve_version_by_code(session, VAR_TOTAL_MODEL_CODE),
            exposure_run_id=loadings.run.run_id,
            covariance_run_id=covariance.run.run_id,
        )
        _require_completed(total, "stage-13 total-VaR contrast run")

        # --- The unified public+private number (the capstone; repartitions the residual) ---
        unified_model = register_var_parametric_unified_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=registrar,
            code_version=_CODE_VERSION,
            confidence_level=_CONFIDENCE,
            appraisal_days=_APPRAISAL_DAYS,
            max_estimate_age_days=_MAX_ESTIMATE_AGE_DAYS,
        )
        unified = run_var_unified(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=VarActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=str(unified_model.id),
            exposure_run_id=loadings.run.run_id,
            covariance_run_id=covariance.run.run_id,
            private_covariance_run_id=omega_pp_run_id,
        )
        _require_completed(unified, "stage-13 unified-VaR run")

        total_row = total.rows[0]
        unified_row = unified.rows[0]
        if total_row.metric_type != METRIC_TYPE_VAR_PARAMETRIC_TOTAL:
            raise DemoPpf3PrereqError(f"total row metric_type is {total_row.metric_type!r}")
        if unified_row.metric_type != METRIC_TYPE_VAR_PARAMETRIC_UNIFIED:
            raise DemoPpf3PrereqError(f"unified row metric_type is {unified_row.metric_type!r}")
        # Parametric rows always carry sigma; the unified row always carries the private block.
        # Guard (narrows the Decimal | None columns AND fails closed on a degenerate row).
        if (
            unified_row.sigma is None
            or total_row.sigma is None
            or unified_row.private_variance is None
        ):
            raise DemoPpf3PrereqError("a parametric VaR row is missing sigma / private_variance")
        # THE HEADLINE: the unified number differs from the total over the SAME book by the
        # cross-segment pure-private co-movement — a non-trivial delta only with >= 2 segments.
        if unified_row.sigma == total_row.sigma:
            raise DemoPpf3PrereqError(
                "σ_unified == σ_total — the two-fund cross-segment term did not move the number "
                "(expected a non-trivial difference; is Ω_pp off-diagonal zero?)"
            )
        variance_delta = unified_row.sigma * unified_row.sigma - total_row.sigma * total_row.sigma

        # --- Tier + the INITIAL AWC (NEW code ⇒ SOME record; the MG-1/CC-2/PPF-2 precedent) ---
        assign_model_tier(
            session,
            acting_tenant=DEMO_TENANT_ID,
            model_id=str(unified_model.model_id),
            materiality_rating=PPF3_UNIFIED_VAR_TIER.materiality_rating,
            complexity_rating=PPF3_UNIFIED_VAR_TIER.complexity_rating,
            rationale=PPF3_UNIFIED_VAR_TIER.rationale,
            actor_id=validator,
        )
        findings = _findings_from_registry(
            session, str(unified_model.id), PPF3_UNIFIED_VAR_INITIAL.finding_keys
        )
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ModelValidationActor(actor_id=validator),
            request=RecordValidationRequest(
                model_version_id=unified_model.id,
                validation_type=VALIDATION_TYPE_INITIAL,
                outcome=PPF3_UNIFIED_VAR_INITIAL.outcome,
                scope_summary=PPF3_UNIFIED_VAR_INITIAL.scope_note,
                conditions=PPF3_UNIFIED_VAR_INITIAL.conditions,
                report_ref=_REPORT_REF,
                next_review_due=date(2026, 7, 22) + timedelta(days=365),
                findings=findings,
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="CALCULATION_RUN", run_id=str(unified.run.run_id)
                    ),
                ),
            ),
        )

        return Ppf3Stage13Summary(
            tenant_id=DEMO_TENANT_ID,
            portfolio_id=str(portfolio_id),
            unified_model_version_id=str(unified_model.id),
            unified_run_id=str(unified.run.run_id),
            total_run_id=str(total.run.run_id),
            exposure_run_id=str(exposure.run.run_id),
            factor_exposure_run_id=str(loadings.run.run_id),
            covariance_run_id=str(covariance.run.run_id),
            private_covariance_run_id=omega_pp_run_id,
            sigma_unified=unified_row.sigma,
            sigma_total=total_row.sigma,
            private_variance=unified_row.private_variance,
            variance_delta=variance_delta,
            initials_filed=1,
        )
    finally:
        detach()
