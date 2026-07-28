"""SR-1 demo stage 17 — the Sharpe ratio over RM-1's book (ENT-065, the 22nd governed number).

**This stage adds ONE thing and reuses everything else.** RM-1's stage 16 already seeded a
purpose-built 20-boundary book and drove it through a real PM-1 return run; SR-1's number needs
exactly that series plus a risk-free leg. So this stage captures an 18-row monthly cash series and
runs Sharpe over the EXISTING return run — it seeds no book, no positions, no valuations, and no
second PM-1 run.

**The upstream run is discovered DETERMINISTICALLY, never by "latest"** (verifier M8). The demo
tenant holds TWO completed ``PORTFOLIO_RETURN`` runs — stage 16's month-end book and the campaign's
own 8-boundary intra-month one — and the campaign's would be REFUSED by the month-alignment gate
with a confusing message if an ordering assumption ever slipped. The stage therefore resolves the
book by CODE, finds the return runs whose rows carry that ``portfolio_id``, and asserts there is
EXACTLY ONE.

**The risk-free series is economically plausible, not decorative** (the test-data realism rule):
USD cash at roughly 0.30-0.45% a month, DECLINING through 2024-25 as a policy-easing cycle would.
It is also deliberately NOT constant — a constant risk-free rate would make ``sigma(excess)`` equal
``sigma(portfolio)``, and the demo would then be unable to distinguish the Sharpe (1994)
construction this platform implements from the Sharpe (1966) one it explicitly refuses. **A demo
that cannot REACH a control does not demonstrate it** (the OPS-1 standing lesson).

**Both windows are requested.** 12 fills and yields a genuine 7-window rolling series; 36 cannot,
so its SUPPRESSED rows exercise the nullable-value + explicit-flag encoding on real data.

**Stage ORDERING is load-bearing** (the standing discipline): local batteries collect
alphabetically and earlier suites pin governed-code sets with set-equality, so each new stage
appends one more ``z``. RM-1's stage 16 is ``stage9zzzzzzz`` (seven), so SR-1's suite is
``stage9zzzzzzzz`` (EIGHT) — verified by ``ls`` rather than read off a record, which is the trap
RM-1 fell into.

Counts move **24/39/132 -> 25/40/133** (MEASURED on a fresh-schema battery, not derived): one new
model code (``perf.sharpe``), one INITIAL validation record, and ONE new COMPLETED run. The
validation record is filed EXPLICITLY here — RM-1's first implementation omitted it and would have
left the new model code the only one in the demo inventory carrying no tier and no validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.entitlement.models import AppUser
from irp_shared.marketdata import BenchmarkActor, capture_benchmark, capture_benchmark_return
from irp_shared.marketdata.models import RETURN_BASIS_TOTAL
from irp_shared.model.models import (
    VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
    VALIDATION_TYPE_INITIAL,
)
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    record_validation,
)
from irp_shared.perf import SharpeRatioActor, register_sharpe_model, run_sharpe_ratio
from irp_shared.perf.bootstrap import SHARPE_WINDOWS
from irp_shared.perf.events import RUN_TYPE_PORTFOLIO_RETURN
from irp_shared.perf.models import PortfolioReturnResult
from irp_shared.portfolio.models import Portfolio
from irp_shared.snapshot import build_sharpe_snapshot
from irp_shared.snapshot.events import SnapshotActor

#: Tier + INITIAL-AWC dossier constants, kept MODULE-LEVEL and deliberately OUT of
#: ``TIER_DOSSIERS``/``FLAGSHIP_DOSSIERS`` — ``campaign.py`` refuses on a set mismatch and five
#: suites pin ``len == 16`` (the RM-1 precedent).
_TIER_MATERIALITY = "MEDIUM"
_TIER_COMPLEXITY = "MEDIUM"
_TIER_RATIONALE = (
    "A risk-adjusted return over an existing governed return series and a captured risk-free "
    "series: no new estimator family and a registered domain of two windows — but the Sharpe ratio "
    "is the number an allocator quotes first, so it is the most externally-visible figure this "
    "platform produces and its materiality is not low."
)
_INITIAL_SCOPE = (
    "Initial validation of perf.sharpe v1: the Sharpe (1994) differential-return construction with "
    "the disclosed n-1 divisor divergence, single-quantization with the suppression predicate on "
    "the unquantized sigma, the x sqrt(12) iid annualization from the stored value, and the "
    "month-key risk-free join with its completeness and uniqueness refusals."
)
_INITIAL_CONDITIONS = (
    "The n-1 divisor DIVERGES from Sharpe (1994)'s own endnote (population sigma), making the "
    "reported ratio about 4.3% smaller at n = 12 — disclosed, not corrected. The x sqrt(12) "
    "annualization assumes iid returns and MISSTATES under autocorrelation (Lo 2002 Eq. 20 is the "
    "recorded v2). Rolling values are NOT independent (~92% overlap between adjacent 12-month "
    "windows). The risk-free leg is a CAPTURE and its quality bounds the number; v1 accepts "
    "vendor-published returns only, never levels."
)
_REPORT_REF = "05_analytics_methodologies/sharpe_v1.md"

#: RM-1's book — resolved by CODE, never by "the latest run" (see the module docstring).
_PORTFOLIO_CODE = "DEMO-ROLLING-RISK"
_CODE_VERSION = "sr-1-demo"
_ENVIRONMENT = "demo"
_ACTOR_ID = "demo-sharpe-analyst"

_RF_BENCHMARK_CODE = "USD-CASH-1M"
_RF_BENCHMARK_SOURCE = "DEMO_VENDOR"

#: The 18 MEASURED months of stage 16's book (2024-01 .. 2025-06) and their vendor-published monthly
#: cash returns. Economically plausible and DECLINING — a policy-easing path — and deliberately not
#: constant, so sigma(excess) != sigma(portfolio) and the demo actually reaches the construction it
#: claims to demonstrate. d_0's month (2023-12) contributes no observation and needs no row.
_RF_RETURNS = (
    "0.00450",
    "0.00448",
    "0.00445",
    "0.00443",
    "0.00440",
    "0.00437",
    "0.00433",
    "0.00428",
    "0.00420",
    "0.00410",
    "0.00398",
    "0.00385",
    "0.00372",
    "0.00360",
    "0.00348",
    "0.00337",
    "0.00327",
    "0.00318",
)


class DemoSr1Error(Exception):
    """Base class for stage-17 refusals."""


class DemoSr1AlreadySeededError(DemoSr1Error):
    """The stage has already run in this tenant. Refuses rather than silently skipping, so a dirty
    double-run is a loud failure instead of a partially-mutated demo history."""


@dataclass(frozen=True)
class Sr1Stage17Summary:
    portfolio_id: str
    portfolio_return_run_id: str
    risk_free_benchmark_id: str
    risk_free_row_count: int
    sharpe_run_id: str
    sharpe_row_count: int
    suppressed_row_count: int


def _resolve_principal(session: Session) -> str:
    user = (
        session.execute(select(AppUser).where(AppUser.tenant_id == DEMO_TENANT_ID))
        .scalars()
        .first()
    )
    if user is None:
        raise DemoSr1Error("no demo principal — run the campaign first")
    return str(user.id)


def _resolve_rm1_book(session: Session) -> str:
    row = (
        session.execute(
            select(Portfolio).where(
                Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _PORTFOLIO_CODE
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise DemoSr1Error(f"{_PORTFOLIO_CODE} is missing — run demo stage 16 (RM-1) first")
    return str(row.id)


def _resolve_return_run(session: Session, portfolio_id: str) -> str:
    """The ONE completed PM-1 run over stage 16's book — asserted, not assumed.

    The demo tenant holds TWO completed ``PORTFOLIO_RETURN`` runs. Selecting "the latest" would work
    today and break silently the first time another stage adds a return run; worse, picking the
    campaign's intra-month book would be REFUSED by the month-alignment gate with a message about
    partial months that says nothing about the real mistake. So the run is found through the rows
    that carry this book's ``portfolio_id``, and a count other than one is a loud refusal.
    """
    run_ids = sorted(
        {
            str(r)
            for r in session.execute(
                select(PortfolioReturnResult.calculation_run_id)
                .join(
                    CalculationRun,
                    CalculationRun.run_id == PortfolioReturnResult.calculation_run_id,
                )
                .where(
                    PortfolioReturnResult.tenant_id == DEMO_TENANT_ID,
                    PortfolioReturnResult.portfolio_id == portfolio_id,
                    CalculationRun.run_type == RUN_TYPE_PORTFOLIO_RETURN,
                    CalculationRun.status == "COMPLETED",
                )
                .distinct()
            ).scalars()
        }
    )
    if len(run_ids) != 1:
        raise DemoSr1Error(
            f"expected exactly ONE completed portfolio-return run over {_PORTFOLIO_CODE}, "
            f"found {len(run_ids)}"
        )
    return run_ids[0]


def _measured_month_ends(session: Session, return_run_id: str) -> list[date]:
    """The month-end of every MEASURED month, read off the consumed run's own sub-periods.

    Derived rather than hard-coded: a hard-coded date list would silently drift the moment stage
    16's calendar changed, and the risk-free series would then either refuse (a visible failure)
    or — if the drift were a shift rather than a gap — align against the WRONG months, which is an
    invisible one.
    """
    ends = sorted(
        {
            row.period_end
            for row in session.execute(
                select(PortfolioReturnResult).where(
                    PortfolioReturnResult.tenant_id == DEMO_TENANT_ID,
                    PortfolioReturnResult.calculation_run_id == return_run_id,
                    PortfolioReturnResult.metric_type == "DIETZ_PERIOD",
                )
            ).scalars()
        }
    )
    # One entry per calendar MONTH — stage 16's mid-month boundary makes January hold two
    # sub-periods, and the risk-free leg needs one row per month, not per sub-period.
    by_month: dict[tuple[int, int], date] = {}
    for when in ends:
        by_month[(when.year, when.month)] = max(by_month.get((when.year, when.month), when), when)
    return [by_month[key] for key in sorted(by_month)]


def run_demo_sr1_stage17(session: Session) -> Sr1Stage17Summary:
    """Capture the risk-free series and drive one governed Sharpe run over RM-1's book.

    Idempotent by REFUSAL — a second call raises rather than half-seeding."""
    existing = session.execute(
        select(CalculationRun).where(
            CalculationRun.tenant_id == DEMO_TENANT_ID, CalculationRun.run_type == "SHARPE"
        )
    ).first()
    if existing is not None:
        raise DemoSr1AlreadySeededError("a SHARPE run already exists in the demo tenant")

    registrar = _resolve_principal(session)
    validator = registrar
    portfolio_id = _resolve_rm1_book(session)
    return_run_id = _resolve_return_run(session, portfolio_id)

    month_ends = _measured_month_ends(session, return_run_id)
    if len(month_ends) != len(_RF_RETURNS):
        raise DemoSr1Error(
            f"stage 16's book measures {len(month_ends)} months but this stage carries "
            f"{len(_RF_RETURNS)} risk-free returns — the two must agree exactly"
        )

    # --- the risk-free leg: a captured, vendor-published monthly cash series ---
    benchmark = capture_benchmark(
        session,
        benchmark_code=_RF_BENCHMARK_CODE,
        benchmark_source=_RF_BENCHMARK_SOURCE,
        benchmark_currency="USD",
        acting_tenant=DEMO_TENANT_ID,
        actor=BenchmarkActor(actor_id=registrar),
        benchmark_name="USD 1-month cash (demo risk-free proxy)",
        index_family="CASH",
    )
    session.flush()
    from decimal import Decimal

    for when, value in zip(month_ends, _RF_RETURNS, strict=True):
        capture_benchmark_return(
            session,
            benchmark,
            return_date=when,
            return_basis=RETURN_BASIS_TOTAL,
            return_value=Decimal(value),
            acting_tenant=DEMO_TENANT_ID,
            actor=BenchmarkActor(actor_id=registrar),
        )
    session.flush()

    # --- SR-1: the governed Sharpe run over the pinned return series + risk-free window ---
    sharpe_version = register_sharpe_model(
        session, tenant_id=DEMO_TENANT_ID, actor_id=registrar, code_version=_CODE_VERSION
    )
    snapshot = build_sharpe_snapshot(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=SnapshotActor(actor_id=_ACTOR_ID),
        portfolio_return_run_id=return_run_id,
        risk_free_benchmark_id=benchmark.id,
        rf_return_basis=RETURN_BASIS_TOTAL,
    )
    result = run_sharpe_ratio(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=SharpeRatioActor(actor_id=_ACTOR_ID),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT,
        model_version_id=str(sharpe_version.id),
        # BOTH windows: 12 fills and yields a genuine rolling series; 36 cannot and therefore
        # exercises the suppression encoding on real data rather than in a unit fixture.
        window_months=SHARPE_WINDOWS,
        snapshot_id=snapshot.id,
    )
    if result.status != "COMPLETED":
        raise DemoSr1Error(
            f"sharpe run did not COMPLETE (status={result.status}, reason={result.failure_reason})"
        )

    # --- Tier + the INITIAL AWC. NEW code => SOME record (the MG-1/CC-2/PPF-3/RM-1 precedent).
    # Filed EXPLICITLY: the perf registrar mints none implicitly, and RM-1's first implementation
    # omitted this, which would have left its model code the only one in the demo inventory with no
    # tier and no validation while the record claimed otherwise.
    assign_model_tier(
        session,
        acting_tenant=DEMO_TENANT_ID,
        model_id=str(sharpe_version.model_id),
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
            model_version_id=str(sharpe_version.id),
            validation_type=VALIDATION_TYPE_INITIAL,
            outcome=VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
            scope_summary=_INITIAL_SCOPE,
            conditions=_INITIAL_CONDITIONS,
            report_ref=_REPORT_REF,
            next_review_due=date(2026, 7, 28) + timedelta(days=365),
            findings=(),
            evidence=(
                ValidationEvidenceInput(
                    evidence_type="CALCULATION_RUN", run_id=str(result.run.run_id)
                ),
            ),
        ),
    )

    return Sr1Stage17Summary(
        portfolio_id=portfolio_id,
        portfolio_return_run_id=return_run_id,
        risk_free_benchmark_id=str(benchmark.id),
        risk_free_row_count=len(_RF_RETURNS),
        sharpe_run_id=result.run.run_id,
        sharpe_row_count=len(result.rows),
        suppressed_row_count=sum(1 for r in result.rows if r.suppressed),
    )
