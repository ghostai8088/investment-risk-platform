"""The MF-1 demo multi-family extension runner (OD-MF-1-A/B/C/D, plan Steps 1-6).

EXTENDS the LIVING demo tenant the MG-1 campaign seeded — never re-runs or edits the campaign
(`campaign.py` stays byte-untouched; its refuse-not-skip + 16-code set-equality lock are ratified
integrity checks). The sequence is the ratified OD enumeration: register the loadings family (the
17th code) + a distinct alpha=1 desmoothing VERSION (alpha is version identity, OD-PA-1-E); tier
the new head (2L); seed the multi-asset sleeve (OD-A: 3 NEW instruments, 3 NEW multi-family
factors — the legacy book gains NO multi-family rows, the mixed-family fence); run the estimation
chain per instrument (marks -> alpha=1 desmooth -> the k=3 Sharpe-1992 OLS -> the analyst promotes
the STRUCTURAL coefficients); run the evidence chain (exposure -> the loadings-family factor
exposure -> covariance -> one VaR/HS/total/ES/ES-total run each, bound to the SAME demo-mg1
versions that carry the flagship AWCs — the version grain); then file the validation set (5
TRIGGERED AWC re-validations closing the CURRENCY-only condition + the loadings INITIAL + the
alpha=1 EXCEPTION), transcribed from the ratified MF-1 dossier section (`dossiers.py`).

Idempotency is REFUSE-NOT-SKIP on the extension's OWN footprint: a demo tenant already holding the
loadings model refuses (`DemoMultifamilyAlreadySeededError`); a tenant WITHOUT the base campaign
refuses (`DemoMultifamilyPrereqError` — the extension extends the living tenant, it never
bootstraps one). The caller owns the ONE commit (the campaign shim's shape), so a mid-chain
failure rolls back whole and the tenant stays clean and re-runnable.

Fixture realism (TD-1): a small single-currency multi-asset sleeve (two listed equities + one
corporate bond), ~12 daily marks each GENERATED deterministically from a declared true-loading
structure over the seeded factor-index paths plus a small idiosyncratic cycle (documented below —
the numeric reviewer re-derives the OLS from the same stored inputs); daily factor returns well
under 1%. No 'FL-1' token appears in ANY record this module files (the OQ-MF-1-6 grep discipline:
the token stays exactly in the 5 historical flagship AWC conditions).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.demo.dossiers import (
    EXCEPTION_CONDITIONS,
    MF1_CLOSURE_FINDING,
    MF1_LOADINGS_INITIAL,
    MF1_LOADINGS_TIER,
    MF1_NON_INDEPENDENCE_DISCLOSURE,
    MF1_TRIGGERED_DOSSIERS,
)
from irp_shared.entitlement.models import AppUser, Role, UserRole
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    FactorActor,
    ProxyMappingActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.model.models import (
    MODEL_TIER_REVIEW_MAX_DAYS,
    VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
    VALIDATION_TYPE_EXCEPTION,
    VALIDATION_TYPE_INITIAL,
    VALIDATION_TYPE_TRIGGERED,
    Model,
    ModelLimitation,
    ModelVersion,
    derive_model_tier,
)
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)
from irp_shared.perf import (
    DesmoothedReturnActor,
    register_desmoothed_return_model,
    run_desmoothed_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
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
    register_factor_exposure_loadings_model,
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

#: One code_version stamps every MF-1 registration + run (FW-RUN/TR-15; distinct from demo-mg1 so
#: the extension's footprint is greppable).
_CODE_VERSION = "demo-mf1"
_ENVIRONMENT_ID = "demo"
_BASE_CODE_VERSION = "demo-mg1"  # the campaign versions the flagship AWCs sit on

#: Validity base for every capture — the campaign's own base, safely before every economic as-of.
_T0 = datetime(2024, 6, 1, tzinfo=UTC)

# --- The multi-family factor set (OD-A): the Sharpe-1992 asset-class palette under the FL-1 FRTB
# names. CALENDAR-daily SIMPLE returns (the OLS per-period coverage gate has no zero-fill — a
# calendar-daily series makes mark/return alignment unconditional) spanning 2026-05-01..06-20:
# 51 dates, covering the demo-mg1 covariance window (30) and HS window (21) ending at the sleeve
# as-of, and every mark-to-mark period. Three ten-value cycles, |r| <= 0.6%, deliberately
# non-collinear. ---
_MF_RETURN_START = date(2026, 5, 1)
_MF_RETURN_END = date(2026, 6, 20)
_MKT_CYCLE = (
    "0.0052", "-0.0031", "0.0018", "0.0060", "-0.0044",
    "0.0011", "-0.0027", "0.0043", "-0.0016", "0.0034",
)  # fmt: skip
_RATES_CYCLE = (
    "-0.0012", "0.0019", "0.0006", "-0.0022", "0.0015",
    "-0.0005", "0.0021", "-0.0009", "0.0003", "0.0014",
)  # fmt: skip
_CRSPD_CYCLE = (
    "0.0008", "-0.0016", "0.0023", "-0.0007", "0.0012",
    "-0.0020", "0.0005", "0.0018", "-0.0011", "0.0025",
)  # fmt: skip
_FACTOR_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("MF_MKT_BROAD", "MARKET", _MKT_CYCLE),
    ("MF_RATES_GOV", "RATES", _RATES_CYCLE),
    ("MF_CRSPD_IG", "CREDIT_SPREAD", _CRSPD_CYCLE),
)

# --- The sleeve book (OD-A; TD-1 realism, single currency = USD): 12 consecutive calendar-daily
# marks per instrument, GENERATED as mark_i = mark_{i-1} * (1 + Sum_f L_f*r_f(d_i) + eps_i)
# quantized HALF_UP to 6dp — a declared true-loading structure the k=3 OLS recovers (the small eps
# cycles, |eps| <= 5e-5, keep the regression honest-but-clean: the numeric review proved recovery
# bias = (X'X)^-1 X'eps scales LINEARLY in eps, and at this amplitude every recovered beta sits
# within ~0.03 of its structural value with unloaded betas < 0.03). The TRUE loadings are the
# promote targets' neighborhoods, never asserted as the estimates:
#   MF-EQ-A ~ {MARKET 0.9};  MF-EQ-B ~ {MARKET 0.7, RATES -0.2};
#   MF-CR-A ~ {RATES 0.6, CREDIT_SPREAD 0.8}   (a duration+spread-duration credit shape;
#   Sum_f L_f = 1.4 — the MV*Sum_w residual-leg scaling OD-C discloses).
# 12 marks => 11 observed => 10 alpha=1 periods; k=3 => OLS floor max(4, 5) = 5 — cleared. ---
_MF_MARK_DATES: tuple[date, ...] = tuple(date(2026, 6, 8) + timedelta(days=i) for i in range(12))
_MF_AS_OF = _MF_MARK_DATES[-1]  # 2026-06-19 — the sleeve exposure boundary
_DESMOOTH_WINDOW = (date(2026, 6, 7), date(2026, 6, 20))
_SIX_DP = Decimal("0.000001")

_STRUCTURAL_LOADINGS: dict[str, dict[str, str]] = {
    "MF-EQ-A": {"MF_MKT_BROAD": "0.9"},
    "MF-EQ-B": {"MF_MKT_BROAD": "0.7", "MF_RATES_GOV": "-0.2"},
    "MF-CR-A": {"MF_RATES_GOV": "0.6", "MF_CRSPD_IG": "0.8"},
}
_INSTRUMENT_SPECS: tuple[tuple[str, str, str, str, str, tuple[str, ...]], ...] = (
    # (code, name, asset_class, quantity, start mark, idiosyncratic 7-cycle)
    (
        "MF-EQ-A",
        "Meridian Semiconductors common stock",
        "EQUITY",
        "250",
        "84.00",
        ("0.00004", "-0.00003", "0.00005", "-0.00002", "0.00001", "-0.00005", "0.00003"),
    ),
    (
        "MF-EQ-B",
        "Atlas Consumer Brands common stock",
        "EQUITY",
        "120",
        "152.00",
        ("-0.00002", "0.00004", "-0.00004", "0.00002", "-0.00001", "0.00005", "-0.00003"),
    ),
    (
        "MF-CR-A",
        "Northgate Utilities 4.25% 2031 senior notes",
        "CORPORATE_BOND",
        "400",
        "98.50",
        ("0.00003", "-0.00001", "0.00002", "-0.00005", "0.00004", "-0.00002", "0.00001"),
    ),
)
_BASE_CURRENCY = "USD"  # every sleeve mark; passed to run_exposure explicitly (no FX legs)


def _cycle_value(cycle: tuple[str, ...], on: date) -> Decimal:
    return Decimal(cycle[(on - _MF_RETURN_START).days % len(cycle)])


def _mark_series(start: str, loadings: dict[str, str], eps: tuple[str, ...]) -> tuple[Decimal, ...]:
    """The deterministic sleeve mark generator (documented above; pure Decimal, 6dp HALF_UP)."""
    factor_cycles = {code: cycle for code, _family, cycle in _FACTOR_SPECS}
    marks = [Decimal(start)]
    for i, on in enumerate(_MF_MARK_DATES[1:]):
        r = sum(
            (
                Decimal(weight) * _cycle_value(factor_cycles[code], on)
                for code, weight in loadings.items()
            ),
            Decimal("0"),
        ) + Decimal(eps[i % len(eps)])
        marks.append((marks[-1] * (Decimal("1") + r)).quantize(_SIX_DP, rounding=ROUND_HALF_UP))
    return tuple(marks)


class DemoMultifamilyError(RuntimeError):
    """An extension step did not produce the state the ratified sequence requires (fail-loud)."""


class DemoMultifamilyPrereqError(RuntimeError):
    """The demo tenant does not hold the MG-1 base campaign — the extension extends the LIVING
    tenant (its TRIGGERED records must supersede the campaign's flagship AWCs at the version
    grain); it never bootstraps one. Run the base campaign first."""


class DemoMultifamilyAlreadySeededError(RuntimeError):
    """Refuse-not-skip on the extension's OWN footprint: the loadings model is already registered
    in the demo tenant. The extension files append-only validation records and never skips or
    partially re-runs. Reset the demo tenant (or the schema) and re-run both stages."""

    def __init__(self) -> None:
        super().__init__(
            f"demo tenant {DEMO_TENANT_ID} already holds {FACTOR_EXPOSURE_LOADINGS_MODEL_CODE!r} "
            f"— refusing to re-extend (append-only validation records are never double-filed). "
            f"Reset the demo tenant's rows (or the schema) and re-run campaign + extension."
        )


@dataclass(frozen=True)
class MultifamilyExtensionSummary:
    """The extension's end state, returned to the caller (counts + the load-bearing ids)."""

    tenant_id: str
    portfolio_id: str
    loadings_model_version_id: str
    alpha1_version_id: str
    factor_ids: dict[str, str]  # factor code -> factor id
    instrument_ids: dict[str, str]  # instrument code -> instrument id
    estimate_run_ids: dict[str, str]  # instrument code -> OLS estimate run id
    promoted_loadings: int
    exposure_run_id: str
    loadings_run_id: str
    covariance_run_id: str
    flagship_run_ids: dict[str, str]  # flagship model code -> its MF-1 evidence run id
    triggered_validations_filed: int
    initial_validations_filed: int
    exceptions_filed: int


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _require_completed(result: object, label: str) -> None:
    status = getattr(result, "status", None)
    if status != "COMPLETED":
        reason = getattr(result, "failure_reason", None)
        raise DemoMultifamilyError(
            f"{label} did not COMPLETE (status={status!r}, reason={reason!r})"
        )


