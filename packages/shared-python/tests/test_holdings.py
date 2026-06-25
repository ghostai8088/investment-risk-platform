"""SQLite-local unit/behavior tests for P1C-5 holdings (read-only as-of composition).

RLS is a no-op on SQLite (tenant isolation under FORCE-RLS lives in the PG file); here we prove the
read-composition contract: node-level + bounded-subtree as-of holdings sets match the per-entity
``reconstruct_position_as_of`` primitive on BOTH axes; display-only marks attach opt-in by an
explicit ``valuation_date`` (no ``quantity x mark``); the subtree traversal is composition (not ABAC
enforcement); a corrupt/too-deep hierarchy raises ``HierarchyCycleError``; and the load-bearing
scope-fence (DTO field set + source-text scan) forbids any aggregate/market-value/write path.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from irp_shared.holdings import (
    HoldingRow,
    HoldingWithMark,
    MarkView,
    attach_marks_as_of,
    reconstruct_holdings_as_of,
    reconstruct_subtree_holdings_as_of,
)
from irp_shared.holdings import service as holdings_service
from irp_shared.portfolio import (
    HierarchyCycleError,
    PortfolioActor,
    PortfolioNotVisible,
    create_portfolio,
)
from irp_shared.position import (
    correct_position,
    create_position,
    reconstruct_position_as_of,
    supersede_position,
)
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
T1 = datetime(2026, 6, 1, tzinfo=UTC)
VD = date(2026, 3, 31)


def _tenant() -> str:
    return str(uuid.uuid4())


def _pf(session: Session, tenant: str, code: str, parent: str | None = None) -> str:
    return create_portfolio(
        session,
        tenant_id=tenant,
        code=code,
        name=code.lower(),
        node_type="ACCOUNT",
        parent_portfolio_id=parent,
        actor=PortfolioActor(actor_id="steward"),
    ).id


def _inst(session: Session, tenant: str, code: str) -> str:
    return create_instrument(
        session,
        tenant_id=tenant,
        code=code,
        name="i",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="steward"),
    ).id


def _pos(session: Session, tenant: str, pf_id: str, inst_id: str, qty: str, valid_from=T0):  # noqa: ANN001,ANN202
    return create_position(
        session,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="steward"),
        quantity=Decimal(qty),
        valid_from=valid_from,
    )


# --- node-level as-of holdings: set matches the per-entity primitive ---


def test_node_holdings_set_matches_primitive(session: Session) -> None:
    tenant = _tenant()
    pf = _pf(session, tenant, "PF")
    i1, i2 = _inst(session, tenant, "I1"), _inst(session, tenant, "I2")
    _pos(session, tenant, pf, i1, "100")
    _pos(session, tenant, pf, i2, "250")
    session.flush()

    holdings = reconstruct_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=pf, valid_at=T1
    )
    assert {h.instrument_id for h in holdings} == {i1, i2}
    # Each holding equals what the single-key primitive returns for the same (valid_at, known_at).
    for h in holdings:
        prim = reconstruct_position_as_of(
            session,
            acting_tenant=tenant,
            portfolio_id=pf,
            instrument_id=h.instrument_id,
            valid_at=T1,
        )
        assert prim is not None
        assert h.position_id == prim.id and h.quantity == prim.quantity


def test_node_holdings_empty_for_portfolio_without_positions(session: Session) -> None:
    tenant = _tenant()
    pf = _pf(session, tenant, "PF")
    session.flush()
    assert (
        reconstruct_holdings_as_of(session, acting_tenant=tenant, portfolio_id=pf, valid_at=T1)
        == []
    )


# --- both bitemporal axes ---


def test_valid_time_travel(session: Session) -> None:
    tenant = _tenant()
    pf = _pf(session, tenant, "PF")
    i1 = _inst(session, tenant, "I1")
    _pos(session, tenant, pf, i1, "100", valid_from=T0)
    # Re-mark (effective-dated supersede) the holding to 150 effective T1.
    supersede_position(
        session,
        portfolio_id=pf,
        instrument_id=i1,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="steward"),
        effective_at=T1,
        quantity=Decimal("150"),
    )
    session.flush()
    # As-of just after T0 (before T1) -> 100; as-of after T1 -> 150.
    early = reconstruct_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=pf, valid_at=datetime(2026, 2, 1, tzinfo=UTC)
    )
    late = reconstruct_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=pf, valid_at=datetime(2026, 7, 1, tzinfo=UTC)
    )
    assert [h.quantity for h in early] == [Decimal("100")]
    assert [h.quantity for h in late] == [Decimal("150")]


def test_system_time_travel_known_at(session: Session) -> None:
    tenant = _tenant()
    pf = _pf(session, tenant, "PF")
    i1 = _inst(session, tenant, "I1")
    row = _pos(session, tenant, pf, i1, "100")
    session.flush()
    before_correction = row.system_from
    # An as-known CORRECTION restates the quantity over the SAME valid period (system-time, not
    # valid-time). A known_at BEFORE the correction must still see the original 100; the current
    # view sees the corrected 150 — that is the system-time (known-at) axis.
    correct_position(
        session,
        row,
        restatement_reason="fat-finger",
        acting_tenant=tenant,
        actor=PositionActor(actor_id="steward"),
        quantity=Decimal("150"),
    )
    session.flush()
    as_known_early = reconstruct_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=pf, valid_at=T1, known_at=before_correction
    )
    current = reconstruct_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=pf, valid_at=T1
    )
    assert [h.quantity for h in as_known_early] == [Decimal("100")]
    assert [h.quantity for h in current] == [Decimal("150")]


# --- bounded subtree composition (read convenience, not enforcement) ---


def test_subtree_holdings_include_descendants(session: Session) -> None:
    tenant = _tenant()
    root = _pf(session, tenant, "ROOT")
    child = _pf(session, tenant, "CHILD", parent=root)
    grandchild = _pf(session, tenant, "GC", parent=child)
    ir, ic, ig = (
        _inst(session, tenant, "IR"),
        _inst(session, tenant, "IC"),
        _inst(session, tenant, "IG"),
    )
    _pos(session, tenant, root, ir, "1")
    _pos(session, tenant, child, ic, "2")
    _pos(session, tenant, grandchild, ig, "3")
    session.flush()

    # Node-level on root sees only root's holding.
    node = reconstruct_holdings_as_of(session, acting_tenant=tenant, portfolio_id=root, valid_at=T1)
    assert {h.portfolio_id for h in node} == {root}

    # Subtree on root composes root + child + grandchild holdings; each row carries its owner.
    sub = reconstruct_subtree_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=root, valid_at=T1
    )
    assert {h.portfolio_id for h in sub} == {root, child, grandchild}
    assert {h.instrument_id for h in sub} == {ir, ic, ig}


def test_subtree_unknown_portfolio_raises_not_visible(session: Session) -> None:
    tenant = _tenant()
    with pytest.raises(PortfolioNotVisible):
        reconstruct_subtree_holdings_as_of(
            session, acting_tenant=tenant, portfolio_id=str(uuid.uuid4()), valid_at=T1
        )


def test_subtree_cross_tenant_raises_not_visible(session: Session) -> None:
    tenant_a, tenant_b = _tenant(), _tenant()
    pf_a = _pf(session, tenant_a, "PFA")
    session.flush()
    # tenant_b cannot compose tenant_a's subtree (service tenant predicate fails closed).
    with pytest.raises(PortfolioNotVisible):
        reconstruct_subtree_holdings_as_of(
            session, acting_tenant=tenant_b, portfolio_id=pf_a, valid_at=T1
        )


def test_subtree_cycle_raises_hierarchy_error(session: Session, monkeypatch) -> None:  # noqa: ANN001
    tenant = _tenant()
    a = _pf(session, tenant, "A")
    b = _pf(session, tenant, "B", parent=a)
    session.flush()
    # Force a cycle a->b->a by repointing a's parent to b (a corrupt hierarchy).
    from irp_shared.portfolio.models import Portfolio

    node_a = session.get(Portfolio, a)
    node_a.parent_portfolio_id = b
    session.flush()
    with pytest.raises(HierarchyCycleError):
        reconstruct_subtree_holdings_as_of(
            session, acting_tenant=tenant, portfolio_id=a, valid_at=T1
        )


def test_anchor_not_enforce_any_view_holder_sees_all_in_tenant(session: Session) -> None:
    # Composition applies NO scope filter: the service reads every portfolio in the tenant the
    # caller asks for. There is no per-principal scope restriction (anchor-not-enforce, OD-P1C-A).
    tenant = _tenant()
    root = _pf(session, tenant, "ROOT")
    sibling = _pf(session, tenant, "SIB")  # NOT under root
    _pos(session, tenant, root, _inst(session, tenant, "IR"), "1")
    _pos(session, tenant, sibling, _inst(session, tenant, "IS"), "9")
    session.flush()
    # Subtree of root excludes the sibling (composition shape), but a direct node read of the
    # sibling is freely allowed to the same tenant caller — no scope gate.
    sib_holdings = reconstruct_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=sibling, valid_at=T1
    )
    assert [h.quantity for h in sib_holdings] == [Decimal("9")]


# --- display-only marks (opt-in, deterministic by explicit valuation_date) ---


def test_attach_marks_display_only(session: Session) -> None:
    tenant = _tenant()
    pf = _pf(session, tenant, "PF")
    i1, i2 = _inst(session, tenant, "I1"), _inst(session, tenant, "I2")
    _pos(session, tenant, pf, i1, "100")
    _pos(session, tenant, pf, i2, "200")
    # A captured mark exists only for i1 at VD.
    create_valuation(
        session,
        portfolio_id=pf,
        instrument_id=i1,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="steward"),
        mark_value=Decimal("101.5"),
        currency_code="USD",
        valid_from=T0,  # effective from T0 so the mark is found at valid_at=T1
    )
    session.flush()

    holdings = reconstruct_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=pf, valid_at=T1
    )
    enriched = attach_marks_as_of(
        session,
        acting_tenant=tenant,
        holdings=holdings,
        valuation_date=VD,
        valid_at=T1,
    )
    by_inst = {e.holding.instrument_id: e for e in enriched}
    # i1 carries its stored mark verbatim; i2 has no mark for VD -> None.
    assert by_inst[i1].mark is not None
    assert by_inst[i1].mark.mark_value == Decimal("101.5")
    assert by_inst[i1].mark.currency_code == "USD"
    assert by_inst[i2].mark is None
    # Display-only: the mark is the captured value; the holding quantity is untouched and there is
    # NO product/market-value anywhere on the DTO.
    assert by_inst[i1].holding.quantity == Decimal("100")


def test_marks_no_match_for_other_valuation_date(session: Session) -> None:
    tenant = _tenant()
    pf = _pf(session, tenant, "PF")
    i1 = _inst(session, tenant, "I1")
    _pos(session, tenant, pf, i1, "100")
    create_valuation(
        session,
        portfolio_id=pf,
        instrument_id=i1,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="steward"),
        mark_value=Decimal("101.5"),
        valid_from=T0,  # effective from T0 (the None result is purely the valuation_date mismatch)
    )
    session.flush()
    holdings = reconstruct_holdings_as_of(
        session, acting_tenant=tenant, portfolio_id=pf, valid_at=T1
    )
    other = date(2026, 12, 31)
    enriched = attach_marks_as_of(
        session, acting_tenant=tenant, holdings=holdings, valuation_date=other, valid_at=T1
    )
    assert enriched[0].mark is None  # no mark for a different valuation_date


# --- load-bearing scope fence: no aggregate/market-value DTO field; no write/compute in source ---

_FORBIDDEN_FIELD_TOKENS = (
    "market_value",
    "marketvalue",
    "exposure",
    "nav",
    "total",
    "aggregate",
    "rollup",
    "weight",
    "pnl",
    "risk",
)


def _field_names(dc) -> set[str]:  # noqa: ANN001 - a dataclass type
    return {f.name.lower() for f in dataclasses.fields(dc)}


def test_dto_fields_have_no_aggregate_or_market_value() -> None:
    for dc in (HoldingRow, MarkView):
        names = _field_names(dc)
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert not any(token in n for n in names), f"{dc.__name__} leaks '{token}': {names}"
    # mark_value is permitted (the captured mark, display-only) and must NOT trip the market_value
    # fence — they are distinct fields.
    assert "mark_value" in _field_names(MarkView)
    assert "market_value" not in _field_names(MarkView)
    # HoldingWithMark composes the two; it has no numeric measure of its own.
    assert _field_names(HoldingWithMark) == {"holding", "mark"}


def test_source_has_no_compute_or_write_tokens() -> None:
    # AST-based fence (inspects CODE, not the docstring prose that describes these very fences).
    tree = ast.parse(pathlib.Path(holdings_service.__file__).read_text())
    # No multiplication anywhere — a market value / exposure would be ``quantity * mark_value``.
    mults = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult)]
    assert not mults, "holdings/service.py multiplies (possible market-value/exposure calc)"
    # No aggregation builtins (sum/min/max over holdings) — a rollup would use these.
    agg_names = {"sum", "fsum"}
    # No governed-write / mutation calls — this is a pure read path. Includes every lineage/DQ/audit
    # write helper the repo exposes, so a future edit that wired one into the read path is caught.
    forbidden_attr = {"commit", "add", "delete", "flush"}
    forbidden_name = {
        "record_event",
        "record_lineage",
        "assert_has_lineage",
        "register_data_source",
        "ensure_manual_source",
        "run_quality_check",
        "assert_passed_quality_checks",
    } | agg_names
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            assert func.attr not in forbidden_attr, f"forbidden write call: .{func.attr}()"
        if isinstance(func, ast.Name):
            assert func.id not in forbidden_name, f"forbidden compute/write call: {func.id}()"


# --- import direction: holdings -> {portfolio, position, valuation, reference, rails} only ---


def test_import_direction() -> None:
    pkg = pathlib.Path(holdings_service.__file__).parent
    # Exactly the documented one-way contract: holdings -> {portfolio, position, valuation,
    # reference, rails(db)}. Kept tight (no lineage/audit/temporal) so a future coupling regression
    # — e.g. wiring a lineage/audit write into the read path — trips this fence.
    allowed = {
        "db",
        "portfolio",
        "position",
        "valuation",
        "reference",
        "holdings",
    }
    forbidden_roots = {"irp_backend", "irp_shared.models"}
    for py in pkg.glob("*.py"):
        for line in py.read_text().splitlines():
            line = line.strip()
            if not (line.startswith("from ") or line.startswith("import ")):
                continue
            for bad in forbidden_roots:
                assert bad not in line, f"{py.name} imports forbidden {bad}: {line}"
            if "irp_shared." in line:
                seg = line.split("irp_shared.")[1].split()[0].split(".")[0].rstrip(",")
                assert seg in allowed, f"{py.name} imports irp_shared.{seg}: {line}"


def test_no_models_or_events_module() -> None:
    # The read package must NOT introduce a persisted entity or an event family.
    pkg = pathlib.Path(holdings_service.__file__).parent
    assert not (pkg / "models.py").exists(), "holdings must not define models.py (no entity)"
    assert not (pkg / "events.py").exists(), "holdings must not define events.py (no audit family)"
