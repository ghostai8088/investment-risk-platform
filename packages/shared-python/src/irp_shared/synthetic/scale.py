"""PERF-0 scale seed — a SIZE-PARAMETERIZED deterministic book under the reserved PERF tenant.

Sibling to :mod:`irp_shared.synthetic.builder`, which seeds a FIXED three-account dataset. This
module seeds an arbitrarily large one so the scale probe has something to measure, under the same
discipline: deterministic ``uuid5`` ids, the fixed :class:`SeedClock`, an explicit confirmation
argument, a non-production env gate, and an EXACT-tenant refusal.

**Two reserved tenants, each refusing the other's** (OQ-PERF-0-10, REVERSED at first implementation
contact). ``build_synthetic_dataset`` writes ONLY to ``SYNTHETIC_TENANT_ID``; this writes ONLY to
``PERF_TENANT_ID``. The separation is not cosmetic: ``test_synthetic_pg.py`` asserts
``count(Position) == 6`` under a NOBYPASSRLS role with the synthetic tenant context set — an
RLS-SCOPED count — so seeding thousands of perf positions into that tenant would break it, and
relaxing the number would permanently destroy the precision of a guard whose whole value is being
exact.

**NO ARITHMETIC.** The no-compute AST fence over this package forbids ``ast.Mult`` outright, so that
a seed can never fabricate a market value or exposure (those come only from the AD-014/FW-RUN gate).
Deterministic quantities and marks therefore come from fixed value TABLES indexed by position —
never ``i * step``. This is a real constraint respected, not a fence widened to fit new code.

**Timing lives OUTSIDE this module** (OQ-PERF-0-9). The package is AST-fenced against wall-clock
precisely so its output is byte-reproducible; a ``perf_counter()`` in here would break the guarantee
the fence exists to provide. The harness wraps these calls and times them from the outside.

Capture-only, exactly like its sibling: this seeds positions/valuations/factor returns and computes
NOTHING. The governed chain is driven separately, by the harness, through the shipped binders.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from irp_shared.classification.service import (
    ClassificationActor,
    capture_assignment,
    create_node,
    create_scheme,
)
from irp_shared.db.tenant import set_tenant_context
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.portfolio.models import Portfolio
from irp_shared.position.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.currency import create_currency
from irp_shared.reference.instrument import create_instrument, update_instrument
from irp_shared.reference.issuer import create_issuer
from irp_shared.reference.legal_entity import create_legal_entity
from irp_shared.reference.service import ReferenceActor
from irp_shared.synthetic.ids import (
    SEED_EPOCH,
    SeedClock,
    business_date,
    synthetic_id,
)
from irp_shared.valuation.service import ValuationActor
from irp_shared.valuation.valuation import create_valuation

#: The env gate for the scale seed — distinct from the synthetic seed's, so enabling one never
#: silently enables the other.
ALLOW_PERF_SEED_ENV = "IRP_ALLOW_PERF_SEED"

#: The reserved PERF tenant. Deterministic, distinct from SYNTHETIC and from SYSTEM.
PERF_TENANT_ID = synthetic_id("tenant:perf-probe")

#: The perf seed actor (an audit/lineage label; the perf tenant has no API users).
PERF_ACTOR_ID = synthetic_id("actor:perf-probe-seed")


class PerfSeedRefused(RuntimeError):
    """The scale seed refused: missing confirmation, missing env gate, or a non-PERF tenant."""


#: Deterministic quantity values, indexed by position ordinal. A TABLE rather than an expression
#: because the no-compute fence forbids multiplication (see the module docstring). Economically
#: plausible round lots (the standing test-data-realism rule): no zero, no absurd size.
_QUANTITIES: tuple[str, ...] = (
    "100",
    "250",
    "500",
    "1000",
    "1500",
    "2000",
    "3000",
    "5000",
    "750",
    "1250",
    "1750",
    "4000",
    "600",
    "900",
    "2500",
    "1200",
)

#: Deterministic per-unit marks, indexed by instrument ordinal. Plausible equity/bond prices.
_MARKS: tuple[str, ...] = (
    "10.50",
    "25.75",
    "42.10",
    "88.20",
    "13.35",
    "67.90",
    "101.25",
    "55.40",
    "31.15",
    "74.60",
    "19.80",
    "126.45",
    "48.05",
    "92.70",
    "37.90",
    "58.30",
)

#: Deterministic daily factor returns, indexed by (factor ordinal + day ordinal). Small signed
#: decimals in a plausible daily range; the sequence is long and non-repeating enough that no
#: factor's series is a constant (a constant series would make covariance singular).
_FACTOR_RETURNS: tuple[str, ...] = (
    "0.0012",
    "-0.0007",
    "0.0031",
    "-0.0019",
    "0.0004",
    "0.0022",
    "-0.0038",
    "0.0015",
    "-0.0011",
    "0.0027",
    "0.0008",
    "-0.0025",
    "0.0041",
    "-0.0003",
    "0.0018",
    "-0.0014",
    "0.0006",
    "0.0033",
    "-0.0021",
    "0.0009",
    "-0.0029",
    "0.0017",
    "0.0002",
    "-0.0036",
)

#: Distinct currency codes, one per CURRENCY-family factor. The factor-exposure allocation model
#: requires ONE factor per currency and refuses a duplicate scope, so a single shared code makes
#: every factor beyond the first unbuildable.
_CURRENCIES: tuple[str, ...] = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CHF",
    "CAD",
    "AUD",
    "SEK",
    "NOK",
    "NZD",
    "SGD",
    "HKD",
    "DKK",
    "PLN",
    "MXN",
    "ZAR",
)

#: Instruments per ISSUER. Concentration ALWAYS computes an ISSUER dimension, and an
#: instrument with no issuer is UNCLASSIFIABLE — a book of issuer-less instruments makes that
#: dimension entirely unclassifiable, which is a GAP, which commits a FAILED run with zero rows.
#: The chain then "runs" while measuring the failure path. Sharing issuers across instruments also
#: makes the concentration numbers meaningful rather than one bucket per position.
_INSTRUMENTS_PER_ISSUER = 5

#: Instruments per portfolio — the book is split across portfolios so the chain exercises
#: multi-portfolio scope rather than one giant account.
_POSITIONS_PER_PORTFOLIO = 250

#: Month-end mark dates are generated as day offsets from SEED_EPOCH (OQ-PERF-0-2: month-end
#: position marks over a THREE-year span). 36 offsets, each ~30 days apart, built by REPEATED
#: ADDITION so the module stays multiplication-free.
_MONTH_STEP_DAYS = 30
_MONTHS = 36


def _month_end_offsets() -> tuple[int, ...]:
    """Day offsets for 36 month-ends, accumulated additively (no multiplication)."""
    offsets: list[int] = []
    day = 0
    for _ in range(_MONTHS):
        day += _MONTH_STEP_DAYS
        offsets.append(day)
    return tuple(offsets)


@dataclass(frozen=True)
class PerfSeedSummary:
    """What one rung of the ladder actually wrote — reported, never inferred."""

    tenant_id: str
    rung_positions: int
    portfolios: int
    instruments: int
    positions: int
    valuations: int
    factors: int
    factor_returns: int
    #: The explicitly-selected measurement date (never "latest COMPLETED" — OQ-CON-1-20).
    measurement_date: datetime
    #: The SECTOR_INDUSTRY scheme the instruments were assigned under, or None when
    #: ``classify=False``. The concentration segment cannot run without it. Defaulted fields must
    #: follow the non-default ones — dataclass ordering.
    sector_scheme_id: str | None = None
    assignments: int = 0
    issuers: int = 0


def _refuse_unless_gated(*, allow_perf_seed: bool, tenant_id: str) -> None:
    """The three-part gate, mirroring ``build_synthetic_dataset``'s."""
    if not allow_perf_seed:
        raise PerfSeedRefused(
            "the perf scale seed requires explicit allow_perf_seed=True (never-auto-run)"
        )
    if os.environ.get(ALLOW_PERF_SEED_ENV) != "1":
        raise PerfSeedRefused(
            f"the perf scale seed requires {ALLOW_PERF_SEED_ENV}=1 (non-production gate)"
        )
    if str(tenant_id) != PERF_TENANT_ID:
        raise PerfSeedRefused(
            "the perf scale seed refuses any tenant but the reserved PERF tenant — it can never "
            "write to the SYNTHETIC tenant (whose exact-count guards it would corrupt) or to a "
            "real one"
        )