def _resolve_principal(session: Session, role_code: str, label: str) -> str:
    """The campaign-seeded principal holding ``role_code`` (the 2L validator / 1L registrar).
    Exactly ONE must exist — zero means the campaign is unseeded; several means the tenant has
    drifted (a labelled refusal, never a raw MultipleResultsFound 500)."""
    rows = session.execute(
        select(AppUser.id)
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(AppUser.tenant_id == DEMO_TENANT_ID, Role.code == role_code)
    ).all()
    if len(rows) != 1:
        raise DemoMultifamilyPrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) (role {role_code!r}) — "
            f"expected exactly one from the MG-1 base campaign; "
            f"{'run it first' if not rows else 'the tenant has drifted'}"
        )
    return str(rows[0][0])


def _resolve_base_version(session: Session, code: str) -> ModelVersion:
    """The demo-mg1 version of ``code`` — the exact version the flagship AWC sits on (the
    version grain: a TRIGGERED record on any OTHER version would leave the AWC operative)."""
    versions = (
        session.execute(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(
                Model.tenant_id == DEMO_TENANT_ID,
                Model.code == code,
                ModelVersion.code_version == _BASE_CODE_VERSION,
            )
        )
        .scalars()
        .all()
    )
    if len(versions) != 1:
        raise DemoMultifamilyPrereqError(
            f"the demo tenant holds {len(versions)} {_BASE_CODE_VERSION!r} version(s) of "
            f"{code!r} — expected exactly one (the MG-1 base campaign unseeded, or the tenant "
            f"has drifted); refusing"
        )
    return versions[0]


