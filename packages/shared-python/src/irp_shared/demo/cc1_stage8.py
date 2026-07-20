"""The CC-1 stage-8 demo runner (OD-CC-1-H): one commitment lifecycle on the living tenant.

EXTENDS the living demo tenant an EIGHTH time (every prior stage byte-untouched) — the
CAPTURE half of the ratified Wave-8 commitment walk (the projection half lands at CC-2 on
THIS seeded commitment). **Deliberately capture-only, honestly recorded**: a captured-input
family registers NO model code, files NO validation record, and creates NO calculation run
— the exercising suites assert the campaign count pins DID NOT MOVE (19 registered codes /
34 validation records / 95 COMPLETED runs; the HG-1 OQ-5 false-ceremony bar a fortiori:
there is no model version to validate). The sequence:

1. Seed **``PE-MERIDIAN-X``** — a NEW private-equity fund instrument (an ORDINARY
   instrument row under the PA-0 asset-class convention; instrument #, not a model).
2. Capture the **25M USD commitment** by ``DEMO-GLOBAL`` (the flagship book) to the fund
   (``PRIVATE.COMMITMENT_CREATE``; the MANUAL ORIGIN edge; the NOT_NULL DQ gate).
3. Record **three DRAWDOWN calls** — including one deliberately MIS-CAPTURED (9M instead
   of 4M), then **REVERSED** (the negation append, ``PRIVATE.CAPITAL_CALL_REVERSE``) and
   recaptured right: the append-only correction demonstrated live, Σ self-correcting.
4. Record **two distributions** — an INCOME and a RETURN_OF_CAPITAL flagged
   ``is_recallable`` (captured as DATA; the unfunded interpretation is CC-2's).

THE READ RULE lives here too: none of these events touch the perf/backtest chains — the
mechanical evidence is the 95-COMPLETED-runs pin (any perf/backtest computation would mint
a run) plus the zero-transactions assertion on the stage-8 fund (nothing auto-bridged).

Idempotency is REFUSE-NOT-SKIP on this stage's OWN footprint (any commitment row in the
demo tenant, probed FIRST). Requires the campaign (principals + the flagship book). The
caller owns the ONE commit. The ``stage8`` filename component of the exercising suites is
LOAD-BEARING (alpha-sorts after every prior stage's suites).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.entitlement.models import AppUser, Role, UserRole
from irp_shared.portfolio.models import Portfolio
from irp_shared.private_capital.capital_flow_service import (
    CapitalFlowActor,
    capture_capital_call,
    capture_distribution,
    reverse_capital_call,
)
from irp_shared.private_capital.commitment_service import (
    CommitmentActor,
    capture_commitment,
)
from irp_shared.private_capital.models import Commitment
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor

_FUND_CODE = "PE-MERIDIAN-X"
_FUND_NAME = "Meridian Growth Partners X LP interest"
_PORTFOLIO_CODE = "DEMO-GLOBAL"  # the flagship book (campaign stage 1)
#: TD-1-realistic economics: a mid-size LP commitment with a first-year call pace of
#: ~40% drawn and one early income + one recallable return-of-capital distribution.
_COMMITTED = Decimal("25000000.000000")
_COMMITMENT_DATE = date(2025, 6, 30)
_VALID_FROM = datetime(2025, 6, 30, tzinfo=UTC)


class DemoCc1Error(RuntimeError):
    """Base class for stage-8 refusals."""


class DemoCc1AlreadySeededError(DemoCc1Error):
    """The stage-8 footprint (any demo-tenant commitment) already exists — REFUSE, not skip."""


class DemoCc1PrereqError(DemoCc1Error):
    """The MG-1 campaign substrate (principals + the flagship book) is missing."""


@dataclass(frozen=True)
class Cc1Stage8Summary:
    tenant_id: str
    fund_instrument_id: str
    commitment_id: str
    calls_recorded: int  # ordinary captures (incl. the mis-capture and its recapture)
    reversals_recorded: int
    distributions_recorded: int
    net_called: Decimal  # Σ(call amounts) — self-correcting through the reversal
    net_distributed: Decimal


def _resolve_user(session: Session, role_code: str, label: str) -> str:
    rows = session.execute(
        select(AppUser.id)
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(AppUser.tenant_id == DEMO_TENANT_ID, Role.code == role_code)
    ).all()
    if len(rows) != 1:
        raise DemoCc1PrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one "
            f"from the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def run_demo_cc1_stage8(session: Session) -> Cc1Stage8Summary:
    """Extend the living tenant with the CC-1 capture walk. The caller owns the commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # REFUSE-NOT-SKIP on this stage's own footprint, probed FIRST.
        existing = session.execute(
            select(func.count())
            .select_from(Commitment)
            .where(Commitment.tenant_id == DEMO_TENANT_ID)
        ).scalar_one()
        if existing:
            raise DemoCc1AlreadySeededError(
                f"demo tenant {DEMO_TENANT_ID} already holds {existing} commitment row(s) — "
                f"stage 8 refuses to re-seed"
            )

        registrar = _resolve_user(session, "risk_analyst_1l", "registrar/1L")
        flagship = session.execute(
            select(Portfolio.id).where(
                Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _PORTFOLIO_CODE
            )
        ).scalar_one_or_none()
        if flagship is None:
            raise DemoCc1PrereqError(
                f"the flagship book {_PORTFOLIO_CODE!r} is missing — run the MG-1 campaign first"
            )

        actor = CommitmentActor(actor_id=registrar)
        flow_actor = CapitalFlowActor(actor_id=registrar)

        fund_id = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=_FUND_CODE,
            name=_FUND_NAME,
            asset_class="PRIVATE_EQUITY",
            actor=ReferenceActor(actor_id=registrar),
        ).id

        commitment = capture_commitment(
            session,
            portfolio_id=flagship,
            instrument_id=fund_id,
            committed_amount=_COMMITTED,
            currency_code="USD",
            commitment_date=_COMMITMENT_DATE,
            acting_tenant=DEMO_TENANT_ID,
            actor=actor,
            valid_from=_VALID_FROM,
        )

        def _call(event_date: date, amount: str, external_ref: str) -> str:
            return capture_capital_call(
                session,
                portfolio_id=flagship,
                instrument_id=fund_id,
                event_date=event_date,
                amount=Decimal(amount),
                currency_code="USD",
                call_type="DRAWDOWN",
                acting_tenant=DEMO_TENANT_ID,
                actor=flow_actor,
                external_ref=external_ref,
            ).id

        # Two clean drawdowns, then the MIS-CAPTURED third (9M keyed for a 4M notice).
        _call(date(2025, 8, 15), "3000000.000000", "MERX-CALL-1")
        _call(date(2025, 11, 14), "3000000.000000", "MERX-CALL-2")
        wrong_id = _call(date(2026, 2, 13), "9000000.000000", "MERX-CALL-3")
        reverse_capital_call(
            session,
            capital_call_id=wrong_id,
            acting_tenant=DEMO_TENANT_ID,
            actor=flow_actor,
            reason="capture error: the notice was 4.0M, keyed as 9.0M (fat-finger)",
        )
        _call(date(2026, 2, 13), "4000000.000000", "MERX-CALL-3R")

        capture_distribution(
            session,
            portfolio_id=flagship,
            instrument_id=fund_id,
            event_date=date(2026, 4, 30),
            amount=Decimal("600000.000000"),
            currency_code="USD",
            distribution_type="INCOME",
            acting_tenant=DEMO_TENANT_ID,
            actor=flow_actor,
            external_ref="MERX-DIST-1",
        )
        capture_distribution(
            session,
            portfolio_id=flagship,
            instrument_id=fund_id,
            event_date=date(2026, 6, 30),
            amount=Decimal("1200000.000000"),
            currency_code="USD",
            distribution_type="RETURN_OF_CAPITAL",
            acting_tenant=DEMO_TENANT_ID,
            actor=flow_actor,
            is_recallable=True,  # captured as DATA; the unfunded arithmetic is CC-2's
            external_ref="MERX-DIST-2",
        )

        return Cc1Stage8Summary(
            tenant_id=DEMO_TENANT_ID,
            fund_instrument_id=fund_id,
            commitment_id=commitment.id,
            calls_recorded=4,
            reversals_recorded=1,
            distributions_recorded=2,
            net_called=Decimal("10000000.000000"),  # 3 + 3 + 9 − 9 + 4
            net_distributed=Decimal("1800000.000000"),
        )
    finally:
        detach()
