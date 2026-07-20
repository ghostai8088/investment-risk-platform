"""BT-3 kernel tests — the AS Z̄1/Z̄2 statistics + the Christoffersen Markov leg.

The identity fixtures are EXACT (``fractions.Fraction`` end-to-end where the algebra is
rational): the null-expectation identities E[Z̄2] = 0 and E[Z̄1 | N > 0] = 0 hold EXACTLY on a
finite discrete distribution whose tail is analytically known — and the '+1'-grouping
corruption (the ES-HS-1 debt's transcription-hazard class) provably BREAKS them. The corrupted
conditional statistic evaluates to −ES/(ES+1) ≈ −0.7004 at N(0,1)/a=0.025 — numerically
COINCIDING with the −0.70 critical — so these identity tests are the only mechanical defense
against a corruption that emits plausible-looking values (the planning verifier's finding)."""

from __future__ import annotations

import itertools
import math
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from irp_shared.risk.es_backtest_kernel import (
    ES_DECISION_FAIL_TO_REJECT,
    ES_DECISION_REJECT,
    Z2_CRITICALS,
    AsZStatistics,
    EsBacktestKernelError,
    as_z_statistics,
    z2_verdict,
)
from irp_shared.risk.var_backtest_kernel import (
    CHI2_2DF_CRITICALS,
    DECISION_FAIL_TO_REJECT,
    DECISION_REJECT,
    VarBacktestKernelError,
    christoffersen_lr_cc,
    christoffersen_lr_ind,
    kupiec_decision,
    lr_cc_decision,
    markov_counts,
)

# --- The exact discrete distribution: X in {-10, -5, +1} with P = {1/50, 1/50, 48/50}.
# With VaR = 4 (positive forecast): exceptions are X in {-10, -5}, so the TRUE tail
# a = 2/50 = 1/25 and the TRUE ES = -E[X | X < -VaR] = (10 + 5)/2 = 15/2. The identity
# E[X·I] = -a·ES = -(2/50)·(15/2) = -15/50 holds by construction.
_OUTCOMES: tuple[tuple[Fraction, Fraction], ...] = (
    (Fraction(-10), Fraction(1, 50)),
    (Fraction(-5), Fraction(1, 50)),
    (Fraction(1), Fraction(48, 50)),
)
_VAR = Fraction(4)
_ES = Fraction(15, 2)
_TAIL_A = Fraction(1, 25)


def _z2_exact(seq: tuple[Fraction, ...], plus_one_outside: bool) -> Fraction:
    """Z̄2 over one outcome sequence, exact; ``plus_one_outside=False`` is the CORRUPTED
    inside-denominator grouping."""
    t = len(seq)
    if plus_one_outside:
        total = sum((x / _ES for x in seq if x + _VAR < 0), Fraction(0))
        return total / (t * _TAIL_A) + 1
    total = sum((x / (_ES + 1) for x in seq if x + _VAR < 0), Fraction(0))
    return total / (t * _TAIL_A)


def _z1_exact(seq: tuple[Fraction, ...], plus_one_outside: bool) -> Fraction | None:
    n = sum(1 for x in seq if x + _VAR < 0)
    if n == 0:
        return None
    if plus_one_outside:
        total = sum((x / _ES for x in seq if x + _VAR < 0), Fraction(0))
        return total / n + 1
    total = sum((x / (_ES + 1) for x in seq if x + _VAR < 0), Fraction(0))
    return total / n


def _seq_probability(seq: tuple[Fraction, ...]) -> Fraction:
    prob = Fraction(1)
    lookup = dict(_OUTCOMES)
    for x in seq:
        prob *= lookup[x]
    return prob


def test_z2_null_expectation_identity_exact_and_corruption_breaks_it() -> None:
    """EXACT over all length-2 i.i.d. sequences: E[Z̄2] = 0 with the '+1' outside; the
    corrupted grouping is bounded away from zero."""
    values = tuple(x for x, _ in _OUTCOMES)
    e_correct = Fraction(0)
    e_corrupt = Fraction(0)
    for seq in itertools.product(values, repeat=2):
        p = _seq_probability(seq)
        e_correct += p * _z2_exact(seq, plus_one_outside=True)
        e_corrupt += p * _z2_exact(seq, plus_one_outside=False)
    assert e_correct == 0
    assert e_corrupt != 0
    # The corrupted unconditional expectation is E[Z2_corrupt] = -ES/(ES+1) exactly:
    assert e_corrupt == -_ES / (_ES + 1)