# The four small helpers below are DUPLICATED from campaign.py, not imported: campaign.py is
# byte-frozen (the OD-B fence) and the two raising helpers must raise extension-typed errors —
# importing the campaign's privates would couple the extension to a module it must never edit.
def _registered_limitations(session: Session, version_id: str) -> list[str]:
    rows = (
        session.execute(
            select(ModelLimitation)
            .where(
                ModelLimitation.model_version_id == str(version_id),
                ModelLimitation.tenant_id == DEMO_TENANT_ID,
            )
            .order_by(ModelLimitation.system_from, ModelLimitation.id)
        )
        .scalars()
        .all()
    )
    return [r.limitation_text for r in rows]


def _findings_from_registry(
    session: Session, version_id: str, keys: tuple[str, ...], code: str
) -> tuple[ValidationFindingInput, ...]:
    """The campaign's fail-loud key mechanism, verbatim discipline: each dossier finding KEY must
    match exactly one REGISTERED limitation row, whose text becomes the finding."""
    texts = _registered_limitations(session, version_id)
    findings: list[ValidationFindingInput] = []
    for key in keys:
        matches = [t for t in texts if key in t]
        if len(matches) != 1:
            raise DemoMultifamilyError(
                f"dossier finding key {key!r} matched {len(matches)} registered limitation "
                f"row(s) of {code} — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


@dataclass(frozen=True)
class _Sleeve:
    portfolio_id: str
    instrument_ids: dict[str, str]
    factor_ids: dict[str, str]


def _seed_sleeve(session: Session, actor_id: str) -> _Sleeve:
    """The multi-asset sleeve (OD-A): 3 NEW instruments + 3 NEW multi-family factors — the legacy
    book is never touched (the mixed-family fence)."""
    pf = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="DEMO-MULTIASSET",
        name="Demo multi-asset sleeve (MF-1)",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id=actor_id),
    ).id

    instrument_ids: dict[str, str] = {}
    for code, name, asset_class, qty, start, eps in _INSTRUMENT_SPECS:
        inst = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            asset_class=asset_class,
            actor=ReferenceActor(actor_id=actor_id),
        ).id
        instrument_ids[code] = inst
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=DEMO_TENANT_ID,
            actor=PositionActor(actor_id=actor_id),
            quantity=Decimal(qty),
            valid_from=_T0,
        )
        for on, mark in zip(
            _MF_MARK_DATES, _mark_series(start, _STRUCTURAL_LOADINGS[code], eps), strict=True
        ):
            create_valuation(
                session,
                portfolio_id=pf,
                instrument_id=inst,
                valuation_date=on,
                acting_tenant=DEMO_TENANT_ID,
                actor=ValuationActor(actor_id=actor_id),
                mark_value=mark,
                currency_code=_BASE_CURRENCY,
                valid_from=_T0,
            )

    factor_ids: dict[str, str] = {}
    for code, family, cycle in _FACTOR_SPECS:
        fid = capture_factor(
            session,
            factor_code=code,
            factor_source="DEMO_VENDOR",
            factor_family=family,
            acting_tenant=DEMO_TENANT_ID,
            actor=FactorActor(actor_id=actor_id),
            valid_from=_T0,
        ).id
        factor_ids[code] = fid
        factor = resolve_factor(session, fid, acting_tenant=DEMO_TENANT_ID)
        on = _MF_RETURN_START
        while on <= _MF_RETURN_END:
            capture_factor_return(
                session,
                factor,
                return_date=on,
                return_value=_cycle_value(cycle, on),
                acting_tenant=DEMO_TENANT_ID,
                actor=FactorActor(actor_id=actor_id),
                valid_from=_T0,
            )
            on += timedelta(days=1)
    session.flush()
    return _Sleeve(portfolio_id=pf, instrument_ids=instrument_ids, factor_ids=factor_ids)


