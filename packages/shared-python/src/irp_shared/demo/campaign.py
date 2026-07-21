"""The MG-1 demo validation campaign runner (OD-MG-1-G, plan Step 5).

Drives the REAL service layer end-to-end against a dedicated DEMO tenant — NEVER
``build_synthetic_dataset`` (census-disqualified three ways; AD-017's capture-only contract stays
byte-intact — nothing here imports the synthetic seed). The sequence is the ratified Step-5
enumeration: reference + market data through the real capture services; the 2L principal NAMED FOR
THE USER + tenant-local role wiring; ALL 16 model codes through their real family registrars; the
honest per-flagship evidence chain (exposure -> factor exposure -> covariance -> 8-point plain/HS/
total forecast series -> the PM-1 return series -> REAL BT-1 and BT-2 backtest runs -> ES +
ES-total runs — where the total leg builds the REAL marks -> desmooth -> PA-3 OLS -> promote
chain, the estimate-seam ride-along's chain living in this tenant); tier assignment for all 16
heads (2L, audited ``MODEL.TIER_ASSIGN``); then the 6 INITIAL validations + 10 EXCEPTION records
transcribed from the ratified dossier map (``dossiers.py``).

Idempotency is REFUSE-NOT-SKIP (the RD-3 no-op-sentinel lesson, inverted deliberately): a demo
tenant already holding ANY model row raises :class:`DemoCampaignAlreadySeededError` — the campaign
is a governance ceremony, not a converging seed, and a partial re-run would double-file
append-only validation records. The operator resets the demo tenant (or the schema) and re-runs.

Fixture realism (TD-1): a small multi-currency book (two listed equities in USD/EUR + one
appraisal-marked private fund carried at its last appraisal), daily marks moving fractions of a
percent with ONE large designed equity-drawdown day (the currency-only factor model cannot see
it — the flagship condition demonstrated, not decorated), FX near 1.08, daily currency-factor
returns well under 1%.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.dossiers import (
    EXCEPTION_CONDITIONS,
    FLAGSHIP_CODES,
    FLAGSHIP_DOSSIERS,
    NON_INDEPENDENCE_DISCLOSURE,
    TIER_DOSSIERS,
)
from irp_shared.entitlement.bootstrap import PERMISSIONS
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    FactorActor,
    FxRateActor,
    ProxyMappingActor,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    resolve_factor,
)
from irp_shared.model.models import (
    MODEL_TIER_REVIEW_MAX_DAYS,
    VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
    VALIDATION_TYPE_EXCEPTION,
    VALIDATION_TYPE_INITIAL,
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
    PortfolioReturnActor,
    register_benchmark_relative_model,
    register_desmoothed_return_model,
    register_portfolio_return_model,
    run_desmoothed_return,
    run_portfolio_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_WEIGHT,
    CovarianceActor,
    FactorExposureActor,
    ProxyWeightEstimateActor,
    VarActor,
    VarBacktestActor,
    list_proxy_weight_results,
    promote_proxy_weight_estimate,
    register_active_risk_model,
    register_covariance_model,
    register_factor_exposure_model,
    register_factor_exposure_proxy_model,
    register_historical_var_model,
    register_proxy_weight_regression_model,
    register_scenario_model,
    register_sensitivity_model,
    register_var_backtest_model,
    register_var_model,
    register_var_parametric_es_model,
    register_var_parametric_es_total_model,
    register_var_parametric_total_model,
    run_covariance,
    run_factor_exposure,
    run_proxy_weight_estimate,
    run_var,
    run_var_backtest,
    run_var_historical,
)
from irp_shared.snapshot import build_var_hs_snapshot
from irp_shared.snapshot.events import SnapshotActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

#: Reserved demo-campaign uuid5 namespace — the ``synthetic/ids.py`` pattern MIRRORED, never
#: imported from it (AD-017's seed stays untouched): a fixed namespace distinct from both the
#: entitlement ``_NS`` (…00a1) and the synthetic ``_SYN_NS`` (…00c6); ``…00d1`` nods to the
#: MG-1 demo. Same key discipline, DIFFERENT label ("tenant:demo", not "tenant:synthetic"), so
#: the two reserved tenants can never collide.
_DEMO_NS = uuid.UUID("00000000-0000-0000-0000-0000000000d1")


def demo_id(key: str) -> str:
    """Deterministic ``uuid5`` id for a demo-campaign entity (the synthetic ``ids.py`` shape)."""
    return str(uuid.uuid5(_DEMO_NS, key))


#: The reserved DEMO-CAMPAIGN tenant (OD-MG-1-G) — NOT the synthetic tenant.
DEMO_TENANT_ID = demo_id("tenant:demo")

#: One code_version stamps every registration + run of the campaign (FW-RUN/TR-15).
_CODE_VERSION = "demo-mg1"
_ENVIRONMENT_ID = "demo"

#: Validity base for every capture — safely before every economic as-of the campaign uses.
_T0 = datetime(2024, 6, 1, tzinfo=UTC)

# --- The backtest calendar: 9 daily valuation boundaries -> 8 one-day Dietz sub-periods, and 8
# consecutive VaR window_ends pairing 1:1 with them (BT-1's all-or-nothing calendar alignment:
# each forecast applies as of its window_end and pairs with EXACTLY the sub-period starting
# there and spanning horizon_days=1 calendar day). ---
_BOUNDARY_DATES: tuple[date, ...] = tuple(date(2026, 5, 18) + timedelta(days=i) for i in range(9))
_WINDOW_ENDS: tuple[date, ...] = _BOUNDARY_DATES[:8]
_BACKTEST_PAIRS = len(_WINDOW_ENDS)

# --- The book (TD-1 realism): two listed equities + one appraisal-marked private fund. Daily
# equity marks move ~0.1-0.3% except the ONE designed drawdown day (2026-05-22 -> 23: ~-4%, an
# equity move the CURRENCY factor model cannot see — the flagship condition made concrete); the
# private fund is carried daily at its last quarterly appraisal (flat between marks). ---
_ACME_MARKS = (
    "150.00",
    "150.30",
    "149.95",
    "150.20",
    "150.10",
    "143.90",
    "144.20",
    "143.95",
    "144.10",
)  # noqa: E501
_EURX_MARKS = ("95.00", "94.85", "95.10", "95.05", "95.30", "91.90", "92.05", "91.85", "92.00")
_PE_CARRY_MARK = "1080.00"  # the 2026-03-31 appraisal, carried daily
#: EUR->USD daily mids near 1.08, moving <= ~0.15%/day (captured at each boundary date — the
#: exposure FX pin is exact-date, OD-P2-2-D).
_FX_EURUSD = (
    "1.080000000000",
    "1.080500000000",
    "1.079800000000",
    "1.080200000000",
    "1.081000000000",
    "1.079500000000",
    "1.080300000000",
    "1.080000000000",
    "1.080600000000",
)

# --- The private leg (the desmooth -> OLS -> promote chain): seven quarterly appraisals ->
# six observed returns -> five desmoothed periods (the first seeds the AR(1) recursion). Mild
# quarterly PE marks (~+0.6%..+2.3%/quarter). ---
_PE_MARK_DATES: tuple[date, ...] = (
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
    date(2026, 3, 31),
)
_PE_MARK_VALUES = ("1000.00", "1012.00", "1018.50", "1031.00", "1042.20", "1055.80", "1080.00")
#: The desmoothing window covers ONLY the quarterly appraisal series — it ends before the daily
#: carried marks begin, so the daily boundary marks cannot pollute the appraisal-return series.
_DESMOOTH_WINDOW = (date(2024, 6, 1), date(2026, 4, 30))

#: One factor return per desmoothed period end (each appraisal period compounds one value —
#: the PA-3 coverage rule satisfied exactly); the five desmoothed periods end at marks 3..7.
_OLS_RETURN_DATES: tuple[date, ...] = _PE_MARK_DATES[2:]
_FX_USD_QUARTERLY = ("0.012", "-0.008", "0.015", "0.004", "0.021")
_FX_EUR_QUARTERLY = ("-0.006", "0.011", "0.002", "-0.009", "0.013")

# --- Daily currency-factor returns spanning the covariance window: 2026-04-01..2026-05-25
# (55 days; the 30-observation window ending at the FIRST window_end 2026-05-18 needs 30 daily
# dates, and the HS window needs 21). Two ten-value cycles, |r| <= 0.45%, deliberately
# non-collinear. ---
_DAILY_RETURN_START = date(2026, 4, 1)
_DAILY_RETURN_END = date(2026, 5, 25)
_FX_USD_DAILY_CYCLE = (
    "0.0021", "-0.0034", "0.0012", "0.0045", "-0.0028",
    "0.0007", "-0.0015", "0.0038", "-0.0042", "0.0019",
)  # fmt: skip
_FX_EUR_DAILY_CYCLE = (
    "-0.0018", "0.0027", "0.0041", "-0.0009", "0.0016",
    "-0.0037", "0.0024", "-0.0011", "0.0033", "-0.0026",
)  # fmt: skip

#: Declared model parameters (ratified-vocabulary values; task Step 3).
_COVARIANCE_WINDOW = 30
_VAR_CONFIDENCE = "0.99"
_HS_CONFIDENCE = "0.95"  # the 0.95 adequacy floor is 21 — an 8-run series stays honest
_HS_WINDOW = 21
_ES_CONFIDENCE = "0.975"
_APPRAISAL_DAYS = 91
_MAX_ESTIMATE_AGE_DAYS = 400
_BACKTEST_ALPHA = "0.05"
_DESMOOTHING_ALPHA = "0.4"
_MIN_OLS_OBSERVATIONS = 4

#: The 2L role wiring (the test_model_endpoint.py pattern): the validator holds the validation
#: verb + the inventory read ONLY (SOD-03 at role level); the 1L registrar holds the maker verbs.
_VALIDATOR_PERMS = ("model.validate", "model.inventory.view")
_REGISTRAR_PERMS = ("model.inventory.register", "risk.run", "risk.view", "perf.run", "perf.view")


class DemoCampaignError(RuntimeError):
    """A campaign step did not produce the state the ratified sequence requires (fail-loud)."""


class DemoCampaignAlreadySeededError(RuntimeError):
    """Refuse-not-skip (OD-MG-1-G): the demo tenant already holds model rows. The campaign is a
    governance ceremony over append-only records — a partial or repeated run would double-file
    validations, so it never skips or converges. Reset the demo tenant (or the schema) first."""

    def __init__(self, model_count: int) -> None:
        super().__init__(
            f"demo tenant {DEMO_TENANT_ID} already holds {model_count} model row(s) — refusing "
            f"to re-seed (the campaign files append-only validation records and never skips or "
            f"partially re-runs). Reset the demo tenant's rows (or reset the schema) and re-run."
        )
        self.model_count = model_count


@dataclass(frozen=True)
class CampaignSummary:
    """The campaign's end state, returned to the caller (counts + the load-bearing ids)."""

    tenant_id: str
    validator_user_id: str
    registrar_user_id: str
    portfolio_id: str
    model_ids: dict[str, str]  # model code -> model head id
    model_version_ids: dict[str, str]  # model code -> registered version id
    models_registered: int
    tiers_assigned: int
    initial_validations_filed: int
    exceptions_filed: int
    backtest_pairs: int
    var_run_ids: tuple[str, ...]
    hs_run_ids: tuple[str, ...]
    total_run_ids: tuple[str, ...]
    es_run_id: str
    es_total_run_id: str
    portfolio_return_run_id: str
    bt1_run_id: str
    bt2_run_id: str
    desmoothed_run_id: str
    estimate_run_id: str


