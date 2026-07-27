"""RM-1 binder + end-to-end governed run (ENT-064, the 21st governed number).

Drives a REAL PM-1 return run through the rolling-risk binder over a purpose-built month-end book,
so the pin -> relink -> window -> emit chain is exercised end to end rather than stubbed. The
refusal tests then attack the binder's pre-create gate, and the suppression tests attack the
encoding that keeps "not computable" distinguishable from a legitimate zero.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.perf.bootstrap import (
    ROLLING_RISK_MODEL_CODE,
    ROLLING_RISK_WINDOWS,
    register_rolling_risk_model,
)
from irp_shared.perf.events import RUN_TYPE_ROLLING_RISK, RollingRiskActor
from irp_shared.perf.models import (
    ANNUALIZATION_GEOMETRIC_12,
    ANNUALIZATION_NONE,
    ANNUALIZATION_SQRT_12,
    METRIC_TYPE_DIETZ_PERIOD,
    METRIC_TYPE_MAX_DRAWDOWN,
    METRIC_TYPE_ROLLING_RETURN,
    METRIC_TYPE_ROLLING_RETURN_ANN,
    METRIC_TYPE_ROLLING_VOLATILITY,
    METRIC_TYPE_ROLLING_VOLATILITY_ANN,
    METRIC_TYPE_TWR_LINKED,
    PortfolioReturnResult,
)
from irp_shared.perf.rolling_kernel import last_weekday_of_month
from irp_shared.perf.rolling_service import (
    RollingRiskInputError,
    RollingRiskNotVisible,
    RollingRiskRunNotVisible,
    _adjudicate_pins,
    latest_rolling_risk,
    list_rolling_risk_rows,
    list_rolling_risks,
    resolve_rolling_risk,
    resolve_rolling_risk_run,
    run_rolling_risk,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.snapshot import build_rolling_risk_snapshot
from irp_shared.snapshot.events import SnapshotActor

_ACTOR = RollingRiskActor(actor_id="analyst-1")
_SNAP_ACTOR = SnapshotActor(actor_id="analyst-1")
_CODE_VERSION = "rm1-test"


def _month_ends(count: int, *, start_year: int = 2024, start_month: int = 1) -> list[date]:
    """``count`` consecutive month-end boundaries under the business-day allowance."""
    out: list[date] = []
    year, month = start_year, start_month
    for _ in range(count):
        out.append(last_weekday_of_month(year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _seed_return_run(
    session: Session,
    tenant: str,
    *,
    returns: list[str],
    boundaries: list[date] | None = None,
) -> tuple[CalculationRun, str]:
    """A COMPLETED PM-1 run with one DIETZ_PERIOD row per sub-period plus its TWR_LINKED summary.

    Hand-seeded on purpose: RM-1 consumes PM-1's OUTPUT, and driving PM-1 itself here would test
    PM-1, not this binder. The rows are shaped exactly as PM-1 writes them so the pin serializer
    (which RM-1 reuses verbatim) produces real content.
    """
    portfolio = create_portfolio(
        session,
        tenant_id=tenant,
        code=f"pf-{uuid.uuid4().hex[:8]}",
        name="Book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    run = CalculationRun(
        tenant_id=tenant,
        run_type="PORTFOLIO_RETURN",
        status="COMPLETED",
        initiated_by="seed",
        code_version="pm1",
        environment_id="test",
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(run)
    session.flush()

    bounds = boundaries if boundaries is not None else _month_ends(len(returns) + 1)
    assert len(bounds) == len(returns) + 1, "one more boundary than sub-periods"

    def _row(metric: str, start: date, end: date, value: str, n_periods: int) -> None:
        session.add(
            PortfolioReturnResult(
                tenant_id=tenant,
                calculation_run_id=run.run_id,
                input_snapshot_id=str(uuid.uuid4()),
                model_version_id=str(uuid.uuid4()),
                portfolio_id=str(portfolio.id),
                metric_type=metric,
                period_start=start,
                period_end=end,
                begin_mv=Decimal("1000000.000000"),
                end_mv=Decimal("1000000.000000"),
                net_external_flow=Decimal("0.000000"),
                return_value=Decimal(value),
                n_flows=0,
                n_periods=n_periods,
                base_currency="USD",
            )
        )

    for i, value in enumerate(returns):
        _row(METRIC_TYPE_DIETZ_PERIOD, bounds[i], bounds[i + 1], value, 1)
    _row(METRIC_TYPE_TWR_LINKED, bounds[0], bounds[-1], "0.0", len(returns))
    session.flush()
    return run, str(portfolio.id)


def _run_rolling(
    session: Session,
    tenant: str,
    *,
    returns: list[str],
    boundaries: list[date] | None = None,
    windows: tuple[int, ...] = ROLLING_RISK_WINDOWS,
):  # noqa: ANN202
    run, _pf = _seed_return_run(session, tenant, returns=returns, boundaries=boundaries)
    version = register_rolling_risk_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(
        session, acting_tenant=tenant, actor=_SNAP_ACTOR, portfolio_return_run_id=run.run_id
    )
    return run_rolling_risk(
        session,
        acting_tenant=tenant,
        actor=_ACTOR,
        code_version=_CODE_VERSION,
        environment_id="test",
        model_version_id=str(version.id),
        window_months=windows,
        snapshot_id=snapshot.id,
    )


# --- the end-to-end governed run ---------------------------------------------------------------


def test_a_governed_rolling_risk_run_completes_and_emits_every_metric(session: Session) -> None:
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 14, windows=(12,))
    assert result.status == "COMPLETED"
    assert result.run.run_type == RUN_TYPE_ROLLING_RISK

    emitted = {r.metric_type for r in result.rows}
    assert emitted == {
        METRIC_TYPE_ROLLING_RETURN,
        METRIC_TYPE_ROLLING_VOLATILITY,
        METRIC_TYPE_ROLLING_VOLATILITY_ANN,
        METRIC_TYPE_MAX_DRAWDOWN,
    }
    # 14 months, a 12-month window => 3 complete windows, 4 metrics each.
    assert len(result.rows) == 12
    assert all(r.window_months == 12 for r in result.rows)
    assert all(r.n_observations == 12 for r in result.rows)
    assert all(r.sampling_frequency == "MONTHLY" for r in result.rows)


def test_every_row_is_run_snapshot_and_model_bound(session: Session) -> None:
    """The AD-014 / CTRL-003 invariant at the row level — not merely at the run."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 13, windows=(12,))
    for row in result.rows:
        assert row.calculation_run_id == result.run.run_id
        assert row.input_snapshot_id
        assert row.model_version_id
        assert row.portfolio_return_run_id  # the ONE upstream run, a hard FK