def _estimate_and_promote(
    session: Session,
    sleeve: _Sleeve,
    alpha1_version_id: str,
    estimate_version_id: str,
    actor_id: str,
) -> tuple[dict[str, str], int]:
    """The per-instrument estimation chain (OD-C): alpha=1 desmooth (identity) -> the k=3
    Sharpe-1992 OLS over the FULL factor set -> the analyst promotes the STRUCTURAL coefficients
    only (the PA-3 deliberate-per-coefficient design; near-zero betas on unloaded factors stay
    first-class on the estimate rows, unpromoted). All of an instrument's promoted rows cite its
    ONE estimate run — the shape the total-VaR single-cited-run gate requires."""
    all_factor_ids = list(sleeve.factor_ids.values())
    estimate_runs: dict[str, str] = {}
    promoted = 0
    for code, inst in sleeve.instrument_ids.items():
        dm = run_desmoothed_return(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=DesmoothedReturnActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=alpha1_version_id,
            portfolio_id=sleeve.portfolio_id,
            instrument_id=inst,
            window_start=_DESMOOTH_WINDOW[0],
            window_end=_DESMOOTH_WINDOW[1],
        )
        _require_completed(dm, f"alpha=1 desmoothed-return run ({code})")

        est = run_proxy_weight_estimate(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ProxyWeightEstimateActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=estimate_version_id,
            desmoothed_run_id=dm.run.run_id,
            factor_ids=all_factor_ids,
        )
        _require_completed(est, f"proxy-weight estimate run ({code}, k=3)")
        estimate_runs[code] = est.run.run_id

        weights = {
            str(r.factor_id).lower(): r.metric_value
            for r in list_proxy_weight_results(
                session, est.run.run_id, acting_tenant=DEMO_TENANT_ID
            )
            if r.metric_type == METRIC_TYPE_WEIGHT
        }
        for factor_code in _STRUCTURAL_LOADINGS[code]:
            fid = sleeve.factor_ids[factor_code]
            weight = weights.get(fid.lower())
            if weight is None:
                raise DemoMultifamilyError(
                    f"the {code} estimate run produced no WEIGHT row for {factor_code} — refusing"
                )
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
    session.flush()
    return estimate_runs, promoted


