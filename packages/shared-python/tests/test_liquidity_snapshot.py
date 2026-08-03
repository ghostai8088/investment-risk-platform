"""The `build_liquidity_snapshot` pre-build refusals, each made to FIRE (P9).

The Wave-14 close's strongest survivor — found independently by two lanes and it survived all six
refutation attempts: the builder declares four refusals (wrong-dimension scheme, mixed live scheme
VERSIONS, mixed basis, empty atoms) and **no test anywhere referenced any of them**. The project
has shipped a structurally unfireable refusal before (CON-1's mixed-VERSION, as ratified), which
is exactly why "the refusal exists in the source" is not evidence.

Every refusal here is executed against real staged state, and every one asserts NOTHING was
persisted — a refusal that leaves a half-built snapshot behind is worse than none.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.classification.models import (
    DIMENSION_KIND_LIQUIDITY_TIER,
    DIMENSION_KIND_SECTOR_INDUSTRY,
    SCHEME_FAMILY_SEC_22E4,
    ClassificationAssignment,
)
from irp_shared.classification.service import (
    ClassificationActor,
    capture_assignment,
    create_node,
    create_scheme,
)
from irp_shared.exposure.models import ExposureAggregate
from irp_shared.snapshot.events import SnapshotActor
from irp_shared.snapshot.models import DatasetSnapshot
from irp_shared.snapshot.service import (
    LiquiditySnapshotError,
    build_liquidity_snapshot,
    list_components,
)

TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_NOW = datetime(2026, 5, 18, tzinfo=UTC)


def _actor() -> ClassificationActor:
    return ClassificationActor(tenant_id=TENANT, actor_id="steward")


def _snap_actor() -> SnapshotActor:
    return SnapshotActor(actor_id="steward", actor_type="user")


def _ladder(session: Session, version: str = "2024"):  # noqa: ANN202
    scheme = create_scheme(
        session,
        actor=_actor(),
        scheme_family=SCHEME_FAMILY_SEC_22E4,
        version_label=version,
        name=f"SEC 22e-4 ({version})",
        dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
        authority="SEC",
    )
    create_node(
        session, actor=_actor(), scheme_id=scheme.id, code="ILLIQUID", name="Illiquid", level=1
    )
    return scheme


def _parent_snapshot(session: Session) -> DatasetSnapshot:
    snap = DatasetSnapshot(
        tenant_id=TENANT,
        label="staged",
        purpose="EXPOSURE_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_NOW.date(),
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="staged",
    )
    session.add(snap)
    session.flush()
    return snap


def _exposure_run(session: Session, instrument_id: str | None) -> CalculationRun:
    """A COMPLETED exposure run; one staged atom when ``instrument_id`` is given, none otherwise."""
    run = CalculationRun(
        tenant_id=TENANT,
        run_type="EXPOSURE_AGGREGATE",
        status="COMPLETED",
        initiated_by="t",
        scope_portfolio_id=str(uuid.uuid4()),
    )
    session.add(run)
    session.flush()
    if instrument_id is not None:
        session.add(
            ExposureAggregate(
                tenant_id=TENANT,
                calculation_run_id=run.run_id,
                input_snapshot_id=_parent_snapshot(session).id,
                portfolio_id=run.scope_portfolio_id,
                instrument_id=instrument_id,
                base_currency="USD",
                mark_currency="USD",
                signed_quantity=Decimal("100"),
                mark_value=Decimal("100"),
                fx_rate=Decimal("1"),
                fx_legs=json.dumps([]),
                exposure_amount=Decimal("10000"),
                exposure_type="MARKET_VALUE",
            )
        )
        session.flush()
    return run


def _snapshot_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(DatasetSnapshot)).scalar_one()


def _build(session: Session, run: CalculationRun, scheme_id: str) -> DatasetSnapshot:
    return build_liquidity_snapshot(
        session,
        acting_tenant=TENANT,
        actor=_snap_actor(),
        exposure_run_id=str(run.run_id),
        scheme_id=str(scheme_id),
    )


def test_the_happy_path_pins_all_three_shapes(session: Session) -> None:
    scheme = _ladder(session)
    instrument = str(uuid.uuid4())
    capture_assignment(
        session,
        actor=_actor(),
        entity_type="instrument",
        entity_id=instrument,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
        node_code="ILLIQUID",
    )
    run = _exposure_run(session, instrument)
    snap = _build(session, run, scheme.id)
    kinds = sorted(
        c.component_kind
        for c in list_components(session, snapshot_id=str(snap.id), acting_tenant=TENANT)
    )
    assert kinds == ["CLASSIFICATION", "CLASSIFICATION_SCHEME", "EXPOSURE"]


def test_a_scheme_of_the_WRONG_DIMENSION_refuses_with_nothing_persisted(session: Session) -> None:
    """Refusal 1: an ISIC sector scheme handed to the liquidity builder is not a ladder."""
    sector = create_scheme(
        session,
        actor=_actor(),
        scheme_family="ISIC",
        version_label="Rev. 5",
        name="ISIC",
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        authority="UNSD",
    )
    run = _exposure_run(session, str(uuid.uuid4()))
    before = _snapshot_count(session)
    with pytest.raises(LiquiditySnapshotError, match="not a ladder"):
        _build(session, run, sector.id)
    assert _snapshot_count(session) == before, "the refusal left a snapshot behind"


def test_MIXED_LIVE_SCHEME_VERSIONS_refuse_over_the_live_book(session: Session) -> None:
    """Refusal 2 — the inherited CON-1 class, which this platform once shipped UNFIREABLE.

    Two live ladder versions, the pinned instrument assigned under BOTH (different scheme_id =
    different logical key, so both heads are legitimately open). Tiering one version while the
    other's assignments read UNCLASSIFIED silently moves the illiquid share, so the build refuses
    over the LIVE book — never over the pinned set, which is scheme-filtered and can never hold
    the second version (the exact wording that made CON-1's ratified discriminator unfireable).
    """
    v2024 = _ladder(session, "2024")
    v2025 = _ladder(session, "2025")
    instrument = str(uuid.uuid4())
    for scheme in (v2024, v2025):
        capture_assignment(
            session,
            actor=_actor(),
            entity_type="instrument",
            entity_id=instrument,
            scheme_id=scheme.id,
            dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
            node_code="ILLIQUID",
        )
    run = _exposure_run(session, instrument)
    before = _snapshot_count(session)
    with pytest.raises(LiquiditySnapshotError, match="mixed live scheme VERSIONS"):
        _build(session, run, v2024.id)
    assert _snapshot_count(session) == before


def test_MIXED_BASIS_refuses_even_when_only_hostile_writes_could_produce_it(
    session: Session,
) -> None:
    """Refusal 3, defence-in-depth: the binder's vocabulary admits only NOT_APPLICABLE for the
    liquidity kind, so a mixed-basis state cannot arise through `capture_assignment` — the hostile
    row is INJECTED directly, which is precisely the write path this refusal exists to survive.
    A guard reachable only via the binder that already refuses is vacuous; this one is not."""
    scheme = _ladder(session)
    instrument = str(uuid.uuid4())
    capture_assignment(
        session,
        actor=_actor(),
        entity_type="instrument",
        entity_id=instrument,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
        node_code="ILLIQUID",
    )
    hostile = str(uuid.uuid4())
    session.add(
        ClassificationAssignment(
            tenant_id=TENANT,
            entity_type="instrument",
            entity_id=hostile,
            scheme_id=str(scheme.id),
            dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
            node_code="ILLIQUID",
            basis="ULTIMATE_RISK",  # the binder refuses this; a raw write does not
            valid_from=_NOW,
        )
    )
    session.flush()
    run = _exposure_run(session, instrument)
    # the hostile instrument must carry exposure too, or its assignment is never in scope
    session.add(
        ExposureAggregate(
            tenant_id=TENANT,
            calculation_run_id=run.run_id,
            input_snapshot_id=_parent_snapshot(session).id,
            portfolio_id=run.scope_portfolio_id,
            instrument_id=hostile,
            base_currency="USD",
            mark_currency="USD",
            signed_quantity=Decimal("1"),
            mark_value=Decimal("1"),
            fx_rate=Decimal("1"),
            fx_legs=json.dumps([]),
            exposure_amount=Decimal("1"),
            exposure_type="MARKET_VALUE",
        )
    )
    session.flush()
    before = _snapshot_count(session)
    with pytest.raises(LiquiditySnapshotError, match="mixed basis"):
        _build(session, run, scheme.id)
    assert _snapshot_count(session) == before


def test_EMPTY_ATOMS_refuse_with_nothing_persisted(session: Session) -> None:
    """Refusal 4: an exposure run with no visible atoms has nothing to pin."""
    scheme = _ladder(session)
    run = _exposure_run(session, None)
    before = _snapshot_count(session)
    with pytest.raises(LiquiditySnapshotError, match="no visible atoms"):
        _build(session, run, scheme.id)
    assert _snapshot_count(session) == before
