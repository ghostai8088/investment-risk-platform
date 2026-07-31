"""PostgreSQL end-state test for the LIM-2 demo stage 20 — concentration limits that actually bind.

Gated on ``IRP_TEST_DATABASE_URL``. Runs the stage ONCE (module-scoped) over the living demo tenant
and asserts the governed end state by READING THE DATABASE, never by trusting the stage's own
summary — the PERF-0 lesson, where a harness reported six segments OK while no COMPLETED run
existed.

**The filename is load-bearing** (the standing stage-ordering discipline): ELEVEN ``z`` — verified
by ``ls`` on the tests directory (con1 = ten), never read off a decision record.

**The count pin is UNCHANGED at 26/41/136 and relays here.** LIM-2 registers no model, records no
validation, and mints no ``calculation_run``: limits and breaches are neither. So this suite takes
the FINAL-POSITION pin with the SAME triple CON-1 left, which is a stronger statement than a new
number would be — it asserts that adding a whole slice moved nothing it should not have moved.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_lim2_stage20
from irp_shared.demo.lim2_stage20 import DemoLim2AlreadySeededError
from irp_shared.limit.models import Breach, LimitDefinition
from irp_shared.limit.service import limit_health, list_limits
from irp_shared.model.models import Model, ModelValidation

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_ISSUER_NAMED = {"DEMO-ISSUER-CEIL", "DEMO-ISSUER-HEADROOM", "DEMO-ISSUER-PROPOSED"}
_NOT_ISSUER_NAMED = {"DEMO-SECTOR-CEIL", "DEMO-HHI-CEIL"}


@pytest.fixture(scope="module")
def staged():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    result = None
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        try:
            result = run_demo_lim2_stage20(session)
            session.commit()
        except DemoLim2AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory, result
    engine.dispose()


@pytest.fixture()
def db(staged):  # noqa: ANN001, ANN201
    factory, _ = staged
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        yield session
    finally:
        session.close()


def _limits(db) -> dict[str, LimitDefinition]:  # noqa: ANN001
    rows = db.execute(
        select(LimitDefinition).where(
            LimitDefinition.tenant_id == DEMO_TENANT_ID,
            LimitDefinition.target_run_type == "CONCENTRATION",
        )
    ).scalars()
    return {r.code: r for r in rows}


def test_five_concentration_limits_exist_in_the_expected_lifecycle_states(db) -> None:  # noqa: ANN001
    limits = _limits(db)
    assert set(limits) == _ISSUER_NAMED | _NOT_ISSUER_NAMED
    # Four approved through the maker-checker gate; the fifth left DRAFT deliberately, because a
    # limit awaiting sign-off constrains nothing and the approval queue needs content.
    assert {c for c, x in limits.items() if x.status == "ACTIVE"} == {
        "DEMO-ISSUER-CEIL",
        "DEMO-ISSUER-HEADROOM",
        "DEMO-SECTOR-CEIL",
        "DEMO-HHI-CEIL",
    }
    assert limits["DEMO-ISSUER-PROPOSED"].status == "DRAFT"


def test_every_threshold_was_DERIVED_from_the_measured_number(db, staged) -> None:  # noqa: ANN001
    """The thresholds must be arithmetic on what the run actually computed, not literals. A demo
    whose numbers are invented proves nothing about the platform that produced them."""
    _factory, summary = staged
    if summary is None:
        pytest.skip(
            "stage already seeded in this database; the derivation is asserted on a fresh run"
        )
    limits = _limits(db)
    issuer = Decimal(summary.measured_issuer_share)
    sector = Decimal(summary.measured_sector_share)
    hhi = Decimal(summary.measured_hhi)

    assert Decimal(limits["DEMO-ISSUER-CEIL"].threshold_value) == (issuer / 2).quantize(
        Decimal("0.000001")
    )
    assert Decimal(limits["DEMO-SECTOR-CEIL"].threshold_value) == (sector / 2).quantize(
        Decimal("0.000001")
    )
    assert Decimal(limits["DEMO-HHI-CEIL"].threshold_value) == (hhi / 2).quantize(
        Decimal("0.000001")
    )
    # The headroom limit sits HALFWAY to 1, not at double the share. Executing the stage is what
    # forced that rule: doubling a 0.60 share produced a 0.999999 ceiling no share can ever exceed,
    # i.e. a limit that renders green for a reason having nothing to do with the book.
    headroom = Decimal(limits["DEMO-ISSUER-HEADROOM"].threshold_value)
    assert headroom == (issuer + (Decimal(1) - issuer) / 2).quantize(Decimal("0.000001"))
    assert issuer < headroom < Decimal(1), "the headroom ceiling must be reachable, not degenerate"


def test_three_breaches_were_DETECTED_and_are_self_describing(db) -> None:  # noqa: ANN001
    """Read the breach rows, not the stage's count. Each must carry the LIM-2 echo set, which is
    what makes a breach reproducible from its own row months later."""
    breaches = list(
        db.execute(
            select(Breach).where(
                Breach.tenant_id == DEMO_TENANT_ID, Breach.target_run_type == "CONCENTRATION"
            )
        ).scalars()
    )
    assert len(breaches) == 3
    by_metric = {b.metric_type for b in breaches}
    assert by_metric == {"SHARE", "HHI_ISSUER"}

    for b in breaches:
        assert b.dimension_kind in {"ISSUER", "SECTOR_INDUSTRY"}
        assert b.denominator_basis == "INVESTED_LONG"
        assert b.scope_portfolio_id is not None, "the scope echo (the paid LOW) must be populated"
        assert Decimal(b.observed_value) > Decimal(b.threshold_value), "an ABOVE breach"

    sector = next(b for b in breaches if b.dimension_kind == "SECTOR_INDUSTRY")
    # A classification breach records WHICH taxonomy produced the number it breached on — the pair
    # (authored on the limit, resolved on the breach) is what makes scheme drift provable later.
    assert sector.scheme_family is not None
    assert sector.resolved_scheme_id is not None
    # ISSUER rows carry no scheme, by CON-1's grain.
    for b in breaches:
        if b.dimension_kind == "ISSUER":
            assert b.scheme_family is None and b.resolved_scheme_id is None


def test_the_healthy_limit_did_NOT_breach(db) -> None:  # noqa: ANN001
    """The positive control for the three breaches above: if EVERY limit breached, the fixture
    would prove the evaluator fires, not that it discriminates."""
    limits = _limits(db)
    healthy_id = limits["DEMO-ISSUER-HEADROOM"].id
    count = db.execute(
        select(func.count())
        .select_from(Breach)
        .where(Breach.tenant_id == DEMO_TENANT_ID, Breach.limit_definition_id == healthy_id)
    ).scalar_one()
    assert count == 0


def test_the_issuer_fence_holds_on_both_read_surfaces(db) -> None:  # noqa: ANN001
    """The fence keys on issuer IDENTITY, not on the concentration family — with the positive
    control in the same test, without which a broken read would pass as a fence."""
    fenced = {x.code for x in list_limits(db, acting_tenant=DEMO_TENANT_ID)}
    assert not (_ISSUER_NAMED & fenced), "issuer-named limits leaked to an unfenced list read"
    assert _NOT_ISSUER_NAMED <= fenced, "the fence hid non-issuer limits — it is filtering family"

    health = {h.code for h in limit_health(db, acting_tenant=DEMO_TENANT_ID)}
    assert not (_ISSUER_NAMED & health), "issuer-named limits leaked to the health surface"

    unfenced = {
        x.code for x in list_limits(db, acting_tenant=DEMO_TENANT_ID, include_issuer_detail=True)
    }
    assert _ISSUER_NAMED <= unfenced, "a holder of concentration.issuer.view must still see them"


def test_a_regulatory_shaped_threshold_was_REFUSED(db, staged) -> None:  # noqa: ANN001
    """The CON-1 descope made visible: no NAV denominator is computable on this schema, so a
    UCITS-shaped limit cannot be written at all. Asserted as a refusal the stage OBSERVED, and
    corroborated by the absence of any such row."""
    _factory, summary = staged
    if summary is not None:
        assert "NAV" in summary.regulatory_threshold_refused
        assert "not a computable basis" in summary.regulatory_threshold_refused
    assert (
        db.execute(
            select(func.count())
            .select_from(LimitDefinition)
            .where(
                LimitDefinition.tenant_id == DEMO_TENANT_ID,
                LimitDefinition.code.like("DEMO-UCITS%"),
            )
        ).scalar_one()
        == 0
    )


def test_the_final_position_count_pin_is_UNCHANGED(db) -> None:  # noqa: ANN001
    """26/41/136, relayed from the CON-1 suite. LIM-2 adds limits and breaches, which are none of
    these things — so the triple must be IDENTICAL. A slice that moved one of these counts without
    intending to would be a defect, and this is where it surfaces."""
    model_codes = db.execute(
        select(func.count()).select_from(Model).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    validations = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    completed = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.status == RunStatus.COMPLETED.value,
        )
    ).scalar_one()
    assert (model_codes, validations, completed) == (26, 41, 136)
