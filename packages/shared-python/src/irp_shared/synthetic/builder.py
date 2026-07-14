"""Deterministic synthetic-dataset seed builder (P1C-6) — labeled, never-auto-run.

``build_synthetic_dataset`` composes the **governed binders** (so every seeded row carries the same
audit + MANUAL-source lineage + RLS as production) into a small, fixed, reproducible demo dataset
for
tests / demos / UI. It writes **only** to the reserved SYNTHETIC tenant, **never** ``BYPASSRLS``,
and
**refuses to run** without an explicit confirmation + a non-production env gate (the never-auto-run
contract — OD-P1C6-4). Every id is a ``uuid5`` and every timestamp comes from a fixed seed clock via
the keyword-only ``entity_id``/``now`` binder seam (default-None ⇒ production paths unchanged).

Capture-only (AD-017): it creates only captured rows — NO market value, NO ``quantity × mark``, NO
exposure, NO aggregation, NO risk. All names are obviously synthetic (``SYNTH_*`` / neutral); no
real
client/vendor/agency/exchange/issuer names; no real ISIN/CUSIP/SEDOL/LEI (synthetic identifiers use
a
reserved ``ZZ`` ISIN prefix with a structurally-invalid body).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from irp_shared.db.tenant import set_tenant_context
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position.position import correct_position, create_position, supersede_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.identifier import create_identifier_xref
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.synthetic.ids import (
    SYNTHETIC_ACTOR_ID,
    SYNTHETIC_TENANT_ID,
    SeedClock,
    business_date,
    synthetic_id,
)
from irp_shared.transaction.service import TransactionActor
from irp_shared.transaction.transaction import record_transaction, reverse_transaction
from irp_shared.valuation.service import ValuationActor
from irp_shared.valuation.valuation import correct_valuation, create_valuation

#: Env gate — the seed refuses to run unless this is exactly "1" (a non-production confirmation).
ALLOW_SYNTHETIC_SEED_ENV = "IRP_ALLOW_SYNTHETIC_SEED"


class SyntheticSeedRefused(RuntimeError):
    """Raised when the synthetic seed is invoked without the explicit confirmation, without the env
    gate, or against any non-synthetic tenant — the never-auto-run / no-prod safety contract."""


@dataclass(frozen=True)
class SyntheticDatasetSummary:
    """A small machine-readable summary of what the seed created (for tests/demos)."""

    tenant_id: str
    instruments: int
    identifiers: int
    portfolios: int
    transactions: int
    positions: int
    valuations: int
    scenarios: tuple[str, ...]


#: The fixed, deterministic summary — identical on every seed regardless of whether this run
#: actually wrote rows or found them already present (RD-3 OD-D: the whole-seed no-op below).
_SUMMARY = SyntheticDatasetSummary(
    tenant_id=SYNTHETIC_TENANT_ID,
    instruments=3,
    identifiers=2,
    portfolios=6,
    transactions=3,  # BUY + reversal + SELL
    positions=6,  # rows: acct1/bond(v1+v2) + acct1/eq + acct2/bond(v1+corr) + acct3/cash
    valuations=4,  # rows: acct1/bond(vd1 v1 + vd1 corr + vd2) + acct2/bond vd1
    scenarios=(
        "baseline-hierarchy",
        "multi-asset",
        "short-position",
        "reversal-with-price",
        "position-correction",
        "valuation-correction",
        "multi-valuation-date",
        "stale-missing-valuation",
        "identifiers",
        "bounded-subtree",
    ),
)


def build_synthetic_dataset(
    session: Session,
    *,
    allow_synthetic_seed: bool = False,
    tenant_id: str = SYNTHETIC_TENANT_ID,
) -> SyntheticDatasetSummary:
    """Seed the deterministic synthetic dataset under the SYNTHETIC tenant. Caller owns the commit.

    Refuses (``SyntheticSeedRefused``) unless ``allow_synthetic_seed=True`` AND
    ``IRP_ALLOW_SYNTHETIC_SEED=1`` AND ``tenant_id`` is the reserved SYNTHETIC tenant — the seed can
    NEVER touch a real/production tenant. Deterministic: re-running on a fresh database yields a
    byte-identical dataset surface (``uuid5`` ids + injected fixed timestamps + business data)."""
    if not allow_synthetic_seed:
        raise SyntheticSeedRefused(
            "synthetic seed requires explicit allow_synthetic_seed=True (never-auto-run)"
        )
    if os.environ.get(ALLOW_SYNTHETIC_SEED_ENV) != "1":
        raise SyntheticSeedRefused(
            f"synthetic seed requires {ALLOW_SYNTHETIC_SEED_ENV}=1 (non-production gate)"
        )
    if str(tenant_id) != SYNTHETIC_TENANT_ID:
        raise SyntheticSeedRefused("synthetic seed refuses any non-synthetic tenant")

    set_tenant_context(session, SYNTHETIC_TENANT_ID)  # RLS-scoped; never BYPASSRLS

    # RD-3 OD-D: the seed's ids are deterministic uuid5s (a documented product FEATURE, byte-
    # identical across runs — the docstring's contract) but the individual binder CALLS are not
    # idempotent (a re-run's supersede/correct chains would mint EXTRA versions, not raise a clean
    # IntegrityError). Rather than rewrite every one of the ~25 binder call sites with per-row
    # resolve-or-insert (and reason through what a second supersede/correct means), treat the whole
    # seed as ONE unit: if its first row is already present, the seed already ran — return the
    # same fixed summary as a no-op instead of re-inserting (fixes the local dirty-schema
    # double-run collision against test_data_quality_pg/test_lineage_pg, PA-4 Part 6.4).
    bond_id = synthetic_id("instrument:SYNTH-BOND-A")
    if session.get(Instrument, bond_id) is not None:
        return _SUMMARY

    clock = SeedClock()
    t = SYNTHETIC_TENANT_ID
    ref_actor = ReferenceActor(actor_id=SYNTHETIC_ACTOR_ID)
    pf_actor = PortfolioActor(actor_id=SYNTHETIC_ACTOR_ID)
    pos_actor = PositionActor(actor_id=SYNTHETIC_ACTOR_ID)
    val_actor = ValuationActor(actor_id=SYNTHETIC_ACTOR_ID)
    txn_actor = TransactionActor(actor_id=SYNTHETIC_ACTOR_ID)

    # --- synthetic reference: instruments (no issuer; plain ISO currency-code strings) ---
    bond = create_instrument(
        session,
        tenant_id=t,
        code="SYNTH-BOND-A",
        name="Synthetic Bond A",
        asset_class="BOND",
        actor=ref_actor,
        currency_code="USD",
        entity_id=synthetic_id("instrument:SYNTH-BOND-A"),
        now=clock.tick(),
    )
    equity = create_instrument(
        session,
        tenant_id=t,
        code="SYNTH-EQ-B",
        name="Synthetic Equity B",
        asset_class="EQUITY",
        actor=ref_actor,
        currency_code="USD",
        entity_id=synthetic_id("instrument:SYNTH-EQ-B"),
        now=clock.tick(),
    )
    cash = create_instrument(
        session,
        tenant_id=t,
        code="SYNTH-CASH-C",
        name="Synthetic Cash USD",
        asset_class="CASH",
        actor=ref_actor,
        currency_code="USD",
        entity_id=synthetic_id("instrument:SYNTH-CASH-C"),
        now=clock.tick(),
    )

    # --- synthetic identifiers (structurally-invalid synthetic ISIN + an internal scheme) ---
    create_identifier_xref(
        session,
        tenant_id=t,
        instrument_id=bond.id,
        scheme="ISIN",
        value="ZZ0000000001",
        actor=ref_actor,
        source="SYNTH_PX",
        entity_id=synthetic_id("xref:SYNTH-BOND-A:ISIN"),
        now=clock.tick(),
    )
    create_identifier_xref(
        session,
        tenant_id=t,
        instrument_id=bond.id,
        scheme="INTERNAL",
        value="SYNTH-BOND-A",
        actor=ref_actor,
        source="SYNTH_PX",
        entity_id=synthetic_id("xref:SYNTH-BOND-A:INTERNAL"),
        now=clock.tick(),
    )

    # --- bounded portfolio subtree: FUND → {STRAT-1 → {ACCT-1, ACCT-2}, STRAT-2 → ACCT-3} ---
    def _pf(code: str, name: str, node_type: str, parent: str | None) -> str:
        return create_portfolio(
            session,
            tenant_id=t,
            code=code,
            name=name,
            node_type=node_type,
            actor=pf_actor,
            parent_portfolio_id=parent,
            base_currency_code="USD",
            entity_id=synthetic_id(f"portfolio:{code}"),
            now=clock.tick(),
        ).id

    fund = _pf("SYNTH-FUND", "Synthetic Fund", "FUND", None)
    strat1 = _pf("SYNTH-STRAT-1", "Synthetic Strategy 1", "STRATEGY", fund)
    acct1 = _pf("SYNTH-ACCT-1", "Synthetic Account 1", "ACCOUNT", strat1)
    acct2 = _pf("SYNTH-ACCT-2", "Synthetic Account 2", "ACCOUNT", strat1)
    strat2 = _pf("SYNTH-STRAT-2", "Synthetic Strategy 2", "STRATEGY", fund)
    acct3 = _pf("SYNTH-ACCT-3", "Synthetic Account 3", "ACCOUNT", strat2)

    # --- transactions: a BUY + a reversal-WITH-PRICE (the reversal carries the original's price);
    #     plus a SELL. Inert captures only — NO position is derived from these (capture-only). ---
    buy = record_transaction(
        session,
        tenant_id=t,
        portfolio_id=acct1,
        instrument_id=bond.id,
        txn_type="BUY",
        trade_date=business_date(0).date(),
        quantity=Decimal("1000"),
        actor=txn_actor,
        price=Decimal("100.00"),
        gross_amount=Decimal("100000.00"),
        currency_code="USD",
        external_ref="SYNTH-TXN-BUY-1",
        entity_id=synthetic_id("txn:buy:acct1:bond"),
        now=clock.tick(),
    )
    reverse_transaction(
        session,
        buy,
        actor=txn_actor,
        reason="synthetic demo reversal",
        external_ref="SYNTH-TXN-BUY-1-REV",
        entity_id=synthetic_id("txn:reverse:acct1:bond"),
        now=clock.tick(),
    )  # reversal.price == original.price (100.00) → the required non-null-price reversal scenario
    record_transaction(
        session,
        tenant_id=t,
        portfolio_id=acct1,
        instrument_id=equity.id,
        txn_type="SELL",
        trade_date=business_date(1).date(),
        quantity=Decimal("-200"),
        actor=txn_actor,
        price=Decimal("50.00"),
        gross_amount=Decimal("-10000.00"),
        currency_code="USD",
        external_ref="SYNTH-TXN-SELL-1",
        entity_id=synthetic_id("txn:sell:acct1:eq"),
        now=clock.tick(),
    )

    # --- positions (captured directly) ---
    # acct1/bond: long 1000 then effective-dated supersede to 1500
    create_position(
        session,
        portfolio_id=acct1,
        instrument_id=bond.id,
        acting_tenant=t,
        actor=pos_actor,
        quantity=Decimal("1000"),
        valid_from=business_date(0),
        cost_basis=Decimal("100000"),
        entity_id=synthetic_id("position:acct1:bond:v1"),
        now=clock.tick(),
    )
    supersede_position(
        session,
        portfolio_id=acct1,
        instrument_id=bond.id,
        acting_tenant=t,
        actor=pos_actor,
        effective_at=business_date(30),
        quantity=Decimal("1500"),
        entity_id=synthetic_id("position:acct1:bond:v2"),
        now=clock.tick(),
    )
    # acct1/equity: SHORT -200 (and intentionally NO valuation → stale/missing scenario)
    create_position(
        session,
        portfolio_id=acct1,
        instrument_id=equity.id,
        acting_tenant=t,
        actor=pos_actor,
        quantity=Decimal("-200"),
        valid_from=business_date(0),
        cost_basis=Decimal("10000"),
        entity_id=synthetic_id("position:acct1:eq:v1"),
        now=clock.tick(),
    )
    # acct2/bond: long 500 then as-known correction to 550
    pos_acct2 = create_position(
        session,
        portfolio_id=acct2,
        instrument_id=bond.id,
        acting_tenant=t,
        actor=pos_actor,
        quantity=Decimal("500"),
        valid_from=business_date(0),
        cost_basis=Decimal("50000"),
        entity_id=synthetic_id("position:acct2:bond:v1"),
        now=clock.tick(),
    )
    correct_position(
        session,
        pos_acct2,
        restatement_reason="synthetic fat-finger restatement",
        acting_tenant=t,
        actor=pos_actor,
        quantity=Decimal("550"),
        entity_id=synthetic_id("position:acct2:bond:v2-corr"),
        now=clock.tick(),
    )
    # acct3/cash: long 100000
    create_position(
        session,
        portfolio_id=acct3,
        instrument_id=cash.id,
        acting_tenant=t,
        actor=pos_actor,
        quantity=Decimal("100000"),
        valid_from=business_date(0),
        entity_id=synthetic_id("position:acct3:cash:v1"),
        now=clock.tick(),
    )

    # --- valuations (captured marks) ---
    vd1 = business_date(0).date()
    vd2 = business_date(30).date()
    val1 = create_valuation(
        session,
        portfolio_id=acct1,
        instrument_id=bond.id,
        valuation_date=vd1,
        acting_tenant=t,
        actor=val_actor,
        mark_value=Decimal("101.50"),
        currency_code="USD",
        mark_source="SYNTH_PX",
        valid_from=business_date(0),
        entity_id=synthetic_id("valuation:acct1:bond:vd1:v1"),
        now=clock.tick(),
    )
    # multiple valuation_date marks for the same holding (distinct open heads under the 4-part key)
    create_valuation(
        session,
        portfolio_id=acct1,
        instrument_id=bond.id,
        valuation_date=vd2,
        acting_tenant=t,
        actor=val_actor,
        mark_value=Decimal("102.00"),
        currency_code="USD",
        mark_source="SYNTH_PX",
        valid_from=business_date(30),
        entity_id=synthetic_id("valuation:acct1:bond:vd2:v1"),
        now=clock.tick(),
    )
    # valuation as-known correction (restatement) on the vd1 mark
    correct_valuation(
        session,
        val1,
        restatement_reason="synthetic mark restatement",
        acting_tenant=t,
        actor=val_actor,
        mark_value=Decimal("101.75"),
        entity_id=synthetic_id("valuation:acct1:bond:vd1:v2-corr"),
        now=clock.tick(),
    )
    # acct2/bond vd1 mark
    create_valuation(
        session,
        portfolio_id=acct2,
        instrument_id=bond.id,
        valuation_date=vd1,
        acting_tenant=t,
        actor=val_actor,
        mark_value=Decimal("101.50"),
        currency_code="USD",
        mark_source="SYNTH_PX",
        valid_from=business_date(0),
        entity_id=synthetic_id("valuation:acct2:bond:vd1:v1"),
        now=clock.tick(),
    )
    # NOTE: acct1/equity has NO mark → the stale/missing-valuation scenario.

    return _SUMMARY