@dataclass(frozen=True)
class _Book:
    portfolio_id: str
    pe_id: str
    fx_usd_factor_id: str
    fx_eur_factor_id: str


@dataclass(frozen=True)
class _Chains:
    factor_exposure_run_id: str
    covariance_run_ids: tuple[str, ...]
    var_run_ids: tuple[str, ...]
    hs_run_ids: tuple[str, ...]
    total_run_ids: tuple[str, ...]
    es_run_id: str
    es_total_run_id: str
    portfolio_return_run_id: str
    bt1_run_id: str
    bt2_run_id: str
    desmoothed_run_id: str
    estimate_run_id: str


def _require_completed(result: object, label: str) -> None:
    status = getattr(result, "status", None)
    if status != "COMPLETED":
        reason = getattr(result, "failure_reason", None)
        raise DemoCampaignError(f"{label} did not COMPLETE (status={status!r}, reason={reason!r})")


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _resolve_permission(session: Session, code: str) -> Permission:
    """Resolve-or-create the GLOBAL permission row (non-RLS; may pre-exist from the entitlement
    bootstrap or another tenant's wiring). Descriptions come from the governed catalog — the
    campaign mints NO permission code (OD-MG-1-C/H)."""
    catalog = dict(PERMISSIONS)
    if code not in catalog:
        raise DemoCampaignError(f"permission {code!r} is not in the governed catalog — refusing")
    perm = session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
    if perm is None:
        perm = Permission(code=code, description=catalog[code])
        session.add(perm)
        session.flush()
    return perm


