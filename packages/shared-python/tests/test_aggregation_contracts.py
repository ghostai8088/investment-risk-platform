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