def test_z1_conditional_null_expectation_identity_exact_and_corruption_breaks_it() -> None:
    """EXACT over all length-2 sequences: E[Z̄1 | N > 0] = 0 with the '+1' outside; the
    corrupted grouping lands at -ES/(ES+1) — the plausible-looking near-threshold value."""
    values = tuple(x for x, _ in _OUTCOMES)
    num_correct = Fraction(0)
    num_corrupt = Fraction(0)
    p_nonzero = Fraction(0)
    for seq in itertools.product(values, repeat=2):
        p = _seq_probability(seq)
        z1c = _z1_exact(seq, plus_one_outside=True)
        z1x = _z1_exact(seq, plus_one_outside=False)
        if z1c is None:
            continue
        assert z1x is not None
        p_nonzero += p
        num_correct += p * z1c
        num_corrupt += p * z1x
    assert p_nonzero > 0
    assert num_correct / p_nonzero == 0
    assert num_corrupt / p_nonzero == -_ES / (_ES + 1)


def test_kernel_matches_the_exact_fraction_reference_on_a_mixed_sequence() -> None:
    """The Decimal kernel reproduces the exact-Fraction Z̄1/Z̄2 on a hand sequence with two
    exceptions, to the 12dp quantum."""
    seq = (Fraction(-10), Fraction(1), Fraction(-5), Fraction(1), Fraction(1))
    pairs = [(Decimal(int(x)), Decimal(4), Decimal("7.5")) for x in seq]
    stats = as_z_statistics(pairs, Decimal("0.04"))
    z2_ref = _z2_exact(seq, plus_one_outside=True)  # = (-2)/(5·(1/25)) + 1 = -9
    z1_ref = _z1_exact(seq, plus_one_outside=True)  # = (-2)/2 + 1 = 0
    assert z2_ref == Fraction(-9)
    assert z1_ref == Fraction(0)
    assert stats.z2 == Decimal("-9.000000000000")
    assert stats.z1 == Decimal("0.000000000000")
    assert stats.n_exceptions == 2
    assert stats.n_pairs == 5


def test_z1_is_none_not_zero_at_zero_exceptions() -> None:
    pairs = [(Decimal("1"), Decimal(4), Decimal("7.5"))] * 6
    stats = as_z_statistics(pairs, Decimal("0.04"))
    assert stats.z1 is None
    assert stats.n_exceptions == 0
    # Z-bar-2 is well-defined (= +1) at zero breaches — the verdict suppression there is the
    # binder's POLICY (OD-BT-3-A/B cross-reference), not kernel arithmetic.
    assert stats.z2 == Decimal("1.000000000000")


def test_kernel_refusals() -> None:
    with pytest.raises(EsBacktestKernelError):
        as_z_statistics([], Decimal("0.025"))
    with pytest.raises(EsBacktestKernelError):
        as_z_statistics([(Decimal(1), Decimal(4), Decimal("7.5"))], Decimal("1"))
    with pytest.raises(EsBacktestKernelError):
        as_z_statistics([(Decimal(1), Decimal(4), Decimal(0))], Decimal("0.025"))
    with pytest.raises(EsBacktestKernelError):
        as_z_statistics([(Decimal(1), Decimal(-1), Decimal("7.5"))], Decimal("0.025"))
    with pytest.raises(EsBacktestKernelError):
        z2_verdict(Decimal("-1"), Decimal("0.10"))


def test_z2_verdict_boundary_is_strict_below() -> None:
    """REJECT strictly BELOW the critical; AT the critical fails to reject (one-sided left)."""
    assert z2_verdict(Decimal("-0.70"), Decimal("0.05")) == ES_DECISION_FAIL_TO_REJECT
    assert z2_verdict(Decimal("-0.700000000001"), Decimal("0.05")) == ES_DECISION_REJECT
    assert z2_verdict(Decimal("-1.8"), Decimal("0.0001")) == ES_DECISION_FAIL_TO_REJECT
    assert z2_verdict(Decimal("-1.9"), Decimal("0.0001")) == ES_DECISION_REJECT
    assert Z2_CRITICALS[Decimal("0.05")] == Decimal("-0.70")


