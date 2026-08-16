"""STRUCT-2 (REQ-PPM-007) census 2 — MECHANICAL aggregation-site discovery.

The row: "Every place in the code that aggregates must look up the contract first. This is
checked by a census of aggregation sites, and a site with no lookup FAILS." The verifier killed
the marker-only design (a marker census sees only sites that already consult) and the hand-list
design (the inventory freezes at plan time). This census DISCOVERS the sites from the AST — every
``sum(...)`` call, every ``d[k] = d.get(k, ...) + ...`` accumulation, every ``+=`` — across all of
``irp_shared``, and classifies each against a PINNED taxonomy:

- ``CROSS_FAMILY_CONSUMPTION`` — the site sums ANOTHER family's governed result rows (the
  census's true subject). Its guard module MUST contain an ``assert_aggregatable`` lookup, and
  the lookup's result governs (the result-obedience tests + the M-S2 mutants prove firing).
- ``INTRA_FAMILY_COMPUTE`` — a family's own registered model math (quadratic forms, Dietz
  denominators, likelihoods, its own bucket re-sums). The contract DECLARES what the family
  emits; its internal math is governed by the model registration, not by an operator lookup.
- ``TIME_SERIES_STATISTIC`` — a consuming family computes a statistic (mean/stdev/linking) over
  its input SERIES as its registered methodology (Sharpe, rolling risk, benchmark-relative,
  TWR linking). A statistic over a series is not a cross-sectional rollup; the aggregation
  contract governs rollups. Stated here deliberately, not smuggled.
- ``CAPTURED_INPUT`` — sums over captured inputs (transaction flows, benchmark weights,
  commitments, reference series bookkeeping), which bind no snapshot/run/model triple.
- ``NON_MEASURE`` — counters, ``record_version += 1`` bumps, id ticks, audit-chain walks,
  demo/synthetic seeding arithmetic.

EXACT set equality with counts: a NEW aggregation construct anywhere in ``irp_shared`` fails
this census until someone classifies it — deliberately, in this file, with the taxonomy's teeth.
"""

from __future__ import annotations

import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src" / "irp_shared"

C = "CROSS_FAMILY_CONSUMPTION"
I = "INTRA_FAMILY_COMPUTE"  # noqa: E741 - a taxonomy code, used in one table below
T = "TIME_SERIES_STATISTIC"
P = "CAPTURED_INPUT"
N = "NON_MEASURE"