def build_perf_book(
    session: Session,
    *,
    rung_positions: int,
    allow_perf_seed: bool = False,
    tenant_id: str = PERF_TENANT_ID,
    n_factors: int = 8,
    n_return_days: int = 260,
    factor_family: str = "CURRENCY",
    factor_currency_code: str | None = None,
    classify: bool = False,
    positions_per_portfolio: int = _POSITIONS_PER_PORTFOLIO,
) -> PerfSeedSummary:
    """Seed ONE rung of the scale ladder. Caller owns the commit and owns all timing.

    ``rung_positions`` is the ladder point (500 / 2,000 / 5,000 / 10,000 — OQ-PERF-0-3). Positions
    are spread across portfolios at ``positions_per_portfolio`` each (default 250). The parameter
    exists for ONE consumer: the CI smoke, whose regression guard is the multi-portfolio
    ``portfolio_return`` shape — at the default packing its tiny rung produced exactly ONE
    portfolio, so the guard was VACUOUS and its two-portfolio comment described a protection the
    test did not provide (the 2026-08-01 review's F1; the LIM-2 level-trap lesson recurring inside
    the slice that cited it). Every position is marked at
    36 month-ends over three years (OQ-PERF-0-2), and ``n_factors`` factor-return series are seeded
    DAILY over ``n_return_days`` because covariance/VaR consume factor series, not position marks.

    Deterministic for every shape that carries an ``entity_id`` hook: portfolios, positions,
    valuations, factors and factor returns are byte-identical across runs.
    **THREE shapes are the exception, not two** (the 2026-08-01 review's F3 — the caveat as first
    recorded named only ``legal_entity`` and ``issuer``): their binders mint their own ids with no
    ``entity_id`` override, and the per-run-random issuer id is then written INTO
    ``instrument.issuer_id`` via ``update_instrument``, so instrument rows are not byte-identical
    either. (Under ``classify=True`` the classification rows also sit outside the guarantee.)
    Recorded rather than glossed: none of it affects any measurement — issuer grouping MEMBERSHIP
    is ordinal-keyed, so concentration shapes and every timing are unchanged — but the seed's
    determinism claim is NOT universal and must not be cited as such.

    **Each rung requires a fresh schema, and this refuses otherwise.** Ids are keyed by ORDINAL so
    that a larger rung extends a smaller one rather than reshuffling it (the ladder must compare
    like with like) — which means re-seeding into a tenant that already holds a rung collides on
    the first row. It is refused UP FRONT with an actionable message rather than surfacing as a raw
    ``UniqueViolation`` a thousand inserts deep. Deliberately NOT a resume-from-delta path: a
    per-row existence check would add a SELECT to every insert and contaminate the very timing this
    seed exists to measure.
    """
    _refuse_unless_gated(allow_perf_seed=allow_perf_seed, tenant_id=tenant_id)
    set_tenant_context(session, PERF_TENANT_ID)  # RLS-scoped; never BYPASSRLS

    # FRESH-SCHEMA precondition (see the docstring). ONE query, before any timed write, so it
    # cannot skew a reading.
    # ``session.get`` by the deterministic first-portfolio id, mirroring the builder's own
    # double-run check. NOT ``session.execute(select(...))``: the package's no-raw-SQL fence
    # forbids ``.execute`` outright, and it caught this line when it was written that way.
    if session.get(Portfolio, synthetic_id("perf:portfolio:PERF-ACCT-0000")) is not None:
        raise PerfSeedRefused(
            "the PERF tenant already holds a seeded rung — each ladder rung needs a FRESH schema "
            "(ordinal-keyed ids mean rungs overlap by design). Reset the schema between rungs."
        )

    clock = SeedClock()
    ref_actor = ReferenceActor(actor_id=PERF_ACTOR_ID)
    pf_actor = PortfolioActor(actor_id=PERF_ACTOR_ID)
    pos_actor = PositionActor(actor_id=PERF_ACTOR_ID)
    val_actor = ValuationActor(actor_id=PERF_ACTOR_ID)

    # A CURRENCY the tenant can actually see. capture_factor RESOLVES currency_code against the
    # reference table under the ACTING tenant, and a freshly reserved tenant owns no currencies —
    # so a CURRENCY-family factor is unbuildable without this. Seeded only when asked for.
    if factor_currency_code is not None:
        for currency_ordinal in range(n_factors):
            code = _CURRENCIES[currency_ordinal % len(_CURRENCIES)]
            create_currency(
                session,
                tenant_id=PERF_TENANT_ID,
                code=code,
                name=f"Perf probe {code}",
                actor=ref_actor,
            )
        session.flush()

    # A minimal SECTOR_INDUSTRY taxonomy (root + one leaf). CON-1's concentration binder refuses
    # without at least one classification dimension and its scheme, so a book with no taxonomy
    # leaves that whole segment unmeasurable. Tenant-owned rather than SYSTEM: the perf tenant is
    # self-contained and must not depend on a seeded global vocabulary.
    cls_actor = ClassificationActor(tenant_id=PERF_TENANT_ID, actor_id=PERF_ACTOR_ID)
    sector_scheme_id: str | None = None
    if classify:
        scheme = create_scheme(
            session,
            actor=cls_actor,
            scheme_family="ISIC",
            version_label="perf-probe",
            name="Perf probe sector taxonomy",
            dimension_kind="SECTOR_INDUSTRY",
            authority="PERF_SEED",
        )
        create_node(
            session, actor=cls_actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1
        )
        create_node(
            session,
            actor=cls_actor,
            scheme_id=scheme.id,
            code="C26",
            name="Electronics",
            level=2,
            parent_code="C",
        )
        session.flush()
        sector_scheme_id = str(scheme.id)

    offsets = _month_end_offsets()
    measurement_date = business_date(offsets[-1])
    t0 = business_date(0)

    # --- portfolios ---
    portfolio_ids: list[str] = []
    remaining = rung_positions
    pf_ordinal = 0
    while remaining > 0:
        code = f"PERF-ACCT-{pf_ordinal:04d}"
        pf = create_portfolio(
            session,
            tenant_id=PERF_TENANT_ID,
            code=code,
            name=f"Perf probe account {pf_ordinal:04d}",
            node_type="ACCOUNT",
            actor=pf_actor,
            entity_id=synthetic_id(f"perf:portfolio:{code}"),
            now=clock.tick(),
        )
        portfolio_ids.append(str(pf.id))
        remaining -= positions_per_portfolio
        pf_ordinal += 1

    # --- instruments + positions + month-end valuations ---
    n_valuations = 0
    n_assignments = 0
    n_issuers = 0
    current_issuer_id: str | None = None
    ordinal = 0
    for portfolio_id in portfolio_ids:
        for _ in range(positions_per_portfolio):
            if ordinal >= rung_positions:
                break
            code = f"PERF-INST-{ordinal:06d}"
            inst = create_instrument(
                session,
                tenant_id=PERF_TENANT_ID,
                code=code,
                name=f"Perf probe instrument {ordinal:06d}",
                asset_class="EQUITY",
                actor=ref_actor,
                entity_id=synthetic_id(f"perf:instrument:{code}"),
                now=clock.tick(),
            )
            if ordinal % _INSTRUMENTS_PER_ISSUER == 0:
                legal_entity = create_legal_entity(
                    session,
                    tenant_id=PERF_TENANT_ID,
                    code=f"PERF-LE-{ordinal:06d}",
                    name=f"Perf probe legal entity {ordinal:06d}",
                    jurisdiction="US",
                    actor=ref_actor,
                )
                issuer = create_issuer(
                    session,
                    tenant_id=PERF_TENANT_ID,
                    legal_entity_id=legal_entity.id,
                    issuer_type="CORPORATE",
                    actor=ref_actor,
                )
                current_issuer_id = str(issuer.id)
                n_issuers += 1
            update_instrument(session, inst, actor=ref_actor, issuer_id=current_issuer_id)
            create_position(
                session,
                portfolio_id=portfolio_id,
                instrument_id=inst.id,
                acting_tenant=PERF_TENANT_ID,
                actor=pos_actor,
                quantity=Decimal(_QUANTITIES[ordinal % len(_QUANTITIES)]),
                valid_from=t0,
                entity_id=synthetic_id(f"perf:position:{code}"),
                now=clock.tick(),
            )
            mark = Decimal(_MARKS[ordinal % len(_MARKS)])
            for offset in offsets:
                create_valuation(
                    session,
                    portfolio_id=portfolio_id,
                    instrument_id=inst.id,
                    valuation_date=business_date(offset).date(),
                    acting_tenant=PERF_TENANT_ID,
                    actor=val_actor,
                    mark_value=mark,
                    currency_code="USD",
                    mark_source="PERF_PX",
                    valid_from=t0,
                    entity_id=synthetic_id(f"perf:valuation:{code}:{offset}"),
                    now=clock.tick(),
                )
                n_valuations += 1
            if sector_scheme_id is not None:
                capture_assignment(
                    session,
                    actor=cls_actor,
                    entity_type="instrument",
                    entity_id=str(inst.id),
                    scheme_id=sector_scheme_id,
                    dimension_kind="SECTOR_INDUSTRY",
                    node_code="C26",
                    basis="NOT_APPLICABLE",
                    asserted_ancestor_code="C",
                )
                n_assignments += 1
            ordinal += 1

    # --- factors + DAILY factor returns (OQ-PERF-0-2: the history the chain actually needs sits
    # at the FACTOR level, where it is cheap — covariance/VaR pin factor series, not position
    # marks). The return VALUES come from the fixed table, indexed by an ADDITIVE walk (the
    # no-compute fence forbids multiplication), so every factor gets a distinct, non-constant
    # series — a constant series would make the covariance matrix singular.
    md_actor = FactorActor(actor_id=PERF_ACTOR_ID)
    n_factor_returns = 0
    value_cursor = 0
    for factor_ordinal in range(n_factors):
        factor_code = f"PERF-FACTOR-{factor_ordinal:03d}"
        factor = capture_factor(
            session,
            factor_code=factor_code,
            factor_source="PERF_SEED",
            # CURRENCY by default: the shipped risk.factor_exposure.allocation model ADMITS only
            # the CURRENCY family, so a STYLE default would leave that whole segment
            # unmeasurable. Parameterized rather than hard-coded so other families stay reachable.
            factor_family=factor_family,
            acting_tenant=PERF_TENANT_ID,
            actor=md_actor,
            factor_type=factor_family,
            # PARAMETERIZED, defaulting to absent. capture_factor RESOLVES currency_code against
            # the SYSTEM currency reference, which a bare unit-tier schema has not seeded — so the
            # unit tier passes None. A CURRENCY-family factor DOES need a currency scope for the
            # factor-exposure allocation model, so the PG harness passes a real code.
            currency_code=(
                None
                if factor_currency_code is None
                else _CURRENCIES[factor_ordinal % len(_CURRENCIES)]
            ),
            frequency="DAILY",
            factor_name=f"Perf probe factor {factor_ordinal:03d}",
            valid_from=t0,
            entity_id=synthetic_id(f"perf:factor:{factor_code}"),
            now=clock.tick(),
        )
        for day in range(n_return_days):
            value_cursor += 1
            capture_factor_return(
                session,
                factor=factor,
                return_date=business_date(day).date(),
                return_value=Decimal(_FACTOR_RETURNS[value_cursor % len(_FACTOR_RETURNS)]),
                acting_tenant=PERF_TENANT_ID,
                actor=md_actor,
                valid_from=t0,
                entity_id=synthetic_id(f"perf:factor_return:{factor_code}:{day}"),
                now=clock.tick(),
            )
            n_factor_returns += 1

    summary = PerfSeedSummary(
        tenant_id=PERF_TENANT_ID,
        rung_positions=rung_positions,
        portfolios=len(portfolio_ids),
        instruments=ordinal,
        positions=ordinal,
        valuations=n_valuations,
        # COUNTED, never echoed back from the arguments: an earlier draft reported
        # ``factors=n_factors`` while creating none, which would have made the summary lie.
        factors=n_factors,
        factor_returns=n_factor_returns,
        sector_scheme_id=sector_scheme_id,
        assignments=n_assignments,
        issuers=n_issuers,
        measurement_date=measurement_date,
    )
    return summary


def perf_business_day(offset_days: int) -> datetime:
    """A fixed instant ``SEED_EPOCH + offset_days`` — re-exported so the harness never reaches for
    a wall clock when it needs a date."""
    return SEED_EPOCH + timedelta(days=offset_days)


__all__ = [
    "ALLOW_PERF_SEED_ENV",
    "PERF_ACTOR_ID",
    "PERF_TENANT_ID",
    "PerfSeedRefused",
    "PerfSeedSummary",
    "build_perf_book",
    "perf_business_day",
]