def test_kernel_fuzz_against_independent_float_implementation() -> None:
    """500 seeded random paired series vs a float re-implementation at 1e-9 relative."""
    rng = random.Random(20260719)
    for _ in range(500):
        t = rng.randint(1, 60)
        pairs = []
        for _ in range(t):
            x = round(rng.uniform(-30, 10), 6)
            var = round(rng.uniform(0.5, 8), 6)
            es = round(var + rng.uniform(0.01, 6), 6)
            pairs.append((Decimal(str(x)), Decimal(str(var)), Decimal(str(es))))
        a = round(rng.uniform(0.005, 0.2), 4)
        stats = as_z_statistics(pairs, Decimal(str(a)))
        total = sum(float(x) / float(es) for x, var, es in pairs if -float(x) > float(var))
        n = sum(1 for x, var, _ in pairs if -float(x) > float(var))
        z2_f = total / (t * a) + 1
        assert math.isclose(float(stats.z2), z2_f, rel_tol=1e-9, abs_tol=1e-9)
        if n:
            assert stats.z1 is not None
            assert math.isclose(float(stats.z1), total / n + 1, rel_tol=1e-9, abs_tol=1e-9)
        else:
            assert stats.z1 is None
        assert stats.n_exceptions == n


# --- Christoffersen Markov leg ---


def test_markov_counts_and_exact_independence_gives_lr_zero() -> None:
    """(a) The transition counter reproduces a hand count; (b) a 2x2 whose MLEs coincide
    (pi01 = pi11 = pi2 = 1/4) has LR_ind = 0 EXACTLY."""
    series = [0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 0, 0]
    c = markov_counts(series)
    # Hand count of the 12 adjacent pairs of the series above:
    assert (c.n00, c.n01, c.n10, c.n11) == (5, 3, 3, 1)
    from irp_shared.risk.var_backtest_kernel import MarkovCounts

    balanced = MarkovCounts(n00=6, n01=2, n10=3, n11=1)  # pi01 = pi11 = pi2 = 1/4
    assert christoffersen_lr_ind(balanced) == Decimal("0.000000000000")


def test_lr_ind_matches_independent_float_reference_on_a_dependent_series() -> None:
    """Clustered exceptions: LR_ind recomputed independently in floats at 1e-9."""
    series = [0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0]
    c = markov_counts(series)
    lr = christoffersen_lr_ind(c)
    assert lr is not None and lr > 0
    n00, n01, n10, n11 = c.n00, c.n01, c.n10, c.n11
    pi01 = n01 / (n00 + n01)
    pi11 = n11 / (n10 + n11)
    pi2 = (n01 + n11) / (n00 + n01 + n10 + n11)

    def _ll(x: int, total: int, p: float) -> float:
        out = 0.0
        if x > 0:
            out += x * math.log(p)
        if x < total:
            out += (total - x) * math.log(1 - p)
        return out

    log_alt = _ll(n01, n00 + n01, pi01) + _ll(n11, n10 + n11, pi11)
    log_null = _ll(n01 + n11, c.total, pi2)
    assert math.isclose(float(lr), 2 * (log_alt - log_null), rel_tol=1e-9, abs_tol=1e-9)


def test_lr_ind_degenerate_tables_return_none_never_zero() -> None:
    assert christoffersen_lr_ind(markov_counts([0, 0, 0, 0])) is None  # no exit from state 1
    assert christoffersen_lr_ind(markov_counts([0, 0, 0, 1])) is None  # trailing lone exception
    assert christoffersen_lr_ind(markov_counts([1, 1, 1, 1])) is None  # no exit from state 0
    with pytest.raises(VarBacktestKernelError):
        markov_counts([0])
    with pytest.raises(VarBacktestKernelError):
        markov_counts([0, 2])