def _seed_principals(session: Session) -> tuple[str, str]:
    """The tenant-local role wiring (the endpoint-test pattern — the only working one): the 2L
    ``app_user`` NAMED FOR THE USER (the validator of record per OD-MG-1-G) + a 1L registrar for
    the register-side acts. Returns ``(registrar_user_id, validator_user_id)``."""
    # external_subject binds the OIDC ``sub`` claim (SSO-1, AD-007) — stable values so a token from
    # the documented local Keycloak realm (infra/keycloak/) resolves to these demo principals. A
    # column set only: no new run, no count change.
    validator = AppUser(
        tenant_id=DEMO_TENANT_ID, display_name="Andrew Cox", external_subject="demo-validator"
    )
    registrar = AppUser(
        tenant_id=DEMO_TENANT_ID,
        display_name="MG-1 demo registrar (Claude, scribe)",
        external_subject="demo-registrar",
    )
    role_2l = Role(tenant_id=DEMO_TENANT_ID, code="risk_manager_2l", name="Risk manager (2L)")
    role_1l = Role(tenant_id=DEMO_TENANT_ID, code="risk_analyst_1l", name="Risk analyst (1L)")
    session.add_all([validator, registrar, role_2l, role_1l])
    session.flush()
    for role, codes in ((role_2l, _VALIDATOR_PERMS), (role_1l, _REGISTRAR_PERMS)):
        for code in codes:
            perm = _resolve_permission(session, code)
            session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    session.add(UserRole(tenant_id=DEMO_TENANT_ID, user_id=validator.id, role_id=role_2l.id))
    session.add(UserRole(tenant_id=DEMO_TENANT_ID, user_id=registrar.id, role_id=role_1l.id))
    session.flush()
    return registrar.id, validator.id