#: (module, enclosing function, construct kind) -> (count, taxonomy class).
#: For CROSS entries the guard module (where the assert_aggregatable lookup lives) is either the
#: site's own module or, for pure kernels, the family SERVICE that feeds them (kernels stay
#: import-light; the binder consults the contract before invoking them).
_ALLOWLIST: dict[tuple[str, str, str], tuple[int, str]] = {
    # --- cross-family consumption: the contract lookup governs these ---
    ("irp_shared.concentration.kernel", "decompose", "sum-call"): (4, C),
    ("irp_shared.liquidity.kernel", "compute_liquidity", "dict-get-add"): (1, C),
    ("irp_shared.liquidity.kernel", "compute_liquidity", "sum-call"): (3, C),
    ("irp_shared.perf.return_service", "_adjudicate_pins", "dict-get-add"): (1, C),
    # The STRUCT-2 summed read itself — the census caught it the day it was written, which is
    # the discovery half working; its own module carries the lookup.
    ("irp_shared.exposure.service", "summed_latest_exposure", "sum-call"): (1, C),
    ("irp_shared.risk.var_service", "run_var", "dict-get-add"): (1, C),
    ("irp_shared.risk.var_service", "run_var_unified", "dict-get-add"): (1, C),
    ("irp_shared.risk.var_hs_service", "_adjudicate_pins", "dict-get-add"): (1, C),
    ("irp_shared.risk.scenario_service", "_adjudicate_pins", "augassign-add"): (1, C),
    ("irp_shared.risk.active_risk_service", "_adjudicate_pins", "dict-get-add"): (2, C),
    # --- a family's own registered model math ---
    ("irp_shared.concentration.kernel", "compute_dimension", "sum-call"): (4, I),
    ("irp_shared.concentration.service", "_dimension_rows", "sum-call"): (4, I),
    ("irp_shared.perf.return_kernel", "compute_dietz_period", "augassign-add"): (1, I),
    ("irp_shared.perf.return_kernel", "dietz_denominator", "augassign-add"): (1, I),
    ("irp_shared.perf.return_service", "_compute", "sum-call"): (2, I),
    ("irp_shared.perf.desmoothing_kernel", "lag_autocorrelation", "sum-call"): (3, I),
    ("irp_shared.risk.active_risk_kernel", "compute_tracking_error", "augassign-add"): (1, I),
    ("irp_shared.risk.covariance_kernel", "estimate_covariance", "sum-call"): (2, I),
    ("irp_shared.risk.es_backtest_kernel", "as_z_statistics", "augassign-add"): (2, I),
    ("irp_shared.risk.private_factor_kernel", "member_pure_private_return", "augassign-add"): (
        1,
        I,
    ),
    ("irp_shared.risk.private_factor_kernel", "pool_equal_weight", "augassign-add"): (1, I),
    ("irp_shared.risk.private_factor_kernel", "sample_stdev", "sum-call"): (2, I),
    ("irp_shared.risk.proxy_weight_kernel", "estimate_ols", "sum-call"): (8, I),
    ("irp_shared.risk.residual_shrinkage_kernel", "shrink_residual_variances", "sum-call"): (3, I),
    ("irp_shared.risk.service", "_build_rows", "augassign-add"): (1, I),
    ("irp_shared.risk.var_backtest_kernel", "christoffersen_lr_ind", "augassign-add"): (4, I),
    ("irp_shared.risk.var_backtest_kernel", "kupiec_lr", "augassign-add"): (3, I),
    ("irp_shared.risk.var_backtest_kernel", "markov_counts", "augassign-add"): (1, I),
    ("irp_shared.risk.var_backtest_service", "_compute", "augassign-add"): (1, I),
    ("irp_shared.risk.var_hs_kernel", "_sorted_scenario_pnls", "augassign-add"): (1, I),
    ("irp_shared.risk.var_hs_kernel", "compute_historical_es", "sum-call"): (1, I),
    ("irp_shared.risk.var_kernel", "compute_parametric_var", "augassign-add"): (1, I),
    ("irp_shared.risk.var_kernel", "compute_parametric_var", "dict-get-add"): (1, I),
    ("irp_shared.risk.var_total_kernel", "total_var_residual", "augassign-add"): (1, I),
    ("irp_shared.risk.var_unified_kernel", "private_block_variance", "augassign-add"): (1, I),
    ("irp_shared.risk.scenario_service", "_compute", "augassign-add"): (1, I),
    # --- statistics over an input SERIES (the consuming family's registered methodology) ---
    ("irp_shared.perf.stats_kernel", "mean_and_stdev_unquantized", "sum-call"): (2, T),
    ("irp_shared.perf.stats_kernel", "mean_return", "sum-call"): (1, T),
    ("irp_shared.perf.benchmark_relative_service", "_adjudicate_pins", "sum-call"): (1, T),
    ("irp_shared.perf.benchmark_relative_service", "_compute", "sum-call"): (1, T),
    # --- sums over captured inputs (no snapshot/run/model binding on the inputs) ---
    ("irp_shared.perf.return_service", "_adjudicate_pins", "sum-call"): (1, P),
    ("irp_shared.risk.active_risk_service", "_adjudicate_pins", "sum-call"): (2, P),
    ("irp_shared.risk.var_service", "_build_p_vector", "dict-get-add"): (1, P),
    ("irp_shared.pacing.service", "_adjudicate_anchor", "augassign-add"): (2, P),
    ("irp_shared.marketdata.benchmark_series", "_current_open", "augassign-add"): (1, P),
    ("irp_shared.marketdata.benchmark_series", "_reconstruct", "augassign-add"): (1, P),
    # --- counters, version bumps, chains, demo/synthetic bookkeeping ---
    ("irp_shared.audit.service", "verify_chain", "augassign-add"): (1, N),
    ("irp_shared.demo.bt3_stage7", "run_demo_bt3_stage7", "augassign-add"): (1, N),
    ("irp_shared.demo.campaign", "_assign_tiers", "augassign-add"): (1, N),
    ("irp_shared.demo.campaign", "_file_records", "augassign-add"): (2, N),
    ("irp_shared.demo.campaign", "_seed_book", "augassign-add"): (2, N),
    ("irp_shared.demo.con1_stage19", "_census_and_teardown_entitlements", "augassign-add"): (1, N),
    ("irp_shared.demo.ds2_stage6", "run_demo_ds2_stage6", "augassign-add"): (1, N),
    ("irp_shared.demo.hg1_private", "_mark_series", "sum-call"): (1, N),
    ("irp_shared.demo.hg1_private", "run_demo_hg1_private", "augassign-add"): (2, N),
    ("irp_shared.demo.lim2_stage20", "_teardown_roles", "augassign-add"): (1, N),
    ("irp_shared.demo.lim2_stage20", "run_demo_lim2_stage20", "augassign-add"): (4, N),
    ("irp_shared.demo.multifamily", "_estimate_and_promote", "augassign-add"): (1, N),
    ("irp_shared.demo.multifamily", "_file_records", "augassign-add"): (1, N),
    ("irp_shared.demo.multifamily", "_mark_series", "sum-call"): (1, N),
    ("irp_shared.demo.multifamily", "_seed_sleeve", "augassign-add"): (1, N),
    ("irp_shared.demo.ops_stage14", "_grant_auditor_reads", "augassign-add"): (1, N),
    ("irp_shared.demo.ops_stage14", "run_demo_ops_stage14", "augassign-add"): (1, N),
    ("irp_shared.demo.ppf1_stage11", "run_demo_ppf1_stage11", "augassign-add"): (1, N),
    ("irp_shared.demo.ref1_stage18", "run_demo_ref1_stage18", "augassign-add"): (6, N),
    ("irp_shared.demo.rm1_stage16", "run_demo_rm1_stage16", "sum-call"): (1, N),
    ("irp_shared.demo.rs1_stage5", "run_demo_rs1_stage5", "augassign-add"): (2, N),
    ("irp_shared.demo.sr1_stage17", "run_demo_sr1_stage17", "sum-call"): (1, N),
    ("irp_shared.dq.rules", "evaluate_not_null", "sum-call"): (1, N),
    ("irp_shared.dq.service", "update_dq_rule", "augassign-add"): (1, N),
    ("irp_shared.ingestion.service", "stage_upload", "augassign-add"): (1, N),
    ("irp_shared.limit.service", "approve_limit", "augassign-add"): (1, N),
    ("irp_shared.limit.service", "update_limit", "augassign-add"): (1, N),
    ("irp_shared.lineage.service", "update_data_source", "augassign-add"): (1, N),
    ("irp_shared.liquidity.service", "_parse_pins", "augassign-add"): (1, N),
    ("irp_shared.marketdata.benchmark_rates", "refresh_benchmark_rates", "augassign-add"): (1, N),
    ("irp_shared.portfolio.portfolio", "update_portfolio", "augassign-add"): (1, N),
    ("irp_shared.reference.calendar", "refresh_calendar_holidays", "augassign-add"): (1, N),
    ("irp_shared.reference.calendar", "update_calendar", "augassign-add"): (1, N),
    (
        "irp_shared.reference.corporate_action",
        "transition_corporate_action_status",
        "augassign-add",
    ): (1, N),
    ("irp_shared.reference.corporate_action", "update_corporate_action", "augassign-add"): (1, N),
    ("irp_shared.reference.counterparty", "update_counterparty", "augassign-add"): (1, N),
    ("irp_shared.reference.currency", "update_currency", "augassign-add"): (1, N),
    ("irp_shared.reference.identifier", "update_identifier_xref", "augassign-add"): (1, N),
    ("irp_shared.reference.instrument", "update_instrument", "augassign-add"): (1, N),
    ("irp_shared.reference.issuer", "update_issuer", "augassign-add"): (1, N),
    ("irp_shared.reference.legal_entity", "update_legal_entity", "augassign-add"): (1, N),
    ("irp_shared.reference.rating", "update_rating_scale", "augassign-add"): (1, N),
    ("irp_shared.reproduction.service", "alarm_channel_health", "augassign-add"): (3, N),
    ("irp_shared.reproduction.service", "alarm_channel_health", "sum-call"): (2, N),
    ("irp_shared.reproduction.service", "compare_rows", "augassign-add"): (4, N),
    ("irp_shared.risk.bootstrap", "_hs_window_floor", "augassign-add"): (1, N),
    ("irp_shared.risk.scenario", "update_scenario_definition", "augassign-add"): (1, N),
    ("irp_shared.scheduling.service", "update_schedule", "augassign-add"): (1, N),
    ("irp_shared.synthetic.ids", "tick", "augassign-add"): (1, N),
    ("irp_shared.synthetic.scale", "_month_end_offsets", "augassign-add"): (1, N),
    ("irp_shared.synthetic.scale", "build_perf_book", "augassign-add"): (7, N),
    ("irp_shared.tenancy.service", "onboard_tenant", "augassign-add"): (1, N),
    # --- the extended patterns' hits (review folds: SQL + plain-assign + all three trees).
    # The sql-text-agg matches below are docstring PROSE ("sum of pinned weights") — the pattern
    # deliberately over-captures so a REAL raw-SQL aggregate cannot hide; a prose match costs one
    # allowlist line, a missed SUM() would cost the census its subject.
    ("irp_shared.demo.dossiers", "<module>", "sql-text-agg"): (2, N),
    ("irp_shared.risk.active_risk_service", "<module>", "sql-text-agg"): (1, N),
    ("irp_shared.risk.active_risk_service", "_assert_partitioning_exposure_run", "sql-text-agg"): (
        1,
        N,
    ),
    ("irp_shared.risk.bootstrap", "<module>", "sql-text-agg"): (4, N),
    ("irp_shared.marketdata.benchmark", "update_benchmark", "plain-assign-add"): (1, N),
    ("irp_shared.marketdata.factor", "update_factor", "plain-assign-add"): (1, N),
}