def test_lr_cc_composition_and_df2_decision() -> None:
    lr_cc = christoffersen_lr_cc(Decimal("3.2"), Decimal("2.9"))
    assert lr_cc == Decimal("6.100000000000")
    assert lr_cc_decision(lr_cc, Decimal("0.05")) == DECISION_REJECT
    assert lr_cc_decision(Decimal("5.991465"), Decimal("0.05")) == DECISION_FAIL_TO_REJECT
    assert lr_cc_decision(Decimal("9.3"), Decimal("0.01")) == DECISION_REJECT
    with pytest.raises(VarBacktestKernelError):
        lr_cc_decision(Decimal("1"), Decimal("0.10"))
    # The df=2 constants are the exact closed form -2·ln(alpha):
    assert CHI2_2DF_CRITICALS[Decimal("0.05")] == Decimal("5.991465")
    # The LR_ind decision reuses the df=1 table (same shape as Kupiec):
    assert kupiec_decision(Decimal("3.9"), Decimal("0.05")) == DECISION_REJECT
    assert AsZStatistics(z2=Decimal("1"), z1=None, n_exceptions=0, n_pairs=250).n_pairs == 250


# ------------------------------------------------------------------ binder adjudication (dicts)


def _ret_row(mt: str, s: str, e: str, bmv: str, emv: str, flow: str = "0.000000") -> dict:
    return {
        "metric_type": mt,
        "period_start": s,
        "period_end": e,
        "begin_mv": bmv,
        "end_mv": emv,
        "net_external_flow": flow,
        "calculation_run_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "portfolio_id": "pf-1",
        "base_currency": "USD",
    }


def _leg_row(
    mt: str,
    we: str,
    value: str,
    *,
    snap: str = "cccccccc-0000-0000-0000-00000000000",
    mv: str = "dddddddd-0000-0000-0000-00000000000",
) -> dict:
    """One pinned forecast row (VAR_HISTORICAL or ES_HISTORICAL). ``snap``/``mv`` take a suffix
    from the window day so siblings share per-as-of snapshot ids by default."""
    day = we[-2:]
    return {
        "metric_type": mt,
        "window_end": we,
        "var_value": value,
        "confidence_level": "0.9750",
        "horizon_days": 1,
        "base_currency": "USD",
        "calculation_run_id": f"bbbbbbb{'1' if mt == 'VAR_HISTORICAL' else '2'}-0000-0000-0000-0000000000{day}",
        "exposure_run_id": "eeeeeeee-0000-0000-0000-000000000001",
        "input_snapshot_id": f"{snap}{day[-1]}",
        "model_version_id": f"{mv}{'1' if mt == 'VAR_HISTORICAL' else '2'}",
    }


def _valid_es_pins() -> tuple[list[dict], list[dict]]:
    ret = [
        _ret_row("DIETZ_PERIOD", "2026-06-01", "2026-06-02", "70000.000000", "69800.000000"),
        _ret_row("DIETZ_PERIOD", "2026-06-02", "2026-06-03", "69800.000000", "69900.000000"),
        _ret_row("TWR_LINKED", "2026-06-01", "2026-06-03", "70000.000000", "69900.000000"),
    ]
    legs = [
        _leg_row(
            "VAR_HISTORICAL", "2026-06-01", "150.000000", snap="cccccccc-0000-0000-0000-00000000001"
        ),
        _leg_row(
            "ES_HISTORICAL", "2026-06-01", "210.000000", snap="cccccccc-0000-0000-0000-00000000001"
        ),
        _leg_row(
            "VAR_HISTORICAL", "2026-06-02", "155.000000", snap="cccccccc-0000-0000-0000-00000000002"
        ),
        _leg_row(
            "ES_HISTORICAL", "2026-06-02", "215.000000", snap="cccccccc-0000-0000-0000-00000000002"
        ),
    ]
    return ret, legs


def test_adjudicate_es_valid_baseline() -> None:
    from irp_shared.risk.es_backtest_service import _adjudicate_es_pins

    ret, legs = _valid_es_pins()
    parsed = _adjudicate_es_pins(ret, legs)
    assert len(parsed.pairs) == 2
    assert parsed.confidence_level == Decimal("0.9750")
    p0 = parsed.pairs[0]
    assert p0.realized_pnl == Decimal("-200.000000")  # 69800 - 70000
    assert p0.var_value == Decimal("150.000000") and p0.es_value == Decimal("210.000000")
    assert parsed.var_run_ids != parsed.es_run_ids