def _seed_book(session: Session, actor_id: str) -> _Book:
    """Reference + market data via the real capture services (Step 5 item 1)."""
    for code, name in (("USD", "US Dollar"), ("EUR", "Euro")):
        session.add(Currency(tenant_id=DEMO_TENANT_ID, code=code, name=name, valid_from=_T0))
    session.flush()

    pf = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="DEMO-GLOBAL",
        name="Demo campaign multi-asset book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id=actor_id),
    ).id
    instruments = {
        "EQ-ACME-US": ("ACME Corp common stock", "EQUITY", "400"),
        "EQ-EURX-DE": ("EURX Industries AG common stock", "EQUITY", "300"),
        "PE-HARBOR-IV": ("Harbor Buyout Fund IV LP interest", "PRIVATE_EQUITY", "50"),
    }
    ids: dict[str, str] = {}
    for code, (name, asset_class, qty) in instruments.items():
        inst = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            asset_class=asset_class,
            actor=ReferenceActor(actor_id=actor_id),
        ).id
        ids[code] = inst
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=DEMO_TENANT_ID,
            actor=PositionActor(actor_id=actor_id),
            quantity=Decimal(qty),
            valid_from=_T0,
        )

    def _mark(inst: str, on: date, value: str, ccy: str) -> None:
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=on,
            acting_tenant=DEMO_TENANT_ID,
            actor=ValuationActor(actor_id=actor_id),
            mark_value=Decimal(value),
            currency_code=ccy,
            valid_from=_T0,
        )

    # The private fund's quarterly appraisal series (the desmooth leg's input) ...
    for on, value in zip(_PE_MARK_DATES, _PE_MARK_VALUES, strict=True):
        _mark(ids["PE-HARBOR-IV"], on, value, "USD")
    # ... then the daily boundary marks: equities move, the fund is carried at its last appraisal
    # (the marks are exact-date reads — every instrument needs one per exposure boundary).
    for i, on in enumerate(_BOUNDARY_DATES):
        _mark(ids["EQ-ACME-US"], on, _ACME_MARKS[i], "USD")
        _mark(ids["EQ-EURX-DE"], on, _EURX_MARKS[i], "EUR")
        _mark(ids["PE-HARBOR-IV"], on, _PE_CARRY_MARK, "USD")
        capture_fx_rate(
            session,
            base_currency="EUR",
            quote_currency="USD",
            rate_date=on,
            rate=Decimal(_FX_EURUSD[i]),
            acting_tenant=DEMO_TENANT_ID,
            actor=FxRateActor(actor_id=actor_id),
            valid_from=_T0,
        )

    # CURRENCY factors + their return series: the daily leg spans the covariance/HS windows; the
    # quarterly leg (one return per appraisal-period end) feeds the PA-3 regression coverage rule.
    factor_ids: dict[str, str] = {}
    for code, ccy, quarterly, cycle in (
        ("FX_USD", "USD", _FX_USD_QUARTERLY, _FX_USD_DAILY_CYCLE),
        ("FX_EUR", "EUR", _FX_EUR_QUARTERLY, _FX_EUR_DAILY_CYCLE),
    ):
        fid = capture_factor(
            session,
            factor_code=code,
            factor_source="DEMO_VENDOR",
            factor_family="CURRENCY",
            currency_code=ccy,
            acting_tenant=DEMO_TENANT_ID,
            actor=FactorActor(actor_id=actor_id),
            valid_from=_T0,
        ).id
        factor_ids[code] = fid
        factor = resolve_factor(session, fid, acting_tenant=DEMO_TENANT_ID)
        for on, value in zip(_OLS_RETURN_DATES, quarterly, strict=True):
            capture_factor_return(
                session,
                factor,
                return_date=on,
                return_value=Decimal(value),
                acting_tenant=DEMO_TENANT_ID,
                actor=FactorActor(actor_id=actor_id),
                valid_from=_T0,
            )
        on = _DAILY_RETURN_START
        i = 0
        while on <= _DAILY_RETURN_END:
            capture_factor_return(
                session,
                factor,
                return_date=on,
                return_value=Decimal(cycle[i % len(cycle)]),
                acting_tenant=DEMO_TENANT_ID,
                actor=FactorActor(actor_id=actor_id),
                valid_from=_T0,
            )
            on += timedelta(days=1)
            i += 1
    session.flush()
    return _Book(
        portfolio_id=pf,
        pe_id=ids["PE-HARBOR-IV"],
        fx_usd_factor_id=factor_ids["FX_USD"],
        fx_eur_factor_id=factor_ids["FX_EUR"],
    )


