"""STRUCT-1 (REQ-PPM-006) — the consumed-measure declarations are LOAD-BEARING, proven by
mutation, not by presence.

The verifier's exploit against the plan: declarations in a module nothing consults, with the real
selection hard-coded in each pin builder, and the refusal fired only against synthetic pins. The
tests here kill that shape: flipping a family's declaration CHANGES the built pin set (the
declaration governs the filter), the parser refusal fires against a REAL produced NOTIONAL row
(never only a hand-typed dict), and an undeclared family is refused by the builder itself.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session
from test_exposure import (  # noqa: F401 - the shared session fixture + seeded-book helpers
    _bond,
    _ccy,
    _pf,
    _pos,
    _run,
    _val,
    session,
)

from irp_shared.aggregation.contracts import (
    EXPOSURE_CONSUMER_MEASURES,
    ForeignMeasureError,
    UndeclaredConsumerError,
    consumed_exposure_measure,
    refuse_foreign_measure,
)
from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION
from irp_shared.exposure.models import (
    EXPOSURE_TYPE_MARKET_VALUE,
    EXPOSURE_TYPE_NOTIONAL,
)
from irp_shared.liquidity.models import RUN_TYPE_LIQUIDITY
from irp_shared.perf.events import RUN_TYPE_PORTFOLIO_RETURN
from irp_shared.risk.events import RUN_TYPE_FACTOR_EXPOSURE
from irp_shared.snapshot import service as snapshot_service
from irp_shared.snapshot.serialize import exposure_content


def test_contract_keys_are_the_real_run_type_strings() -> None:
    """The contract module declares by string literal (an import back into the four families
    would cycle); this pins each literal to the family's actual RUN_TYPE constant so the two can
    never drift apart silently."""
    assert set(EXPOSURE_CONSUMER_MEASURES) == {
        RUN_TYPE_FACTOR_EXPOSURE,
        RUN_TYPE_PORTFOLIO_RETURN,
        RUN_TYPE_CONCENTRATION,
        RUN_TYPE_LIQUIDITY,
    }


def test_all_four_consumers_declare_market_value() -> None:
    for family in EXPOSURE_CONSUMER_MEASURES:
        assert consumed_exposure_measure(family) == EXPOSURE_TYPE_MARKET_VALUE


def test_undeclared_consumer_refuses() -> None:
    """REQ-PPM-006: a consumer that declares nothing FAILS — fail-closed, never a default."""
    with pytest.raises(UndeclaredConsumerError):
        consumed_exposure_measure("VAR")  # a real family that does NOT consume exposure atoms


def test_parser_refusal_fires_on_foreign_and_unlabeled_atoms() -> None:
    with pytest.raises(ForeignMeasureError):
        refuse_foreign_measure(RUN_TYPE_FACTOR_EXPOSURE, {"exposure_type": "NOTIONAL"})
    with pytest.raises(ForeignMeasureError):
        refuse_foreign_measure(RUN_TYPE_FACTOR_EXPOSURE, {})  # unlabeled is not declared
    refuse_foreign_measure(RUN_TYPE_FACTOR_EXPOSURE, {"exposure_type": "MARKET_VALUE"})


def _seeded_two_measure_run(db: Session) -> tuple[str, str]:
    """A bond book whose executed run emits BOTH measures. Returns (tenant, run_id)."""
    tenant = str(uuid.uuid4())
    _ccy(db, "USD")
    pf = _pf(db, tenant)
    inst = _bond(db, tenant, "UST-2033", face_value="1000.0000")
    _pos(db, tenant, pf, inst, "40")
    _val(db, tenant, pf, inst, "991.10", "USD")
    db.flush()
    result = _run(db, tenant, pf, "USD")
    assert result.status == "COMPLETED"
    assert {r.exposure_type for r in result.rows} == {"MARKET_VALUE", "NOTIONAL"}
    return tenant, result.run.run_id


def test_declaration_governs_the_built_pin_set(
    session: Session,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE anti-inert-declaration control (the verifier's exploit, killed by mutation): the pin
    builder's atom set must CHANGE when the declaration changes — a hard-coded filter consulted
    from nothing stays green under this only by consulting the contract."""
    tenant, run_id = _seeded_two_measure_run(session)

    default_atoms = snapshot_service._list_exposure_atoms(
        session, run_id, acting_tenant=tenant, consuming_run_type=RUN_TYPE_CONCENTRATION
    )
    assert {a.exposure_type for a in default_atoms} == {EXPOSURE_TYPE_MARKET_VALUE}

    monkeypatch.setitem(EXPOSURE_CONSUMER_MEASURES, RUN_TYPE_CONCENTRATION, EXPOSURE_TYPE_NOTIONAL)
    mutated_atoms = snapshot_service._list_exposure_atoms(
        session, run_id, acting_tenant=tenant, consuming_run_type=RUN_TYPE_CONCENTRATION
    )
    assert {a.exposure_type for a in mutated_atoms} == {EXPOSURE_TYPE_NOTIONAL}
    assert {a.id for a in mutated_atoms}.isdisjoint({a.id for a in default_atoms})


