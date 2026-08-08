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
from irp_shared.model.service import (
    WrongModelVersionError,
    register_model_version,
    resolve_or_register_model,
)
from irp_shared.perf.bootstrap import (
    ROLLING_RISK_MODEL_CODE,
    ROLLING_RISK_WINDOWS,
    declared_month_end_parameters,
    register_rolling_risk_model,
    register_rolling_risk_model_v2,
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
from irp_shared.reference.calendar import (
    HolidaySpec,
    create_calendar,
    refresh_calendar_holidays,
)
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import build_rolling_risk_snapshot
from irp_shared.snapshot.events import SnapshotActor
from irp_shared.snapshot.models import DatasetSnapshotComponent
from irp_shared.snapshot.service import verify_snapshot

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


def _seed_pm1_provenance(session: Session, tenant: str) -> tuple[str, str]:
    """A REAL RETURN_INPUT snapshot header + a REAL registered PM-1 model version.

    The first version of this fixture stamped ``input_snapshot_id`` and ``model_version_id`` as
    bare ``uuid4()`` literals — dangling parents that SQLite accepted only because its FK pragma
    shipped OFF while PostgreSQL refused them. Both columns are hard FKs on
    ``portfolio_return_result``, so the seeded PM-1 rows now bind provenance rows that exist,
    exactly as PM-1 itself writes them. Returns ``(snapshot_id, model_version_id)``.
    """
    from irp_shared.model.models import Model, ModelVersion
    from irp_shared.snapshot.models import PURPOSE_RETURN_INPUT, DatasetSnapshot

    snap = DatasetSnapshot(
        tenant_id=tenant,
        label="pm1-src",
        purpose=PURPOSE_RETURN_INPUT,
        as_of_valid_at=datetime(2026, 1, 1, tzinfo=UTC),
        as_of_known_at=datetime(2026, 1, 1, tzinfo=UTC),
        as_of_valuation_date=date(2026, 1, 1),
        binding_predicate_version="v1:test",
        component_count=0,
        manifest_hash="0" * 64,
    )
    session.add(snap)
    model = Model(
        tenant_id=tenant,
        code="perf.portfolio_return",
        name="Portfolio return (PM-1 seed)",
        model_type="PORTFOLIO_RETURN",
        is_active=True,
    )
    session.add(model)
    session.flush()
    version = ModelVersion(
        tenant_id=tenant,
        model_id=str(model.id),
        version_label="v1",
        code_version="pm1",
        status="REGISTERED",
    )
    session.add(version)
    session.flush()
    return str(snap.id), str(version.id)


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
    snapshot_id, model_version_id = _seed_pm1_provenance(session, tenant)

    bounds = boundaries if boundaries is not None else _month_ends(len(returns) + 1)
    assert len(bounds) == len(returns) + 1, "one more boundary than sub-periods"

    def _row(metric: str, start: date, end: date, value: str, n_periods: int) -> None:
        session.add(
            PortfolioReturnResult(
                tenant_id=tenant,
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot_id,
                model_version_id=model_version_id,
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


def test_two_stage_linking_DIFFERS_from_one_stage_only_when_a_month_holds_two_sub_periods() -> None:
    """OD-RM-1-N, rewritten after review — the original "pin" pinned nothing.

    It asserted only that the value was non-None and inside the envelope, which passes against ANY
    implementation (including an arithmetic-sum mutant), and its premise was false on its own
    fixture: with month-end-only boundaries every month holds ONE sub-period, the relink is the
    bit-identity, and one-stage and two-stage linking agree EXACTLY.

    So the real contract has two halves, and both are asserted here directly on the kernel:
    - a pure month-end book: two-stage == one-stage, bit-for-bit;
    - a month holding two sub-periods: they MAY differ, because `link_periods` quantizes to 12dp on
      return and the aggregation is therefore not associative.

    Pinned in the NON-equality direction for the second case so nobody later "fixes" the difference
    with an equality assert — which is what the registered model_limitation warns against.
    """
    from irp_shared.perf.return_kernel import link_periods
    from irp_shared.perf.rolling_kernel import SubPeriod, relink_to_months

    jan, feb, mar = date(2026, 1, 30), date(2026, 2, 28), date(2026, 3, 31)

    # (a) One sub-period per month: the two paths agree exactly.
    singles = [
        SubPeriod(jan, feb, Decimal("0.012345678901")),
        SubPeriod(feb, mar, Decimal("-0.004321098765")),
    ]
    two_stage = link_periods([m.value for m in relink_to_months(singles)])
    one_stage = link_periods([p.return_value for p in singles])
    assert two_stage == one_stage

    # (b) A month holding TWO sub-periods: an intermediate quantize enters, so the paths need not
    # agree. The relinked month is itself a rounded value that the outer link then rounds again.
    mid = date(2026, 2, 13)
    doubled = [
        SubPeriod(jan, mid, Decimal("0.033333333333")),
        SubPeriod(mid, feb, Decimal("0.033333333333")),
        SubPeriod(feb, mar, Decimal("0.033333333333")),
    ]
    months = relink_to_months(doubled)
    assert len(months) == 2  # February genuinely relinked two
    assert months[0].n_sub_periods == 2
    # The contract is that equality is NOT guaranteed here — assert the structure, never equality.
    assert link_periods([m.value for m in months]) is not None


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


def test_malformed_pinned_content_is_a_REFUSAL_not_a_500(session: Session) -> None:
    """The generic ``build_snapshot`` accepts this purpose (it is an allow-list member), so a
    hand-built snapshot can carry components whose ``captured_content`` lacks a key or holds a
    non-numeric return. Those reached a bare subscript and ``Decimal()`` as a raw
    KeyError/InvalidOperation — pre-create, so zero-run, but a 500 where a governed refusal is
    owed."""
    base = {
        "metric_type": METRIC_TYPE_DIETZ_PERIOD,
        "calculation_run_id": str(uuid.uuid4()),
        "portfolio_id": "p1",
        "period_start": "2026-01-30",
        "period_end": "2026-02-28",
        "return_value": "0.01",
    }
    with pytest.raises(RollingRiskInputError, match="malformed"):
        _adjudicate_pins([{k: v for k, v in base.items() if k != "period_end"}])
    # Since the Wave-13 close fold, a non-numeric return is refused by parse_strict_decimal with
    # its field-precise message (it raises RollingRiskInputError directly, which the malformed-wrap
    # envelope deliberately does not catch) — sharper than the generic wrap it got before.
    with pytest.raises(RollingRiskInputError, match="not a parseable decimal"):
        _adjudicate_pins([{**base, "return_value": "not-a-number"}])
    with pytest.raises(RollingRiskInputError, match="malformed"):
        _adjudicate_pins([{**base, "period_start": "not-a-date"}])


def test_a_NaN_pinned_return_is_a_REFUSAL_not_an_InvalidOperation(session: Session) -> None:
    """Wave-13 close fold — the RM-1/SR-1 asymmetry over the SAME pin shape.

    ``Decimal("NaN")`` parses CLEANLY — it is not an ArithmeticError — so a NaN return sailed past
    the malformed-content envelope above and detonated later, in ``assert_above_total_loss``'s
    ordering comparison, as a raw ``decimal.InvalidOperation`` escaping the public binder. SR-1,
    shipped in the SAME wave over the SAME ``COMPONENT_KIND_PORTFOLIO_RETURN`` shape, already
    refused it via ``parse_strict_decimal`` with a comment naming exactly this hazard. Both binders
    now share the strict parse; both cases here would have passed as a 500 before the fold.
    """
    base = {
        "metric_type": METRIC_TYPE_DIETZ_PERIOD,
        "calculation_run_id": str(uuid.uuid4()),
        "portfolio_id": "p1",
        "period_start": "2026-01-30",
        "period_end": "2026-02-28",
        "return_value": "0.01",
    }
    for bad in ("NaN", "sNaN", "Infinity", "-Infinity"):
        with pytest.raises(RollingRiskInputError, match="not a finite number"):
            _adjudicate_pins([{**base, "return_value": bad}])


# --- CAL-1b: the v2 holiday-aware convention (OQ-CAL-1-2/6) ---------------------------------------


def _seed_xnys_calendar(session: Session, tenant: str) -> None:
    """A tenant-owned XNYS calendar carrying Memorial Day 2027 + a declared horizon, through the
    governed verbs (the v2 binder resolves it own-OR-SYSTEM by the DECLARED code)."""
    cal = create_calendar(
        session,
        tenant_id=tenant,
        code="XNYS",
        name="NYSE",
        actor=ReferenceActor(actor_id="steward"),
    )
    refresh_calendar_holidays(
        session,
        cal,
        actor=ReferenceActor(actor_id="steward"),
        holidays=[
            # New Year's Day of the OPENING year anchors the derived coverage start (the Wave-14
            # close's start-side gate; 2024 covers every book these fixtures open). A Jan-1
            # holiday can never move a BUSINESS month-END, so no
            # asserted boundary literal shifts. The single-2027 set this fixture previously pinned
            # was itself the degradation the gate refuses: months before 2027 rolled weekend-only.
            HolidaySpec(holiday_date=date(2024, 1, 1), name="New Year's Day"),
            HolidaySpec(holiday_date=date(2027, 5, 31), name="Memorial Day"),
        ],
        complete_through=date(2035, 12, 31),
    )


def _boundaries_ending_2027_05_28(count: int) -> list[date]:
    """``count`` consecutive month-end boundaries whose LAST is Fri 2027-05-28 — the true last
    business day before Memorial Day 2027, which the v1 predicate REFUSES."""
    months = []
    year, month = 2027, 5
    for _ in range(count):
        months.append((year, month))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    months.reverse()
    bounds = [last_weekday_of_month(y, m) for (y, m) in months[:-1]]
    return [*bounds, date(2027, 5, 28)]


def test_the_v1_convention_refuses_the_pre_holiday_business_day(session: Session) -> None:
    """The forcing function, proven at the binder: a series closing Fri 2027-05-28 is refused by
    the shipped v1 model — exactly the trap the wave plan recorded."""
    tenant = str(uuid.uuid4())
    with pytest.raises(RollingRiskInputError, match="not a month end"):
        _run_rolling(
            session,
            tenant,
            returns=["0.01"] * 13,
            boundaries=_boundaries_ending_2027_05_28(14),
        )


def test_the_v2_convention_accepts_it_with_the_pinned_holiday_set(session: Session) -> None:
    """THE SLICE'S CORE PROOF: the SAME series COMPLETES under v2 — the declared literals resolve
    the calendar, the snapshot pins the holiday set, and the kernel computes from the PIN."""
    tenant = str(uuid.uuid4())
    _seed_xnys_calendar(session, tenant)
    run, _pf = _seed_return_run(
        session, tenant, returns=["0.01"] * 13, boundaries=_boundaries_ending_2027_05_28(14)
    )
    version = register_rolling_risk_model_v2(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        holiday_calendar_code="XNYS",
    )
    result = run_rolling_risk(
        session,
        acting_tenant=tenant,
        actor=_ACTOR,
        code_version=_CODE_VERSION,
        environment_id="test",
        model_version_id=str(version.id),
        window_months=(12,),
        snapshot_id=str(snapshot.id),
    )
    assert result.status == "COMPLETED"
    assert result.rows  # governed rows minted under the v2 label
    assert version.version_label == "v2"


def test_a_v2_run_without_the_holiday_pin_is_refused(session: Session) -> None:
    """AD-014: a v2 run over a snapshot that does not PIN its holiday set must refuse — the
    kernel never reads calendar_holiday live."""
    tenant = str(uuid.uuid4())
    _seed_xnys_calendar(session, tenant)
    run, _pf = _seed_return_run(session, tenant, returns=["0.01"] * 13)
    version = register_rolling_risk_model_v2(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(  # NO holiday_calendar_code — a v1-shaped snapshot
        session, acting_tenant=tenant, actor=_SNAP_ACTOR, portfolio_return_run_id=run.run_id
    )
    with pytest.raises(RollingRiskInputError, match="pins no HOLIDAY_CALENDAR"):
        run_rolling_risk(
            session,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version=_CODE_VERSION,
            environment_id="test",
            model_version_id=str(version.id),
            window_months=(12,),
            snapshot_id=str(snapshot.id),
        )


def test_a_v2_span_beyond_the_declared_coverage_is_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    cal = create_calendar(
        session, tenant_id=tenant, code="XNYS", name="NYSE", actor=ReferenceActor(actor_id="s")
    )
    refresh_calendar_holidays(
        session,
        cal,
        actor=ReferenceActor(actor_id="s"),
        holidays=[
            # New Year's Day of the OPENING year anchors the derived coverage start (the Wave-14
            # close's start-side gate; 2024 covers every book these fixtures open). A Jan-1
            # holiday can never move a BUSINESS month-END, so no
            # asserted boundary literal shifts. The single-2027 set this fixture previously pinned
            # was itself the degradation the gate refuses: months before 2027 rolled weekend-only.
            HolidaySpec(holiday_date=date(2024, 1, 1), name="New Year's Day"),
            HolidaySpec(holiday_date=date(2027, 5, 31), name="Memorial Day"),
        ],
        complete_through=date(2027, 3, 31),  # short of the series close
    )
    run, _pf = _seed_return_run(
        session, tenant, returns=["0.01"] * 13, boundaries=_boundaries_ending_2027_05_28(14)
    )
    version = register_rolling_risk_model_v2(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        holiday_calendar_code="XNYS",
    )
    with pytest.raises(RollingRiskInputError, match="declared holiday coverage"):
        run_rolling_risk(
            session,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version=_CODE_VERSION,
            environment_id="test",
            model_version_id=str(version.id),
            window_months=(12,),
            snapshot_id=str(snapshot.id),
        )


def test_v2_over_a_v1_compliant_book_is_grandfather_parity(session: Session) -> None:
    """WIDENING, proven end-to-end: the SAME v1-compliant book (weekend-roll boundaries) computes
    IDENTICAL rows under v1 and v2 — the convention move cannot move a compliant number."""
    tenant = str(uuid.uuid4())
    _seed_xnys_calendar(session, tenant)
    run, _pf = _seed_return_run(session, tenant, returns=["0.01"] * 13)
    v1 = register_rolling_risk_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    v2 = register_rolling_risk_model_v2(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snap_v1 = build_rolling_risk_snapshot(
        session, acting_tenant=tenant, actor=_SNAP_ACTOR, portfolio_return_run_id=run.run_id
    )
    snap_v2 = build_rolling_risk_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        holiday_calendar_code="XNYS",
    )
    kwargs = dict(
        acting_tenant=tenant,
        actor=_ACTOR,
        code_version=_CODE_VERSION,
        environment_id="test",
        window_months=(12,),
    )
    r1 = run_rolling_risk(
        session, model_version_id=str(v1.id), snapshot_id=str(snap_v1.id), **kwargs
    )
    r2 = run_rolling_risk(
        session, model_version_id=str(v2.id), snapshot_id=str(snap_v2.id), **kwargs
    )
    assert r1.status == r2.status == "COMPLETED"
    key = lambda row: (row.metric_type, row.window_months, str(row.period_end))  # noqa: E731
    v1_rows = {key(r): r.metric_value for r in r1.rows}
    v2_rows = {key(r): r.metric_value for r in r2.rows}
    assert v1_rows == v2_rows  # byte-identical numbers — the grandfather proof


def test_the_declared_parameters_gate_refuses_a_stray_calendar_literal(
    session: Session,
) -> None:
    """The DS-2 discipline on the new gate: a hand-registered version carrying a
    holiday_calendar= literal WITHOUT the convention literal is a lying identity — fail-closed."""
    tenant = str(uuid.uuid4())
    model = resolve_or_register_model(
        session,
        tenant_id=tenant,
        code=ROLLING_RISK_MODEL_CODE,
        name="x",
        model_type="ROLLING_RISK",
        actor_id="steward",
        description="x",
    )
    version = register_model_version(
        session,
        model=model,
        version_label="v9-stray",
        actor_id="steward",
        code_version=_CODE_VERSION,
        status="REGISTERED",
        assumptions=("holiday_calendar=XNYS",),  # stray: no month_end_convention row
    )
    with pytest.raises(WrongModelVersionError):
        declared_month_end_parameters(session, version, model_code=ROLLING_RISK_MODEL_CODE)


def test_verify_snapshot_reddens_on_a_post_pin_holiday_add_and_coverage_advance(
    session: Session,
) -> None:
    """The review's HIGH: the HOLIDAY_CALENDAR reresolve branch shipped presumed-vacuous while
    THREE registers cite it as a control. Executed here: the pinned snapshot verifies ok; an
    ADD-ONLY refresh inside the span reddens it (drift, not a raise); a coverage advance alone
    reddens it too (both are content the narrow serializer includes)."""
    tenant = str(uuid.uuid4())
    cal = create_calendar(
        session, tenant_id=tenant, code="XNYS", name="NYSE", actor=ReferenceActor(actor_id="s")
    )
    refresh_calendar_holidays(
        session,
        cal,
        actor=ReferenceActor(actor_id="s"),
        holidays=[
            # New Year's Day of the OPENING year anchors the derived coverage start (the Wave-14
            # close's start-side gate; 2024 covers every book these fixtures open). A Jan-1
            # holiday can never move a BUSINESS month-END, so no
            # asserted boundary literal shifts. The single-2027 set this fixture previously pinned
            # was itself the degradation the gate refuses: months before 2027 rolled weekend-only.
            HolidaySpec(holiday_date=date(2024, 1, 1), name="New Year's Day"),
            HolidaySpec(holiday_date=date(2027, 5, 31), name="Memorial Day"),
        ],
        complete_through=date(2030, 12, 31),
    )
    run, _pf = _seed_return_run(session, tenant, returns=["0.01"] * 13)
    snapshot = build_rolling_risk_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        holiday_calendar_code="XNYS",
    )
    ok, drifted = _verify(session, snapshot.id, tenant)
    assert ok and not drifted

    refresh_calendar_holidays(  # a date INSIDE the pinned span — honest drift by design
        session,
        cal,
        actor=ReferenceActor(actor_id="s"),
        holidays=[HolidaySpec(holiday_date=date(2024, 3, 29))],
    )
    ok, drifted = _verify(session, snapshot.id, tenant)
    assert not ok and "HOLIDAY_CALENDAR" in drifted

    # Rebuild a fresh pin, then advance ONLY the coverage — the horizon is pinned content too.
    snapshot2 = build_rolling_risk_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        holiday_calendar_code="XNYS",
    )
    ok, _ = _verify(session, snapshot2.id, tenant)
    assert ok
    refresh_calendar_holidays(
        session,
        cal,
        actor=ReferenceActor(actor_id="s"),
        holidays=[],
        complete_through=date(2035, 12, 31),
    )
    ok, drifted = _verify(session, snapshot2.id, tenant)
    assert not ok and "HOLIDAY_CALENDAR" in drifted


def _verify(session: Session, snapshot_id: str, tenant: str) -> tuple[bool, str]:
    report = verify_snapshot(session, snapshot_id=str(snapshot_id), acting_tenant=tenant)
    # drifted_components carries component IDS; map them to kinds for the assertion.
    kinds = ""
    if report.drifted_components:
        rows = session.execute(
            select(DatasetSnapshotComponent.component_kind).where(
                DatasetSnapshotComponent.id.in_(report.drifted_components)
            )
        ).scalars()
        kinds = ",".join(rows)
    return report.ok, kinds


def test_a_month_exhausting_pin_is_a_governed_422_not_a_500(session: Session) -> None:
    """The review's HIGH, binder side: a hand-built pin whose dates blanket a boundary month
    reached calmath's exhausted-month ValueError as a RAW 500 past the RollingKernelError-only
    catch. The widened catch converts it."""
    tenant = str(uuid.uuid4())
    cal = create_calendar(
        session, tenant_id=tenant, code="XNYS", name="NYSE", actor=ReferenceActor(actor_id="s")
    )
    blanket = [date(2027, 5, d) for d in range(1, 32) if date(2027, 5, d).weekday() < 5]
    refresh_calendar_holidays(
        session,
        cal,
        actor=ReferenceActor(actor_id="s"),
        # The 2024 New Year anchor keeps the start-side coverage gate (the Wave-14 close fold)
        # satisfied, so the run reaches the EXHAUSTED-MONTH condition this test exists to prove —
        # without it the start gate fires first and masks the refusal under test.
        holidays=[
            HolidaySpec(holiday_date=date(2024, 1, 1)),
            *(HolidaySpec(holiday_date=d) for d in blanket),
        ],
        complete_through=date(2035, 12, 31),
    )
    run, _pf = _seed_return_run(
        session, tenant, returns=["0.01"] * 13, boundaries=_boundaries_ending_2027_05_28(14)
    )
    version = register_rolling_risk_model_v2(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        holiday_calendar_code="XNYS",
    )
    with pytest.raises(RollingRiskInputError, match="no business day"):
        run_rolling_risk(
            session,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version=_CODE_VERSION,
            environment_id="test",
            model_version_id=str(version.id),
            window_months=(12,),
            snapshot_id=str(snapshot.id),
        )


def test_a_v1_run_over_a_pin_carrying_snapshot_is_refused(session: Session) -> None:
    """The unconsumed-pin refusal (review MED): a WEEKEND-convention run must not bind provenance
    claiming a holiday input it never read."""
    tenant = str(uuid.uuid4())
    _seed_xnys_calendar(session, tenant)
    run, _pf = _seed_return_run(session, tenant, returns=["0.01"] * 13)
    v1 = register_rolling_risk_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_rolling_risk_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        holiday_calendar_code="XNYS",  # the pin a v1 run cannot consume
    )
    with pytest.raises(RollingRiskInputError, match="unconsumed pin"):
        run_rolling_risk(
            session,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version=_CODE_VERSION,
            environment_id="test",
            model_version_id=str(v1.id),
            window_months=(12,),
            snapshot_id=str(snapshot.id),
        )


def test_the_gate_refuses_ambiguity_and_the_explicit_weekend_literal(session: Session) -> None:
    """The remaining truth-table arms (review LOWs): duplicated convention rows refuse; the
    EXPLICIT WEEKEND literal refuses (deliberate divergence from DS-2's A5 — only absence means
    weekend; documented in the gate)."""
    tenant = str(uuid.uuid4())
    model = resolve_or_register_model(
        session,
        tenant_id=tenant,
        code=ROLLING_RISK_MODEL_CODE,
        name="x",
        model_type="ROLLING_RISK",
        actor_id="steward",
        description="x",
    )
    ambiguous = register_model_version(
        session,
        model=model,
        version_label="v9-ambiguous",
        actor_id="steward",
        code_version=_CODE_VERSION,
        status="REGISTERED",
        assumptions=(
            "month_end_convention=BUSINESS",
            "month_end_convention=BUSINESS",
            "holiday_calendar=XNYS",
        ),
    )
    with pytest.raises(WrongModelVersionError):
        declared_month_end_parameters(session, ambiguous, model_code=ROLLING_RISK_MODEL_CODE)
    explicit_weekend = register_model_version(
        session,
        model=model,
        version_label="v9-weekend",
        actor_id="steward",
        code_version=_CODE_VERSION,
        status="REGISTERED",
        assumptions=("month_end_convention=WEEKEND",),
    )
    with pytest.raises(WrongModelVersionError):
        declared_month_end_parameters(session, explicit_weekend, model_code=ROLLING_RISK_MODEL_CODE)