#: CROSS site -> the module whose AST must carry the assert_aggregatable lookup. Pure kernels
#: are guarded by the family service that feeds them (the binder consults before invoking).
_GUARD_MODULE: dict[str, str] = {
    "irp_shared.concentration.kernel": "irp_shared.concentration.service",
    "irp_shared.liquidity.kernel": "irp_shared.liquidity.service",
}


def _scan_file(mod: str, tree: ast.AST, sites: dict[tuple[str, str, str], int]) -> None:
    stack = ["<module>"]

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):  # noqa: ANN001, ANN202
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def _hit(self, kind: str) -> None:
            key = (mod, stack[-1], kind)
            sites[key] = sites.get(key, 0) + 1

        def visit_Call(self, node):  # noqa: ANN001, ANN202
            if isinstance(node.func, ast.Name) and node.func.id in ("sum", "fsum"):
                self._hit("sum-call")
            # SQL-level aggregation (review fold: REQ-PPM-007 names SQL read views explicitly):
            # sqlalchemy func.sum/func.avg — invisible to the Python-construct patterns.
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in ("sum", "avg")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "func"
            ):
                self._hit("sqlfunc-agg")
            self.generic_visit(node)

        def visit_Constant(self, node):  # noqa: ANN001, ANN202
            # Raw-SQL aggregates inside string literals (text() queries).
            if isinstance(node.value, str) and (
                "SUM(" in node.value.upper() or "AVG(" in node.value.upper()
            ):
                self._hit("sql-text-agg")
            self.generic_visit(node)

        def visit_Assign(self, node):  # noqa: ANN001, ANN202
            v = node.value
            if isinstance(v, ast.BinOp) and isinstance(v.op, ast.Add):
                if (
                    isinstance(v.left, ast.Call)
                    and isinstance(v.left.func, ast.Attribute)
                    and v.left.func.attr == "get"
                ):
                    self._hit("dict-get-add")
                elif len(node.targets) == 1 and ast.unparse(node.targets[0]) == ast.unparse(v.left):
                    # x = x + y / x[k] = x[k] + y — the AugAssign-evasion shape (review fold).
                    self._hit("plain-assign-add")
            self.generic_visit(node)

        def visit_AugAssign(self, node):  # noqa: ANN001, ANN202
            if isinstance(node.op, ast.Add):
                self._hit("augassign-add")
            self.generic_visit(node)

    V().visit(tree)