def _register_models(session: Session, actor_id: str) -> dict[str, ModelVersion]:
    """Register ALL 16 model codes via their real family registrars (Step 5 item 3 — the
    planning verifier's HIGH: tier assignment and EXCEPTION filing both require a registered
    head/version, so a 6-code runner cannot produce the 16-code end state)."""
    tenant, actor, cv = DEMO_TENANT_ID, actor_id, _CODE_VERSION
    versions: dict[str, ModelVersion] = {
        "risk.sensitivity.analytic": register_sensitivity_model(
            session, tenant_id=tenant, actor_id=actor, code_version=cv
        ),
        "risk.factor_exposure.allocation": register_factor_exposure_model(
            session, tenant_id=tenant, actor_id=actor, code_version=cv
        ),
        "risk.factor_exposure.proxy": register_factor_exposure_proxy_model(
            session, tenant_id=tenant, actor_id=actor, code_version=cv
        ),
        "risk.covariance.sample": register_covariance_model(
            session,
            tenant_id=tenant,
            actor_id=actor,
            code_version=cv,
            window_observations=_COVARIANCE_WINDOW,
        ),
        "risk.var.parametric": register_var_model(
            session,
            tenant_id=tenant,
            actor_id=actor,
            code_version=cv,
            confidence_level=_VAR_CONFIDENCE,
        ),
        "risk.var.historical": register_historical_var_model(
            session,
            tenant_id=tenant,
            actor_id=actor,
            code_version=cv,
            confidence_level=_HS_CONFIDENCE,
            window_observations=_HS_WINDOW,
        ),
        "risk.active_risk.parametric": register_active_risk_model(
            session, tenant_id=tenant, actor_id=actor, code_version=cv
        ),
        "risk.var_backtest": register_var_backtest_model(
            session, tenant_id=tenant, actor_id=actor, code_version=cv, alpha=_BACKTEST_ALPHA
        ),
        "risk.scenario.factor_shock": register_scenario_model(
            session, tenant_id=tenant, actor_id=actor, code_version=cv
        ),
        "risk.proxy_weight.regression": register_proxy_weight_regression_model(
            session,
            tenant_id=tenant,
            actor_id=actor,
            code_version=cv,
            min_observations=_MIN_OLS_OBSERVATIONS,
        ),
        "risk.var.parametric_total": register_var_parametric_total_model(
            session,
            tenant_id=tenant,
            actor_id=actor,
            code_version=cv,
            confidence_level=_VAR_CONFIDENCE,
            appraisal_days=_APPRAISAL_DAYS,
            max_estimate_age_days=_MAX_ESTIMATE_AGE_DAYS,
        ),
        "risk.var.parametric_es": register_var_parametric_es_model(
            session,
            tenant_id=tenant,
            actor_id=actor,
            code_version=cv,
            confidence_level=_ES_CONFIDENCE,
        ),
        "risk.var.parametric_es_total": register_var_parametric_es_total_model(
            session,
            tenant_id=tenant,
            actor_id=actor,
            code_version=cv,
            confidence_level=_ES_CONFIDENCE,
            appraisal_days=_APPRAISAL_DAYS,
            max_estimate_age_days=_MAX_ESTIMATE_AGE_DAYS,
        ),
        "perf.return.twr": register_portfolio_return_model(
            session, tenant_id=tenant, actor_id=actor, code_version=cv
        ),
        "perf.benchmark_relative": register_benchmark_relative_model(
            session, tenant_id=tenant, actor_id=actor, code_version=cv
        ),
        "perf.return.desmoothed_geltner": register_desmoothed_return_model(
            session,
            tenant_id=tenant,
            actor_id=actor,
            code_version=cv,
            alpha=_DESMOOTHING_ALPHA,
        ),
    }
    if set(versions) != set(TIER_DOSSIERS):
        raise DemoCampaignError(
            "the registered code set does not match the ratified dossier map — refusing"
        )
    return versions


