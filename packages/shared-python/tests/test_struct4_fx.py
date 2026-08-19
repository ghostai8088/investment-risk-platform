"""STRUCT-4 (REQ-PPM-010) — reporting-currency declarations + governed FX made visible.

SQLite-local proofs of the ratified DP-11/DP-12 semantics over the three-currency book the
requirement demands (USD/EUR/GBP; the GBP pair TRIANGULATED — no direct GBP/EUR rate exists):

- DP-11: the silent-USD default is DEAD on BOTH paths — an undeclared root REFUSES at build, an
  unresolvable pinned chain REFUSES at consume; an undeclared child INHERITS its parent; an
  explicit ``base_currency`` contradicting a v3 node declaration REFUSES (never a silent
  override); FX-completeness pins the legs a node-currency read needs, and its missing-rate
  refusal FIRES.
- DP-12: a v3 run's triangulated ``fx_legs`` STATE their pivot; a v2 (legacy) run's bytes carry
  the pre-STRUCT-4 shape EXACTLY and the pivot is DERIVED at read time; shipped rows are never
  rewritten.
- The rollup translates a node total into the node's DECLARED currency from PINNED FX only; a
  pre-PPM-010 snapshot lacking the leg surfaces ``missing-fx`` HONESTLY (no retroactive refusal,
  no fabricated 1.0); the same-currency path is an exact no-op (regression guard on
  ``compose_effective_rate``'s identity path — the path this family actually executes, V-010-2).

The P18 positive control is explicit: the translated-leg count is asserted ``> 0`` BEFORE any
translated-leg assertion — every clause here is non-vacuous on this book by construction.

Hand-derived oracle (worked in ``08_testing_qa/struct4_fx_test_spec.md``; literals, never a
replay of the shipped formula): the SLEEVE-UK read in its declared USD = 100×40 GBP×1.25 +
50×20 EUR×1.08 = 5,000 + 1,080 = **6,080.000000 USD**.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import (
    EXPOSURE_TYPE_MARKET_VALUE,
    ExposureActor,
    ReportingCurrencyConflictError,
    UndeclaredReportingCurrencyError,
    run_exposure,
)
from irp_shared.exposure.service import rollup_exposure
from irp_shared.marketdata import (
    FxRateActor,
    FxRateNotFound,
    capture_fx_rate,
    compose_effective_rate,
    derive_pivot,
)
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio, resolve_reporting_currency
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import (
    NODE_FX_BINDING_PREDICATE,
    SUBTREE_BINDING_PREDICATE,
    SnapshotActor,
    build_snapshot,
    list_components,
    resolve_snapshot,
)
from irp_shared.snapshot.models import COMPONENT_KIND_FX, PURPOSE_EXPOSURE_INPUT
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
ACTOR = ExposureActor(actor_id="analyst")

#: The hand-derived literal (test-spec doc §2): the SLEEVE-UK total in its DECLARED USD.
SLEEVE_UK_USD_ORACLE = Decimal("6080.000000")
#: The same sleeve's total in the run base EUR (test-spec doc §2, the two-row sum).
SLEEVE_UK_EUR_TOTAL = Decimal("5629.629630")


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _ccy(db: Session, *codes: str) -> None:
    from irp_shared.reference.models import Currency

    for code in codes:
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _pf(
    db: Session,
    tenant: str,
    code: str,
    *,
    base: str | None = None,
    parent: str | None = None,
    node_type: str = "ACCOUNT",
) -> str:
    return create_portfolio(
        db,
        tenant_id=tenant,
        code=code,
        name=code.lower(),
        node_type=node_type,
        base_currency_code=base,
        parent_portfolio_id=parent,
        actor=PortfolioActor(actor_id="s"),
    ).id


def _holding(db: Session, tenant: str, pf: str, code: str, qty: str, mark: str, ccy: str) -> str:
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=code,
        name="i",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal(qty),
        valid_from=T0,
    )
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal(mark),
        currency_code=ccy,
        valid_from=T0,
    )
    return inst


def _fx(db: Session, tenant: str, base: str, quote: str, rate: str) -> str:
    return capture_fx_rate(
        db,
        base_currency=base,
        quote_currency=quote,
        rate_date=VD,
        rate=Decimal(rate),
        acting_tenant=tenant,
        actor=FxRateActor(actor_id="s"),
        valid_from=T0,
    ).id


def _run(db: Session, tenant: str, *, base: str | None = None, **kw):  # noqa: ANN202
    return run_exposure(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="v1",
        environment_id="ci",
        as_of_valid_at=(None if "snapshot_id" in kw else VALID_AT),
        as_of_known_at=(None if "snapshot_id" in kw else KNOWN_AT),
        base_currency=base,
        **kw,
    )


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count()).select_from(CalculationRun).where(CalculationRun.tenant_id == tenant)
    ).scalar_one()


def _three_currency_book(db: Session, tenant: str) -> dict[str, str]:
    """The REQ-PPM-010 book (test-spec doc §1): FUND declares EUR; SLEEVE-UK declares USD but
    holds GBP+EUR instruments (the foreign-reporting node — USD is NOT a holdings currency
    there); SLEEVE-CORE is undeclared (inherits EUR); SLEEVE-ALBION declares GBP over an EUR
    holding (review fold C0/C12: the node whose TRANSLATION itself triangulates — two legs +
    a stated pivot on the node-total surface). Rates: EUR/USD 1.08 and GBP/USD 1.25 direct —
    the GBP↔EUR pair in EITHER direction exists ONLY triangulated through USD."""
    _ccy(db, "USD", "EUR", "GBP")
    fund = _pf(db, tenant, "FX-FUND", base="EUR", node_type="FUND")
    uk = _pf(db, tenant, "FX-UK", base="USD", parent=fund, node_type="STRATEGY")
    core = _pf(db, tenant, "FX-CORE", parent=fund, node_type="STRATEGY")
    gbp = _pf(db, tenant, "FX-ALBION", base="GBP", parent=fund, node_type="STRATEGY")
    _holding(db, tenant, uk, "EQ-UK", "100", "40.00", "GBP")
    _holding(db, tenant, uk, "EQ-EU", "50", "20.00", "EUR")
    _holding(db, tenant, core, "EQ-US", "10", "108.00", "USD")
    _holding(db, tenant, gbp, "EQ-EU2", "10", "50.00", "EUR")
    _fx(db, tenant, "EUR", "USD", "1.08")
    _fx(db, tenant, "GBP", "USD", "1.25")
    return {"fund": fund, "uk": uk, "core": core, "gbp": gbp}


# ---------- DP-11: the silent default is dead ----------


def test_undeclared_root_refuses_at_build(session: Session) -> None:
    """NEGATIVE (the DP-11 kill, fired): nothing up the chain declares ⇒ pre-create refusal,
    zero runs — the pre-STRUCT-4 path silently computed this book in USD."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    root = _pf(session, tenant, "BARE-ROOT")
    _holding(session, tenant, root, "EQ-1", "10", "5.00", "USD")
    with pytest.raises(UndeclaredReportingCurrencyError, match="REFUSES rather than defaulting"):
        _run(session, tenant, portfolio_id=root)
    assert _count_runs(session, tenant) == 0