_TREES = (
    _ROOT,
    _ROOT.parents[2] / "apps" / "backend" / "src" / "irp_backend",
    _ROOT.parents[2] / "apps" / "worker" / "src" / "irp_worker",
)


def _discover() -> dict[tuple[str, str, str], int]:
    sites: dict[tuple[str, str, str], int] = {}
    for root in _TREES:
        for py in sorted(root.rglob("*.py")):
            mod = str(py).replace("/", ".")
            for marker in ("irp_shared", "irp_backend", "irp_worker"):
                i = mod.find(marker)
                if i >= 0:
                    mod = mod[i:-3]
                    break
            _scan_file(mod, ast.parse(py.read_text()), sites)
    return sites


def _count_assert_aggregatable_calls(mod: str) -> int:
    py = _ROOT.parent / (mod.replace(".", "/") + ".py")
    tree = ast.parse(py.read_text())
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            if name in ("assert_aggregatable", "_assert_aggregatable"):
                n += 1
    return n


#: guard module -> the EXACT number of contract lookups it must carry (review fold: the
#: module-level presence check let one of var_service's TWO sites vanish with every gate green;
#: an exact count fails on any deletion).
_GUARD_CALL_COUNTS: dict[str, int] = {
    "irp_shared.concentration.service": 1,
    "irp_shared.liquidity.service": 1,
    "irp_shared.perf.return_service": 1,
    "irp_shared.exposure.service": 1,
    "irp_shared.risk.var_service": 2,
    "irp_shared.risk.var_hs_service": 1,
    "irp_shared.risk.scenario_service": 1,
    "irp_shared.risk.active_risk_service": 1,
}