@dataclass(frozen=True)
class _Runs:
    exposure_run_id: str
    loadings_run_id: str
    covariance_run_id: str
    flagship_run_ids: dict[str, str]


def _build_runs(
    session: Session,
    sleeve: _Sleeve,
    loadings_version_id: str,
    actor_id: str,
) -> _Runs:
    """The evidence chain (OD-C): one COMPLETED run per flagship, every VaR-family run bound to
    the demo-mg1 version its AWC sits on."""
    factor_ids = list(sleeve.factor_ids.values())

    exposure = run_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        portfolio_id=sleeve.portfolio_id,
        as_of_valid_at=_dt(_MF_AS_OF),
        base_currency=_BASE_CURRENCY,
    )
    _require_completed(exposure, "sleeve exposure run")

    loadings = run_factor_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=FactorExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=loadings_version_id,
        exposure_run_id=exposure.run.run_id,
        factor_ids=factor_ids,
    )
    _require_completed(loadings, "loadings-family factor-exposure run")

    cov = run_covariance(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=CovarianceActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=_resolve_base_version(session, "risk.covariance.sample").id,
        factor_ids=factor_ids,
        as_of_valid_at=_dt(_MF_AS_OF),
    )
    _require_completed(cov, "multi-family covariance run")

    def _var_run(code: str, label: str) -> str:
        result = run_var(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=VarActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=_resolve_base_version(session, code).id,
            exposure_run_id=loadings.run.run_id,
            covariance_run_id=cov.run.run_id,
        )
        _require_completed(result, label)
        return result.run.run_id

    flagship_runs: dict[str, str] = {
        "risk.var.parametric": _var_run("risk.var.parametric", "multi-family VaR run"),
        "risk.var.parametric_total": _var_run(
            "risk.var.parametric_total", "multi-family total-VaR run"
        ),
        "risk.var.parametric_es": _var_run("risk.var.parametric_es", "multi-family ES run"),
        "risk.var.parametric_es_total": _var_run(
            "risk.var.parametric_es_total", "multi-family ES-total run"
        ),
    }

    hs_snapshot = build_var_hs_snapshot(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=SnapshotActor(actor_id=actor_id),
        exposure_run_id=loadings.run.run_id,
        window_observations=21,  # the demo-mg1 declared HS window
        as_of_valid_at=_dt(_MF_AS_OF),
    )
    hs = run_var_historical(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=VarActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=_resolve_base_version(session, "risk.var.historical").id,
        snapshot_id=hs_snapshot.id,
    )
    _require_completed(hs, "multi-family historical-VaR run")
    flagship_runs["risk.var.historical"] = hs.run.run_id

    return _Runs(
        exposure_run_id=exposure.run.run_id,
        loadings_run_id=loadings.run.run_id,
        covariance_run_id=cov.run.run_id,
        flagship_run_ids=flagship_runs,
    )


