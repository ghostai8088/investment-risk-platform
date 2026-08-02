"""The DATA-1 demo stage — the first genuinely EXTERNAL dataset, captured live on the rails.

**What it demonstrates, end to end (OQ-DATA-1-11).**

1. **The real dataset lands through the governed rail**: a ``US-TBILL-3M`` benchmark head
   (source ``US-FRB-H15`` — the Board of Governors' H.15 release, the authoritative origin) is
   created in the DEMO tenant, and the 30 hand-verified TB3MS observations 2024-01..2026-06 are
   captured through ``refresh_benchmark_rates`` with the declared series start and coverage
   horizon — per-row ``MARKET.BENCHMARK_RATE_CREATE`` events, ORIGIN lineage, one head
   ``REFERENCE.UPDATE``, and the ratified capture-first doctrine (fractions verbatim; NO derived
   monthly return anywhere).
2. **The completeness gate runs FOR REAL**: the refresh's effective leg executes the DATA-1-minted
   ``RULE_TYPE_COMPLETENESS`` rule (expected month keys carried IN the persisted rule — the
   REF-1 trigger honored) and ``assert_passed_quality_checks`` — the gate's first capture-rail
   caller — proves the PASS evidence is queryable.
3. **Idempotence, executed**: a second identical refresh is a TRUE silent no-op (added 0, no
   events, no DQ leg) — the re-run behavior CTRL-034 Execution 2 item 7 records.

**The demo rf series (``USD-CASH-1M``/``DEMO_VENDOR``) coexists untouched** — different
``(benchmark_code, benchmark_source)`` — and Sharpe keeps consuming IT: feeding the real series
into a governed number is the ratified OQ-DATA-1-1a carry (a registered yield→period-return
model + new version labels), deliberately NOT taken here.

Counts: ZERO new model codes, ZERO validations, ZERO calculation runs — the FINAL-POSITION pin
**26/43/139 does not move** (a captured input binds none of those; the 13-z suite measures it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.dq.service import assert_passed_quality_checks
from irp_shared.marketdata import (
    BenchmarkActor,
    capture_benchmark,
    refresh_benchmark_rates,
    resolve_benchmark,
)
from irp_shared.marketdata.benchmark_rates import ENTITY_BENCHMARK_RATE
from irp_shared.marketdata.models import (
    OBSERVATION_CONVENTION_MONTHLY_AVG_BUSINESS_DAYS,
    QUOTE_BASIS_DISCOUNT_360,
    RATE_TYPE_BILL_DISCOUNT_YIELD,
    Benchmark,
)
from irp_shared.marketdata.tb3ms_rates import (
    TB3MS_COMPLETE_THROUGH,
    TB3MS_RATES,
    TB3MS_SERIES_START,
)

_ACTOR_ID = "demo-data-steward"

#: The real series' identity in the demo tenant (coexists with USD-CASH-1M/DEMO_VENDOR).
DATA1_BENCHMARK_CODE = "US-TBILL-3M"
DATA1_BENCHMARK_SOURCE = "US-FRB-H15"


class DemoData1Error(RuntimeError):
    """Base class for stage-22 failures."""


class DemoData1AlreadySeededError(DemoData1Error):
    """The stage already ran against this database (the US-TBILL-3M head exists)."""


@dataclass(frozen=True)
class Data1Stage22Summary:
    benchmark_id: str
    added: int
    rates_complete_through: date
    rerun_added: int


def run_demo_data1_stage22(session: Session) -> Data1Stage22Summary:
    """Capture the real TB3MS series in the DEMO tenant through the governed rail; prove the
    completeness gate and the idempotent re-run. The session must already carry the DEMO tenant
    context (the demo-suite convention)."""
    existing = session.execute(
        select(Benchmark).where(
            Benchmark.tenant_id == DEMO_TENANT_ID,
            Benchmark.benchmark_code == DATA1_BENCHMARK_CODE,
            Benchmark.benchmark_source == DATA1_BENCHMARK_SOURCE,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DemoData1AlreadySeededError(
            f"{DATA1_BENCHMARK_CODE}/{DATA1_BENCHMARK_SOURCE} already exists in the demo tenant"
        )

    actor = BenchmarkActor(actor_id=_ACTOR_ID)
    head = capture_benchmark(
        session,
        benchmark_code=DATA1_BENCHMARK_CODE,
        benchmark_source=DATA1_BENCHMARK_SOURCE,
        benchmark_currency="USD",
        acting_tenant=DEMO_TENANT_ID,
        actor=actor,
        benchmark_name="U.S. 3-Month Treasury Bill (secondary market, discount basis)",
    )
    session.flush()
    benchmark = resolve_benchmark(session, head.id, acting_tenant=DEMO_TENANT_ID)

    def _refresh() -> dict[str, object]:
        return refresh_benchmark_rates(
            session,
            benchmark,
            rates=dict(TB3MS_RATES),
            rate_type=RATE_TYPE_BILL_DISCOUNT_YIELD,
            quote_basis=QUOTE_BASIS_DISCOUNT_360,
            observation_convention=OBSERVATION_CONVENTION_MONTHLY_AVG_BUSINESS_DAYS,
            series_start=TB3MS_SERIES_START,
            acting_tenant=DEMO_TENANT_ID,
            actor=actor,
            complete_through=TB3MS_COMPLETE_THROUGH,
        )

    first = _refresh()
    if first["added"] != len(TB3MS_RATES) or not first["completeness_ran"]:
        raise DemoData1Error(f"the first refresh did not land the full dataset: {first}")

    # The gate's first capture-rail caller: PASS evidence must be queryable (fail-closed).
    assert_passed_quality_checks(
        session, ENTITY_BENCHMARK_RATE, str(benchmark.id), tenant_id=DEMO_TENANT_ID
    )

    # Idempotence, executed: the identical re-supply is a TRUE silent no-op.
    rerun = _refresh()
    if rerun["added"] != 0 or rerun["completeness_ran"]:
        raise DemoData1Error(f"the identical re-run was not a silent no-op: {rerun}")

    return Data1Stage22Summary(
        benchmark_id=str(benchmark.id),
        added=int(first["added"]),
        rates_complete_through=TB3MS_COMPLETE_THROUGH,
        rerun_added=int(rerun["added"]),
    )