def test_census2_every_aggregation_site_is_classified() -> None:
    """A new sum/accumulation ANYWHERE in irp_shared fails until classified here — with counts,
    so a construct added inside an already-listed function fails too."""
    discovered = _discover()
    allow = {k: n for k, (n, _) in _ALLOWLIST.items()}
    missing = {k: v for k, v in discovered.items() if k not in allow}
    gone = {k: v for k, v in allow.items() if k not in discovered}
    drifted = {
        k: (allow[k], discovered[k])
        for k in set(allow) & set(discovered)
        if allow[k] != discovered[k]
    }
    assert not missing and not gone and not drifted, (
        f"aggregation-site census drift — unclassified: {sorted(missing)}; vanished: "
        f"{sorted(gone)}; count-changed: {sorted(drifted.items())}"
    )


def test_census2_every_cross_family_site_is_guarded_by_a_contract_lookup() -> None:
    """REQ-PPM-007: a consumption site with no contract lookup FAILS. The lookup count is pinned
    EXACTLY per guard module — deleting ONE of two lookups in a module fails here (the review's
    granularity fold), and every CROSS site maps into a counted guard module."""
    for mod, expected in _GUARD_CALL_COUNTS.items():
        actual = _count_assert_aggregatable_calls(mod)
        assert actual == expected, (mod, expected, actual)
    for (mod, func, kind), (_, cls) in _ALLOWLIST.items():
        if cls != C:
            continue
        guard = _GUARD_MODULE.get(mod, mod)
        assert (
            guard in _GUARD_CALL_COUNTS
        ), f"CROSS site {mod}::{func}::{kind} maps to guard {guard} with no pinned lookup count"


def test_census2_the_guard_check_itself_can_fail() -> None:
    """The census's own positive control (P18): a module KNOWN to carry no lookup counts zero —
    the counter is not vacuously positive."""
    assert _count_assert_aggregatable_calls("irp_shared.audit.service") == 0
    assert _count_assert_aggregatable_calls("irp_shared.concentration.service") == 1