@pytest.mark.parametrize(
    "mutate",
    [
        "stray_metric",
        "no_es_leg",
        "no_var_leg",
        "bijection_break",
        "sibling_snapshot_mismatch",
        "confidence_mismatch",
        "version_mix",
        "es_zero",
        "duplicate_asof",
        "unaligned_asof",
    ],
)
def test_adjudicate_es_refusals(mutate: str) -> None:
    from irp_shared.risk.es_backtest_service import EsBacktestInputError, _adjudicate_es_pins

    ret, legs = _valid_es_pins()
    if mutate == "stray_metric":
        legs[1] = {**legs[1], "metric_type": "ES_PARAMETRIC"}
    elif mutate == "no_es_leg":
        legs = [r for r in legs if r["metric_type"] == "VAR_HISTORICAL"]
    elif mutate == "no_var_leg":
        legs = [r for r in legs if r["metric_type"] == "ES_HISTORICAL"]
    elif mutate == "bijection_break":
        legs = legs[:3]  # drop the second ES sibling
    elif mutate == "sibling_snapshot_mismatch":
        legs[1] = {**legs[1], "input_snapshot_id": "ffffffff-0000-0000-0000-000000000009"}
    elif mutate == "confidence_mismatch":
        legs[1] = {**legs[1], "confidence_level": "0.9500"}
        legs[3] = {**legs[3], "confidence_level": "0.9500"}
    elif mutate == "version_mix":
        legs[2] = {**legs[2], "model_version_id": "dddddddd-0000-0000-0000-000000000099"}
    elif mutate == "es_zero":
        legs[1] = {**legs[1], "var_value": "0.000000"}
    elif mutate == "duplicate_asof":
        legs.append(dict(legs[0]))
    elif mutate == "unaligned_asof":
        legs = [
            {**r, "window_end": "2026-06-05"} if r["window_end"] == "2026-06-02" else r
            for r in legs
        ]
    with pytest.raises(EsBacktestInputError):
        _adjudicate_es_pins(ret, legs)


# ------------------------------------------------------- hand-minted end-to-end (SQLite session)


