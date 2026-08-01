"""RM-1 demo stage 16 — the rolling-risk book (ENT-064, the 21st governed number).

**A purpose-built PAST-DATED book, not an extension of the campaign** (OQ-RM-1-6). Three reasons the
alternative was rejected at ratification, all still true:

- the campaign's 9-boundary calendar yields ONE scalar, not a rolling series;
- its mid-month boundaries are refused outright by the month-alignment criterion;
- extending it would push new private-fund marks toward the valuation series the desmoothing window
  deliberately keeps clean.

**The fixture is designed, not arbitrary.** Every element exists to make a specific control
reachable — the OPS-1 standing lesson ("a demo that cannot REACH a control does not demonstrate
it"):

- **19 month-end boundaries + 1 MID-MONTH boundary.** The mid-month one is the load-bearing piece:
  on a pure month-end calendar the within-month relink is the IDENTITY, so the slice's crux would
  never be exercised and the demo would silently prove nothing about it. One month here genuinely
  links two sub-periods.
- **A designed MULTI-MONTH drawdown.** Without it MDD is identically zero everywhere and the
  drawdown leg is indistinguishable from an unimplemented one.
- **Both windows requested.** 12 fills (a genuine 7-window rolling series); 36 cannot, so its
  SUPPRESSED rows exercise the nullable-value + explicit-flag encoding on real data.

**Stage ORDERING is load-bearing** (the standing discipline): local batteries collect
alphabetically and earlier suites pin governed-code sets with set-equality, so each new stage
appends one more ``z``. SCH-2's stage 15 is ``stage9zzzzzz`` (six), so RM-1's suite is
``stage9zzzzzzz`` (SEVEN). The ratified record said stage 15 / six ``z`` — written the day before
SCH-2 merged; that name would now COLLIDE and collate ahead of it.

Counts move **23/38/110 -> 24/39/132** (MEASURED on a fresh-schema battery, not derived): one new
model code, one INITIAL validation record, and 22 COMPLETED runs (20 boundary exposure runs +
1 PM-1 return run + 1 RM-1 rolling-risk run). The ratified `24/39/131` was right except for the
BASELINE: SCH-2's stage 15 adds one COMPLETED run its own record did not count.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import date as dt_date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.entitlement.models import AppUser
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.model.models import (
    VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
    VALIDATION_TYPE_INITIAL,
    Model,
    ModelVersion,
)
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    record_validation,
)
from irp_shared.perf import (
    PortfolioReturnActor,
    RollingRiskActor,
    register_rolling_risk_model,
    run_portfolio_return,
    run_rolling_risk,
)
from irp_shared.perf.bootstrap import PORTFOLIO_RETURN_MODEL_CODE, ROLLING_RISK_WINDOWS
from irp_shared.perf.rolling_kernel import last_weekday_of_month
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.portfolio.models import Portfolio
from irp_shared.position import PositionActor, create_position
from irp_shared.reference.models import Instrument
from irp_shared.snapshot import build_rolling_risk_snapshot
from irp_shared.snapshot.events import SnapshotActor
from irp_shared.valuation import ValuationActor, create_valuation

#: Tier + INITIAL-AWC dossier constants, kept MODULE-LEVEL and deliberately OUT of
#: ``TIER_DOSSIERS``/``FLAGSHIP_DOSSIERS`` — ``campaign.py`` refuses on a set mismatch and five
#: suites pin ``len == 16`` (OD-RM-1-P).
_TIER_MATERIALITY = "MEDIUM"
_TIER_COMPLEXITY = "MEDIUM"
_TIER_RATIONALE = (
    "Trailing-window risk statistics over an existing governed return series: no new market data, "
    "no new estimator family, and a registered parameter domain of two windows — but the drawdown "
    "and volatility figures are supervisor-facing and feed allocator conversations, so the "
    "materiality is not low."
)
_INITIAL_SCOPE = (
    "Initial validation of perf.rolling_risk v1: the calendar-month relink and its five-condition "
    "alignment gate, the n-1 volatility with the x sqrt(12) transform, the geometric return "
    "annualization above 12 months, and the window-local maximum drawdown with V_0 as an "
    "observation."
)
_INITIAL_CONDITIONS = (
    "Rolling values are NOT independent (~92% overlap between adjacent 12-month windows) and must "
    "not be read as a re-estimate; the month-end convention is holiday-free in v1 (the "
    "holiday-aware v2 shipped at CAL-1b); two-stage "
    "linking is not bit-identical to PM-1's one-stage TWR_LINKED where a month holds two or more "
    "sub-periods; no benchmark leg, so GIPS 2.A.18.a binds only the v2."
)
_REPORT_REF = "05_analytics_methodologies/rolling_risk_v1.md"

_PORTFOLIO_CODE = "DEMO-ROLLING-RISK"
_CODE_VERSION = "rm-1-demo"
_ENVIRONMENT = "demo"
_ACTOR_ID = "demo-rolling-analyst"

#: The book opens well before the campaign's own window so the two never interact.
_T0 = datetime(2023, 11, 1, 9, 0, tzinfo=UTC)

#: Two EXISTING listed equities — reused, so the stage mints no new reference data.
_INSTRUMENT_CODES = ("EQ-ACME-US", "EQ-EURX-DE")


#: 19 month-ends from 2023-12 through 2025-06, in order.
def _month_end_grid() -> list[dt_date]:
    grid: list[dt_date] = []
    year, month = 2023, 12
    for _ in range(19):
        grid.append(last_weekday_of_month(year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return grid


#: The per-boundary USD mark path for the FIRST instrument. Designed so the monthly series contains
#: a genuine MULTI-MONTH drawdown (a peak, five consecutive down months, then a partial recovery) —
#: otherwise maximum drawdown is identically zero and its leg proves nothing.
_MARK_PATH = (
    "100.00",  # 2023-12 open
    "104.00",
    "108.00",
    "112.00",  # the peak
    "106.00",  # the drawdown begins
    "100.00",
    "95.00",
    "90.00",
    "86.00",  # the trough — about -23% from peak
    "89.00",  # recovery
    "92.00",
    "95.00",
    "97.00",
    "99.00",
    "101.00",
    "103.00",
    "105.00",
    "107.00",
    "109.00",
    "111.00",
)


class DemoRm1Error(Exception):
    """Base class for stage-16 refusals."""


class DemoRm1AlreadySeededError(DemoRm1Error):
    """The stage has already run in this tenant. Refuses rather than silently skipping, so a dirty
    double-run is a loud failure instead of a partially-mutated demo history."""


@dataclass(frozen=True)
class Rm1Stage16Summary:
    portfolio_id: str
    exposure_run_ids: list[str]
    portfolio_return_run_id: str
    rolling_risk_run_id: str
    rolling_row_count: int
    suppressed_row_count: int


def _resolve_instrument(session: Session, code: str) -> str:
    row = (
        session.execute(
            select(Instrument).where(
                Instrument.tenant_id == DEMO_TENANT_ID, Instrument.code == code
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise DemoRm1Error(f"demo instrument {code} is missing — run the campaign first")
    return str(row.id)


def _resolve_principal(session: Session) -> str:
    user = (
        session.execute(select(AppUser).where(AppUser.tenant_id == DEMO_TENANT_ID))
        .scalars()
        .first()
    )
    if user is None:
        raise DemoRm1Error("no demo principal — run the campaign first")
    return str(user.id)


def _resolve_registered_version(session: Session, model_code: str) -> str:
    """The EXISTING registered ``model_version`` for a demo model code.

    PM-1's ``perf.return.twr`` v1 is already in the demo inventory with the CAMPAIGN's own
    ``code_version``, and that tuple IS the version identity — re-registering under this stage's
    code_version raises ``ModelVersionConflictError`` (correctly: two different declarations cannot
    share one ``v1`` label). So the stage RESOLVES the shipped version rather than minting a rival,
    which is also why this stage adds exactly ONE model code (RM-1's own) to the counts.
    """
    row = (
        session.execute(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(Model.tenant_id == DEMO_TENANT_ID, Model.code == model_code)
        )
        .scalars()
        .first()
    )
    if row is None:
        raise DemoRm1Error(f"model {model_code} is not registered — run the campaign first")
    return str(row.id)


def _require_completed(result: object, label: str) -> None:
    status = getattr(result, "status", None)
    if status != "COMPLETED":
        reason = getattr(result, "failure_reason", None)
        raise DemoRm1Error(f"{label} did not COMPLETE (status={status}, reason={reason})")


def run_demo_rm1_stage16(session: Session) -> Rm1Stage16Summary:
    """Seed the rolling-risk book, drive 20 boundary exposure runs + PM-1 + RM-1, and return the
    ids. Idempotent by REFUSAL — a second call raises rather than half-seeding."""
    existing = (
        session.execute(
            select(Portfolio).where(
                Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _PORTFOLIO_CODE
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise DemoRm1AlreadySeededError(f"{_PORTFOLIO_CODE} already exists in the demo tenant")

    registrar = _resolve_principal(session)
    validator = registrar
    instrument_ids = [_resolve_instrument(session, code) for code in _INSTRUMENT_CODES]

    month_ends = _month_end_grid()
    # THE MID-MONTH BOUNDARY: inserted inside the second measured month so that month relinks TWO
    # sub-periods. Without it every relink is the identity and the crux is never exercised.
    mid_month = dt_date(month_ends[1].year, month_ends[1].month, 15)
    boundaries = sorted([*month_ends, mid_month])
    if len(boundaries) != 20:
        raise DemoRm1Error(f"expected 20 boundaries, built {len(boundaries)}")

    portfolio_id = str(
        create_portfolio(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=_PORTFOLIO_CODE,
            name="Rolling-risk demo book (RM-1)",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id=registrar),
        ).id
    )
    for instrument_id in instrument_ids:
        create_position(
            session,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            acting_tenant=DEMO_TENANT_ID,
            actor=PositionActor(actor_id=registrar),
            quantity=Decimal("1000"),
            valid_from=_T0,
        )
    session.flush()

    # A mark per instrument per boundary. The second instrument tracks the first at a constant
    # ratio, so the BOOK's return path is exactly the designed one — a second independent path would
    # blur the drawdown the fixture exists to demonstrate.
    for index, boundary in enumerate(boundaries):
        mark = Decimal(_MARK_PATH[index])
        for offset, instrument_id in enumerate(instrument_ids):
            create_valuation(
                session,
                portfolio_id=portfolio_id,
                instrument_id=instrument_id,
                valuation_date=boundary,
                acting_tenant=DEMO_TENANT_ID,
                actor=ValuationActor(actor_id=registrar),
                mark_value=(mark if offset == 0 else mark * Decimal("2")),
                currency_code="USD",
                valid_from=_T0,
            )
    session.flush()

    # --- 20 boundary exposure runs (the PM-1 sub-period boundaries) ---
    exposure_run_ids: list[str] = []
    for boundary in boundaries:
        result = run_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ExposureActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT,
            portfolio_id=portfolio_id,
            # END of the boundary day: a mark for day T is captured DURING T, so a midnight cutoff
            # would make it invisible under `valid_from <= valid_at` (the SCH-2 lesson).
            as_of_valid_at=datetime(
                boundary.year, boundary.month, boundary.day, 23, 59, 59, 999999, tzinfo=UTC
            ),
            base_currency="USD",
        )
        _require_completed(result, f"exposure run at {boundary}")
        exposure_run_ids.append(result.run.run_id)

    # --- PM-1: the governed return series over those boundaries ---
    return_version_id = _resolve_registered_version(session, PORTFOLIO_RETURN_MODEL_CODE)
    return_result = run_portfolio_return(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=PortfolioReturnActor(actor_id=_ACTOR_ID),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT,
        model_version_id=return_version_id,
        exposure_run_ids=exposure_run_ids,
    )
    _require_completed(return_result, "portfolio-return run")

    # --- RM-1: the rolling-risk run over the pinned return series ---
    rolling_version = register_rolling_risk_model(
        session, tenant_id=DEMO_TENANT_ID, actor_id=registrar, code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=SnapshotActor(actor_id=_ACTOR_ID),
        portfolio_return_run_id=return_result.run.run_id,
    )
    rolling_result = run_rolling_risk(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=RollingRiskActor(actor_id=_ACTOR_ID),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT,
        model_version_id=str(rolling_version.id),
        # BOTH windows: 12 fills and yields a genuine rolling series; 36 cannot and therefore
        # exercises the suppression encoding on real data rather than in a unit fixture.
        window_months=ROLLING_RISK_WINDOWS,
        snapshot_id=snapshot.id,
    )
    _require_completed(rolling_result, "rolling-risk run")

    # --- Tier + the INITIAL AWC. NEW code => SOME record (the MG-1/CC-2/PPF-2/PPF-3 precedent).
    # The 4-finder review found this missing: every prior new-code stage files one, and without it
    # `perf.rolling_risk` would be the ONLY model code in the demo inventory carrying no tier and no
    # validation — breaking the MG-1 governance story the demo exists to demonstrate, while the
    # ratified record, the stage docstring and the CI comment all claimed the record was filed.
    assign_model_tier(
        session,
        acting_tenant=DEMO_TENANT_ID,
        model_id=str(rolling_version.model_id),
        materiality_rating=_TIER_MATERIALITY,
        complexity_rating=_TIER_COMPLEXITY,
        rationale=_TIER_RATIONALE,
        actor_id=validator,
    )
    record_validation(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ModelValidationActor(actor_id=validator),
        request=RecordValidationRequest(
            model_version_id=str(rolling_version.id),
            validation_type=VALIDATION_TYPE_INITIAL,
            outcome=VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
            scope_summary=_INITIAL_SCOPE,
            conditions=_INITIAL_CONDITIONS,
            report_ref=_REPORT_REF,
            next_review_due=date(2026, 7, 27) + timedelta(days=365),
            findings=(),
            evidence=(
                ValidationEvidenceInput(
                    evidence_type="CALCULATION_RUN", run_id=str(rolling_result.run.run_id)
                ),
            ),
        ),
    )

    return Rm1Stage16Summary(
        portfolio_id=portfolio_id,
        exposure_run_ids=exposure_run_ids,
        portfolio_return_run_id=return_result.run.run_id,
        rolling_risk_run_id=rolling_result.run.run_id,
        rolling_row_count=len(rolling_result.rows),
        suppressed_row_count=sum(1 for r in rolling_result.rows if r.suppressed),
    )