def test_the_twelve_month_window_omits_the_definitionally_redundant_annualized_row(
    session: Session,
) -> None:
    """OD-RM-1-G: at W = 12 the geometric exponent is exactly 1, so an annualized return row would
    be identical to the cumulative one FOREVER. Two always-equal governed numbers is worse than
    one."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 13, windows=(12,))
    assert METRIC_TYPE_ROLLING_RETURN_ANN not in {r.metric_type for r in result.rows}


def test_a_thirty_six_month_window_does_emit_the_annualized_return(session: Session) -> None:
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 36, windows=(36,))
    annualized = [r for r in result.rows if r.metric_type == METRIC_TYPE_ROLLING_RETURN_ANN]
    assert annualized
    assert all(r.annualization_basis == ANNUALIZATION_GEOMETRIC_12 for r in annualized)


def test_the_annualization_basis_is_stamped_on_every_row(session: Session) -> None:
    """The read surface's disambiguation key is (metric_type, window_months, annualization_basis) —
    the family emits the same statistic under two transforms, so a NULL or wrong basis would make
    two governed numbers indistinguishable to a consumer."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 13, windows=(12,))
    expected = {
        METRIC_TYPE_ROLLING_RETURN: ANNUALIZATION_NONE,
        METRIC_TYPE_ROLLING_VOLATILITY: ANNUALIZATION_NONE,
        METRIC_TYPE_ROLLING_VOLATILITY_ANN: ANNUALIZATION_SQRT_12,
        METRIC_TYPE_MAX_DRAWDOWN: ANNUALIZATION_NONE,
    }
    for row in result.rows:
        assert row.annualization_basis == expected[row.metric_type], row.metric_type