def _build_chains(
    session: Session, book: _Book, versions: dict[str, ModelVersion], actor_id: str
) -> _Chains:
    """The evidence chains (Step 5 item 4): exposure boundaries -> factor exposure -> per-date
    covariance -> the 8-point plain/HS forecast series -> the PM-1 return run -> the REAL BT-1
    backtest; then the private leg (desmooth -> PA-3 OLS -> promote) -> the 8-point total-v2
    series -> the REAL BT-2 backtest -> one ES + one ES-total run."""
    factor_ids = [book.fx_usd_factor_id, book.fx_eur_factor_id]

    # 9 daily valuation-boundary exposure runs (r0 doubles as the factor-model book basis).
    boundary_runs: list[str] = []
    for on in _BOUNDARY_DATES:
        result = run_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ExposureActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            portfolio_id=book.portfolio_id,
            as_of_valid_at=_dt(on),
            base_currency="USD",
        )
        _require_completed(result, f"exposure boundary run @{on.isoformat()}")
        boundary_runs.append(result.run.run_id)

    fx_result = run_factor_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=FactorExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=versions["risk.factor_exposure.allocation"].id,
        exposure_run_id=boundary_runs[0],
        factor_ids=factor_ids,
    )
    _require_completed(fx_result, "factor-exposure run")
    fx_run = fx_result.run.run_id

    # One covariance run per window_end (the bitemporal valid_at cut bounds the return window,
    # so each run's 30-date window ends exactly at its forecast date).
    cov_runs: list[str] = []
    for w in _WINDOW_ENDS:
        cov = run_covariance(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=CovarianceActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=versions["risk.covariance.sample"].id,
            factor_ids=factor_ids,
            as_of_valid_at=_dt(w),
        )
        _require_completed(cov, f"covariance run @{w.isoformat()}")
        cov_runs.append(cov.run.run_id)

    def _var_series(model_code: str, label: str) -> list[str]:
        runs: list[str] = []
        for w, cov_run in zip(_WINDOW_ENDS, cov_runs, strict=True):
            result = run_var(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=VarActor(actor_id=actor_id),
                code_version=_CODE_VERSION,
                environment_id=_ENVIRONMENT_ID,
                model_version_id=versions[model_code].id,
                exposure_run_id=fx_run,
                covariance_run_id=cov_run,
            )
            _require_completed(result, f"{label} run @{w.isoformat()}")
            if result.rows[0].window_end != w:
                raise DemoCampaignError(
                    f"{label} run window_end {result.rows[0].window_end} != {w} — the backtest "
                    f"pairing would break"
                )
            runs.append(result.run.run_id)
        return runs

    var_runs = _var_series("risk.var.parametric", "parametric VaR")

    # HS series via the consume-existing path: the builder's valid_at cut is the only lever that
    # moves the HS window_end backwards in time (the build-in-request path pins at "now").
    hs_runs: list[str] = []
    for w in _WINDOW_ENDS:
        snapshot = build_var_hs_snapshot(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=SnapshotActor(actor_id=actor_id),
            exposure_run_id=fx_run,
            window_observations=_HS_WINDOW,
            as_of_valid_at=_dt(w),
        )
        hs_result = run_var_historical(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=VarActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=versions["risk.var.historical"].id,
            snapshot_id=snapshot.id,
        )
        _require_completed(hs_result, f"historical VaR run @{w.isoformat()}")
        hs_runs.append(hs_result.run.run_id)

    # The PM-1 return run whose Dietz sub-periods align 1:1 with the forecast series.
    return_result = run_portfolio_return(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=PortfolioReturnActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=versions["perf.return.twr"].id,
        exposure_run_ids=boundary_runs,
    )
    _require_completed(return_result, "portfolio-return run")
    return_run = return_result.run.run_id

    bt1 = run_var_backtest(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=VarBacktestActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=versions["risk.var_backtest"].id,
        portfolio_return_run_id=return_run,
        var_run_ids=var_runs,
    )
    _require_completed(bt1, "BT-1 backtest run (plain series)")

    # --- The private leg: real marks -> desmooth -> PA-3 OLS -> promote (the estimate-seam
    # ride-along's chain, built once and living in this tenant). ---
    desmooth = run_desmoothed_return(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=DesmoothedReturnActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=versions["perf.return.desmoothed_geltner"].id,
        portfolio_id=book.portfolio_id,
        instrument_id=book.pe_id,
        window_start=_DESMOOTH_WINDOW[0],
        window_end=_DESMOOTH_WINDOW[1],
    )
    _require_completed(desmooth, "desmoothed-return run")

    estimate = run_proxy_weight_estimate(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ProxyWeightEstimateActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=versions["risk.proxy_weight.regression"].id,
        desmoothed_run_id=desmooth.run.run_id,
        factor_ids=factor_ids,
    )
    _require_completed(estimate, "proxy-weight estimate run")
    estimate_run = estimate.run.run_id

    # The analyst promotes the estimated FX_USD loading (the fund's own series currency) —
    # the deliberate human-mediated second capture step citing the estimation run (OD-PA-3-E).
    weight_row = next(
        (
            r
            for r in list_proxy_weight_results(session, estimate_run, acting_tenant=DEMO_TENANT_ID)
            if r.metric_type == METRIC_TYPE_WEIGHT
            and str(r.factor_id).lower() == book.fx_usd_factor_id.lower()
        ),
        None,
    )
    if weight_row is None:
        raise DemoCampaignError("the estimate run produced no FX_USD WEIGHT row — refusing")
    promote_proxy_weight_estimate(
        session,
        private_instrument_id=book.pe_id,
        factor_id=book.fx_usd_factor_id,
        weight=weight_row.metric_value,
        acting_tenant=DEMO_TENANT_ID,
        actor=ProxyMappingActor(actor_id=actor_id),
        source_calculation_run_id=estimate_run,
    )

    total_runs = _var_series("risk.var.parametric_total", "total VaR")
    bt2 = run_var_backtest(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=VarBacktestActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=versions["risk.var_backtest"].id,
        portfolio_return_run_id=return_run,
        var_run_ids=total_runs,
    )
    _require_completed(bt2, "BT-2 backtest run (total series)")

    def _es_run(model_code: str, label: str) -> str:
        result = run_var(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=VarActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=versions[model_code].id,
            exposure_run_id=fx_run,
            covariance_run_id=cov_runs[-1],
        )
        _require_completed(result, label)
        return result.run.run_id

    es_run = _es_run("risk.var.parametric_es", "ES run")
    es_total_run = _es_run("risk.var.parametric_es_total", "ES-total run")

    return _Chains(
        factor_exposure_run_id=fx_run,
        covariance_run_ids=tuple(cov_runs),
        var_run_ids=tuple(var_runs),
        hs_run_ids=tuple(hs_runs),
        total_run_ids=tuple(total_runs),
        es_run_id=es_run,
        es_total_run_id=es_total_run,
        portfolio_return_run_id=return_run,
        bt1_run_id=bt1.run.run_id,
        bt2_run_id=bt2.run.run_id,
        desmoothed_run_id=desmooth.run.run_id,
        estimate_run_id=estimate_run,
    )