def _mint_es_substrate(session, n_pairs: int, *, breach_at: set[int] = frozenset()) -> tuple:
    """Hand-mint the minimal DB substrate for run_es_backtest's BUILD path: a COMPLETED
    PORTFOLIO_RETURN run with n_pairs contiguous daily DIETZ rows + TWR_LINKED, one COMPLETED
    VAR-type run per leg carrying per-as-of VAR_HISTORICAL / ES_HISTORICAL rows (siblings share
    per-as-of input_snapshot_id), the portfolio, and per-leg factor-exposure identity rows.
    SQLite enforces no FKs — bare GUIDs stand in for unrelated parents (the house unit-tier
    pattern)."""
    from datetime import date, timedelta
    from decimal import Decimal as D

    from irp_shared.calc.models import CalculationRun
    from irp_shared.db.mixins import new_uuid
    from irp_shared.perf.models import PortfolioReturnResult
    from irp_shared.portfolio.models import Portfolio
    from irp_shared.risk.models import FactorExposureResult, VarResult

    tenant = "11111111-1111-1111-1111-111111111111"
    pf = new_uuid()
    session.add(
        Portfolio(
            id=pf,
            tenant_id=tenant,
            code="PF-ES",
            name="pf",
            node_type="PORTFOLIO",
            base_currency_code="USD",
        )
    )

    def _completed_run(run_type: str) -> str:
        run = CalculationRun(
            tenant_id=tenant, run_type=run_type, status="COMPLETED", initiated_by="a"
        )
        session.add(run)
        session.flush()
        return run.run_id

    ret_run = _completed_run("PORTFOLIO_RETURN")
    # ONE forecast run per as-of per leg — var_result's UNIQUE (run, metric_type) grain means a
    # T-day series is T sibling RUN pairs (the record's Grounding fact, confirmed by the schema).
    var_runs: list[str] = []
    es_runs: list[str] = []
    ret_snap = new_uuid()
    var_mv, es_mv = new_uuid(), new_uuid()
    exp_run = _completed_run("FACTOR_EXPOSURE")
    session.add(
        FactorExposureResult(
            tenant_id=tenant,
            calculation_run_id=exp_run,
            input_snapshot_id=new_uuid(),
            model_version_id=new_uuid(),
            portfolio_id=pf,
            instrument_id=new_uuid(),
            factor_id=new_uuid(),
            factor_code="USD",
            factor_family="CURRENCY",
            mark_currency="USD",
            loading=D("1.000000000000"),
            exposure_amount=D("70000.000000"),
            base_currency="USD",
        )
    )

    start = date(2026, 6, 2)
    mv0 = D("70000.000000")
    for i in range(n_pairs):
        s, e = start + timedelta(days=i), start + timedelta(days=i + 1)
        pnl = D("-450.000000") if i in breach_at else D("5.000000")
        session.add(
            PortfolioReturnResult(
                tenant_id=tenant,
                calculation_run_id=ret_run,
                input_snapshot_id=ret_snap,
                model_version_id=new_uuid(),
                portfolio_id=pf,
                metric_type="DIETZ_PERIOD",
                period_start=s,
                period_end=e,
                begin_mv=mv0,
                end_mv=mv0 + pnl,
                net_external_flow=D("0.000000"),
                return_value=D("0.000000000000"),
                n_flows=0,
                n_periods=1,
                base_currency="USD",
            )
        )
        shared_snap = new_uuid()
        pair_var_run = _completed_run("VAR")
        pair_es_run = _completed_run("VAR")
        var_runs.append(pair_var_run)
        es_runs.append(pair_es_run)
        for metric, run_id, mv_id, val in (
            ("VAR_HISTORICAL", pair_var_run, var_mv, D("300.000000")),
            ("ES_HISTORICAL", pair_es_run, es_mv, D("420.000000")),
        ):
            session.add(
                VarResult(
                    tenant_id=tenant,
                    calculation_run_id=run_id,
                    input_snapshot_id=shared_snap,
                    model_version_id=mv_id,
                    exposure_run_id=exp_run,
                    metric_type=metric,
                    base_currency="USD",
                    confidence_level=D("0.9750"),
                    horizon_days=1,
                    var_value=val,
                    n_factors=1,
                    n_observations=41,
                    window_start=date(2026, 1, 1),
                    window_end=s,
                )
            )
        mv0 = mv0 + pnl
    session.add(
        PortfolioReturnResult(
            tenant_id=tenant,
            calculation_run_id=ret_run,
            input_snapshot_id=ret_snap,
            model_version_id=new_uuid(),
            portfolio_id=pf,
            metric_type="TWR_LINKED",
            period_start=start,
            period_end=start + timedelta(days=n_pairs),
            begin_mv=D("70000.000000"),
            end_mv=mv0,
            net_external_flow=D("0.000000"),
            return_value=D("0.000000000000"),
            n_flows=0,
            n_periods=n_pairs,
            base_currency="USD",
        )
    )
    session.flush()
    return tenant, ret_run, var_runs, es_runs


def test_es_backtest_end_to_end_off_domain_no_verdict(session) -> None:
    """3 pairs at 0.9750 with ONE breach: Z rows + ES_PAIR_COUNT persist; NO verdict off the
    n_pairs=250 domain (the T-dependence HIGH); Z1 present (one exception); es_value echoed."""
    from irp_shared.risk.bootstrap import register_es_backtest_model
    from irp_shared.risk.es_backtest_service import run_es_backtest
    from irp_shared.risk.events import EsBacktestActor

    tenant, ret_run, var_runs, es_runs = _mint_es_substrate(session, 3, breach_at={1})
    mv = register_es_backtest_model(
        session, tenant_id=tenant, actor_id="a", code_version="bt3-v1"
    ).id
    result = run_es_backtest(
        session,
        acting_tenant=tenant,
        actor=EsBacktestActor(actor_id="a"),
        code_version="bt3-v1",
        environment_id="ci",
        model_version_id=mv,
        portfolio_return_run_id=ret_run,
        var_run_ids=var_runs,
        es_run_ids=es_runs,
    )
    assert result.status == "COMPLETED"
    rows = {}
    for r in result.rows:
        rows.setdefault(r.metric_type, []).append(r)
    assert len(rows["ES_EXCEPTION_INDICATOR"]) == 3
    breached = [r for r in rows["ES_EXCEPTION_INDICATOR"] if r.metric_value == Decimal("1.000000")]
    assert len(breached) == 1 and breached[0].es_value == Decimal("420.000000")
    (count_row,) = rows["ES_PAIR_COUNT"]
    assert count_row.metric_value == Decimal("3.000000") and count_row.n_exceptions == 1
    (z2_row,) = rows["AS_Z2"]
    # X=-450, ES=420, T=3, a=0.025: Z2 = (-450/420)/(0.075) + 1 = -13.285714...
    assert z2_row.metric_value == Decimal("-13.285714")
    assert z2_row.test_decision is None  # OFF-DOMAIN: no verdict, mechanically derivable
    (z1_row,) = rows["AS_Z1"]
    assert z1_row.metric_value == Decimal("-0.071429")  # -450/420 + 1
    assert z1_row.test_decision is None
    assert z2_row.var_metric_type == "ES_HISTORICAL"