# --- suppression: the encoding that keeps zero honest ------------------------------------------


def test_an_unfillable_window_is_SUPPRESSED_with_a_reason_not_a_stuffed_zero(
    session: Session,
) -> None:
    """OD-RM-1-I. A 36-month window on a 13-month book emits governed rows carrying NULL + an
    explicit flag + a reason. A stuffed 0.0 would be INDISTINGUISHABLE from a legitimate zero (a
    monotonically rising window really does have MDD = 0), and a naive consumer would read "not
    computable" as "no drawdown, excellent"."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 13, windows=(12, 36))
    suppressed = [r for r in result.rows if r.window_months == 36]
    assert suppressed, "the unfillable window emitted nothing at all"
    # EVERY metric a computable 36-month window would emit must be disclosed — including the
    # annualized return. Omitting it left that key with no row at all: an UNDISCLOSED absence,
    # which is exactly the state the suppression design exists to prevent.
    assert {r.metric_type for r in suppressed} == {
        METRIC_TYPE_ROLLING_RETURN,
        METRIC_TYPE_ROLLING_RETURN_ANN,
        METRIC_TYPE_ROLLING_VOLATILITY,
        METRIC_TYPE_ROLLING_VOLATILITY_ANN,
        METRIC_TYPE_MAX_DRAWDOWN,
    }
    for row in suppressed:
        assert row.suppressed is True
        assert row.metric_value is None
        assert row.suppression_reason is not None
        assert "13 monthly observations" in row.suppression_reason
        assert "36-month window" in row.suppression_reason


def test_suppression_is_one_row_per_metric_and_window_not_per_evaluation_point(
    session: Session,
) -> None:
    """V2-B1: per-evaluation-point suppression would COLLIDE on the four-column grain at n=12 (the
    same (run, metric, window, period_start) twice), i.e. an IntegrityError at flush."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 13, windows=(12, 36))
    suppressed = [r for r in result.rows if r.window_months == 36]
    assert len(suppressed) == 5  # one per metric, once
    assert len({r.metric_type for r in suppressed}) == 5


def test_an_emitted_row_carries_a_value_and_NO_reason(session: Session) -> None:
    """The other side of the DB CHECK: suppressed and emitted are mutually exclusive states."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 13, windows=(12, 36))
    for row in (r for r in result.rows if r.window_months == 12):
        assert row.suppressed is False
        assert row.metric_value is not None
        assert row.suppression_reason is None


def test_a_legitimate_zero_drawdown_is_emitted_as_zero_not_suppressed(session: Session) -> None:
    """THE case the encoding exists for: a monotonically rising book has MDD = 0, and that must be
    a real emitted value — flagged NOT suppressed — so it can never be confused with "unknown"."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 13, windows=(12,))
    mdd = [r for r in result.rows if r.metric_type == METRIC_TYPE_MAX_DRAWDOWN]
    assert mdd
    assert all(r.metric_value == Decimal("0.000000000000") for r in mdd)
    assert all(r.suppressed is False for r in mdd)


# --- pre-create refusals ------------------------------------------------------------------------