def test_builder_refuses_an_undeclared_family(session: Session) -> None:  # noqa: F811
    """The census failure fires in the BUILDER, not only in a unit test of the lookup."""
    tenant, run_id = _seeded_two_measure_run(session)
    with pytest.raises(UndeclaredConsumerError):
        snapshot_service._list_exposure_atoms(
            session, run_id, acting_tenant=tenant, consuming_run_type="VAR"
        )


def test_parser_refusal_fires_against_a_real_produced_notional_row(
    session: Session,  # noqa: F811
) -> None:
    """The real-row positive control (judge graft): 'fired' means fired against the governed
    producer's own output — the serialized content of an actually produced NOTIONAL row, not a
    hand-typed dict."""
    tenant, run_id = _seeded_two_measure_run(session)
    all_atoms = snapshot_service._list_exposure_atoms(
        session, run_id, acting_tenant=tenant, consuming_run_type=RUN_TYPE_CONCENTRATION
    )
    # The builder filtered NOTIONAL out; fetch it via the mutated declaration path instead.
    from sqlalchemy import select

    from irp_shared.exposure.models import ExposureAggregate

    notional = (
        session.execute(
            select(ExposureAggregate).where(
                ExposureAggregate.calculation_run_id == run_id,
                ExposureAggregate.exposure_type == EXPOSURE_TYPE_NOTIONAL,
            )
        )
        .scalars()
        .one()
    )
    with pytest.raises(ForeignMeasureError) as exc:
        refuse_foreign_measure(RUN_TYPE_FACTOR_EXPOSURE, exposure_content(notional))
    assert exc.value.found == EXPOSURE_TYPE_NOTIONAL
    assert all_atoms  # and the declared-measure path still yields the family its atoms


# ---------- review folds F-8/F-13: the refusal fires through each REAL parser ----------


class _ForeignComp:
    """A pinned component whose captured content is a REAL produced NOTIONAL row's serialization
    — presented to each family's actual parser, not to the bare contracts function."""

    def __init__(self, captured_content: str, component_kind: str) -> None:
        self.captured_content = captured_content
        self.component_kind = component_kind


def _foreign_component(db: Session) -> _ForeignComp:
    from sqlalchemy import select

    from irp_shared.exposure.models import ExposureAggregate
    from irp_shared.snapshot.models import COMPONENT_KIND_EXPOSURE
    from irp_shared.snapshot.serialize import exposure_content, serialize_content

    _tenant, run_id = _seeded_two_measure_run(db)
    notional = (
        db.execute(
            select(ExposureAggregate).where(
                ExposureAggregate.calculation_run_id == run_id,
                ExposureAggregate.exposure_type == EXPOSURE_TYPE_NOTIONAL,
            )
        )
        .scalars()
        .one()
    )
    return _ForeignComp(serialize_content(exposure_content(notional)), COMPONENT_KIND_EXPOSURE)


def test_factor_parser_refuses_a_real_notional_atom(session: Session) -> None:  # noqa: F811
    from irp_shared.risk import factor_service

    with pytest.raises(ForeignMeasureError):
        factor_service._parse_pins([_foreign_component(session)])


def test_concentration_parser_refuses_a_real_notional_atom(session: Session) -> None:  # noqa: F811
    from irp_shared.concentration import service as concentration_service

    with pytest.raises(ForeignMeasureError):
        concentration_service._parse_pins([_foreign_component(session)])


def test_liquidity_parser_refuses_a_real_notional_atom(session: Session) -> None:  # noqa: F811
    from irp_shared.liquidity import service as liquidity_service

    with pytest.raises(ForeignMeasureError):
        liquidity_service._parse_pins([_foreign_component(session)])


