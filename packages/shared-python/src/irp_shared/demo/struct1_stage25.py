"""Demo stage 25 (STRUCT-1, REQ-PPM-006) — the demonstrating bond: two measures from one holding.

A SEPARATE fixed-income book (``DEMO-FI``) inside the demo tenant, deliberately NOT a holding
added to ``DEMO-GLOBAL``: every downstream stage's totals are hand-derived goldens over that book,
and a new instrument in it would move all of them (the stage-24 lesson — adding to a shared demo
book changes what every subsequent stage sees; a new book changes nothing).

What the stage delivers is the row's demonstrating case, executed through the REAL services:
a US Treasury bond captured with its terms (face value 1,000, denomination USD) through
``create_instrument_terms``, marked OFF PAR through ``create_valuation``, and a governed exposure
run whose ONE holding yields BOTH measures — NOTIONAL 250 x 1,000 = 250,000.000000 and
MARKET-VALUE 250 x 985.40 = 246,350.000000 (hand-derived, off-par, so the two DIFFER). Both rows
carry the run + snapshot binding (the valuation path, never a fixture insert).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from irp_shared.demo.campaign import (
    _CODE_VERSION,
    _ENVIRONMENT_ID,
    _T0,
    DEMO_TENANT_ID,
    _dt,
)
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.portfolio.models import Portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.instrument_terms import create_instrument_terms
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_FI_PORTFOLIO_CODE = "DEMO-FI"
_BOND_CODE = "FI-UST-2031"
_VALUATION_DATE = date(2026, 5, 26)  # the day after the campaign's last boundary date
_FACE_VALUE = Decimal("1000.0000")
_QUANTITY = Decimal("250")
_OFF_PAR_MARK = Decimal("985.40")


class DemoStruct1AlreadySeededError(RuntimeError):
    """The DEMO-FI book already exists — refuse-not-skip, the campaign rule."""


@dataclass(frozen=True)
class Struct1StageSummary:
    tenant_id: str
    portfolio_id: str
    instrument_id: str
    run_id: str
    notional_amount: Decimal
    market_value_amount: Decimal


def run_demo_struct1_stage25(session: Session, *, actor_id: str) -> Struct1StageSummary:
    """Seed the fixed-income book and execute the two-measure demonstrating run."""
    existing = (
        session.query(Portfolio)
        .filter(Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _FI_PORTFOLIO_CODE)
        .first()
    )
    if existing is not None:
        raise DemoStruct1AlreadySeededError(
            f"portfolio {_FI_PORTFOLIO_CODE} already exists — re-seed from a clean database"
        )

    pf = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_FI_PORTFOLIO_CODE,
        name="Demo fixed-income book",
        node_type="ACCOUNT",
        base_currency_code="USD",
        actor=PortfolioActor(actor_id=actor_id),
    ).id
    inst = create_instrument(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_BOND_CODE,
        name="US Treasury 4.25% 2031",
        asset_class="BOND",
        instrument_type="GOVT_BOND",
        currency_code="USD",
        actor=ReferenceActor(actor_id=actor_id),
    ).id
    create_instrument_terms(
        session,
        instrument_id=inst,
        acting_tenant=DEMO_TENANT_ID,
        actor=ReferenceActor(actor_id=actor_id),
        valid_from=_T0,
        face_value=_FACE_VALUE,
        denomination_currency="USD",
        coupon_rate=Decimal("0.0425"),
        coupon_frequency="SEMI_ANNUAL",
        maturity_date=date(2031, 5, 15),
        day_count="ACT/ACT",
    )
    create_position(
        session,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=DEMO_TENANT_ID,
        actor=PositionActor(actor_id=actor_id),
        quantity=_QUANTITY,
        valid_from=_T0,
    )
    create_valuation(
        session,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=_VALUATION_DATE,
        acting_tenant=DEMO_TENANT_ID,
        actor=ValuationActor(actor_id=actor_id),
        mark_value=_OFF_PAR_MARK,
        currency_code="USD",
        valid_from=_T0,
    )

    result = run_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        portfolio_id=pf,
        as_of_valid_at=_dt(_VALUATION_DATE),
        base_currency="USD",
    )
    if result.status != "COMPLETED":
        raise RuntimeError(
            f"stage-25 exposure run {result.run.run_id} is {result.status}: "
            f"{result.failure_reason}"
        )
    by_type = {r.exposure_type: r for r in result.rows}
    if set(by_type) != {"MARKET_VALUE", "NOTIONAL"}:
        raise RuntimeError(f"stage-25 run emitted measures {sorted(by_type)} — expected both")
    if by_type["NOTIONAL"].exposure_amount == by_type["MARKET_VALUE"].exposure_amount:
        raise RuntimeError("stage-25 bond priced AT PAR — the two measures must differ")
    return Struct1StageSummary(
        tenant_id=DEMO_TENANT_ID,
        portfolio_id=pf,
        instrument_id=inst,
        run_id=result.run.run_id,
        notional_amount=by_type["NOTIONAL"].exposure_amount,
        market_value_amount=by_type["MARKET_VALUE"].exposure_amount,
    )
