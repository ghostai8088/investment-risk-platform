"""The HG-1 stage-3 demo runner (OD-HG-1-D): the genuinely-private α=0.4 chain on multi-family
factors — the one combination neither prior stage exercises (the campaign's PE fund desmooths at
α=0.4 on CURRENCY factors only; the MF-1 sleeve used PUBLIC instruments via the α=1 identity).

EXTENDS the living demo tenant a THIRD time (campaign + multifamily stay byte-untouched): a NEW
private-credit instrument (`PC-BRIDGEWATER-II`) joins the multi-asset sleeve with 8 QUARTERLY
appraisal marks 2024-06-30…2026-03-31 (START-extended — the planning verifier killed the
end-extended draft: the 2026-06-19 carry mark must sit OUTSIDE the desmoothing window, the mint
must cover period ends = marks 3..8, and the estimate age must be a real +80 days, never a
look-ahead), a carry mark ON the sleeve boundary 2026-06-19, and the 18-row quarterly factor-
return mint (one SIMPLE return per desmoothed-period-end per MF factor — the campaign's
`_OLS_RETURN_DATES` precedent; every minted date ≤ 2026-03-31, provably invisible to all daily
windows). The chain reuses SHIPPED versions only (`demo-mg1` α=0.4 desmoothing / regression /
covariance / the five VaR flagships; `demo-mf1` loadings) — stage 3 registers NOTHING: α=0.4
desmooth → k=3 Sharpe-1992 OLS on the full MF palette → the analyst promotes the STRUCTURAL
RATES + CREDIT_SPREAD coefficients (one estimate run, NO promotion-age bound — the OD-A gate is
exercised by its tests with controlled dates, never by demo seeds) → a fresh 4-atom exposure run
→ the loadings-family run → covariance → the five flagship numbers. NO validation record is
filed (OQ-HG-1-5: every bound version carries a live latest outcome; the runs ARE the
demonstration).

Mark generation is honest at α=0.4 (the ratified V7 fold): observed marks are PRE-SMOOTHED from
a declared true-return structure `r_obs_t = α·r_true_t + (1−α)·r_obs_{t−1}` with NO idiosyncratic
term (at df=2 any useful eps amplitude swamps recovery; the only noise is 6dp mark quantization,
amplified ×1/α=2.5 by the inversion), `r_true_t = 0.5·RATES_q + 0.7·CREDIT_SPREAD_q` — the
desmoothing inversion recovers r_true exactly modulo rounding, so the OLS recovers the structure
within |β̂−β| ≤ 0.05 (asserted in the suite).

Idempotency is REFUSE-NOT-SKIP on this stage's OWN footprint — the new instrument's code, seeded
FIRST (any partially-committed state contains the probe); refuses without BOTH prior stages. The
caller owns the ONE commit. The flywheel grep token appears in nothing this module writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    FactorActor,
    ProxyMappingActor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.marketdata.models import Factor
from irp_shared.model.models import Model, ModelVersion
from irp_shared.perf import DesmoothedReturnActor, run_desmoothed_return
from irp_shared.portfolio.models import Portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
    METRIC_TYPE_WEIGHT,
    CovarianceActor,
    FactorExposureActor,
    ProxyWeightEstimateActor,
    VarActor,
    list_proxy_weight_results,
    promote_proxy_weight_estimate,
    run_covariance,
    run_factor_exposure,
    run_proxy_weight_estimate,
    run_var,
    run_var_historical,
)
from irp_shared.snapshot import build_var_hs_snapshot
from irp_shared.snapshot.events import SnapshotActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_CODE_VERSION = "demo-hg1"
_ENVIRONMENT_ID = "demo"
_BASE_CODE_VERSION = "demo-mg1"  # the campaign versions (α=0.4 / regression / covariance / VaR)
_MF_CODE_VERSION = "demo-mf1"  # the extension's loadings version
_T0 = datetime(2024, 6, 1, tzinfo=UTC)  # the campaign validity base — before every economic as-of

_INSTRUMENT_CODE = "PC-BRIDGEWATER-II"
_SLEEVE_PORTFOLIO_CODE = "DEMO-MULTIASSET"
_MF_FACTOR_CODES = ("MF_MKT_BROAD", "MF_RATES_GOV", "MF_CRSPD_IG")
_BASE_CURRENCY = "USD"

# --- The quarterly calendar (V2-redesigned): 8 marks ⇒ 7 observed ⇒ 6 desmoothed periods with
# ends = marks 3..8; the desmoothing window is the campaign's exact shape, excluding the
# 2026-06-19 carry mark; every minted return date ≤ 2026-03-31. ---
_MARK_DATES: tuple[date, ...] = (
    date(2024, 6, 30),
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
    date(2026, 3, 31),
)
_CARRY_DATE = date(2026, 6, 19)  # the sleeve exposure boundary — OUTSIDE the window below
_DESMOOTH_WINDOW = (date(2024, 6, 1), date(2026, 4, 30))
_ALPHA = Decimal("0.4")
_SIX_DP = Decimal("0.000001")

#: The declared quarterly factor paths, aligned to the 7 inter-mark periods (ends = marks 2..8);
#: the mint captures the LAST SIX (ends = marks 3..8 — the desmoothed periods). TD-1-plausible.
_Q_MKT = ("0.031", "-0.018", "-0.024", "0.012", "0.026", "0.019", "-0.008")
_Q_RATES = ("-0.006", "0.011", "0.004", "-0.009", "0.007", "-0.003", "0.010")
_Q_CRSPD = ("0.008", "-0.004", "0.012", "0.006", "-0.011", "0.009", "0.005")
_QUARTERLY_PATHS: dict[str, tuple[str, ...]] = {
    "MF_MKT_BROAD": _Q_MKT,
    "MF_RATES_GOV": _Q_RATES,
    "MF_CRSPD_IG": _Q_CRSPD,
}
#: The structural loadings the OLS recovers (private credit: duration + spread duration),
#: plus a constant quarterly income carry (review fold: private-credit NAVs accrete; the
#: kernel fits an intercept, which absorbs the carry EXACTLY — slope recovery unchanged).
_STRUCTURE: dict[str, str] = {"MF_RATES_GOV": "0.5", "MF_CRSPD_IG": "0.7"}
_QUARTERLY_CARRY = Decimal("0.02")
_START_MARK = Decimal("100.00")
_QUANTITY = Decimal("60")


def _mark_series() -> tuple[Decimal, ...]:
    """Pre-smoothed appraisal marks (the module docstring's recursion; pure Decimal, 6dp)."""
    alpha = _ALPHA
    marks = [_START_MARK]
    r_obs_prev: Decimal | None = None
    for i in range(len(_MARK_DATES) - 1):
        r_true = _QUARTERLY_CARRY + sum(
            (Decimal(w) * Decimal(_QUARTERLY_PATHS[code][i]) for code, w in _STRUCTURE.items()),
            Decimal("0"),
        )
        r_obs = r_true if r_obs_prev is None else alpha * r_true + (1 - alpha) * r_obs_prev
        marks.append((marks[-1] * (1 + r_obs)).quantize(_SIX_DP, rounding=ROUND_HALF_UP))
        r_obs_prev = r_obs
    return tuple(marks)


class DemoHg1Error(RuntimeError):
    """A stage-3 step did not produce the state the ratified sequence requires (fail-loud)."""


class DemoHg1PrereqError(RuntimeError):
    """Stage 3 extends the LIVING tenant — it requires BOTH prior stages (the MG-1 campaign and
    the MF-1 extension) and never bootstraps either. Run them first."""


class DemoHg1AlreadySeededError(RuntimeError):
    """Refuse-not-skip on stage 3's OWN footprint: the private-credit instrument already exists.
    Append-only records are never double-filed; reset the schema and re-run all three stages."""

    def __init__(self) -> None:
        super().__init__(
            f"demo tenant {DEMO_TENANT_ID} already holds instrument {_INSTRUMENT_CODE!r} — "
            f"refusing to re-run stage 3 (reset the schema and re-run campaign + extension + "
            f"stage 3)."
        )


@dataclass(frozen=True)
class Hg1PrivateSummary:
    """Stage 3's end state (counts + the load-bearing ids)."""

    tenant_id: str
    instrument_id: str
    desmoothed_run_id: str
    estimate_run_id: str
    promoted_loadings: int
    exposure_run_id: str
    loadings_run_id: str
    covariance_run_id: str
    flagship_run_ids: dict[str, str]
    minted_return_rows: int


# The small helpers below are DUPLICATED from campaign.py/multifamily.py, not imported —
# both prior stages are byte-frozen fences and the raising helpers must raise stage-3-typed
# errors (the recorded MF-1 adjudication, applied again).
def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _require_completed(result: object, label: str) -> None:
    status = getattr(result, "status", None)
    if status != "COMPLETED":
        reason = getattr(result, "failure_reason", None)
        raise DemoHg1Error(f"{label} did not COMPLETE (status={status!r}, reason={reason!r})")


def _resolve_version(session: Session, code: str, code_version: str) -> ModelVersion:
    versions = (
        session.execute(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(
                Model.tenant_id == DEMO_TENANT_ID,
                Model.code == code,
                ModelVersion.code_version == code_version,
            )
        )
        .scalars()
        .all()
    )
    if len(versions) != 1:
        raise DemoHg1PrereqError(
            f"the demo tenant holds {len(versions)} {code_version!r} version(s) of {code!r} — "
            f"expected exactly one from the prior stages; run campaign + extension first"
        )
    return versions[0]


def _resolve_principal(session: Session) -> str:
    from irp_shared.entitlement.models import AppUser, Role, UserRole

    rows = session.execute(
        select(AppUser.id)
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(AppUser.tenant_id == DEMO_TENANT_ID, Role.code == "risk_analyst_1l")
    ).all()
    if len(rows) != 1:
        raise DemoHg1PrereqError(
            f"the demo tenant holds {len(rows)} 1L registrar principal(s) — expected exactly "
            f"one from the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def run_demo_hg1_private(session: Session) -> Hg1PrivateSummary:
    """Execute stage 3 against the LIVING demo tenant. The caller owns the ONE commit; the
    runner arms (and re-arms) the tenant context itself (the campaign's context contract —
    a caller with its own persistent context must re-arm after this returns)."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        model_count = session.execute(
            select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
        ).scalar_one()
        if not model_count:
            raise DemoHg1PrereqError(
                f"demo tenant {DEMO_TENANT_ID} holds no model rows — the MG-1 campaign has not "
                f"been seeded; stage 3 never bootstraps"
            )
        loadings_present = session.execute(
            select(func.count())
            .select_from(Model)
            .where(
                Model.tenant_id == DEMO_TENANT_ID,
                Model.code == FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
            )
        ).scalar_one()
        if not loadings_present:
            raise DemoHg1PrereqError(
                "the loadings model is not registered — the MF-1 extension has not run; "
                "stage 3 requires both prior stages"
            )
        already = session.execute(
            select(func.count())
            .select_from(Instrument)
            .where(Instrument.tenant_id == DEMO_TENANT_ID, Instrument.code == _INSTRUMENT_CODE)
        ).scalar_one()
        if already:
            raise DemoHg1AlreadySeededError()

        sleeve = session.execute(
            select(Portfolio).where(
                Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _SLEEVE_PORTFOLIO_CODE
            )
        ).scalar_one_or_none()
        if sleeve is None:
            raise DemoHg1PrereqError(
                f"the sleeve portfolio {_SLEEVE_PORTFOLIO_CODE!r} is absent — the MF-1 "
                f"extension has not run"
            )
        factors = {
            f.factor_code: f
            for f in session.execute(
                select(Factor).where(
                    Factor.tenant_id == DEMO_TENANT_ID,
                    Factor.factor_code.in_(_MF_FACTOR_CODES),
                )
            )
            .scalars()
            .all()
        }
        if set(factors) != set(_MF_FACTOR_CODES):
            raise DemoHg1PrereqError(
                f"the MF factor set is incomplete ({sorted(factors)}) — the MF-1 extension has "
                f"not run"
            )
        actor_id = _resolve_principal(session)

        # --- The book: the instrument is the FIRST write (the footprint probe object). ---
        inst = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=_INSTRUMENT_CODE,
            name="Bridgewater Private Credit Fund II LP interest",
            asset_class="PRIVATE_CREDIT",
            actor=ReferenceActor(actor_id=actor_id),
        ).id
        create_position(
            session,
            portfolio_id=sleeve.id,
            instrument_id=inst,
            acting_tenant=DEMO_TENANT_ID,
            actor=PositionActor(actor_id=actor_id),
            quantity=_QUANTITY,
            valid_from=_T0,
        )
        marks = _mark_series()
        for on, value in zip(_MARK_DATES, marks, strict=True):
            create_valuation(
                session,
                portfolio_id=sleeve.id,
                instrument_id=inst,
                valuation_date=on,
                acting_tenant=DEMO_TENANT_ID,
                actor=ValuationActor(actor_id=actor_id),
                mark_value=value,
                currency_code=_BASE_CURRENCY,
                valid_from=_T0,
            )
        # The carry mark at the sleeve boundary — OUTSIDE the desmoothing window.
        create_valuation(
            session,
            portfolio_id=sleeve.id,
            instrument_id=inst,
            valuation_date=_CARRY_DATE,
            acting_tenant=DEMO_TENANT_ID,
            actor=ValuationActor(actor_id=actor_id),
            mark_value=marks[-1],
            currency_code=_BASE_CURRENCY,
            valid_from=_T0,
        )
        # The 18-row quarterly mint: one SIMPLE return per desmoothed-period-end per factor
        # (ends = marks 3..8; values = the declared paths the generator consumed).
        minted = 0
        for code in _MF_FACTOR_CODES:
            factor = resolve_factor(session, factors[code].id, acting_tenant=DEMO_TENANT_ID)
            for i, on in enumerate(_MARK_DATES[2:]):  # period ends = marks 3..8
                capture_factor_return(
                    session,
                    factor,
                    return_date=on,
                    return_value=Decimal(_QUARTERLY_PATHS[code][i + 1]),
                    acting_tenant=DEMO_TENANT_ID,
                    actor=FactorActor(actor_id=actor_id),
                    valid_from=_T0,
                )
                minted += 1
        session.flush()

        # --- The chain: α=0.4 desmooth → k=3 OLS → promote structural → runs. ---
        dm = run_desmoothed_return(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=DesmoothedReturnActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=str(
                _resolve_version(session, "perf.return.desmoothed_geltner", _BASE_CODE_VERSION).id
            ),
            portfolio_id=sleeve.id,
            instrument_id=inst,
            window_start=_DESMOOTH_WINDOW[0],
            window_end=_DESMOOTH_WINDOW[1],
        )
        _require_completed(dm, "alpha=0.4 desmoothed-return run (stage 3)")

        est = run_proxy_weight_estimate(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ProxyWeightEstimateActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=str(
                _resolve_version(session, "risk.proxy_weight.regression", _BASE_CODE_VERSION).id
            ),
            desmoothed_run_id=dm.run.run_id,
            factor_ids=[str(factors[c].id) for c in _MF_FACTOR_CODES],
        )
        _require_completed(est, "k=3 proxy-weight estimate run (stage 3)")
        weights = {
            str(r.factor_id).lower(): r.metric_value
            for r in list_proxy_weight_results(
                session, est.run.run_id, acting_tenant=DEMO_TENANT_ID
            )
            if r.metric_type == METRIC_TYPE_WEIGHT
        }
        promoted = 0
        for code in _STRUCTURE:
            fid = str(factors[code].id)
            weight = weights.get(fid.lower())
            if weight is None:
                raise DemoHg1Error(f"the estimate produced no WEIGHT row for {code} — refusing")
            promote_proxy_weight_estimate(
                session,
                private_instrument_id=inst,
                factor_id=fid,
                weight=weight,
                acting_tenant=DEMO_TENANT_ID,
                actor=ProxyMappingActor(actor_id=actor_id),
                source_calculation_run_id=est.run.run_id,
            )
            promoted += 1

        exposure = run_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ExposureActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            portfolio_id=sleeve.id,
            as_of_valid_at=_dt(_CARRY_DATE),
            base_currency=_BASE_CURRENCY,
        )
        _require_completed(exposure, "stage-3 sleeve exposure run (4 atoms)")

        loadings = run_factor_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=FactorExposureActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=str(
                _resolve_version(session, FACTOR_EXPOSURE_LOADINGS_MODEL_CODE, _MF_CODE_VERSION).id
            ),
            exposure_run_id=exposure.run.run_id,
            factor_ids=[str(factors[c].id) for c in _MF_FACTOR_CODES],
        )
        _require_completed(loadings, "stage-3 loadings-family run")

        cov = run_covariance(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=CovarianceActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=str(
                _resolve_version(session, "risk.covariance.sample", _BASE_CODE_VERSION).id
            ),
            factor_ids=[str(factors[c].id) for c in _MF_FACTOR_CODES],
            as_of_valid_at=_dt(_CARRY_DATE),
        )
        _require_completed(cov, "stage-3 covariance run")

        def _var_run(code: str, label: str) -> str:
            result = run_var(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=VarActor(actor_id=actor_id),
                code_version=_CODE_VERSION,
                environment_id=_ENVIRONMENT_ID,
                model_version_id=str(_resolve_version(session, code, _BASE_CODE_VERSION).id),
                exposure_run_id=loadings.run.run_id,
                covariance_run_id=cov.run.run_id,
            )
            _require_completed(result, label)
            return result.run.run_id

        flagships = {
            "risk.var.parametric": _var_run("risk.var.parametric", "stage-3 VaR run"),
            "risk.var.parametric_total": _var_run(
                "risk.var.parametric_total", "stage-3 total-VaR run"
            ),
            "risk.var.parametric_es": _var_run("risk.var.parametric_es", "stage-3 ES run"),
            "risk.var.parametric_es_total": _var_run(
                "risk.var.parametric_es_total", "stage-3 ES-total run"
            ),
        }
        hs_snapshot = build_var_hs_snapshot(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=SnapshotActor(actor_id=actor_id),
            exposure_run_id=loadings.run.run_id,
            window_observations=21,
            as_of_valid_at=_dt(_CARRY_DATE),
        )
        hs = run_var_historical(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=VarActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=str(
                _resolve_version(session, "risk.var.historical", _BASE_CODE_VERSION).id
            ),
            snapshot_id=hs_snapshot.id,
        )
        _require_completed(hs, "stage-3 historical-VaR run")
        flagships["risk.var.historical"] = hs.run.run_id

        session.flush()
        return Hg1PrivateSummary(
            tenant_id=DEMO_TENANT_ID,
            instrument_id=str(inst),
            desmoothed_run_id=dm.run.run_id,
            estimate_run_id=est.run.run_id,
            promoted_loadings=promoted,
            exposure_run_id=exposure.run.run_id,
            loadings_run_id=loadings.run.run_id,
            covariance_run_id=cov.run.run_id,
            flagship_run_ids=flagships,
            minted_return_rows=minted,
        )
    finally:
        detach()