def test_undeclared_child_inherits_parent_declaration(session: Session) -> None:
    """POSITIVE (DP-11 inherit): a run at an undeclared child computes in the parent's declared
    currency — inherited, not defaulted (the book has NO USD anywhere)."""
    tenant = str(uuid.uuid4())
    _ccy(session, "EUR")
    fund = _pf(session, tenant, "EUR-FUND", base="EUR", node_type="FUND")
    child = _pf(session, tenant, "EUR-CHILD", parent=fund)
    _holding(session, tenant, child, "EQ-EU2", "10", "5.00", "EUR")
    result = _run(session, tenant, portfolio_id=child)
    assert result.status == RunStatus.COMPLETED.value
    assert {r.base_currency for r in result.rows} == {"EUR"}


def test_resolver_returns_none_above_an_undeclared_chain(session: Session) -> None:
    """The resolver itself: own > inherited > None (the caller refuses on None)."""
    tenant = str(uuid.uuid4())
    fund = _pf(session, tenant, "R-FUND", base="GBP", node_type="FUND")
    mid = _pf(session, tenant, "R-MID", parent=fund)
    leaf = _pf(session, tenant, "R-LEAF", base="EUR", parent=mid)
    bare = _pf(session, tenant, "R-BARE")
    from irp_shared.portfolio import resolve_portfolio

    get = lambda pid: resolve_portfolio(session, pid, acting_tenant=tenant)  # noqa: E731
    assert resolve_reporting_currency(session, get(leaf), acting_tenant=tenant) == "EUR"
    assert resolve_reporting_currency(session, get(mid), acting_tenant=tenant) == "GBP"
    assert resolve_reporting_currency(session, get(bare), acting_tenant=tenant) is None