def test_a_misaligned_month_grid_is_refused_pre_create(session: Session) -> None:
    """A partial trailing month: the binder must refuse BEFORE create_run, so ZERO run exists."""
    tenant = str(uuid.uuid4())
    bounds = _month_ends(13)
    # Strictly AFTER bounds[-2] (2024-12-31) so the ORDERING check cannot fire first — otherwise
    # this test would pass for the wrong reason and prove nothing about the month grid.
    bounds[-1] = date(2025, 1, 16)
    assert bounds[-1] > bounds[-2]
    before = session.query(CalculationRun).filter_by(run_type=RUN_TYPE_ROLLING_RISK).count()
    with pytest.raises(RollingRiskInputError, match="not a month end"):
        _run_rolling(session, tenant, returns=["0.01"] * 12, boundaries=bounds, windows=(12,))
    after = session.query(CalculationRun).filter_by(run_type=RUN_TYPE_ROLLING_RISK).count()
    assert after == before, "a refused input still minted a run"


def test_a_total_loss_month_is_refused_pre_create(session: Session) -> None:
    """PM-1 admits EMV = 0 -> exactly -1.0, which is ABSORBING and makes the drawdown ratio
    undefined. This is not the magnitude gate: -1 is well inside the envelope."""
    tenant = str(uuid.uuid4())
    returns = ["0.01"] * 6 + ["-1.0"] + ["0.01"] * 6
    with pytest.raises(RollingRiskInputError, match="at or below -100%"):
        _run_rolling(session, tenant, returns=returns, windows=(12,))


def test_a_snapshot_of_the_wrong_purpose_is_refused(session: Session) -> None:
    """The ENFORCED allow-list is not the only gate: the binder also checks that the snapshot it was
    handed is a ROLLING_RISK_INPUT, so a header built for another family cannot be consumed as if it
    were this one.

    The header is INSERTED with the foreign purpose rather than mutated — ``dataset_snapshot`` is
    append-only, so an UPDATE raises ``AppendOnlyViolation`` and would test the append-only guard
    instead of the purpose gate.
    """
    from irp_shared.snapshot.models import DatasetSnapshot

    tenant = str(uuid.uuid4())
    run, _pf = _seed_return_run(session, tenant, returns=["0.01"] * 12)
    version = register_rolling_risk_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    foreign = DatasetSnapshot(
        tenant_id=tenant,
        label="",
        purpose="ADHOC",
        as_of_valid_at=datetime(2026, 1, 1, tzinfo=UTC),
        as_of_known_at=datetime(2026, 1, 1, tzinfo=UTC),
        as_of_valuation_date=date(2026, 1, 1),
        binding_predicate_version="v1:test",
        component_count=0,
        manifest_hash="0" * 64,
    )
    session.add(foreign)
    session.flush()

    with pytest.raises(RollingRiskInputError, match="ROLLING_RISK_INPUT"):
        run_rolling_risk(
            session,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version=_CODE_VERSION,
            environment_id="test",
            model_version_id=str(version.id),
            window_months=(12,),
            snapshot_id=foreign.id,
        )
    assert run.run_id  # the upstream run exists; the refusal was about the snapshot, not the run