def _assign_tiers(session: Session, versions: dict[str, ModelVersion], validator_id: str) -> int:
    """Tier-assign all 16 heads (Step 5 item 5) — the 2L act, per the ratified rubric."""
    count = 0
    for code, dossier in TIER_DOSSIERS.items():
        assign_model_tier(
            session,
            acting_tenant=DEMO_TENANT_ID,
            model_id=versions[code].model_id,
            materiality_rating=dossier.materiality_rating,
            complexity_rating=dossier.complexity_rating,
            rationale=dossier.rationale,
            actor_id=validator_id,
        )
        count += 1
    return count


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
    """Resolve each dossier finding KEY against the version's REGISTERED limitation rows — the
    findings are read from the registry, never invented; a key matching zero or several rows
    fails the campaign loudly (dossier/registry drift must never file silently)."""
    texts = _registered_limitations(session, version_id)
    findings: list[ValidationFindingInput] = []
    for key in keys:
        matches = [t for t in texts if key in t]
        if len(matches) != 1:
            raise DemoCampaignError(
                f"dossier finding key {key!r} matched {len(matches)} registered limitation "
                f"row(s) of {code} — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


def _file_records(
    session: Session,
    versions: dict[str, ModelVersion],
    chains: _Chains,
    validator_id: str,
) -> tuple[int, int]:
    """File the 6 INITIAL validations + the 10 EXCEPTION records (Step 5 item 6), transcribed
    from the ratified dossier map. Returns ``(validations, exceptions)`` counts."""
    today = utcnow().date()
    actor = ModelValidationActor(actor_id=validator_id)

    flagship_evidence: dict[str, tuple[str, ...]] = {
        "risk.var.parametric": (*chains.var_run_ids, chains.bt1_run_id),
        "risk.var.historical": chains.hs_run_ids,
        "risk.var.parametric_total": (*chains.total_run_ids, chains.bt2_run_id),
        "risk.var.parametric_es": (chains.es_run_id,),
        "risk.var.parametric_es_total": (chains.es_total_run_id,),
        "risk.var_backtest": (chains.bt1_run_id, chains.bt2_run_id),
    }

    validations = 0
    for code in FLAGSHIP_CODES:
        dossier = FLAGSHIP_DOSSIERS[code]
        tier_dossier = TIER_DOSSIERS[code]
        tier = derive_model_tier(tier_dossier.materiality_rating, tier_dossier.complexity_rating)
        scope = (
            f"{dossier.scope_note} TIER RE-AFFIRMED AT VALIDATION (SS1/23 P1.3(e) hook): {tier} "
            f"(materiality {tier_dossier.materiality_rating} x complexity "
            f"{tier_dossier.complexity_rating}). {NON_INDEPENDENCE_DISCLOSURE}"
        )
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=actor,
            request=RecordValidationRequest(
                model_version_id=versions[code].id,
                validation_type=VALIDATION_TYPE_INITIAL,
                outcome=dossier.outcome,
                scope_summary=scope,
                conditions=dossier.conditions,
                report_ref="10_delivery_backlog/mg_1_decision_record.md",
                next_review_due=today + timedelta(days=365),
                findings=_findings_from_registry(
                    session, versions[code].id, dossier.finding_keys, code
                ),
                evidence=tuple(
                    ValidationEvidenceInput(evidence_type="CALCULATION_RUN", run_id=run_id)
                    for run_id in flagship_evidence[code]
                ),
            ),
        )
        validations += 1

    #: Evidence for the excepted codes: the model's OWN campaign runs where the chain executed
    #: some, else a DOCUMENT citation of the ratified record (honest — no run is invented).
    exception_evidence: dict[str, tuple[ValidationEvidenceInput, ...]] = {
        "risk.covariance.sample": tuple(
            ValidationEvidenceInput(evidence_type="CALCULATION_RUN", run_id=run_id)
            for run_id in chains.covariance_run_ids
        ),
        "risk.factor_exposure.allocation": (
            ValidationEvidenceInput(
                evidence_type="CALCULATION_RUN", run_id=chains.factor_exposure_run_id
            ),
        ),
        "risk.proxy_weight.regression": (
            ValidationEvidenceInput(evidence_type="CALCULATION_RUN", run_id=chains.estimate_run_id),
        ),
        "perf.return.twr": (
            ValidationEvidenceInput(
                evidence_type="CALCULATION_RUN", run_id=chains.portfolio_return_run_id
            ),
        ),
        "perf.return.desmoothed_geltner": (
            ValidationEvidenceInput(
                evidence_type="CALCULATION_RUN", run_id=chains.desmoothed_run_id
            ),
        ),
    }
    no_run_document = ValidationEvidenceInput(
        evidence_type="DOCUMENT",
        reference=(
            "10_delivery_backlog/mg_1_decision_record.md (OD-MG-1-G: registered this slice; "
            "no governed run of this family has executed in the demo tenant yet)"
        ),
    )

    exceptions = 0
    for code in sorted(set(TIER_DOSSIERS) - set(FLAGSHIP_CODES)):
        tier_dossier = TIER_DOSSIERS[code]
        tier = derive_model_tier(tier_dossier.materiality_rating, tier_dossier.complexity_rating)
        expiry = today + timedelta(days=MODEL_TIER_REVIEW_MAX_DAYS[tier])
        limitations = _registered_limitations(session, versions[code].id)
        if not limitations:
            raise DemoCampaignError(f"{code} registered no limitation rows — refusing")
        scope = (
            f"Use-before-validation EXCEPTION for {code} (tier {tier}: materiality "
            f"{tier_dossier.materiality_rating} x complexity {tier_dossier.complexity_rating}), "
            f"time-boxed to {expiry.isoformat()} per the tier-bounded ceiling (OD-MG-1-D). "
            f"{NON_INDEPENDENCE_DISCLOSURE}"
        )
        record_validation(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=actor,
            request=RecordValidationRequest(
                model_version_id=versions[code].id,
                validation_type=VALIDATION_TYPE_EXCEPTION,
                outcome=VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
                scope_summary=scope,
                conditions=EXCEPTION_CONDITIONS,
                report_ref="10_delivery_backlog/mg_1_decision_record.md",
                next_review_due=expiry,
                findings=(
                    ValidationFindingInput(
                        finding_text=limitations[0],
                        severity="LOW",
                        authored_by="Andrew Cox",
                    ),
                ),
                evidence=exception_evidence.get(code, (no_run_document,)),
            ),
        )
        exceptions += 1
    return validations, exceptions