def test_consume_of_an_undeclared_pin_refuses_without_explicit_base(session: Session) -> None:
    """NEGATIVE (the consume-path kill, fired): the snapshot's pinned chain declares nothing ⇒
    the node-scoped consume REFUSES instead of silently recomputing in USD. The reproduction
    adapters are unaffected — they pass the ORIGINAL run's stored base explicitly."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    root = _pf(session, tenant, "BARE-2")
    _holding(session, tenant, root, "EQ-2", "10", "5.00", "USD")
    built = _run(session, tenant, base="USD", portfolio_id=root)  # explicit base: legal build
    runs_before = _count_runs(session, tenant)
    with pytest.raises(UndeclaredReportingCurrencyError, match="pass\\s+base_currency explicitly"):
        _run(session, tenant, snapshot_id=built.run.input_snapshot_id, scope_node_id=root)
    assert _count_runs(session, tenant) == runs_before


def test_explicit_base_conflicting_with_node_declaration_refuses_on_v3(session: Session) -> None:
    """NEGATIVE (the override clause, fired): base_currency EUR at a USD-declared node on a v3
    snapshot ⇒ refused, zero new runs. A MATCHING explicit base passes (positive control)."""
    tenant = str(uuid.uuid4())
    ids = _three_currency_book(session, tenant)
    built = _run(session, tenant, portfolio_id=ids["fund"])
    snap_id = built.run.input_snapshot_id
    runs_before = _count_runs(session, tenant)
    with pytest.raises(ReportingCurrencyConflictError, match="contradicts node"):
        _run(session, tenant, base="EUR", snapshot_id=snap_id, scope_node_id=ids["uk"])
    assert _count_runs(session, tenant) == runs_before
    ok = _run(session, tenant, base="USD", snapshot_id=snap_id, scope_node_id=ids["uk"])
    assert ok.status == RunStatus.COMPLETED.value


# ---------- the three-currency book: the governed read AT the foreign-reporting node ----------


def test_foreign_node_read_matches_the_hand_derived_oracle(session: Session) -> None:
    """The V-010-1 acceptance shape: the node-scoped run AT SLEEVE-UK — whose declared USD is NOT
    a currency its holdings are held in — totals to the HAND-DERIVED literal. The P18 positive
    control runs FIRST: the translated-leg count is > 0 before anything is asserted about legs."""
    tenant = str(uuid.uuid4())
    ids = _three_currency_book(session, tenant)
    built = _run(session, tenant, portfolio_id=ids["fund"])
    assert built.status == RunStatus.COMPLETED.value

    # P18 clause 1: this book actually translates — BEFORE any leg assertion.
    translated_rows = [r for r in built.rows if json.loads(r.fx_legs)]
    assert len(translated_rows) > 0

    node_run = _run(
        session, tenant, snapshot_id=built.run.input_snapshot_id, scope_node_id=ids["uk"]
    )
    assert node_run.status == RunStatus.COMPLETED.value
    mv = [r for r in node_run.rows if r.exposure_type == EXPOSURE_TYPE_MARKET_VALUE]
    assert {r.base_currency for r in mv} == {"USD"}  # the NODE's declaration, not the fund's EUR
    total = sum((r.exposure_amount for r in mv), Decimal(0))
    assert total == SLEEVE_UK_USD_ORACLE  # literal; derivation in the test-spec doc, not here


def test_triangulated_row_states_its_pivot_and_legacy_rows_derive_it(session: Session) -> None:
    """DP-12 both halves. v3 (new): the GBP row's two legs each STATE pivot USD. v2 (legacy
    byte shape): the same book pinned under the v2 predicate emits legs with NO pivot key —
    byte-compatible with every shipped row — and ``derive_pivot`` recovers USD at read time."""
    tenant = str(uuid.uuid4())
    ids = _three_currency_book(session, tenant)
    built = _run(session, tenant, portfolio_id=ids["fund"])
    by_legs = {len(json.loads(r.fx_legs)): json.loads(r.fx_legs) for r in built.rows}
    assert len(by_legs.get(2, [])) == 2  # the GBP→EUR row triangulated through USD
    assert [leg["pivot"] for leg in by_legs[2]] == ["USD", "USD"]  # stated (DP-12, new rows)
    assert derive_pivot(by_legs[2]) == "USD"

    # The legacy writer path: an explicit v2 pin keeps the pre-STRUCT-4 bytes exactly.
    legacy_snap = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose=PURPOSE_EXPOSURE_INPUT,
        portfolio_id=ids["fund"],
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        binding_predicate_version=SUBTREE_BINDING_PREDICATE,
        base_currency="EUR",
    )
    legacy_run = _run(
        session, tenant, base="EUR", snapshot_id=legacy_snap.id, scope_node_id=ids["fund"]
    )
    legacy_tri = [json.loads(r.fx_legs) for r in legacy_run.rows if len(json.loads(r.fx_legs)) == 2]
    assert legacy_tri, "the legacy run must still triangulate the GBP row"
    assert all("pivot" not in leg for legs in legacy_tri for leg in legs)  # bytes unchanged
    assert derive_pivot(legacy_tri[0]) == "USD"  # derived at read time (DP-12, shipped rows)


def test_v3_completeness_pins_the_node_currency_leg_and_its_refusal_fires(session: Session) -> None:
    """DP-11's redefined FX-completeness, both directions. POSITIVE: an all-USD book whose sleeve
    declares EUR pins the EUR leg it would never have pinned before (targets = node reporting
    currencies, not just base). NEGATIVE (the missing-rate refusal, FIRED): the same book with
    no EUR rate refuses the BUILD pre-create — never a silent 1.0."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    fund = _pf(session, tenant, "C-FUND", base="USD", node_type="FUND")
    sleeve = _pf(session, tenant, "C-EU", base="EUR", parent=fund)
    _holding(session, tenant, sleeve, "EQ-C1", "10", "7.00", "USD")
    with pytest.raises(FxRateNotFound):
        _run(session, tenant, portfolio_id=fund)  # no EUR/USD rate captured yet
    assert _count_runs(session, tenant) == 0
    _fx(session, tenant, "EUR", "USD", "1.08")
    built = _run(session, tenant, portfolio_id=fund)
    snap = resolve_snapshot(session, built.run.input_snapshot_id, acting_tenant=tenant)
    assert snap.binding_predicate_version == NODE_FX_BINDING_PREDICATE
    fx_comps = [
        c
        for c in list_components(session, snapshot_id=snap.id, acting_tenant=tenant)
        if c.component_kind == COMPONENT_KIND_FX
    ]
    assert len(fx_comps) == 1  # pre-STRUCT-4 completeness pinned NOTHING on an all-base book