def test_missing_prerequisites_refuse_before_any_write(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run, _pf = _seed_return_run(session, tenant, returns=["0.01"] * 12)
    version = register_rolling_risk_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(
        session, acting_tenant=tenant, actor=_SNAP_ACTOR, portfolio_return_run_id=run.run_id
    )
    common = {
        "acting_tenant": tenant,
        "actor": _ACTOR,
        "environment_id": "test",
        "model_version_id": str(version.id),
        "window_months": (12,),
        "snapshot_id": snapshot.id,
    }
    with pytest.raises(RollingRiskInputError, match="code_version"):
        run_rolling_risk(session, code_version="", **common)
    with pytest.raises(RollingRiskInputError, match="at least one window"):
        run_rolling_risk(session, **{**common, "code_version": _CODE_VERSION, "window_months": ()})
    with pytest.raises(RollingRiskInputError, match="outside the registered domain"):
        run_rolling_risk(
            session, **{**common, "code_version": _CODE_VERSION, "window_months": (24,)}
        )
    with pytest.raises(RollingRiskInputError, match="outside the registered domain"):
        # Below 12 months: previously a COMMITTED FAILED run whose persisted reason was mislabelled
        # `magnitude-out-of-range:` for what is an ill-formed REQUEST, not extreme data.
        run_rolling_risk(
            session, **{**common, "code_version": _CODE_VERSION, "window_months": (6,)}
        )
    with pytest.raises(RollingRiskInputError, match="duplicate windows"):
        run_rolling_risk(
            session, **{**common, "code_version": _CODE_VERSION, "window_months": (12, 12)}
        )


def test_pins_spanning_two_runs_are_refused(session: Session) -> None:
    """A hand-minted snapshot could mix runs; the four-column grain would then carry rows whose
    provenance disagrees with the stamped portfolio_return_run_id."""
    raw = [
        {
            "metric_type": METRIC_TYPE_DIETZ_PERIOD,
            "calculation_run_id": str(uuid.uuid4()),
            "portfolio_id": "p1",
            "period_start": "2024-01-31",
            "period_end": "2024-02-29",
            "return_value": "0.01",
        },
        {
            "metric_type": METRIC_TYPE_DIETZ_PERIOD,
            "calculation_run_id": str(uuid.uuid4()),
            "portfolio_id": "p1",
            "period_start": "2024-02-29",
            "period_end": "2024-03-29",
            "return_value": "0.01",
        },
    ]
    with pytest.raises(RollingRiskInputError, match="span multiple runs"):
        _adjudicate_pins(raw)


def test_a_snapshot_with_no_return_pins_is_refused(session: Session) -> None:
    with pytest.raises(RollingRiskInputError, match="pins no PORTFOLIO_RETURN rows"):
        _adjudicate_pins([])


# --- the non-associativity pin ------------------------------------------------------------------


def test_the_twelve_month_rolling_return_need_not_equal_pm1s_linked_value(
    session: Session,
) -> None:
    """OD-RM-1-N (V1-M1). RM-1 links sub-periods -> month -> window; PM-1 links sub-periods -> span
    in ONE stage. ``link_periods`` quantizes to 12dp on return, so the two are NOT associative and
    can differ in the 12th decimal.

    Pinned in the NON-equality direction deliberately: P3-8's exact-linkage cross-check habit would
    make an equality assert here look natural, and it would be flaky BY CONSTRUCTION. This test
    exists so nobody later "fixes" the difference.
    """
    tenant = str(uuid.uuid4())
    # Returns chosen so the two-stage rounding actually bites somewhere in the chain.
    returns = ["0.0333333333" if i % 2 else "-0.0166666667" for i in range(12)]
    result = _run_rolling(session, tenant, returns=returns, windows=(12,))
    rolling = [r for r in result.rows if r.metric_type == METRIC_TYPE_ROLLING_RETURN]
    assert len(rolling) == 1
    # The assertion is that this is a GOVERNED value in range — NOT that it equals PM-1's link.
    assert rolling[0].metric_value is not None
    assert abs(rolling[0].metric_value) < Decimal("1E7")


def test_the_dietz_metric_constant_matches_pm1s(session: Session) -> None:
    """The binder keeps a fence-kept LOCAL copy of PM-1's metric string (perf modules do not reach
    across for a constant). Pin them equal so a rename cannot silently break the pin filter."""
    from irp_shared.perf.rolling_service import _DIETZ_PERIOD

    assert _DIETZ_PERIOD == METRIC_TYPE_DIETZ_PERIOD


def test_the_registered_window_domain_is_where_gips_2a12_is_enforced() -> None:
    """OD-RM-1-G: the parameter domain, not the kernel guard, is the enforcement point."""
    assert ROLLING_RISK_WINDOWS == (12, 36)
    assert all(w >= 12 for w in ROLLING_RISK_WINDOWS)
    assert ROLLING_RISK_MODEL_CODE == "perf.rolling_risk"


def test_methodology_doc_exists_and_has_required_sections() -> None:
    """The house guard: a registered model_version's `methodology_ref` must resolve to a real doc
    carrying the required sections. A registered pointer to a missing file is a governance gap, not
    a broken link."""
    import pathlib

    from irp_shared.perf.bootstrap import ROLLING_RISK_METHODOLOGY_REF

    root = pathlib.Path(__file__).resolve().parents[3]
    doc = root / ROLLING_RISK_METHODOLOGY_REF
    assert doc.is_file(), f"missing methodology doc: {ROLLING_RISK_METHODOLOGY_REF}"
    text = doc.read_text(encoding="utf-8")
    for section in (
        "Purpose & applicability",
        "Inputs & data policy",
        "Formulas & numerical standards",
        "Assumptions",
        "Validation / reproduction tests",
        "Governed-number contract",
        "Known limitations",
        "External benchmarks",
    ):
        assert section in text, f"missing methodology section: {section}"
    # Rule 6: every external source carries a grade, and the uncited bases stay uncited.
    for grade in ("[V]", "[C]", "[U]"):
        assert grade in text, f"missing source grade {grade}"
    assert (
        "k = 252 / 52 / 365" in text
    ), "the uncited annualization bases must stay declared-uncited"


def test_the_requirement_mints_are_present_in_backbone_AND_rtm() -> None:
    """D19: backbone + RTM in the SAME commit. A REQ minted in one and not the other is a
    traceability hole that no later slice would notice."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    backbone = (root / "02_requirements/requirements_backbone.md").read_text(encoding="utf-8")
    rtm = (root / "02_requirements/requirements_traceability_matrix.md").read_text(encoding="utf-8")
    for req in ("REQ-MKT-006", "REQ-PRF-003"):
        assert req in backbone, f"{req} missing from the backbone"
        assert req in rtm, f"{req} missing from the RTM"
    # OD-RM-1-L: PRF was in use from PM-1 onward but absent from the domain-code line.
    assert "BAI, PRF." in backbone


# --------------------------------------------------- the rule-7 read surface (shipped untested) ---
# The 4-finder review found all five read functions and all three endpoints with ZERO tests. Rule 7
# makes the reads part of the governed number's slice, so they shipped unproven.


def _seeded_run(session: Session, tenant: str, *, returns: list[str] | None = None):  # noqa: ANN202
    return _run_rolling(session, tenant, returns=returns or (["0.01"] * 13), windows=(12,))


def test_the_entity_read_filters_by_metric_type_and_window(session: Session) -> None:
    """The filters exist because this family emits ONE statistic under two transforms at two
    windows; unfiltered, a caller receives four metric types interleaved and reading that as a
    single series is the most likely way to misuse the surface."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["0.01"] * 13, windows=(12, 36))

    everything = list_rolling_risks(session, acting_tenant=tenant)
    assert len(everything) == len(result.rows)

    by_metric = list_rolling_risks(
        session, acting_tenant=tenant, metric_type=METRIC_TYPE_MAX_DRAWDOWN
    )
    assert by_metric
    assert {r.metric_type for r in by_metric} == {METRIC_TYPE_MAX_DRAWDOWN}

    by_window = list_rolling_risks(session, acting_tenant=tenant, window_months=36)
    assert by_window
    assert {r.window_months for r in by_window} == {36}
    assert all(r.suppressed for r in by_window)  # 36 cannot fill on a 13-month book


def test_an_unknown_or_foreign_portfolio_is_silently_empty(session: Session) -> None:
    """The entity-filter precedent: no existence oracle, and no 404 for a read that legitimately
    has nothing to return."""
    tenant = str(uuid.uuid4())
    _seeded_run(session, tenant)
    assert list_rolling_risks(session, acting_tenant=tenant, portfolio_id=str(uuid.uuid4())) == []
    assert list_rolling_risks(session, acting_tenant=str(uuid.uuid4())) == []


def test_the_latest_resolver_returns_ONE_runs_rows_never_a_merge(session: Session) -> None:
    """Cross-run aggregation is a CONSUMER ERROR, and a particularly bad one here: two runs of
    different model versions can carry different window sets, so a merged series would silently
    mix estimator domains."""
    tenant = str(uuid.uuid4())
    first = _seeded_run(session, tenant)
    portfolio_id = first.rows[0].portfolio_id

    # A SECOND run over the same book.
    version = register_rolling_risk_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=first.rows[0].portfolio_return_run_id,
    )
    second = run_rolling_risk(
        session,
        acting_tenant=tenant,
        actor=_ACTOR,
        code_version=_CODE_VERSION,
        environment_id="test",
        model_version_id=str(version.id),
        window_months=(12,),
        snapshot_id=snapshot.id,
    )
    latest = latest_rolling_risk(session, acting_tenant=tenant, portfolio_id=portfolio_id)
    assert latest
    assert {r.calculation_run_id for r in latest} == {second.run.run_id}
    assert first.run.run_id not in {r.calculation_run_id for r in latest}