def _file_records(
    session: Session,
    runs: _Runs,
    loadings_version: ModelVersion,
    alpha1_version: ModelVersion,
    validator_id: str,
) -> tuple[int, int, int]:
    """The validation set (OD-D): 5 TRIGGERED AWC re-validations (the closure), the loadings
    INITIAL, the alpha=1 EXCEPTION. Returns ``(triggered, initials, exceptions)``."""
    today = utcnow().date()
    actor = ModelValidationActor(actor_id=validator_id)
    document = ValidationEvidenceInput(
        evidence_type="DOCUMENT",
        reference="10_delivery_backlog/mf_1_decision_record.md (OD-MF-1-C/D: the ratified "
        "multi-family evidence chain + re-validation shape this record transcribes)",
    )

    triggered = 0
    for code, dossier in MF1_TRIGGERED_DOSSIERS.items():
        version = _resolve_base_version(session, code)
        closure = ValidationFindingInput(
            finding_text=MF1_CLOSURE_FINDING, severity="LOW", authored_by="Andrew Cox"
        )
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=actor,
            request=RecordValidationRequest(
                model_version_id=version.id,
                validation_type=VALIDATION_TYPE_TRIGGERED,
                outcome=dossier.outcome,
                scope_summary=f"{dossier.scope_note} {MF1_NON_INDEPENDENCE_DISCLOSURE}",
                conditions=dossier.conditions,
                report_ref="10_delivery_backlog/mf_1_decision_record.md",
                next_review_due=today + timedelta(days=365),  # TIER_1 write-time ceiling
                findings=(
                    closure,
                    *_findings_from_registry(session, version.id, dossier.finding_keys, code),
                ),
                evidence=(
                    ValidationEvidenceInput(
                        evidence_type="CALCULATION_RUN", run_id=runs.flagship_run_ids[code]
                    ),
                    document,
                ),
            ),
        )
        triggered += 1

    # The loadings model's own INITIAL (AWC) — real evidence from its first campaign; the tier
    # (Step-2, TIER_2) landed BEFORE this record, so the 730-day ceiling governs the date.
    record_validation(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=actor,
        request=RecordValidationRequest(
            model_version_id=loadings_version.id,
            validation_type=VALIDATION_TYPE_INITIAL,
            outcome=MF1_LOADINGS_INITIAL.outcome,
            scope_summary=f"{MF1_LOADINGS_INITIAL.scope_note} {MF1_NON_INDEPENDENCE_DISCLOSURE}",
            conditions=MF1_LOADINGS_INITIAL.conditions,
            report_ref="10_delivery_backlog/mf_1_decision_record.md",
            next_review_due=today + timedelta(days=365),  # within the TIER_2 730-day ceiling
            findings=_findings_from_registry(
                session,
                loadings_version.id,
                MF1_LOADINGS_INITIAL.finding_keys,
                FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
            ),
            evidence=(
                ValidationEvidenceInput(
                    evidence_type="CALCULATION_RUN", run_id=runs.loadings_run_id
                ),
                ValidationEvidenceInput(
                    evidence_type="CALCULATION_RUN",
                    run_id=runs.flagship_run_ids["risk.var.parametric"],
                ),
                document,
            ),
        ),
    )

    # The alpha=1 desmoothing VERSION's time-boxed EXCEPTION — validation is VERSION-grain and
    # the campaign's exception covers the alpha=0.4 version only; without this, the sleeve's
    # three desmoothing runs would sit on the naked use-before-validation default forever.
    head = session.get(Model, alpha1_version.model_id)
    if head is None or not head.tier:
        # Refuse-on-drift, never fail-open (the adversarial finder's F3: this was the module's
        # only silent default) — the campaign guarantees a tiered desmoothing head.
        raise DemoMultifamilyError(
            "the desmoothing head is missing or untiered — the campaign state has drifted; "
            "refusing"
        )
    tier = head.tier
    expiry = today + timedelta(days=MODEL_TIER_REVIEW_MAX_DAYS[tier])
    limitations = _registered_limitations(session, alpha1_version.id)
    if not limitations:
        raise DemoMultifamilyError("the alpha=1 version registered no limitation rows — refusing")
    record_validation(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=actor,
        request=RecordValidationRequest(
            model_version_id=alpha1_version.id,
            validation_type=VALIDATION_TYPE_EXCEPTION,
            outcome=VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
            scope_summary=(
                f"Use-before-validation EXCEPTION for the perf.return.desmoothed_geltner "
                f"alpha=1 VERSION ({_CODE_VERSION}) — the identity-transform detour whose run "
                f"satisfies the pinned-provenance chain for public daily marks (alpha=1 means "
                f"r_true = r_observed exactly; disclosed in both referents). Validation is "
                f"version-grain: the campaign exception covers the alpha=0.4 version only. "
                f"Head tier {tier}; time-boxed to {expiry.isoformat()} per the tier-bounded "
                f"ceiling (OD-MG-1-D). {MF1_NON_INDEPENDENCE_DISCLOSURE}"
            ),
            conditions=EXCEPTION_CONDITIONS,
            report_ref="10_delivery_backlog/mf_1_decision_record.md",
            next_review_due=expiry,
            findings=(
                ValidationFindingInput(
                    finding_text=limitations[0], severity="LOW", authored_by="Andrew Cox"
                ),
            ),
            evidence=(document,),
        ),
    )
    return triggered, 1, 1