# ---------- the rollup translation ----------


def test_rollup_translates_at_the_foreign_node_and_is_exact_on_identity(session: Session) -> None:
    """The read-time half: the fund-base (EUR) run's rollup at SLEEVE-UK translates into the
    node's declared USD from PINNED FX — both totals are the hand-derived literals — while the
    undeclared SLEEVE-CORE inherits EUR and passes through EXACTLY (the same-currency no-op
    regression clause, on a total carrying more decimals than USD/EUR minor units)."""
    tenant = str(uuid.uuid4())
    ids = _three_currency_book(session, tenant)
    built = _run(session, tenant, portfolio_id=ids["fund"])

    uk = {
        r.exposure_type: r
        for r in rollup_exposure(
            session, acting_tenant=tenant, run_id=built.run.run_id, node_id=ids["uk"]
        )
    }[EXPOSURE_TYPE_MARKET_VALUE]
    assert (uk.total, uk.base_currency) == (SLEEVE_UK_EUR_TOTAL, "EUR")
    assert (uk.reporting_currency, uk.translated_currency) == ("USD", "USD")
    assert uk.translated_total == SLEEVE_UK_USD_ORACLE
    assert uk.translation_fx_rate == Decimal("1.08").quantize(Decimal("1E-12"))
    assert len(uk.translation_legs) == 1 and uk.translation_pivot is None  # direct, no pivot
    assert uk.missing_fx is None

    core = {
        r.exposure_type: r
        for r in rollup_exposure(
            session, acting_tenant=tenant, run_id=built.run.run_id, node_id=ids["core"]
        )
    }[EXPOSURE_TYPE_MARKET_VALUE]
    assert core.reporting_currency == "EUR"  # inherited through the pinned chain
    assert core.translated_total == core.total  # EXACT pass-through: no lookup, no re-rounding
    assert core.translation_fx_rate == Decimal(1)
    assert core.translation_legs == () and core.missing_fx is None

    # The identity pass-through asserted on a total carrying SIX decimals (test-spec §2): a
    # minor-unit rounding creeping into the identity path (e.g. quantize to 2dp) must go red
    # on the EXPONENT, not just the numeric value.
    fund = {
        r.exposure_type: r
        for r in rollup_exposure(
            session, acting_tenant=tenant, run_id=built.run.run_id, node_id=ids["fund"]
        )
    }[EXPOSURE_TYPE_MARKET_VALUE]
    assert fund.total == Decimal("7129.629630")
    assert fund.translated_total == fund.total
    assert fund.translated_total.as_tuple().exponent == -6  # untouched, not re-rounded

    # Review fold C0/C12: the TRIANGULATED node-total translation — the branch no earlier test
    # executed true. SLEEVE-ALBION declares GBP over an EUR total: EUR→USD direct @1.08 then
    # USD→GBP reciprocal of GBP/USD @1.25; composite 1.08 × (1/1.25) = 0.864 exactly (test-spec
    # §2b); 500.000000 × 0.864 = 432.000000 GBP; TWO legs, pivot STATED as USD — a reader need
    # not infer it (DP-12 on the node-total surface).
    albion = {
        r.exposure_type: r
        for r in rollup_exposure(
            session, acting_tenant=tenant, run_id=built.run.run_id, node_id=ids["gbp"]
        )
    }[EXPOSURE_TYPE_MARKET_VALUE]
    assert (albion.total, albion.base_currency) == (Decimal("500.000000"), "EUR")
    assert (albion.reporting_currency, albion.translated_currency) == ("GBP", "GBP")
    assert albion.translation_fx_rate == Decimal("0.864000000000")
    assert albion.translated_total == Decimal("432.000000")
    assert len(albion.translation_legs) == 2
    assert albion.translation_pivot == "USD"
    assert albion.missing_fx is None