def test_the_resolvers_refuse_a_foreign_id_rather_than_leaking(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    result = _seeded_run(session, tenant)
    row_id = result.rows[0].id

    assert resolve_rolling_risk(session, row_id, acting_tenant=tenant).id == row_id
    with pytest.raises(RollingRiskNotVisible):
        resolve_rolling_risk(session, row_id, acting_tenant=other)
    assert resolve_rolling_risk_run(session, result.run.run_id, acting_tenant=tenant) is not None
    with pytest.raises(RollingRiskRunNotVisible):
        resolve_rolling_risk_run(session, result.run.run_id, acting_tenant=other)
    with pytest.raises(RollingRiskRunNotVisible):
        resolve_rolling_risk_run(session, str(uuid.uuid4()), acting_tenant=tenant)


def test_the_run_centric_read_returns_every_row_of_one_run(session: Session) -> None:
    tenant = str(uuid.uuid4())
    result = _seeded_run(session, tenant)
    rows = list_rolling_risk_rows(session, run_id=result.run.run_id, acting_tenant=tenant)
    assert len(rows) == len(result.rows)
    assert (
        list_rolling_risk_rows(session, run_id=result.run.run_id, acting_tenant=str(uuid.uuid4()))
        == []
    )


# ------------------------------------------------- the FAILED-run path + the audit-silence pin ---


def test_an_extreme_but_column_legal_pin_yields_a_COMMITTED_FAILED_run(session: Session) -> None:
    """The declared failure model, finally executed. Each monthly return is legal at
    Numeric(20,12), but the 12-month geometric product leaves the result envelope — which must
    produce a COMMITTED FAILED run with ZERO rows, never an uncaught raise with the run stranded in
    RUNNING. The review proved the original catch missed this: `link_periods` raises
    ReturnKernelError, not the sibling class the binder caught."""
    tenant = str(uuid.uuid4())
    result = _run_rolling(session, tenant, returns=["9.0"] * 13, windows=(12,))
    assert result.status == "FAILED"
    assert result.rows == []
    assert result.failure_reason
    assert "magnitude-out-of-range" in result.failure_reason


def test_a_rolling_risk_run_emits_NO_PERF_audit_code(session: Session) -> None:
    """OD-RM-1-C: the `PERF.*` block stays RESERVED-not-minted. The run is audited by the governed
    scaffold's `CALC.*` codes only — the sibling families each carry this same pin."""
    from irp_shared.audit.models import AuditEvent

    tenant = str(uuid.uuid4())
    _seeded_run(session, tenant)
    emitted = {
        e.event_type
        for e in session.execute(select(AuditEvent).where(AuditEvent.chain_id == tenant)).scalars()
    }
    assert emitted, "no audit events at all — the pin would be vacuous"
    assert not [code for code in emitted if code.startswith("PERF.")], sorted(emitted)