def test_es_backtest_end_to_end_on_domain_verdict(session) -> None:
    """250 pairs at 0.9750, zero breaches: the FULL domain => the Z2 verdict fires on the
    stored value (+1.0 => FAIL_TO_REJECT); Z1 absent (zero exceptions) — never zero-coerced."""
    from irp_shared.risk.bootstrap import register_es_backtest_model
    from irp_shared.risk.es_backtest_service import run_es_backtest
    from irp_shared.risk.events import EsBacktestActor

    tenant, ret_run, var_runs, es_runs = _mint_es_substrate(session, 250)
    mv = register_es_backtest_model(
        session, tenant_id=tenant, actor_id="a", code_version="bt3-v1"
    ).id
    result = run_es_backtest(
        session,
        acting_tenant=tenant,
        actor=EsBacktestActor(actor_id="a"),
        code_version="bt3-v1",
        environment_id="ci",
        model_version_id=mv,
        portfolio_return_run_id=ret_run,
        var_run_ids=var_runs,
        es_run_ids=es_runs,
    )
    assert result.status == "COMPLETED"
    rows = {r.metric_type: r for r in result.rows if r.metric_type != "ES_EXCEPTION_INDICATOR"}
    assert rows["ES_PAIR_COUNT"].metric_value == Decimal("250.000000")
    z2 = rows["AS_Z2"]
    assert z2.metric_value == Decimal("1.000000")  # zero breaches => Z2 = +1 exactly
    assert z2.test_decision == "FAIL_TO_REJECT"  # ON-DOMAIN: the verdict exists
    assert "AS_Z1" not in rows  # UNDEFINED at zero exceptions — no row, never 0


# ----------------------------------------------------------------- the v2 gate (tri-state parse)


def test_var_backtest_v2_registration_and_tri_state_parse(session) -> None:
    """The v2 registers with the stamped convention; the parse is the COUNTING tri-state:
    v1 => None (grandfather); the v2 => the Markov literal; TWO independence= rows => refused
    (ambiguity never collapses into the grandfather — the two-rows-refusal golden)."""
    from irp_shared.model.models import ModelAssumption
    from irp_shared.model.service import WrongModelVersionError
    from irp_shared.risk.bootstrap import (
        VAR_BACKTEST_CHRISTOFFERSEN_CONVENTION,
        declared_var_backtest_independence,
        register_var_backtest_christoffersen_model,
        register_var_backtest_model,
    )

    tenant = "11111111-1111-1111-1111-111111111111"
    v1 = register_var_backtest_model(session, tenant_id=tenant, actor_id="a", code_version="c1")
    assert declared_var_backtest_independence(session, v1) is None
    v2 = register_var_backtest_christoffersen_model(
        session, tenant_id=tenant, actor_id="a", code_version="c1"
    )
    assert declared_var_backtest_independence(session, v2) == VAR_BACKTEST_CHRISTOFFERSEN_CONVENTION
    # The two-rows-refusal golden: a second independence= row makes the identity AMBIGUOUS.
    session.add(
        ModelAssumption(
            tenant_id=tenant,
            model_version_id=v2.id,
            assumption_text="independence=CHRISTOFFERSEN_MARKOV",
        )
    )
    session.flush()
    with pytest.raises(WrongModelVersionError):
        declared_var_backtest_independence(session, v2)


def test_es_backtest_registrar_refusals(session) -> None:
    from irp_shared.risk.bootstrap import register_es_backtest_model

    tenant = "11111111-1111-1111-1111-111111111111"
    with pytest.raises(ValueError):
        register_es_backtest_model(
            session, tenant_id=tenant, actor_id="a", code_version="c1", significance="0.10"
        )