def test_rollup_over_a_pre_ppm010_snapshot_surfaces_missing_fx_honestly(session: Session) -> None:
    """NEGATIVE (the risk-first old-snapshot test): a v2 snapshot pinned before node-currency
    completeness lacks the GBP leg — the read reports ``missing-fx:USD->GBP`` with NO translated
    number and NO exception. Never a retroactive refusal, never a fabricated 1.0."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "GBP")
    fund = _pf(session, tenant, "H-FUND", base="USD", node_type="FUND")
    sleeve = _pf(session, tenant, "H-UK", base="GBP", parent=fund)
    _holding(session, tenant, sleeve, "EQ-H1", "10", "9.00", "USD")
    old_snap = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose=PURPOSE_EXPOSURE_INPUT,
        portfolio_id=fund,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        binding_predicate_version=SUBTREE_BINDING_PREDICATE,  # the pre-PPM-010 world
        base_currency="USD",
    )
    run = _run(session, tenant, base="USD", snapshot_id=old_snap.id, scope_node_id=fund)
    assert run.status == RunStatus.COMPLETED.value
    rollup = {
        r.exposure_type: r
        for r in rollup_exposure(
            session, acting_tenant=tenant, run_id=run.run.run_id, node_id=sleeve
        )
    }[EXPOSURE_TYPE_MARKET_VALUE]
    assert rollup.reporting_currency == "GBP"
    assert rollup.missing_fx == "missing-fx:USD->GBP"
    assert rollup.translated_total is None and rollup.translation_fx_rate is None
    assert rollup.total == Decimal("90.000000")  # the untranslated total still reads honestly


def test_same_currency_noop_is_exact_on_the_composed_path(session: Session) -> None:
    """The regression guard the requirement KEEPS (relabelled, not evidence of work), aimed at
    ``compose_effective_rate``'s identity path — the path the family actually executes (V-010-2).
    The value carries more decimals than any minor unit: replacing the short-circuit with a rate
    lookup (the empty map would fail) or adding currency-rounding would both go red."""
    composed = compose_effective_rate({}, from_currency="EUR", to_currency="EUR")
    assert composed is not None
    effective, legs = composed
    assert (effective, legs) == (Decimal(1), [])
    amount = Decimal("100.123456789012")
    assert amount * effective == amount  # untouched to the last of 12 decimals


def test_node_scoped_consume_that_triangulates_states_its_pivot(session: Session) -> None:
    """Review fold C14: a NODE-SCOPED consume whose own rows triangulate. The run at
    SLEEVE-ALBION resolves the node's declared GBP; its EUR holding converts EUR→GBP through
    USD — two legs, pivot STATED on the persisted evidence (the stated_pivot propagation
    through the node-filtered inputs), amount the hand literal 432.000000 GBP (test-spec §2b)."""
    tenant = str(uuid.uuid4())
    ids = _three_currency_book(session, tenant)
    built = _run(session, tenant, portfolio_id=ids["fund"])
    node_run = _run(
        session, tenant, snapshot_id=built.run.input_snapshot_id, scope_node_id=ids["gbp"]
    )
    assert node_run.status == RunStatus.COMPLETED.value
    mv = [r for r in node_run.rows if r.exposure_type == EXPOSURE_TYPE_MARKET_VALUE]
    assert {r.base_currency for r in mv} == {"GBP"}
    assert sum((r.exposure_amount for r in mv), Decimal(0)) == Decimal("432.000000")
    legs = json.loads(mv[0].fx_legs)
    assert len(legs) == 2
    assert [leg["pivot"] for leg in legs] == ["USD", "USD"]
    assert derive_pivot(legs) == "USD"


def test_v2_node_scoped_conflicting_base_still_completes(session: Session) -> None:
    """Review fold C3 (the ratified sentence's v3-only narrowing, PINNED as a decision): a
    node-scoped consume of a v2 (STRUCT-3-era) snapshot with an explicit base contradicting
    the node's pinned declaration COMPLETES — migration 0073 backfilled 'USD' onto every
    previously-undeclared root, so firing the conflict check on v2 artifacts would make
    legacy explicit-base runs' reproductions refusable. The narrowing keys to the snapshot's
    own version marker (the STRUCT-3 lesson), and this test is what keeps a refactor from
    flipping it silently in either direction."""
    tenant = str(uuid.uuid4())
    ids = _three_currency_book(session, tenant)
    v2_snap = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose=PURPOSE_EXPOSURE_INPUT,
        portfolio_id=ids["fund"],
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        binding_predicate_version=SUBTREE_BINDING_PREDICATE,
        base_currency="EUR",
    )
    result = _run(session, tenant, base="EUR", snapshot_id=v2_snap.id, scope_node_id=ids["uk"])
    assert result.status == RunStatus.COMPLETED.value  # uk declares USD; EUR proceeds on v2


def test_build_path_conflicting_base_refuses_symmetrically(session: Session) -> None:
    """Review fold C9 (BLOCKING): the conflict refusal is SYMMETRIC. A build with an explicit
    base contradicting the DECLARED root refuses pre-create — the alternative mints a v3 run
    whose own CTRL-018 reproduction the consume-path check then refuses (an irreproducible
    governed-run class). A MATCHING explicit base and an explicit base over an UNDECLARED
    scope both stay legal (positive controls)."""
    tenant = str(uuid.uuid4())
    ids = _three_currency_book(session, tenant)
    runs_before = _count_runs(session, tenant)
    with pytest.raises(ReportingCurrencyConflictError, match="refused at build"):
        _run(session, tenant, base="USD", portfolio_id=ids["fund"])  # fund declares EUR
    assert _count_runs(session, tenant) == runs_before
    ok = _run(session, tenant, base="EUR", portfolio_id=ids["fund"])  # matching: legal
    assert ok.status == RunStatus.COMPLETED.value
    bare_tenant = str(uuid.uuid4())
    _ccy(session, "CHF")
    bare = _pf(session, bare_tenant, "BARE-3")
    _holding(session, bare_tenant, bare, "EQ-3", "10", "5.00", "USD")
    ok2 = _run(session, bare_tenant, base="USD", portfolio_id=bare)  # undeclared: legal
    assert ok2.status == RunStatus.COMPLETED.value


def test_legacy_v1_multi_top_resolution_refuses_partial_declarations(session: Session) -> None:
    """Review folds C7 + C10 on a hand-built v1 (holdings-only) pin. The v1 snapshot of a
    two-sleeve fund pins TWO dangling tops (the fund root is absent). (C7) With exactly ONE
    top declared, a node-less consume REFUSES rather than adopting that sleeve's currency for
    its sibling — unknown is not agreement (P3-C1: refused, never guessed). (C10) Naming a
    node on the v1 snapshot changes nothing: the compute is whole-book there, so the base
    resolution ignores the named node and the same refusal fires. Both paths complete with an
    explicit base (the reproduction adapters' route — positive control)."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD", "EUR")
    fund = _pf(session, tenant, "V1-FUND", node_type="FUND")  # undeclared root, PRE-0073 shape
    a = _pf(session, tenant, "V1-A", base="EUR", parent=fund)
    b = _pf(session, tenant, "V1-B", parent=fund)  # undeclared sleeve
    _holding(session, tenant, a, "EQ-V1A", "10", "5.00", "EUR")
    _holding(session, tenant, b, "EQ-V1B", "10", "7.00", "USD")
    _fx(session, tenant, "EUR", "USD", "1.08")
    v2_snap = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose=PURPOSE_EXPOSURE_INPUT,
        portfolio_id=fund,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        binding_predicate_version=SUBTREE_BINDING_PREDICATE,
        base_currency="USD",
    )
    # Emulate the PRE-STRUCT-3 artifact shape by raw SQL (the builder auto-upgrades an
    # EXPOSURE_INPUT build, so a true v1 header + holdings-only pin set can no longer be MINTED
    # — only inherited from history; this is the committed-harness pattern for pre-era shapes):
    # v1 pinned PORTFOLIO components only for position-bearing sleeves, so drop the grouping
    # nodes' pins and stamp the v1 predicate.
    from sqlalchemy import delete, update

    from irp_shared.snapshot.models import DatasetSnapshot, DatasetSnapshotComponent

    session.execute(
        update(DatasetSnapshot)
        .where(DatasetSnapshot.id == v2_snap.id)
        .values(binding_predicate_version="v1:subtree-open-positions")
    )
    fund_pin_marker = f'"id": "{fund}"'  # the component's OWN id key, not a parent edge
    for comp in list_components(session, snapshot_id=v2_snap.id, acting_tenant=tenant):
        if comp.component_kind == "PORTFOLIO" and fund_pin_marker in comp.captured_content:
            session.execute(
                delete(DatasetSnapshotComponent).where(DatasetSnapshotComponent.id == comp.id)
            )
    session.flush()
    session.expire_all()
    v1_snap = v2_snap
    with pytest.raises(UndeclaredReportingCurrencyError):
        _run(session, tenant, snapshot_id=v1_snap.id)
    with pytest.raises(UndeclaredReportingCurrencyError):
        _run(session, tenant, snapshot_id=v1_snap.id, scope_node_id=a)  # C10: node ignored
    ok = _run(session, tenant, base="USD", snapshot_id=v1_snap.id)
    assert ok.status == RunStatus.COMPLETED.value


def test_legacy_v1_scope_stamp_must_be_a_real_tenant_visible_node(session: Session) -> None:
    """Wave-18 close fold K24 (the V-008 shape re-opened on the legacy branch): a v1-snapshot
    consume accepted ANY scope_node_id — a nonexistent or foreign UUID minted a COMPLETED run
    stamped with a scope no one owns, and the false label propagates through the
    SCOPE_INHERITED chain. The stamp must resolve as a tenant-visible portfolio; the
    reproduction adapter replays the ORIGINAL run's stored scope, which resolves by
    construction (positive control below)."""
    from irp_shared.portfolio import PortfolioNotVisible

    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    root = _pf(session, tenant, "V1S-ROOT", base="USD")
    _holding(session, tenant, root, "EQ-V1S", "10", "5.00", "USD")
    v2_snap = build_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        purpose=PURPOSE_EXPOSURE_INPUT,
        portfolio_id=root,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        binding_predicate_version=SUBTREE_BINDING_PREDICATE,
        base_currency="USD",
    )
    from sqlalchemy import update

    from irp_shared.snapshot.models import DatasetSnapshot

    session.execute(
        update(DatasetSnapshot)
        .where(DatasetSnapshot.id == v2_snap.id)
        .values(binding_predicate_version="v1:subtree-open-positions")
    )
    session.flush()
    session.expire_all()

    runs_before = _count_runs(session, tenant)
    with pytest.raises(PortfolioNotVisible):
        _run(session, tenant, base="USD", snapshot_id=v2_snap.id, scope_node_id=str(uuid.uuid4()))
    assert _count_runs(session, tenant) == runs_before  # pre-create refusal: zero runs

    # Positive control — the adapter's replay shape: the ORIGINAL run's real scope resolves.
    ok = _run(session, tenant, base="USD", snapshot_id=v2_snap.id, scope_node_id=root)
    assert ok.status == RunStatus.COMPLETED.value
    assert ok.run.scope_portfolio_id == str(root)
