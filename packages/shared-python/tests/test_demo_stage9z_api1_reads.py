"""API-1 stage-10 conformance suite (OD-API-1, OQ-W7C-5) — the runs-only structural pins, SQLite
tier. The live full-chain seed + count/read assertions are the PG twin (``_pg``); this tier pins the
module's own contract without the heavy chain.

The ``stage9z`` filename component is LOAD-BEARING (the CC-2-recorded stage10 zero-pad hazard): a
two-digit ``stage10`` suite sorts lexically BEFORE ``stage2``/``stage4``, so a single-invocation
local PG battery would seed the five extra runs before the earlier stages assert their exact count
pins. ``stage9z`` collates immediately AFTER ``test_demo_stage9_cc2*`` — last among the demo stage
suites — which is where a runs-adding stage must run."""

from __future__ import annotations

from datetime import date

from irp_shared.demo.stage10_api1 import (
    _ACTIVE_RISK_CODE,
    _BENCH_RETURN_DATES,
    _BENCHMARK_RELATIVE_CODE,
    _PROXY_CODE,
    _SCENARIO_CODE,
    _SENSITIVITY_CODE,
    Stage10Api1Summary,
)


def test_stage10_is_runs_only_in_its_story() -> None:
    """The demo's own contrast — a NEW governed number moves codes+records+runs (stage 9), but
    EXERCISING already-registered heads moves ONLY runs (stage 10) — is stated where the runner
    reads first."""
    import irp_shared.demo.stage10_api1 as stage10

    doc = stage10.__doc__ or ""
    assert "RUNS-ONLY" in doc
    assert "20 codes / 35 records UNCHANGED; 96 → 101 runs" in doc


def test_stage10_targets_the_five_registered_but_unrun_codes() -> None:
    """The five codes stage 10 exercises are exactly the campaign's registered-but-never-run set."""
    assert _SENSITIVITY_CODE == "risk.sensitivity.analytic"
    assert _ACTIVE_RISK_CODE == "risk.active_risk.parametric"
    assert _SCENARIO_CODE == "risk.scenario.factor_shock"
    assert _BENCHMARK_RELATIVE_CODE == "perf.benchmark_relative"
    assert _PROXY_CODE == "risk.factor_exposure.proxy"


def test_stage10_benchmark_return_dates_partition_the_pm1_span() -> None:
    """ONE benchmark return per PM-1 DIETZ sub-period end (2026-05-19..26): the binder requires
    >= 1 benchmark row per sub-period window and refuses any row outside the span, so the eight
    dates must be exactly the sub-period ends."""
    assert _BENCH_RETURN_DATES == tuple(
        date(2026, 5, 19) + __import__("datetime").timedelta(days=i) for i in range(8)
    )
    assert _BENCH_RETURN_DATES[0] == date(2026, 5, 19)
    assert _BENCH_RETURN_DATES[-1] == date(2026, 5, 26)


def test_stage10_summary_names_all_five_run_ids() -> None:
    """The summary surfaces the five COMPLETED run ids the API-1 reads now render."""
    fields = set(Stage10Api1Summary.__dataclass_fields__)
    assert {
        "sensitivity_run_id",
        "active_risk_run_id",
        "scenario_run_id",
        "benchmark_relative_run_id",
        "proxy_exposure_run_id",
    } <= fields
