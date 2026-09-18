"""The BOOK-1a orchestrator: one tenant a CRO would recognise, seeded through the real services.

`10_delivery_backlog/w20_book1a_remit.md` (RATIFIED 2026-09-17). Every row here is written by the
same governed capture and run functions the application uses; nothing is inserted behind them
except the three rows the application cannot write for itself: the ``tenant`` registry row, the
tenant's currencies, and the principals (the base campaign's shape, `demo/campaign.py`).

**Refuse-not-skip.** A tenant already present raises :class:`DemoTenantAlreadySeededError`; the
caller owns the one commit, so a failure anywhere leaves nothing behind.

**Admitted at ONE site.** The base campaign admits its tenant from two places, and a mutant anchored
on one of them was green while the other shipped the 401 (the 2026-08-25 fix). This orchestrator
admits in :func:`_create_tenant` and nowhere else.

**No clock.** Every ``valid_from`` is ``book.T0``; every as-of is a date from the marked year. The
two engine gates that read the real clock are handled by parameter (the liquidity tier age,
DS-B1a-8) and by omission (no EXCEPTION validation is filed).

**The public families only.** The private sleeves, the limits and the daily last quarter are
BOOK-1b's; the backtest families need the daily boundaries and are BOOK-1b's too.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.classification.models import (
    BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    BASIS_NOT_APPLICABLE,
    DIMENSION_KIND_COUNTRY_OF_RISK,
    DIMENSION_KIND_LIQUIDITY_TIER,
    DIMENSION_KIND_SECTOR_INDUSTRY,
    LIQUIDITY_TIER_CODES,
    LIQUIDITY_TIER_SEMANTICS,
    SCHEME_FAMILY_ISIC,
    SCHEME_FAMILY_ISO_3166_1,
    SCHEME_FAMILY_SEC_22E4,
    ClassificationNode,
    ClassificationScheme,
)
from irp_shared.classification.service import (
    ClassificationActor,
    capture_assignment,
    create_node,
    create_scheme,
)
from irp_shared.concentration.bootstrap import register_concentration_model
from irp_shared.concentration.events import ConcentrationActor
from irp_shared.concentration.service import run_concentration
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo_tenant import book
from irp_shared.entitlement.bootstrap import PERMISSIONS, SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.liquidity.bootstrap import register_liquidity_model
from irp_shared.liquidity.service import run_liquidity
from irp_shared.marketdata import (
    RETURN_BASIS_TOTAL,
    BenchmarkActor,
    ConstituentInput,
    CurveActor,
    CurveNode,
    FactorActor,
    FxRateActor,
    ProxyMappingActor,
    capture_benchmark,
    capture_benchmark_return,
    capture_curve,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    capture_membership,
    capture_proxy_mapping,
    resolve_benchmark,
    resolve_factor,
)
from irp_shared.model.models import ModelVersion
from irp_shared.perf import (
    BenchmarkRelativeActor,
    PortfolioReturnActor,
    register_benchmark_relative_model,
    register_portfolio_return_model,
    run_benchmark_relative,
    run_portfolio_return,
)
from irp_shared.perf.bootstrap import register_rolling_risk_model_v2, register_sharpe_model_v2
from irp_shared.perf.rolling_service import RollingRiskActor, run_rolling_risk
from irp_shared.perf.sharpe_service import SharpeRatioActor, run_sharpe_ratio
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.calendar import HolidaySpec, create_calendar, refresh_calendar_holidays
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.instrument_terms import create_instrument_terms
from irp_shared.reference.issuer import create_issuer
from irp_shared.reference.legal_entity import create_legal_entity
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.reference.xnys_holidays import XNYS_COMPLETE_THROUGH, XNYS_HOLIDAYS
from irp_shared.risk import (
    ActiveRiskActor,
    CovarianceActor,
    FactorExposureActor,
    ScenarioActor,
    SensitivityActor,
    VarActor,
    capture_scenario_shock,
    create_scenario_definition,
    register_active_risk_model,
    register_covariance_model,
    register_factor_exposure_model,
    register_historical_var_model,
    register_scenario_model,
    register_sensitivity_model,
    register_var_model,
    register_var_parametric_es_model,
    run_active_risk,
    run_covariance,
    run_factor_exposure,
    run_scenario,
    run_sensitivities,
    run_var,
    run_var_historical,
)
from irp_shared.risk.bootstrap import register_factor_exposure_loadings_model
from irp_shared.snapshot import (
    CurveSelector,
    build_rolling_risk_snapshot,
    build_sharpe_snapshot,
    build_var_hs_snapshot,
)
from irp_shared.snapshot.events import SnapshotActor
from irp_shared.tenancy.models import PROVENANCE_ONBOARDED, TENANT_STATUS_ACTIVE, Tenant
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

Log = Callable[[str], None]


class DemoTenantError(RuntimeError):
    """A seeding step did not produce the state the remit requires (fail-loud)."""


class DemoTenantAlreadySeededError(RuntimeError):
    """Refuse-not-skip: the Northlight tenant already exists. Reset the schema and re-seed."""

    def __init__(self) -> None:
        super().__init__(
            f"tenant {book.TENANT_ID} ({book.TENANT_CODE}) already exists — refusing to re-seed; "
            f"the seed writes append-only governed rows and never converges. Reset the schema "
            f"first."
        )


#: The principals a CRO-facing demo needs someone to sign in as. Read sets only, from the
#: governed catalog; the two maker roles hold the run and register verbs the seed itself uses.
_READ_PERMS = (
    "position.view",
    "valuation.view",
    "portfolio.view",
    "risk.view",
    "exposure.view",
    "perf.view",
    "model.inventory.view",
    "snapshot.view",
    "lineage.view",
    "concentration.view",
    "concentration.issuer.view",
    "liquidity.view",
    "limit.view",
    "breach.view",
    "marketdata.view",
    "reference.instrument.view",
    "reference.issuer.view",
    "reference.classification.view",
    "reference.classification_assignment.view",
    "reference.calendar.view",
    "report.view",
    "schedule.view",
)
_PRINCIPALS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    # (external_subject, display_name, role code, role name, permission codes)
    (
        "northlight-cro",
        "Eleanor Vance",
        "cro_2l",
        "Chief Risk Officer (2L)",
        _READ_PERMS + ("limit.approve", "breach.review"),
    ),
    (
        "northlight-pm",
        "Daniel Okafor",
        "portfolio_manager_1l",
        "Portfolio Manager (1L)",
        _READ_PERMS + ("breach.respond",),
    ),
    (
        "northlight-rm",
        "Priya Raman",
        "risk_manager_2l",
        "Risk Manager (2L)",
        _READ_PERMS + ("limit.manage", "breach.review", "model.validate"),
    ),
    (
        "northlight-analyst",
        "Tomas Lindqvist",
        "risk_analyst_1l",
        "Risk Analyst (1L)",
        _READ_PERMS
        + (
            "risk.run",
            "perf.run",
            "exposure.aggregate.run",
            "concentration.run",
            "liquidity.run",
            "model.inventory.register",
            "marketdata.ingest",
            "position.edit",
            "valuation.edit",
            "portfolio.edit",
            "reference.instrument.edit",
            "reference.issuer.edit",
            "reference.legal_entity.edit",
            "reference.classification.edit",
            "reference.calendar.edit",
            "snapshot.create",
        ),
    ),
    (
        "northlight-auditor",
        "Internal Audit (3L, read-only)",
        "auditor_3l",
        "Auditor (3L, read-only)",
        _READ_PERMS,
    ),
)


@dataclass(frozen=True)
class SeedSummary:
    tenant_id: str
    principal_ids: dict[str, str]
    fund_ids: dict[str, str]
    account_ids: dict[str, str]
    instruments: int
    boundaries: int
    month_ends: int
    marks: int
    fx_rates: int
    factor_returns: int
    loadings: int
    model_version_ids: dict[str, str]
    runs: dict[str, int]
    var_run_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass
class _Refs:
    analyst_id: str = ""
    fund_ids: dict[str, str] = field(default_factory=dict)
    account_ids: dict[str, str] = field(default_factory=dict)
    instrument_ids: dict[str, str] = field(default_factory=dict)
    factor_ids: dict[str, str] = field(default_factory=dict)
    benchmark_ids: dict[str, str] = field(default_factory=dict)
    index_member_ids: dict[str, str] = field(default_factory=dict)
    risk_free_ids: dict[str, str] = field(default_factory=dict)
    isic_id: str = ""
    iso_id: str = ""
    tier_scheme_id: str = ""
    scenario_id: str = ""
    versions: dict[str, ModelVersion] = field(default_factory=dict)
    paths: book.Paths | None = None
    counts: dict[str, int] = field(default_factory=dict)
    #: (fund code, boundary) -> the exposure run at the fund's designated return account.
    account_exposure: dict[tuple[str, date], str] = field(default_factory=dict)


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _count(refs: _Refs, key: str, n: int = 1) -> None:
    # Two statements on purpose: the aggregation census reads `d[k] = d.get(k) + x` as an
    # accumulation site, and a progress counter is not one.
    current = refs.counts.get(key, 0)
    refs.counts[key] = current + n


def _require_completed(result: object, label: str) -> None:
    status = getattr(result, "status", None)
    if status != "COMPLETED":
        reason = getattr(result, "failure_reason", None)
        raise DemoTenantError(f"{label} did not COMPLETE (status={status!r}, reason={reason!r})")


# --- 1. tenant, admission, principals ------------------------------------------------------------


def _create_tenant(session: Session) -> None:
    """The ONE site that admits the tenant to the ENT-074 registry."""
    if session.get(Tenant, book.TENANT_ID) is not None:
        raise DemoTenantAlreadySeededError()
    session.add(
        Tenant(
            id=book.TENANT_ID,
            code=book.TENANT_CODE,
            display_name=book.TENANT_NAME,
            status=TENANT_STATUS_ACTIVE,
            provenance=PROVENANCE_ONBOARDED,
        )
    )
    for code, name in book.CURRENCIES:
        session.add(Currency(tenant_id=book.TENANT_ID, code=code, name=name, valid_from=book.T0))
    session.flush()


def _permission(session: Session, code: str) -> Permission:
    catalog = dict(PERMISSIONS)
    if code not in catalog:
        raise DemoTenantError(f"permission {code!r} is not in the governed catalog — refusing")
    perm = session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
    if perm is None:
        perm = Permission(code=code, description=catalog[code])
        session.add(perm)
        session.flush()
    return perm


def _seed_principals(session: Session) -> dict[str, str]:
    ids: dict[str, str] = {}
    for subject, name, role_code, role_name, perms in _PRINCIPALS:
        user = AppUser(tenant_id=book.TENANT_ID, display_name=name, external_subject=subject)
        role = Role(tenant_id=book.TENANT_ID, code=role_code, name=role_name)
        session.add_all([user, role])
        session.flush()
        for code in perms:
            session.add(
                RolePermission(role_id=role.id, permission_id=_permission(session, code).id)
            )
        session.add(UserRole(tenant_id=book.TENANT_ID, user_id=user.id, role_id=role.id))
        ids[subject] = user.id
    session.flush()
    return ids


# --- 2. reference: calendar, schemes, issuers, funds, instruments, positions -------------


def _seed_calendar(session: Session, actor_id: str) -> None:
    calendar = create_calendar(
        session,
        tenant_id=book.TENANT_ID,
        code="XNYS",
        name="New York Stock Exchange",
        actor=ReferenceActor(actor_id=actor_id),
        mic="XNYS",
    )
    refresh_calendar_holidays(
        session,
        calendar,
        actor=ReferenceActor(actor_id=actor_id),
        holidays=[HolidaySpec(holiday_date=d, name=n) for d, n in XNYS_HOLIDAYS],
        complete_through=XNYS_COMPLETE_THROUGH,
    )


def _system_scheme(
    session: Session,
    *,
    actor_id: str,
    family: str,
    version: str,
    name: str,
    dimension: str,
    authority: str,
    nodes: tuple[tuple[str, str], ...],
    descriptions: dict[str, str] | None = None,
) -> str:
    """Resolve-or-create a SYSTEM-tenant scheme: created on a fresh database, reused on one that
    already holds the base campaign (the unique constraint refuses a second creation)."""
    existing = session.execute(
        select(ClassificationScheme).where(
            ClassificationScheme.tenant_id == SYSTEM_TENANT_ID,
            ClassificationScheme.scheme_family == family,
            ClassificationScheme.version_label == version,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Nodes this book needs may be missing from a skeleton another stage created.
        present = {
            n
            for (n,) in session.execute(
                select(ClassificationNode.code).where(ClassificationNode.scheme_id == existing.id)
            )
        }
        actor = ClassificationActor(tenant_id=SYSTEM_TENANT_ID, actor_id=actor_id)
        for code, label in nodes:
            if code not in present:
                create_node(
                    session, actor=actor, scheme_id=existing.id, code=code, name=label, level=1
                )
        session.flush()
        return str(existing.id)
    actor = ClassificationActor(tenant_id=SYSTEM_TENANT_ID, actor_id=actor_id)
    scheme = create_scheme(
        session,
        actor=actor,
        scheme_family=family,
        version_label=version,
        name=name,
        dimension_kind=dimension,
        authority=authority,
    )
    for code, label in nodes:
        kwargs = (
            {"description": descriptions[code]} if descriptions and code in descriptions else {}
        )
        create_node(
            session, actor=actor, scheme_id=scheme.id, code=code, name=label, level=1, **kwargs
        )
    session.flush()
    return str(scheme.id)


def _seed_schemes(session: Session, refs: _Refs) -> None:
    refs.isic_id = _system_scheme(
        session,
        actor_id=refs.analyst_id,
        family=SCHEME_FAMILY_ISIC,
        version="Rev. 5",
        name="ISIC Revision 5",
        dimension=DIMENSION_KIND_SECTOR_INDUSTRY,
        authority="UNSD",
        nodes=book.SECTORS,
    )
    refs.iso_id = _system_scheme(
        session,
        actor_id=refs.analyst_id,
        family=SCHEME_FAMILY_ISO_3166_1,
        version="2026",
        name="ISO 3166-1 alpha-2",
        dimension=DIMENSION_KIND_COUNTRY_OF_RISK,
        authority="ISO/UNSD M49",
        nodes=book.COUNTRIES,
    )
    refs.tier_scheme_id = _system_scheme(
        session,
        actor_id=refs.analyst_id,
        family=SCHEME_FAMILY_SEC_22E4,
        version="2024",
        name="SEC Rule 22e-4 liquidity categories",
        dimension=DIMENSION_KIND_LIQUIDITY_TIER,
        authority="SEC",
        nodes=tuple((c, c.replace("_", " ").title()) for c in LIQUIDITY_TIER_CODES),
        descriptions=LIQUIDITY_TIER_SEMANTICS,
    )


def _seed_funds(session: Session, refs: _Refs) -> None:
    pf_actor = PortfolioActor(actor_id=refs.analyst_id)
    for fund in book.FUNDS:
        root = create_portfolio(
            session,
            tenant_id=book.TENANT_ID,
            code=fund.code,
            name=fund.name,
            node_type="FUND",
            base_currency_code=fund.base_currency,
            actor=pf_actor,
        ).id
        refs.fund_ids[fund.code] = root
        for sleeve in fund.sleeves:
            strat = create_portfolio(
                session,
                tenant_id=book.TENANT_ID,
                code=sleeve.code,
                name=sleeve.name,
                node_type="STRATEGY",
                actor=pf_actor,
                parent_portfolio_id=root,
            ).id
            for account in sleeve.accounts:
                refs.account_ids[account.code] = create_portfolio(
                    session,
                    tenant_id=book.TENANT_ID,
                    code=account.code,
                    name=account.name,
                    node_type="ACCOUNT",
                    actor=pf_actor,
                    parent_portfolio_id=strat,
                ).id
    session.flush()


def _seed_instruments(session: Session, refs: _Refs) -> None:
    ref_actor = ReferenceActor(actor_id=refs.analyst_id)
    cls_actor = ClassificationActor(tenant_id=book.TENANT_ID, actor_id=refs.analyst_id)
    issuer_ids: dict[str, str] = {}
    issuers = {i.code: i for i in book.ISSUERS}
    for issuer in book.ISSUERS:
        core = create_legal_entity(
            session,
            tenant_id=book.TENANT_ID,
            code=issuer.code,
            name=issuer.name,
            jurisdiction=issuer.country,
            actor=ref_actor,
        )
        issuer_ids[issuer.code] = str(
            create_issuer(
                session,
                tenant_id=book.TENANT_ID,
                legal_entity_id=core.id,
                issuer_type=issuer.issuer_type,
                actor=ref_actor,
            ).id
        )
    for spec in book.INSTRUMENTS:
        inst = create_instrument(
            session,
            tenant_id=book.TENANT_ID,
            code=spec.code,
            name=spec.name,
            asset_class=spec.asset_class,
            actor=ref_actor,
            issuer_id=issuer_ids[spec.issuer],
            currency_code=spec.currency,
        ).id
        refs.instrument_ids[spec.code] = inst
        if spec.face_value is not None:
            create_instrument_terms(
                session,
                instrument_id=inst,
                acting_tenant=book.TENANT_ID,
                actor=ref_actor,
                valid_from=book.T0,
                face_value=spec.face_value,
                denomination_currency=spec.currency,
                coupon_rate=spec.coupon_rate,
            )
        issuer = issuers[spec.issuer]
        for dimension, scheme_id, node, basis in (
            (DIMENSION_KIND_SECTOR_INDUSTRY, refs.isic_id, issuer.sector, BASIS_NOT_APPLICABLE),
            (
                DIMENSION_KIND_COUNTRY_OF_RISK,
                refs.iso_id,
                issuer.country,
                BASIS_IMMEDIATE_ISSUER_RESIDENCE,
            ),
            (
                DIMENSION_KIND_LIQUIDITY_TIER,
                refs.tier_scheme_id,
                spec.liquidity_tier,
                BASIS_NOT_APPLICABLE,
            ),
        ):
            capture_assignment(
                session,
                actor=cls_actor,
                entity_type="instrument",
                entity_id=inst,
                scheme_id=scheme_id,
                dimension_kind=dimension,
                node_code=node,
                basis=basis,
            )
        create_position(
            session,
            portfolio_id=refs.account_ids[spec.account],
            instrument_id=inst,
            acting_tenant=book.TENANT_ID,
            actor=PositionActor(actor_id=refs.analyst_id),
            quantity=spec.quantity,
            valid_from=book.T0,
        )
    session.flush()


# --- 3. market data: marks, FX, factors, returns, loadings, benchmarks, curve ------------


def _seed_marks_and_fx(session: Session, refs: _Refs, log: Log) -> None:
    paths = refs.paths
    assert paths is not None
    val_actor = ValuationActor(actor_id=refs.analyst_id)
    fx_actor = FxRateActor(actor_id=refs.analyst_id)
    for i, on in enumerate(book.BOUNDARIES):
        for spec in book.INSTRUMENTS:
            create_valuation(
                session,
                portfolio_id=refs.account_ids[spec.account],
                instrument_id=refs.instrument_ids[spec.code],
                valuation_date=on,
                acting_tenant=book.TENANT_ID,
                actor=val_actor,
                mark_value=paths.marks[spec.code][on],
                currency_code=spec.currency,
                valid_from=book.T0,
            )
            _count(refs, "marks")
        for (base, quote), series in paths.fx.items():
            capture_fx_rate(
                session,
                base_currency=base,
                quote_currency=quote,
                rate_date=on,
                rate=series[on],
                acting_tenant=book.TENANT_ID,
                actor=fx_actor,
                valid_from=book.T0,
            )
            _count(refs, "fx_rates")
        if i % 10 == 9:
            session.flush()
            log(f"  marks and FX through {on.isoformat()} ({i + 1}/{len(book.BOUNDARIES)})")
    session.flush()


def _seed_factors(session: Session, refs: _Refs, log: Log) -> None:
    paths = refs.paths
    assert paths is not None
    actor = FactorActor(actor_id=refs.analyst_id)
    for f in book.FACTORS:
        fid = capture_factor(
            session,
            factor_code=f.code,
            factor_source=book.FACTOR_SOURCE,
            factor_family=f.family,
            currency_code=f.currency,
            acting_tenant=book.TENANT_ID,
            actor=actor,
            factor_name=f.name,
            valid_from=book.T0,
        ).id
        refs.factor_ids[f.code] = fid
        factor = resolve_factor(session, fid, acting_tenant=book.TENANT_ID)
        for on, value in paths.factor_returns[f.code].items():
            capture_factor_return(
                session,
                factor,
                return_date=on,
                return_value=value,
                acting_tenant=book.TENANT_ID,
                actor=actor,
                valid_from=book.T0,
            )
            _count(refs, "factor_returns")
        session.flush()
        log(f"  factor {f.code}: {len(paths.factor_returns[f.code])} returns")


def _seed_loadings(session: Session, refs: _Refs) -> None:
    """One MANUAL loading per (instrument, factor) pair the model should see; every instrument gets
    at least its currency loading, because an atom with no loading at all refuses."""
    actor = ProxyMappingActor(actor_id=refs.analyst_id)

    def _load(inst_code: str, factor_code: str, weight: Decimal) -> None:
        capture_proxy_mapping(
            session,
            private_instrument_id=refs.instrument_ids[inst_code],
            factor_id=refs.factor_ids[factor_code],
            weight=weight,
            acting_tenant=book.TENANT_ID,
            actor=actor,
            valid_from=book.T0,
        )
        _count(refs, "loadings")

    fund_base = {
        account.code: fund.base_currency
        for fund in book.FUNDS
        for sleeve in fund.sleeves
        for account in sleeve.accounts
    }
    for spec in book.INSTRUMENTS:
        # A currency loading of one where the instrument's currency differs from its fund's base
        # (the position moves with that FX rate in base terms) and an explicit ZERO where it is the
        # base itself: zero is coverage, so the atom does not refuse, and it emits no exposure, so
        # a euro bond in the euro fund carries no FX risk against its own numeraire.
        foreign = spec.currency != fund_base[spec.account]
        _load(spec.code, f"FX_{spec.currency}", Decimal("1") if foreign else Decimal("0"))
        if spec.market_beta != 0:
            _load(spec.code, "MKT_GLOBAL_EQ", spec.market_beta)
        if spec.rate_loading != 0:
            _load(
                spec.code,
                "RATES_USD_10Y" if spec.currency == "USD" else "RATES_EUR_10Y",
                spec.rate_loading,
            )
        if spec.credit_factor is not None and spec.credit_loading != 0:
            _load(spec.code, spec.credit_factor, spec.credit_loading)
    session.flush()


def _seed_benchmarks(session: Session, refs: _Refs) -> None:
    """One composite benchmark per fund made of INDEX MEMBERS the fund does not hold (unheld
    instruments with a currency, so active risk can map them to currency factors), constituents
    pinned at every month-end, and a TOTAL-basis return per boundary in the fund's base from the
    members' own factor-implied paths — never a subset of the fund's own marks."""
    paths = refs.paths
    assert paths is not None
    actor = BenchmarkActor(actor_id=refs.analyst_id)
    ref_actor = ReferenceActor(actor_id=refs.analyst_id)
    for fund in book.FUNDS:
        bm = capture_benchmark(
            session,
            benchmark_code=fund.benchmark_code,
            benchmark_source=book.BENCHMARK_SOURCE,
            benchmark_currency=fund.base_currency,
            acting_tenant=book.TENANT_ID,
            actor=actor,
            benchmark_name=fund.benchmark_name,
            index_family="COMPOSITE",
        )
        constituents: list[ConstituentInput] = []
        for member in book.BENCHMARK_MEMBERS[fund.code]:
            inst = create_instrument(
                session,
                tenant_id=book.TENANT_ID,
                code=member.code,
                name=member.name,
                asset_class="INDEX_BASKET",
                actor=ref_actor,
                currency_code=member.currency,
            ).id
            refs.index_member_ids[member.code] = inst
            constituents.append(
                ConstituentInput(
                    instrument_id=inst,
                    weight=Decimal(member.weight),
                    constituent_currency=member.currency,
                )
            )
        for on in book.MONTH_ENDS:
            capture_membership(
                session,
                bm,
                effective_date=on,
                constituents=constituents,
                acting_tenant=book.TENANT_ID,
                actor=actor,
                valid_from=book.T0,
            )
        head = resolve_benchmark(session, bm.id, acting_tenant=book.TENANT_ID)
        for on, value in paths.benchmark_returns[fund.code].items():
            capture_benchmark_return(
                session,
                head,
                return_date=on,
                return_basis=RETURN_BASIS_TOTAL,
                return_value=value,
                acting_tenant=book.TENANT_ID,
                actor=actor,
            )
        refs.benchmark_ids[fund.code] = str(head.id)
        _count(
            refs, "benchmark_rows", len(book.MONTH_ENDS) + len(paths.benchmark_returns[fund.code])
        )
    for ccy, (code, name, monthly) in book.RISK_FREE.items():
        rf = capture_benchmark(
            session,
            benchmark_code=code,
            benchmark_source=book.BENCHMARK_SOURCE,
            benchmark_currency=ccy,
            acting_tenant=book.TENANT_ID,
            actor=actor,
            benchmark_name=name,
            index_family="CASH",
        )
        # One TOTAL return per measured month, dated at that month's end (Jul 2025 .. Jun 2026).
        for on, monthly_text in zip(book.MONTH_ENDS[1:], monthly, strict=True):
            capture_benchmark_return(
                session,
                rf,
                return_date=on,
                return_basis=RETURN_BASIS_TOTAL,
                return_value=Decimal(monthly_text),
                acting_tenant=book.TENANT_ID,
                actor=actor,
            )
            _count(refs, "benchmark_rows")
        refs.risk_free_ids[ccy] = str(rf.id)
    session.flush()


def _seed_curve_and_scenario(session: Session, refs: _Refs) -> None:
    capture_curve(
        session,
        curve_type="SWAP",
        currency_code="USD",
        curve_date=book.CURVE_DATE,
        curve_source=book.CURVE_SOURCE,
        nodes=[
            CurveNode(
                tenor_label=label, tenor_days=days, value_type="ZERO_RATE", point_value=Decimal(v)
            )
            for label, days, v in book.CURVE_NODES
        ],
        acting_tenant=book.TENANT_ID,
        actor=CurveActor(actor_id=refs.analyst_id),
        valid_from=book.T0,
    )
    actor = ScenarioActor(actor_id=refs.analyst_id)
    definition = create_scenario_definition(
        session,
        code=book.SCENARIO_CODE,
        name=book.SCENARIO_NAME,
        scenario_type="HYPOTHETICAL",
        acting_tenant=book.TENANT_ID,
        actor=actor,
    )
    for code, shock in book.SCENARIO_SHOCKS:
        capture_scenario_shock(
            session,
            scenario_definition_id=definition.id,
            factor_id=refs.factor_ids[code],
            shock_value=Decimal(shock),
            acting_tenant=book.TENANT_ID,
            actor=actor,
        )
    refs.scenario_id = str(definition.id)
    session.flush()


# --- 4. models ---------------------------------------------------------------------------------


def _register_models(session: Session, refs: _Refs) -> None:
    t, a, cv = book.TENANT_ID, refs.analyst_id, book.CODE_VERSION
    refs.versions = {
        "factor_exposure.allocation": register_factor_exposure_model(
            session, tenant_id=t, actor_id=a, code_version=cv
        ),
        "factor_exposure.loadings": register_factor_exposure_loadings_model(
            session, tenant_id=t, actor_id=a, code_version=cv
        ),
        "covariance": register_covariance_model(
            session,
            tenant_id=t,
            actor_id=a,
            code_version=cv,
            window_observations=book.COVARIANCE_WINDOW,
        ),
        "var.parametric": register_var_model(
            session, tenant_id=t, actor_id=a, code_version=cv, confidence_level=book.VAR_CONFIDENCE
        ),
        "var.es": register_var_parametric_es_model(
            session, tenant_id=t, actor_id=a, code_version=cv, confidence_level=book.ES_CONFIDENCE
        ),
        "var.historical": register_historical_var_model(
            session,
            tenant_id=t,
            actor_id=a,
            code_version=cv,
            confidence_level=book.HS_CONFIDENCE,
            window_observations=book.HS_WINDOW,
        ),
        "active_risk": register_active_risk_model(
            session, tenant_id=t, actor_id=a, code_version=cv
        ),
        "scenario": register_scenario_model(session, tenant_id=t, actor_id=a, code_version=cv),
        "sensitivity": register_sensitivity_model(
            session, tenant_id=t, actor_id=a, code_version=cv
        ),
        "portfolio_return": register_portfolio_return_model(
            session, tenant_id=t, actor_id=a, code_version=cv
        ),
        "benchmark_relative": register_benchmark_relative_model(
            session, tenant_id=t, actor_id=a, code_version=cv
        ),
        "rolling_risk": register_rolling_risk_model_v2(
            session, tenant_id=t, actor_id=a, code_version=cv
        ),
        "sharpe": register_sharpe_model_v2(session, tenant_id=t, actor_id=a, code_version=cv),
        "concentration": register_concentration_model(
            session, tenant_id=t, actor_id=a, code_version=cv, coverage_floor=book.COVERAGE_FLOOR
        ),
        "liquidity": register_liquidity_model(
            session,
            tenant_id=t,
            actor_id=a,
            code_version=cv,
            coverage_floor=book.COVERAGE_FLOOR,
            tier_max_age_days=book.LIQUIDITY_TIER_MAX_AGE_DAYS,
        ),
    }
    session.flush()


# --- 5. runs -----------------------------------------------------------------------------------


def _run_exposure(
    session: Session, refs: _Refs, portfolio_id: str, base: str, on: date, label: str
) -> str:
    result = run_exposure(
        session,
        acting_tenant=book.TENANT_ID,
        actor=ExposureActor(actor_id=refs.analyst_id),
        code_version=book.CODE_VERSION,
        environment_id=book.ENVIRONMENT_ID,
        portfolio_id=portfolio_id,
        as_of_valid_at=_dt(on),
        base_currency=base,
    )
    _require_completed(result, f"{label} exposure @{on.isoformat()}")
    _count(refs, "exposure")
    return result.run.run_id


def _run_account_boundaries(session: Session, refs: _Refs, log: Log) -> None:
    """Every boundary's exposure run at each fund's designated return account, feeding the
    return chain. (The scenario runs over each fund's SCENARIO account at month-ends, in the
    month-end chain: the scenario engine is single-portfolio and currency-only, so the account it
    stresses must be one holding currencies other than the fund's base.)"""
    for fund in book.FUNDS:
        account = refs.account_ids[fund.return_account]
        for on in book.BOUNDARIES:
            refs.account_exposure[(fund.code, on)] = _run_exposure(
                session, refs, account, fund.base_currency, on, fund.return_account
            )
        session.flush()
        log(f"  {fund.return_account}: {len(book.BOUNDARIES)} boundary exposure runs")


def _run_month_end_chain(session: Session, refs: _Refs, log: Log) -> dict[str, tuple[str, ...]]:
    """At every month-end: the shared covariance matrices, then per fund the two factor-exposure
    paths and every risk family that consumes them."""
    t, a, cv, env = book.TENANT_ID, refs.analyst_id, book.CODE_VERSION, book.ENVIRONMENT_ID
    v = refs.versions
    currency_factors = [refs.factor_ids[c] for c in book.CURRENCY_FACTOR_CODES]
    all_factors = [refs.factor_ids[f.code] for f in book.FACTORS]
    var_runs: dict[str, list[str]] = {f.code: [] for f in book.FUNDS}
    root_exposure: dict[tuple[str, date], str] = {}
    for on in book.MONTH_ENDS:
        cov_ccy = run_covariance(
            session,
            acting_tenant=t,
            actor=CovarianceActor(actor_id=a),
            code_version=cv,
            environment_id=env,
            model_version_id=v["covariance"].id,
            factor_ids=currency_factors,
            as_of_valid_at=_dt(on),
        )
        _require_completed(cov_ccy, f"currency covariance @{on}")
        cov_all = run_covariance(
            session,
            acting_tenant=t,
            actor=CovarianceActor(actor_id=a),
            code_version=cv,
            environment_id=env,
            model_version_id=v["covariance"].id,
            factor_ids=all_factors,
            as_of_valid_at=_dt(on),
        )
        _require_completed(cov_all, f"loadings covariance @{on}")
        _count(refs, "covariance", 2)
        for fund in book.FUNDS:
            root = refs.fund_ids[fund.code]
            exp_run = _run_exposure(session, refs, root, fund.base_currency, on, fund.code)
            root_exposure[(fund.code, on)] = exp_run
            alloc = run_factor_exposure(
                session,
                acting_tenant=t,
                actor=FactorExposureActor(actor_id=a),
                code_version=cv,
                environment_id=env,
                model_version_id=v["factor_exposure.allocation"].id,
                exposure_run_id=exp_run,
                factor_ids=currency_factors,
            )
            _require_completed(alloc, f"{fund.code} allocation factor exposure @{on}")
            loads = run_factor_exposure(
                session,
                acting_tenant=t,
                actor=FactorExposureActor(actor_id=a),
                code_version=cv,
                environment_id=env,
                model_version_id=v["factor_exposure.loadings"].id,
                exposure_run_id=exp_run,
                factor_ids=all_factors,
            )
            _require_completed(loads, f"{fund.code} loadings factor exposure @{on}")
            _count(refs, "factor_exposure", 2)
            for key, label in (("var.parametric", "parametric VaR"), ("var.es", "parametric ES")):
                r = run_var(
                    session,
                    acting_tenant=t,
                    actor=VarActor(actor_id=a),
                    code_version=cv,
                    environment_id=env,
                    model_version_id=v[key].id,
                    exposure_run_id=loads.run.run_id,
                    covariance_run_id=cov_all.run.run_id,
                )
                _require_completed(r, f"{fund.code} {label} @{on}")
                _count(refs, key)
                if key == "var.parametric":
                    var_runs[fund.code].append(r.run.run_id)
            snapshot = build_var_hs_snapshot(
                session,
                acting_tenant=t,
                actor=SnapshotActor(actor_id=a),
                exposure_run_id=loads.run.run_id,
                window_observations=book.HS_WINDOW,
                as_of_valid_at=_dt(on),
            )
            hs = run_var_historical(
                session,
                acting_tenant=t,
                actor=VarActor(actor_id=a),
                code_version=cv,
                environment_id=env,
                model_version_id=v["var.historical"].id,
                snapshot_id=snapshot.id,
            )
            _require_completed(hs, f"{fund.code} historical VaR @{on}")
            _count(refs, "var.historical")
            ar = run_active_risk(
                session,
                acting_tenant=t,
                actor=ActiveRiskActor(actor_id=a),
                code_version=cv,
                environment_id=env,
                model_version_id=v["active_risk"].id,
                exposure_run_id=alloc.run.run_id,
                covariance_run_id=cov_ccy.run.run_id,
                benchmark_id=refs.benchmark_ids[fund.code],
                benchmark_effective_date=on,
            )
            _require_completed(ar, f"{fund.code} active risk @{on}")
            _count(refs, "active_risk")
            if fund.scenario_account is not None:
                # The scenario engine is single-portfolio AND currency-only, so it runs over
                # the ONE account that holds currencies other than the fund's base; a fund with
                # no such account has no meaningful FX scenario and runs none (book.FundSpec).
                sc_exposure = _run_exposure(
                    session,
                    refs,
                    refs.account_ids[fund.scenario_account],
                    fund.base_currency,
                    on,
                    fund.scenario_account,
                )
                sc_alloc = run_factor_exposure(
                    session,
                    acting_tenant=t,
                    actor=FactorExposureActor(actor_id=a),
                    code_version=cv,
                    environment_id=env,
                    model_version_id=v["factor_exposure.allocation"].id,
                    exposure_run_id=sc_exposure,
                    factor_ids=currency_factors,
                )
                _require_completed(sc_alloc, f"{fund.scenario_account} allocation exposure @{on}")
                _count(refs, "factor_exposure")
                sc = run_scenario(
                    session,
                    acting_tenant=t,
                    actor=ScenarioActor(actor_id=a),
                    code_version=cv,
                    environment_id=env,
                    model_version_id=v["scenario"].id,
                    factor_exposure_run_id=sc_alloc.run.run_id,
                    scenario_definition_id=refs.scenario_id,
                )
                _require_completed(sc, f"{fund.code} scenario ({fund.scenario_account}) @{on}")
                _count(refs, "scenario")
            con = run_concentration(
                session,
                acting_tenant=t,
                actor=ConcentrationActor(actor_id=a),
                code_version=cv,
                environment_id=env,
                model_version_id=str(v["concentration"].id),
                exposure_run_id=exp_run,
                scheme_by_dimension={
                    DIMENSION_KIND_SECTOR_INDUSTRY: refs.isic_id,
                    DIMENSION_KIND_COUNTRY_OF_RISK: refs.iso_id,
                },
            )
            _require_completed(con, f"{fund.code} concentration @{on}")
            _count(refs, "concentration")
            lq = run_liquidity(
                session,
                acting_tenant=t,
                actor_id=a,
                actor_type="user",
                exposure_run_id=exp_run,
                scheme_id=refs.tier_scheme_id,
                model_version=v["liquidity"],
                code_version=cv,
                environment_id=env,
            )
            _require_completed(lq, f"{fund.code} liquidity @{on}")
            _count(refs, "liquidity")
        session.flush()
        log(f"  month-end chain @{on.isoformat()} done")
    return {k: tuple(vals) for k, vals in var_runs.items()}


def _run_return_chains(session: Session, refs: _Refs, log: Log) -> None:
    """Per fund, at its designated return account: every boundary's exposure run, then the return
    run, benchmark-relative, rolling risk v2 and Sharpe v2 over the year (DS-B1a-4)."""
    t, a, cv, env = book.TENANT_ID, refs.analyst_id, book.CODE_VERSION, book.ENVIRONMENT_ID
    v = refs.versions
    for fund in book.FUNDS:
        boundary_runs = [refs.account_exposure[(fund.code, on)] for on in book.BOUNDARIES]
        ret = run_portfolio_return(
            session,
            acting_tenant=t,
            actor=PortfolioReturnActor(actor_id=a),
            code_version=cv,
            environment_id=env,
            model_version_id=v["portfolio_return"].id,
            exposure_run_ids=boundary_runs,
        )
        _require_completed(ret, f"{fund.code} portfolio return")
        _count(refs, "portfolio_return")
        br = run_benchmark_relative(
            session,
            acting_tenant=t,
            actor=BenchmarkRelativeActor(actor_id=a),
            code_version=cv,
            environment_id=env,
            model_version_id=v["benchmark_relative"].id,
            portfolio_return_run_id=ret.run.run_id,
            benchmark_id=refs.benchmark_ids[fund.code],
            return_basis=RETURN_BASIS_TOTAL,
        )
        _require_completed(br, f"{fund.code} benchmark relative")
        _count(refs, "benchmark_relative")
        rolling_snap = build_rolling_risk_snapshot(
            session,
            acting_tenant=t,
            actor=SnapshotActor(actor_id=a),
            portfolio_return_run_id=ret.run.run_id,
            holiday_calendar_code="XNYS",
        )
        rr = run_rolling_risk(
            session,
            acting_tenant=t,
            actor=RollingRiskActor(actor_id=a),
            code_version=cv,
            environment_id=env,
            model_version_id=str(v["rolling_risk"].id),
            window_months=book.ROLLING_WINDOWS,
            snapshot_id=str(rolling_snap.id),
        )
        _require_completed(rr, f"{fund.code} rolling risk")
        _count(refs, "rolling_risk")
        sharpe_snap = build_sharpe_snapshot(
            session,
            acting_tenant=t,
            actor=SnapshotActor(actor_id=a),
            portfolio_return_run_id=ret.run.run_id,
            risk_free_benchmark_id=refs.risk_free_ids[fund.base_currency],
            rf_return_basis=RETURN_BASIS_TOTAL,
            holiday_calendar_code="XNYS",
        )
        sh = run_sharpe_ratio(
            session,
            acting_tenant=t,
            actor=SharpeRatioActor(actor_id=a),
            code_version=cv,
            environment_id=env,
            model_version_id=str(v["sharpe"].id),
            window_months=book.SHARPE_WINDOWS,
            snapshot_id=str(sharpe_snap.id),
        )
        _require_completed(sh, f"{fund.code} Sharpe")
        _count(refs, "sharpe")
        session.flush()
        log(f"  return chain for {fund.code} done ({len(boundary_runs)} boundaries)")


def _run_sensitivity(session: Session, refs: _Refs) -> None:
    result = run_sensitivities(
        session,
        acting_tenant=book.TENANT_ID,
        actor=SensitivityActor(actor_id=refs.analyst_id),
        code_version=book.CODE_VERSION,
        environment_id=book.ENVIRONMENT_ID,
        model_version_id=refs.versions["sensitivity"].id,
        curve_selectors=[
            CurveSelector(
                curve_type="SWAP",
                currency_code="USD",
                curve_date=book.CURVE_DATE,
                curve_source=book.CURVE_SOURCE,
            )
        ],
        as_of_valid_at=_dt(book.CURVE_DATE),
    )
    _require_completed(result, "sensitivity")
    _count(refs, "sensitivity")


# --- the runner ---------------------------------------------------------------------------------


def seed_demo_tenant(session: Session, *, log: Log | None = None) -> SeedSummary:
    """Seed the Northlight tenant end to end. The caller owns the commit."""
    say: Log = log or (lambda _msg: None)
    detach = persistent_tenant_context(session, book.TENANT_ID)
    try:
        _create_tenant(session)
        refs = _Refs()
        refs.paths = book.generate_paths()
        principals = _seed_principals(session)
        refs.analyst_id = principals["northlight-analyst"]
        say("principals seeded")
        _seed_calendar(session, refs.analyst_id)
        _seed_schemes(session, refs)
        _seed_funds(session, refs)
        _seed_instruments(session, refs)
        say(
            f"reference seeded: {len(book.INSTRUMENTS)} instruments across "
            f"{len(refs.account_ids)} accounts"
        )
        _seed_marks_and_fx(session, refs, say)
        _seed_factors(session, refs, say)
        _seed_loadings(session, refs)
        _seed_benchmarks(session, refs)
        _seed_curve_and_scenario(session, refs)
        say("market data seeded")
        _register_models(session, refs)
        say(f"{len(refs.versions)} model versions registered")
        _run_account_boundaries(session, refs, say)
        var_runs = _run_month_end_chain(session, refs, say)
        _run_return_chains(session, refs, say)
        _run_sensitivity(session, refs)
        session.flush()
        return SeedSummary(
            tenant_id=book.TENANT_ID,
            principal_ids=principals,
            fund_ids=dict(refs.fund_ids),
            account_ids=dict(refs.account_ids),
            instruments=len(book.INSTRUMENTS),
            boundaries=len(book.BOUNDARIES),
            month_ends=len(book.MONTH_ENDS),
            marks=refs.counts.get("marks", 0),
            fx_rates=refs.counts.get("fx_rates", 0),
            factor_returns=refs.counts.get("factor_returns", 0),
            loadings=refs.counts.get("loadings", 0),
            model_version_ids={k: str(mv.id) for k, mv in refs.versions.items()},
            runs={
                k: n
                for k, n in refs.counts.items()
                if k not in {"marks", "fx_rates", "factor_returns", "loadings", "benchmark_rows"}
            },
            var_run_ids=var_runs,
        )
    finally:
        detach()