def run_demo_campaign(session: Session) -> CampaignSummary:
    """Execute the full ratified campaign against the DEMO tenant (OD-MG-1-G). The caller owns
    the commit; the runner arms (and re-arms) the demo tenant's RLS context itself."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        existing = session.execute(
            select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
        ).scalar_one()
        if existing:
            raise DemoCampaignAlreadySeededError(int(existing))

        registrar_id, validator_id = _seed_principals(session)
        book = _seed_book(session, registrar_id)
        versions = _register_models(session, registrar_id)
        chains = _build_chains(session, book, versions, registrar_id)
        tiers = _assign_tiers(session, versions, validator_id)
        validations, exceptions = _file_records(session, versions, chains, validator_id)
        session.flush()
        return CampaignSummary(
            tenant_id=DEMO_TENANT_ID,
            validator_user_id=validator_id,
            registrar_user_id=registrar_id,
            portfolio_id=book.portfolio_id,
            model_ids={code: v.model_id for code, v in versions.items()},
            model_version_ids={code: v.id for code, v in versions.items()},
            models_registered=len(versions),
            tiers_assigned=tiers,
            initial_validations_filed=validations,
            exceptions_filed=exceptions,
            backtest_pairs=_BACKTEST_PAIRS,
            var_run_ids=chains.var_run_ids,
            hs_run_ids=chains.hs_run_ids,
            total_run_ids=chains.total_run_ids,
            es_run_id=chains.es_run_id,
            es_total_run_id=chains.es_total_run_id,
            portfolio_return_run_id=chains.portfolio_return_run_id,
            bt1_run_id=chains.bt1_run_id,
            bt2_run_id=chains.bt2_run_id,
            desmoothed_run_id=chains.desmoothed_run_id,
            estimate_run_id=chains.estimate_run_id,
        )
    finally:
        detach()
