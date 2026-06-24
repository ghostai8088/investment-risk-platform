"""SQLite-local unit/behavior tests for P1C-1 portfolio hierarchy (REQ-PPM-001).

RLS is a no-op on SQLite, so symmetric-isolation proofs live in the PG test file; here we prove the
governed-write contract (PORTFOLIO.CREATE + MANUAL ORIGIN lineage; PORTFOLIO.UPDATE, no new edge),
the EV temporal class (no system_from), the controlled-vocab + UNIQUE(tenant_id, code), the
tenant-filtered cross-tenant fail-closed (which MUST hold on SQLite too), the bounded cycle-safe
ancestor + descendant resolvers (self-parent reject; planted cycle; depth cap; re-parent cycle
guard), the fail-closed audit rollback, the import direction, and the anchor-not-enforce scope
fence.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import assert_has_lineage
from irp_shared.portfolio import (
    MAX_HIERARCHY_DEPTH,
    HierarchyCycleError,
    Portfolio,
    PortfolioActor,
    PortfolioNotVisible,
    create_portfolio,
    resolve_descendants,
    resolve_ultimate_parent,
    update_portfolio,
)
from irp_shared.temporal import TemporalClass


def _tenant() -> str:
    return str(uuid.uuid4())


def _actor() -> PortfolioActor:
    return PortfolioActor(actor_id="steward")


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _node(session: Session, tenant: str, code: str, node_type: str = "FUND", **kw) -> Portfolio:  # noqa: ANN003
    return create_portfolio(
        session, tenant_id=tenant, code=code, name=code, node_type=node_type, actor=_actor(), **kw
    )


# --- temporal class: EV, no FR/system_from, single status (no is_active) ---


def test_portfolio_is_effective_dated_no_fr() -> None:
    assert Portfolio.__temporal_class__ == TemporalClass.EFFECTIVE_DATED
    assert hasattr(Portfolio, "valid_from") and hasattr(Portfolio, "record_version")
    assert not hasattr(Portfolio, "system_from")  # not IA/FR
    assert not hasattr(Portfolio, "is_active")  # single status flag


def test_portfolio_holds_nothing_scope_fence() -> None:
    # A portfolio is an empty hierarchy node: NO position/valuation/holding/exposure/market column.
    cols = set(Portfolio.__table__.columns.keys())
    forbidden = {
        "position",
        "valuation",
        "holding",
        "market_value",
        "quantity",
        "exposure",
        "price",
        "nav",
    }
    assert not (forbidden & cols), f"portfolio leaks domain columns: {forbidden & cols}"


# --- governed-write contract: lineage + audit ---


def test_create_records_lineage_and_audit(session: Session) -> None:
    tenant = _tenant()
    node = _node(session, tenant, "P1", node_type="PORTFOLIO", base_currency_code="USD")
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == node.id)
    ).scalar_one()
    assert edge.target_entity_type == "portfolio" and edge.edge_kind == "ORIGIN"
    source = session.get(DataSource, edge.source_id)
    assert source is not None and source.source_type == "MANUAL"
    assert_has_lineage(session, "portfolio", node.id, tenant_id=tenant)
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == node.id)).scalar_one()
    assert ev.event_type == "PORTFOLIO.CREATE" and ev.entity_type == "portfolio"
    assert ev.action == "create"
    assert verify_chain(session, tenant).ok is True


def test_update_emits_update_no_new_edge(session: Session) -> None:
    tenant = _tenant()
    node = _node(session, tenant, "P1")
    update_portfolio(session, node, actor=_actor(), name="Renamed", status="CLOSED")
    assert node.name == "Renamed" and node.status == "CLOSED" and node.record_version == 2
    assert _events(session, "PORTFOLIO.UPDATE") == 1
    # EV amend roots NO new lineage edge — still exactly one ORIGIN edge from create.
    n_edges = session.execute(
        select(func.count()).select_from(LineageEdge).where(LineageEdge.target_entity_id == node.id)
    ).scalar_one()
    assert n_edges == 1


def _raise_audit(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
    raise RuntimeError("audit boom")


def test_create_rolls_back_no_orphan(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    # CTRL-032 fail-closed: if record_event raises, the WHOLE co-transactional unit (portfolio row +
    # lazily-created MANUAL data_source + ORIGIN edge + audit event) rolls back — no orphan.
    import irp_shared.portfolio.service as svc

    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        _node(session, _tenant(), "P1")
    session.rollback()
    for model in (Portfolio, LineageEdge, DataSource, AuditEvent):
        assert session.execute(select(func.count()).select_from(model)).scalar_one() == 0


def test_unique_tenant_code(session: Session) -> None:
    tenant = _tenant()
    _node(session, tenant, "DUP")
    with pytest.raises(IntegrityError):
        _node(session, tenant, "DUP")
    session.rollback()


def test_non_updatable_attribute_rejected(session: Session) -> None:
    tenant = _tenant()
    node = _node(session, tenant, "P1")
    with pytest.raises(ValueError, match="non-updatable"):
        update_portfolio(session, node, actor=_actor(), code="NEWCODE")  # code is immutable


# --- hierarchy: adjacency + bounded cycle-safe resolvers ---


def test_resolve_cross_tenant_parent_fails_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    b_node = _node(session, b, "B_ROOT", node_type="PORTFOLIO")
    session.commit()
    # creating a child in tenant a under tenant b's node fails closed at the service layer.
    with pytest.raises(PortfolioNotVisible):
        create_portfolio(
            session,
            tenant_id=a,
            code="A_CHILD",
            name="c",
            node_type="FUND",
            actor=_actor(),
            parent_portfolio_id=b_node.id,
        )
    session.rollback()


def test_self_parent_rejected(session: Session) -> None:
    tenant = _tenant()
    node = _node(session, tenant, "P1")
    with pytest.raises(ValueError, match="cannot be its own parent"):
        update_portfolio(session, node, actor=_actor(), parent_portfolio_id=node.id)


def test_resolve_ultimate_parent_walks_to_root(session: Session) -> None:
    tenant = _tenant()
    root = _node(session, tenant, "ROOT", node_type="PORTFOLIO")
    fund = _node(session, tenant, "FUND", parent_portfolio_id=root.id)
    acct = _node(session, tenant, "ACCT", node_type="ACCOUNT", parent_portfolio_id=fund.id)
    assert resolve_ultimate_parent(session, acct, acting_tenant=tenant) == root.id
    assert resolve_ultimate_parent(session, root, acting_tenant=tenant) == root.id


def test_resolve_descendants_subtree(session: Session) -> None:
    tenant = _tenant()
    root = _node(session, tenant, "ROOT", node_type="PORTFOLIO")
    f1 = _node(session, tenant, "F1", parent_portfolio_id=root.id)
    f2 = _node(session, tenant, "F2", parent_portfolio_id=root.id)
    a1 = _node(session, tenant, "A1", node_type="ACCOUNT", parent_portfolio_id=f1.id)
    desc_ids = {n.id for n in resolve_descendants(session, root, acting_tenant=tenant)}
    assert desc_ids == {f1.id, f2.id, a1.id}
    # a leaf has an empty subtree.
    assert resolve_descendants(session, a1, acting_tenant=tenant) == []


def test_descendants_tenant_bounded(session: Session) -> None:
    # A subtree never reaches another tenant's nodes even when a cross-tenant child edge is planted
    # (the per-hop `tenant_id == acting_tenant` predicate excludes it; RLS is the PG backstop).
    a, b = _tenant(), _tenant()
    a_root = _node(session, a, "A_ROOT", node_type="PORTFOLIO")
    b_child = _node(session, b, "B_CHILD")  # tenant b node
    # plant a cross-tenant edge at the row level (bypassing the binder guard): b_child claims a_root
    # as its parent. resolve_descendants MUST still exclude it (the tenant filter on every hop).
    b_child.parent_portfolio_id = a_root.id
    session.flush()
    assert resolve_descendants(session, a_root, acting_tenant=a) == []


def test_cycle_rejected_in_descendants(session: Session) -> None:
    tenant = _tenant()
    n1 = _node(session, tenant, "N1", node_type="PORTFOLIO")
    n2 = _node(session, tenant, "N2", parent_portfolio_id=n1.id)
    # Force a cycle directly at the row level (bypassing the binder guard) to prove the resolver
    # visited-set catches it rather than looping forever.
    n1.parent_portfolio_id = n2.id
    session.flush()
    with pytest.raises(HierarchyCycleError):
        resolve_descendants(session, n1, acting_tenant=tenant)
    with pytest.raises(HierarchyCycleError):
        resolve_ultimate_parent(session, n1, acting_tenant=tenant)


def test_reparent_cycle_rejected(session: Session) -> None:
    tenant = _tenant()
    root = _node(session, tenant, "ROOT", node_type="PORTFOLIO")
    child = _node(session, tenant, "CHILD", parent_portfolio_id=root.id)
    # re-parenting the root under its own child would create a cycle -> rejected, no write.
    with pytest.raises(HierarchyCycleError):
        update_portfolio(session, root, actor=_actor(), parent_portfolio_id=child.id)


def test_depth_cap_enforced(session: Session) -> None:
    tenant = _tenant()
    nodes = [_node(session, tenant, "D0", node_type="PORTFOLIO")]
    for i in range(1, MAX_HIERARCHY_DEPTH + 3):
        nodes.append(_node(session, tenant, f"D{i}", parent_portfolio_id=nodes[-1].id))
    # ancestor walk from the deepest node exceeds the cap -> HierarchyCycleError (defense-in-depth).
    with pytest.raises(HierarchyCycleError):
        resolve_ultimate_parent(session, nodes[-1], acting_tenant=tenant)


# --- anchor-not-enforce: the descendant resolver computes subtree but enforces nothing ---


def test_subtree_is_computable_but_not_enforced(session: Session) -> None:
    # The subtree is computable (the ABAC anchor substrate) AND a plain list of all tenant nodes is
    # unfiltered (no scope predicate) — the anchor-not-enforce contract. A future SCOPE-PORTFOLIO
    # grant would restrict this; P1C-1 ships nothing of the sort.
    tenant = _tenant()
    root = _node(session, tenant, "ROOT", node_type="PORTFOLIO")
    child = _node(session, tenant, "CHILD", parent_portfolio_id=root.id)
    # subtree computable:
    assert {n.id for n in resolve_descendants(session, root, acting_tenant=tenant)} == {child.id}
    # the unscoped read returns ALL tenant nodes (no portfolio-scope filtering exists):
    all_ids = {n.id for n in session.execute(select(Portfolio)).scalars().all()}
    assert all_ids == {root.id, child.id}


# --- import direction: portfolio package imports only the rails (one-way) ---


def test_portfolio_import_direction() -> None:
    # The portfolio package imports ONLY the rails (one-way) — never irp_backend, the plural
    # aggregator, reference, or any deferred downstream domain package. Scans import-statement lines
    # only (the reference-package scanner pattern), so docstring prose is not a false positive.
    import irp_shared.portfolio as pkg

    forbidden = (
        "irp_backend",
        "irp_shared.models",  # the plural aggregator (cycle vector)
        "irp_shared.reference",
        "irp_shared.ingestion",
        "irp_shared.risk",
        "irp_shared.reporting",
        "irp_shared.market_data",
        "irp_shared.calc",
        "irp_shared.model",
    )
    # Allowlist: any first-party irp_shared.* import must land in exactly these subpackages (fails
    # CLOSED on a new cross-layer import). ``portfolio`` = intra-package; ``temporal`` is a module.
    allowed_subpackages = {"lineage", "audit", "db", "temporal", "portfolio"}
    pkg_dir = pathlib.Path(pkg.__file__).parent
    for py in sorted(pkg_dir.glob("*.py")):
        for line in py.read_text().splitlines():
            stripped = line.strip()
            mods: list[str] = []
            if stripped.startswith("from "):
                base = stripped.split()[1]
                mods.append(base)
                if " import " in stripped:
                    for name in stripped.split(" import ", 1)[1].replace("(", "").split(","):
                        token = name.strip().split(" as ")[0].strip()
                        if token and token != "*":
                            mods.append(f"{base}.{token}")
            elif stripped.startswith("import "):
                mods.append(stripped.split()[1].split(",")[0])
            else:
                continue
            for mod in mods:
                for root in forbidden:
                    assert mod != root and not mod.startswith(
                        root + "."
                    ), f"{py.name} imports forbidden {mod}"
                if mod.startswith("irp_shared."):
                    segments = mod.split(".")
                    assert (
                        segments[1] in allowed_subpackages
                    ), f"{py.name} imports non-allowlisted {mod} (irp_shared.{segments[1]})"