def run_demo_multifamily_extension(session: Session) -> MultifamilyExtensionSummary:
    """Execute the ratified MF-1 extension against the LIVING demo tenant. The caller owns the
    ONE commit; the runner arms (and re-arms) the demo tenant's RLS context itself.

    CONTEXT CONTRACT (the campaign's shape, inherited): the runner REPLACES any caller-armed
    persistent tenant listener and DETACHES its own on exit — a caller that had its own
    persistent context must re-arm after this returns before any post-commit read (the MD-H1
    zero-rows trap; the adversarial finder's F2)."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        model_count = session.execute(
            select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
        ).scalar_one()
        if not model_count:
            raise DemoMultifamilyPrereqError(
                f"demo tenant {DEMO_TENANT_ID} holds no model rows — the MG-1 base campaign has "
                f"not been seeded; the extension extends the living tenant, never bootstraps one"
            )
        already = session.execute(
            select(func.count())
            .select_from(Model)
            .where(
                Model.tenant_id == DEMO_TENANT_ID,
                Model.code == FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
            )
        ).scalar_one()
        if already:
            raise DemoMultifamilyAlreadySeededError()

        registrar_id = _resolve_principal(session, "risk_analyst_1l", "1L registrar")
        validator_id = _resolve_principal(session, "risk_manager_2l", "2L validator")

        # Step 2 — registrations (the 17th code + the alpha=1 version) + the new head's tier.
        loadings_version = register_factor_exposure_loadings_model(
            session, tenant_id=DEMO_TENANT_ID, actor_id=registrar_id, code_version=_CODE_VERSION
        )
        alpha1_version = register_desmoothed_return_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=registrar_id,
            code_version=_CODE_VERSION,
            alpha="1",
            version_label="v1-alpha1",  # the alpha=0.4 'v1' already holds the default label
        )
        assign_model_tier(
            session,
            acting_tenant=DEMO_TENANT_ID,
            model_id=loadings_version.model_id,
            materiality_rating=MF1_LOADINGS_TIER.materiality_rating,
            complexity_rating=MF1_LOADINGS_TIER.complexity_rating,
            rationale=MF1_LOADINGS_TIER.rationale,
            actor_id=validator_id,
        )
        expected_tier = derive_model_tier(
            MF1_LOADINGS_TIER.materiality_rating, MF1_LOADINGS_TIER.complexity_rating
        )
        if expected_tier != "TIER_2":  # the ratified OD-B expectation, asserted not assumed
            raise DemoMultifamilyError(
                f"the loadings dossier ratings derive {expected_tier}, not the ratified TIER_2 "
                f"— the dossier map has drifted; refusing"
            )

        # Steps 3-5 — the sleeve, the estimation chain, the evidence chain.
        sleeve = _seed_sleeve(session, registrar_id)
        estimate_version = _resolve_base_version(session, "risk.proxy_weight.regression")
        estimate_runs, promoted = _estimate_and_promote(
            session, sleeve, str(alpha1_version.id), str(estimate_version.id), registrar_id
        )
        runs = _build_runs(session, sleeve, str(loadings_version.id), registrar_id)

        # Step 6 — the validation set (the closure).
        triggered, initials, exceptions = _file_records(
            session, runs, loadings_version, alpha1_version, validator_id
        )
        session.flush()
        return MultifamilyExtensionSummary(
            tenant_id=DEMO_TENANT_ID,
            portfolio_id=sleeve.portfolio_id,
            loadings_model_version_id=str(loadings_version.id),
            alpha1_version_id=str(alpha1_version.id),
            factor_ids=dict(sleeve.factor_ids),
            instrument_ids=dict(sleeve.instrument_ids),
            estimate_run_ids=estimate_runs,
            promoted_loadings=promoted,
            exposure_run_id=runs.exposure_run_id,
            loadings_run_id=runs.loadings_run_id,
            covariance_run_id=runs.covariance_run_id,
            flagship_run_ids=dict(runs.flagship_run_ids),
            triggered_validations_filed=triggered,
            initial_validations_filed=initials,
            exceptions_filed=exceptions,
        )
    finally:
        detach()