def test_perf_parser_refuses_a_real_notional_atom(session: Session) -> None:  # noqa: F811
    from irp_shared.perf import return_service

    with pytest.raises(ForeignMeasureError):
        return_service._parse_pins([_foreign_component(session)])


# ---------- review fold F-9: a consumer family EXECUTED over a two-measure run ----------


def test_factor_family_runs_over_a_two_measure_run_without_double_count(
    session: Session,  # noqa: F811
) -> None:
    """End to end through the REAL builder + compute: the factor family consumes a run carrying
    BOTH measures, pins exactly the MARKET_VALUE atom, completes, and its total equals the
    market value — never the double-counted sum."""
    from decimal import Decimal as D

    from sqlalchemy import select
    from test_exposure import T0

    from irp_shared.marketdata.factor import FactorActor, capture_factor
    from irp_shared.risk.bootstrap import register_factor_exposure_model
    from irp_shared.risk.events import FactorExposureActor
    from irp_shared.risk.factor_service import run_factor_exposure
    from irp_shared.risk.models import FactorExposureResult
    from irp_shared.snapshot.models import COMPONENT_KIND_EXPOSURE, DatasetSnapshotComponent

    tenant, run_id = _seeded_two_measure_run(session)
    factor = capture_factor(
        session,
        factor_code="FX_USD",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code="USD",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    mv_id = register_factor_exposure_model(
        session, tenant_id=tenant, actor_id="analyst", code_version="risk-v1"
    ).id
    result = run_factor_exposure(
        session,
        acting_tenant=tenant,
        actor=FactorExposureActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv_id,
        exposure_run_id=run_id,
        factor_ids=[factor],
    )
    assert result.status == "COMPLETED"
    # The consumed snapshot pinned EXACTLY the declared measure's one atom.
    pinned = (
        session.execute(
            select(DatasetSnapshotComponent).where(
                DatasetSnapshotComponent.snapshot_id == result.run.input_snapshot_id,
                DatasetSnapshotComponent.component_kind == COMPONENT_KIND_EXPOSURE,
            )
        )
        .scalars()
        .all()
    )
    assert len(pinned) == 1
    # The book: 40 x 991.10 = 39,644 market value; NOTIONAL 40,000 must be absent from the total.
    total = sum(
        (
            r.exposure_amount
            for r in session.execute(
                select(FactorExposureResult).where(
                    FactorExposureResult.calculation_run_id == result.run.run_id
                )
            )
            .scalars()
            .all()
        ),
        D("0"),
    )
    assert total == D("39644.000000")


# ---------- review folds F-10/F-15: the reproduction adapter EXECUTED over two measures ----------


def test_reproduction_matches_a_two_measure_run(session: Session) -> None:  # noqa: F811
    """The widened comparison key executed, not declared: the sweep re-runs the two-measure
    exposure run and every row pairs by (grain + exposure_type) — MATCH. Without the widened key,
    the stored NOTIONAL row would pair against a recomputed MARKET_VALUE row and diverge."""
    from irp_shared.reproduction.events import VERDICT_MATCH
    from irp_shared.reproduction.service import run_reproduction_sweep

    tenant, _run_id = _seeded_two_measure_run(session)
    outcome = run_reproduction_sweep(
        session,
        acting_tenant=tenant,
        actor_id="test",
        code_version="v1",
        environment_id="ci",
    )
    by_family = {c.family_key: c.verdict for c in outcome.checks}
    assert by_family.get("EXPOSURE_AGGREGATE") == VERDICT_MATCH
    checked = next(c for c in outcome.checks if c.family_key == "EXPOSURE_AGGREGATE")
    assert checked.rows_compared == 2  # BOTH measures paired and compared


# ---------- STRUCT-2 (REQ-PPM-007): census 1 + field completeness + the pinned floor ----------


def _registry_universe() -> set[str]:
    from irp_shared.reproduction.registry import (
        REPRODUCIBLE_FAMILIES,
        UNREPRODUCIBLE_FAMILIES,
    )

    return set(REPRODUCIBLE_FAMILIES) | set(UNREPRODUCIBLE_FAMILIES)


def test_census1_contract_keys_equal_the_registry_exactly() -> None:
    """REQ-PPM-007: every family in the run-type registry declares a contract, checked by EXACT
    SET EQUALITY (a subset check passes on an empty contract set — the RPT-3 defect). The
    universe is the registry union, which the shipped reproduction census already proves equals
    the pkgutil RUN_TYPE_* walk minus RUN_TYPE_REPRODUCTION (DP-13's ratified exclusion)."""
    from irp_shared.aggregation.contracts import AGGREGATION_CONTRACTS

    assert set(AGGREGATION_CONTRACTS) == _registry_universe()


#: family -> its result model. Reviewed data guarded by the exact-set assert below; the numeric
#: column reflection is what makes the census MECHANICAL — a new Numeric/Integer value column
#: on any result model fails the census until it is classified.
def _family_models() -> dict:
    from irp_shared.concentration.models import ConcentrationResult
    from irp_shared.exposure.models import ExposureAggregate
    from irp_shared.liquidity.models import LiquidityResult
    from irp_shared.pacing.models import PacingProjectionResult
    from irp_shared.perf.models import (
        BenchmarkRelativeResult,
        DesmoothedReturnResult,
        PortfolioReturnResult,
        RollingRiskResult,
        SharpeRatioResult,
    )
    from irp_shared.report.models import ReportGeneration
    from irp_shared.risk.models import (
        ActiveRiskResult,
        CovarianceResult,
        FactorExposureResult,
        PrivateFactorReturnResult,
        ProxyWeightEstimateResult,
        SensitivityResult,
        VarBacktestResult,
        VarResult,
    )
    from irp_shared.risk.scenario_models import ScenarioResult

    return {
        "EXPOSURE_AGGREGATE": ExposureAggregate,
        "FACTOR_EXPOSURE": FactorExposureResult,
        "SENSITIVITY": SensitivityResult,
        "SCENARIO": ScenarioResult,
        "COVARIANCE": CovarianceResult,
        "COVARIANCE_PRIVATE": CovarianceResult,
        "VAR": VarResult,
        "ACTIVE_RISK": ActiveRiskResult,
        "VAR_BACKTEST": VarBacktestResult,
        "ES_BACKTEST": VarBacktestResult,
        "PORTFOLIO_RETURN": PortfolioReturnResult,
        "BENCHMARK_RELATIVE": BenchmarkRelativeResult,
        "DESMOOTHED_RETURN": DesmoothedReturnResult,
        "ROLLING_RISK": RollingRiskResult,
        "SHARPE": SharpeRatioResult,
        "PURE_PRIVATE_FACTOR": PrivateFactorReturnResult,
        "PROXY_WEIGHT_ESTIMATE": ProxyWeightEstimateResult,
        "PACING_PROJECTION": PacingProjectionResult,
        "CONCENTRATION": ConcentrationResult,
        "LIQUIDITY": LiquidityResult,
        "REPORT": ReportGeneration,
    }


def _numeric_value_columns(model) -> set[str]:  # noqa: ANN001
    """Every Numeric/Integer column that is a VALUE (not an id, key, or FK) — the mechanical
    half of the completeness census."""
    import sqlalchemy as sa

    from irp_shared.db.types import PreciseDecimal

    def _is_numeric(t) -> bool:  # noqa: ANN001
        if isinstance(t, sa.Boolean):
            return False
        # PreciseDecimal's SQLite impl is String (PG gets Numeric via dialect) — detect the
        # decorator itself, not its impl.
        return isinstance(t, sa.Numeric | sa.Integer | PreciseDecimal)

    out = set()
    for col in model.__table__.columns:
        if col.primary_key or col.foreign_keys:
            continue
        if _is_numeric(col.type):
            out.add(col.name)
    return out


def test_every_numeric_value_column_is_classified() -> None:
    """The completeness half: per family, the contract's declared fields equal the result
    model's numeric value columns EXACTLY — a new column fails the census until someone SAYS
    what combining it means (the reproduction-registry key|compared|uncompared precedent)."""
    from irp_shared.aggregation.contracts import AGGREGATION_CONTRACTS

    models = _family_models()
    assert set(models) == set(AGGREGATION_CONTRACTS)
    for family, model in models.items():
        declared = set(AGGREGATION_CONTRACTS[family])
        actual = _numeric_value_columns(model)
        assert declared == actual, (
            f"{family}: contract declares {sorted(declared)} but the result model carries "
            f"numeric value columns {sorted(actual)} — undeclared: {sorted(actual - declared)}, "
            f"phantom: {sorted(declared - actual)}"
        )


def test_operators_are_the_ratified_vocabulary_only() -> None:
    from irp_shared.aggregation.contracts import (
        AGGREGATION_CONTRACTS,
        AGGREGATION_OPERATORS,
    )

    for family, fields in AGGREGATION_CONTRACTS.items():
        for field, op in fields.items():
            assert op in AGGREGATION_OPERATORS, (family, field, op)


def test_the_not_aggregatable_floor_is_pinned() -> None:
    """The permissive-contract negative control (REQ-PPM-007: 'a contract that permits every
    operator on every family FAILS this row'): the load-bearing refusal subjects are pinned BY
    NAME, so a permissive rewrite (everything ADDITIVE) fails here, not in production."""
    from irp_shared.aggregation.contracts import (
        AGGREGATION_CONTRACTS,
        OPERATOR_NOT_AGGREGATABLE,
    )

    floor = {
        ("SHARPE", "metric_value"),  # the DP-6 fired HTTP subject (a ratio)
        ("VAR", "var_value"),  # the DP-6 fired HTTP subject (a quantile)
        ("PORTFOLIO_RETURN", "return_value"),  # TWR is not a weighted mean under flows
        ("ROLLING_RISK", "metric_value"),  # portfolio vol needs correlations
        ("COVARIANCE", "covariance_value"),  # a factor-pair statistic
        ("EXPOSURE_AGGREGATE", "mark_value"),  # a per-unit price
    }
    for family, field in floor:
        assert AGGREGATION_CONTRACTS[family][field] == OPERATOR_NOT_AGGREGATABLE, (family, field)


def test_weighted_ships_empty_with_its_trigger_documented() -> None:
    """DP-5/judge caution: WEIGHTED is vocabulary, not a live classification — duration (its
    canonical subject) has no producing field anywhere. If this assert ever fails, a WEIGHTED
    classification arrived: delete this test and ship the weights plumbing WITH it."""
    from irp_shared.aggregation.contracts import (
        AGGREGATION_CONTRACTS,
        OPERATOR_WEIGHTED,
    )

    weighted = [
        (f, field)
        for f, fields in AGGREGATION_CONTRACTS.items()
        for field, op in fields.items()
        if op == OPERATOR_WEIGHTED
    ]
    assert weighted == []


def test_result_obedience_flipping_an_operator_makes_the_sites_refuse(
    session: Session,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE result-obedience control (the V-007 exploit, killed): the contract lookup's RESULT
    governs the aggregation sites — flip exposure_amount to NOT_AGGREGATABLE and (a) the summed
    read refuses, (b) a consuming family's parser refuses BEFORE any sum. A lookup whose result
    nothing obeys stays green under this only by obeying it."""
    from sqlalchemy import select

    from irp_shared.aggregation.contracts import (
        AGGREGATION_CONTRACTS,
        OPERATOR_NOT_AGGREGATABLE,
        NotAggregatableError,
    )
    from irp_shared.concentration import service as concentration_service
    from irp_shared.exposure.service import summed_latest_exposure
    from irp_shared.snapshot.models import COMPONENT_KIND_EXPOSURE
    from irp_shared.snapshot.serialize import exposure_content, serialize_content

    tenant, run_id = _seeded_two_measure_run(session)

    # Baseline: both sites work under the shipped contract.
    baseline = summed_latest_exposure(
        session,
        acting_tenant=tenant,
        portfolio_id=_pf_of_run(session, run_id),
        exposure_type=EXPOSURE_TYPE_MARKET_VALUE,
    )
    assert baseline.n_rows == 1

    from irp_shared.exposure.models import ExposureAggregate

    mv_row = (
        session.execute(
            select(ExposureAggregate).where(
                ExposureAggregate.calculation_run_id == run_id,
                ExposureAggregate.exposure_type == EXPOSURE_TYPE_MARKET_VALUE,
            )
        )
        .scalars()
        .one()
    )

    class _Comp:
        component_kind = COMPONENT_KIND_EXPOSURE
        captured_content = serialize_content(exposure_content(mv_row))

    concentration_service._parse_pins([_Comp()])  # passes under the shipped contract

    monkeypatch.setitem(
        AGGREGATION_CONTRACTS["EXPOSURE_AGGREGATE"],
        "exposure_amount",
        OPERATOR_NOT_AGGREGATABLE,
    )
    with pytest.raises(NotAggregatableError):
        summed_latest_exposure(
            session,
            acting_tenant=tenant,
            portfolio_id=_pf_of_run(session, run_id),
            exposure_type=EXPOSURE_TYPE_MARKET_VALUE,
        )
    with pytest.raises(NotAggregatableError):
        concentration_service._parse_pins([_Comp()])


def _pf_of_run(db: Session, run_id: str) -> str:
    from sqlalchemy import select

    from irp_shared.exposure.models import ExposureAggregate

    return str(
        db.execute(
            select(ExposureAggregate.portfolio_id)
            .where(ExposureAggregate.calculation_run_id == run_id)
            .limit(1)
        ).scalar_one()
    )


# ---------- STRUCT-2 review folds: the EMITTED GRAIN half (the BLOCKING finding) ----------


def test_grain_census_every_family_declares_and_every_column_exists() -> None:
    """The second machine-readable half the plan ratified ('per family: emitted grain +
    operator'): every family declares its grain, and every named dimension, selector, and
    detail-predicate column EXISTS on the result model — a renamed column fails here, never
    silently detaches the declaration."""
    from irp_shared.aggregation.contracts import AGGREGATION_CONTRACTS, EMITTED_GRAINS

    assert set(EMITTED_GRAINS) == set(AGGREGATION_CONTRACTS)
    models = _family_models()
    for family, grain in EMITTED_GRAINS.items():
        cols = {c.name for c in models[family].__table__.columns}
        for dim in grain.dimensions:
            assert dim in cols, (family, dim)
        for sel in grain.additive_selectors:
            assert sel in grain.dimensions, (family, sel)
        if grain.detail_predicate is not None:
            assert grain.detail_predicate[0] in cols, (family, grain.detail_predicate)


def test_grain_floor_is_pinned() -> None:
    """The load-bearing grain declarations, pinned by name (the permissive-flip control for the
    grain half): the measure selector, the two stored-aggregate exclusions, the concentration
    partition selector, and the portfolio-return period selector."""
    from irp_shared.aggregation.contracts import EMITTED_GRAINS

    assert "exposure_type" in EMITTED_GRAINS["EXPOSURE_AGGREGATE"].additive_selectors
    assert EMITTED_GRAINS["SCENARIO"].detail_predicate == ("metric_type", "SCENARIO_PNL")
    assert EMITTED_GRAINS["CONCENTRATION"].detail_predicate == ("row_kind", "DETAIL")
    assert EMITTED_GRAINS["LIQUIDITY"].detail_predicate == ("row_kind", "DETAIL")
    assert "dimension_kind" in EMITTED_GRAINS["CONCENTRATION"].additive_selectors
    assert "period_start" in EMITTED_GRAINS["PORTFOLIO_RETURN"].additive_selectors


def test_scenario_detail_predicate_kills_the_total_row_double_count() -> None:
    """The review's HIGH made executable: a run stores per-factor SCENARIO_PNL rows AND one
    SCENARIO_PNL_TOTAL row that IS their sum. A NAIVE contract-conformant sum returns 2x; a
    grain-conformant sum (detail rows only) returns the true P&L and equals the stored total —
    the declaration is the thing that makes the difference."""
    from decimal import Decimal

    from irp_shared.aggregation.contracts import EMITTED_GRAINS
    from irp_shared.risk.events import (
        METRIC_TYPE_SCENARIO_PNL,
        METRIC_TYPE_SCENARIO_PNL_TOTAL,
    )

    rows = [
        {"metric_type": METRIC_TYPE_SCENARIO_PNL, "pnl": Decimal("-120.50")},
        {"metric_type": METRIC_TYPE_SCENARIO_PNL, "pnl": Decimal("300.00")},
        {"metric_type": METRIC_TYPE_SCENARIO_PNL_TOTAL, "pnl": Decimal("179.50")},
    ]
    col, required = EMITTED_GRAINS["SCENARIO"].detail_predicate
    conformant = sum((r["pnl"] for r in rows if r[col] == required), Decimal(0))
    naive = sum((r["pnl"] for r in rows), Decimal(0))
    assert conformant == Decimal("179.50")  # == the stored total: the true P&L
    assert naive == Decimal("359.00")  # the double-count the predicate exists to kill


def test_grain_selector_requirement_obeys_the_declaration(
    session: Session,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Result obedience for the GRAIN half: the summed read's exposure_type requirement comes
    FROM the declaration — empty the selector tuple and the requirement disappears (proving the
    hand-written form the review refuted is gone), while the floor test above pins the shipped
    selector so a permissive rewrite fails in review."""
    from irp_shared.aggregation.contracts import EMITTED_GRAINS, EmittedGrain
    from irp_shared.exposure.service import ExposureInputError, summed_latest_exposure

    tenant, run_id = _seeded_two_measure_run(session)
    pf = _pf_of_run(session, run_id)

    with pytest.raises(ExposureInputError, match="additive-selector"):
        summed_latest_exposure(session, acting_tenant=tenant, portfolio_id=pf, exposure_type=None)

    from irp_shared.exposure.service import NothingToSumError

    bare = EmittedGrain(dimensions=EMITTED_GRAINS["EXPOSURE_AGGREGATE"].dimensions)
    monkeypatch.setitem(EMITTED_GRAINS, "EXPOSURE_AGGREGATE", bare)
    with pytest.raises(NothingToSumError):
        # With no selector declared the read no longer REQUIRES a measure — it proceeds to the
        # empty-book refusal instead, proving the declaration governed the requirement.
        summed_latest_exposure(
            session, acting_tenant=tenant, portfolio_id=str(uuid.uuid4()), exposure_type=None
        )


def test_factor_exposure_side_result_obedience(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review fold: the FACTOR_EXPOSURE-side preconditions were never mutated. Flip the
    declared operator and the HS-VaR binder's pin adjudication refuses BEFORE any sum — through
    the REAL parse path, with a minimal well-formed row."""
    from irp_shared.aggregation.contracts import (
        AGGREGATION_CONTRACTS,
        OPERATOR_NOT_AGGREGATABLE,
        NotAggregatableError,
    )
    from irp_shared.risk import var_hs_service

    row = {
        "calculation_run_id": str(uuid.uuid4()),
        "factor_id": str(uuid.uuid4()),
        "portfolio_id": str(uuid.uuid4()),
        "instrument_id": str(uuid.uuid4()),
        "base_currency": "USD",
        "exposure_amount": "100.000000",
        "id": str(uuid.uuid4()),
    }
    monkeypatch.setitem(
        AGGREGATION_CONTRACTS["FACTOR_EXPOSURE"],
        "exposure_amount",
        OPERATOR_NOT_AGGREGATABLE,
    )
    with pytest.raises(NotAggregatableError):
        var_hs_service._adjudicate_pins([row], [], declared_window=250)


# ---------- STRUCT-3 (REQ-PPM-008 clause 7): the node-scope census + execution evidence ----------


def test_node_scope_census_exact_set_and_valid_upstreams() -> None:
    """Every registry family declares its node-scope class (exact set — the 3-entry scheduling
    flag structurally cannot census 21 families, the clause's own insufficiency premise), and
    every SCOPE_INHERITED upstream is itself a declared family."""
    from irp_shared.aggregation.contracts import (
        NODE_SCOPE_INHERITED,
        NODE_SCOPES,
    )

    assert set(NODE_SCOPES) == _registry_universe()
    for family, scope in NODE_SCOPES.items():
        if scope.scope_class == NODE_SCOPE_INHERITED:
            assert scope.upstream in NODE_SCOPES, (family, scope.upstream)
        else:
            assert scope.upstream is None, family


def test_exposure_executes_at_a_middle_node(session: Session) -> None:  # noqa: F811
    """The SUBTREE family's execution evidence: a governed run AT a STRATEGY node (not the
    root) completes and carries the node."""
    import uuid as _uuid

    from test_exposure import _ccy as _ccy2
    from test_exposure import _run as _run_exp
    from test_exposure import _three_level_book

    tenant = str(_uuid.uuid4())
    _ccy2(session, "USD")
    fund, strat, a, b = _three_level_book(session, tenant)
    session.flush()
    result = _run_exp(session, tenant, strat, "USD")  # BUILD at the middle node
    assert result.status == "COMPLETED"
    assert result.run.scope_portfolio_id == str(strat)
    assert {r.portfolio_id for r in result.rows} == {str(a), str(b)}  # the sleeve's subtree


def test_factor_exposure_inherits_a_sleeve_scope(session: Session) -> None:  # noqa: F811
    """The SCOPE_INHERITED chain head's execution evidence: a factor-exposure run over a
    sleeve-rooted exposure run copies the SLEEVE scope forward — the chain executes below the
    top of the tree."""
    import uuid as _uuid

    from test_exposure import T0, _three_level_book
    from test_exposure import _ccy as _ccy2
    from test_exposure import _run as _run_exp

    from irp_shared.marketdata.factor import FactorActor, capture_factor
    from irp_shared.risk.bootstrap import register_factor_exposure_model
    from irp_shared.risk.events import FactorExposureActor
    from irp_shared.risk.factor_service import run_factor_exposure

    tenant = str(_uuid.uuid4())
    _ccy2(session, "USD")
    fund, strat, a, b = _three_level_book(session, tenant)
    session.flush()
    sleeve_run = _run_exp(session, tenant, strat, "USD")
    assert sleeve_run.status == "COMPLETED"

    factor = capture_factor(
        session,
        factor_code="FX_USD",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code="USD",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    mv_id = register_factor_exposure_model(
        session, tenant_id=tenant, actor_id="analyst", code_version="risk-v1"
    ).id
    fe = run_factor_exposure(
        session,
        acting_tenant=tenant,
        actor=FactorExposureActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv_id,
        exposure_run_id=sleeve_run.run.run_id,
        factor_ids=[factor],
    )
    assert fe.status == "COMPLETED"
    assert fe.run.scope_portfolio_id == str(strat)  # the sleeve, inherited


def test_inherited_scope_declarations_are_not_decorative(session: Session) -> None:  # noqa: F811
    """Review BLOCKING fold: five SCOPE_INHERITED declarations were factually false — the
    binders stamped NULL (the SCENARIO defect shape, shipped again as data). The mechanical
    check: every family declared SCOPE_INHERITED must have at least one COMPLETED run in this
    battery carrying a NON-NULL scope... executed per-family in their own suites; here the
    DECLARATION-level guard is that the class list matches the binders that STAMP — pinned by
    name so a new false declaration fails in review."""
    from irp_shared.aggregation.contracts import NODE_SCOPE_INHERITED, NODE_SCOPES

    inherited = {f for f, sc in NODE_SCOPES.items() if sc.scope_class == NODE_SCOPE_INHERITED}
    # Every one of these binders now passes scope_portfolio_id to the scaffold (grep-pinned in
    # the census below); the five that did NOT before this fold: PORTFOLIO_RETURN,
    # BENCHMARK_RELATIVE, VAR_BACKTEST, ES_BACKTEST, PROXY_WEIGHT_ESTIMATE.
    assert inherited == {
        "FACTOR_EXPOSURE",
        "VAR",
        "ACTIVE_RISK",
        "SCENARIO",
        "CONCENTRATION",
        "LIQUIDITY",
        "PORTFOLIO_RETURN",
        "BENCHMARK_RELATIVE",
        "ROLLING_RISK",
        "SHARPE",
        "VAR_BACKTEST",
        "ES_BACKTEST",
        "PROXY_WEIGHT_ESTIMATE",
    }


def test_every_inherited_binder_stamps_scope_mechanically() -> None:
    """The grep-level census: each SCOPE_INHERITED family's service module passes
    scope_portfolio_id to the governed-run scaffold — a stamp deleted from any of them fails
    HERE, not in a demo three stages later."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "irp_shared"
    modules = {
        "FACTOR_EXPOSURE": "risk/factor_service.py",
        "VAR": "risk/var_service.py",
        "ACTIVE_RISK": "risk/active_risk_service.py",
        "SCENARIO": "risk/scenario_service.py",
        "CONCENTRATION": "concentration/service.py",
        "LIQUIDITY": "liquidity/service.py",
        "PORTFOLIO_RETURN": "perf/return_service.py",
        "BENCHMARK_RELATIVE": "perf/benchmark_relative_service.py",
        "ROLLING_RISK": "perf/rolling_service.py",
        "SHARPE": "perf/sharpe_service.py",
        "VAR_BACKTEST": "risk/var_backtest_service.py",
        "ES_BACKTEST": "risk/es_backtest_service.py",
        "PROXY_WEIGHT_ESTIMATE": "risk/proxy_weight_service.py",
    }
    for family, rel in modules.items():
        text = (root / rel).read_text()
        assert "scope_portfolio_id" in text, f"{family}: {rel} never stamps a scope"
