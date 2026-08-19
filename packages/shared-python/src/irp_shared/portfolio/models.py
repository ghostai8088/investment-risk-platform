"""Portfolio ORM model (P1C-1, ENT-010, EV) — the portfolio/fund/strategy/account hierarchy.

A single effective-dated (EV) table — the platform's **first domain entity** and the entitlement
portfolio-scope **ANCHOR** for CAP-1. PROPRIETARY, tenant-scoped, **NEVER hybrid** (no SYSTEM_TENANT
row; symmetric RLS only, migration 0012). EV-mutable: an amend (rename / re-parent / status / dates)
is an **in-place supersede** (``record_version`` bump + ``PORTFOLIO.UPDATE`` audit), not a new row —
so it is NOT append-only (no ``irp_prevent_mutation`` trigger, no ``APPEND_ONLY_TABLES`` entry, no
``system_*`` axis; that is FR, reserved for P1C-3/4).

``node_type`` (PORTFOLIO/FUND/STRATEGY/ACCOUNT) and ``status`` are controlled-vocab **plain
Strings**
(no enum, no CHECK, no lookup table — new values are data, not migrations; MG-01 genericity). A
single
``status`` flag (no ``is_active`` — the P1B-3 ``arch-1`` dual-flag lesson). ``parent_portfolio_id``
is
an intra-tenant self-FK adjacency (NULL = a root; self-parent rejected in the binder; the bounded
cycle-safe ancestor/descendant resolvers live in ``portfolio.py``). ``base_currency_code`` is a
plain
ISO str (the P1B-3 no-FK-to-hybrid precedent), inert. **A portfolio holds nothing** — no
position/valuation/holding/exposure column (those are later slices; scope fence).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass


class Portfolio(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Portfolio hierarchy node (ENT-010, EV) — the entitlement scope anchor.

    ``UNIQUE(tenant_id, code)``; PROPRIETARY, symmetric RLS (never hybrid)."""

    __tablename__ = "portfolio"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_portfolio_tenant_code"),)

    code: Mapped[str] = mapped_column(String(150), nullable=False)  # firm-assigned node code
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Controlled-vocab plain string (no enum/CHECK): PORTFOLIO/FUND/STRATEGY/ACCOUNT; extend by
    # value.
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Intra-tenant self-FK adjacency (hierarchy hook). NULL = a root. Self-parent rejected in the
    # binder; the bounded ancestor/descendant resolvers live in portfolio.py. NO rollup/scope logic
    # in the model (the descendant resolver records future ABAC subtree semantics; no enforcement).
    parent_portfolio_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=True, index=True
    )
    base_currency_code: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )  # plain ISO str, inert (no FK to the hybrid currency table)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE"
    )  # single status flag, no is_active
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PortfolioHierarchyVersion(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One appended snapshot of a portfolio node's structural state per edit (ENT-076, IA TRUE
    append-only; STRUCT-3 / REQ-PPM-001 clause 2 as re-adjudicated 2026-08-15).

    The head table stays the deliberate EV-mutable design (DP-1 ratified: history TABLE beside
    the head, never an EV->FR conversion); THIS table is the entity's OWN version history — the
    re-adjudicated clause's subject: the tree resolves as-of a past time from these rows, by
    timestamp, with NO run or snapshot in scope (see ``resolve_tree_as_of``). A row is written
    co-transactionally by ``create_portfolio`` and every ``update_portfolio`` (it rides the
    existing PORTFOLIO.CREATE/UPDATE audit events — no new audit code, R-07 untouched), capturing
    the POST-state of the fields the tree and its display depend on. ``effective_at`` is the
    write's wall-clock (the as-of axis); ``record_version`` mirrors the head's version after the
    edit (the join key back to the EV head's own counter).

    Migration ``0072`` backfills ONE row per pre-existing node from its head at the head's
    ``valid_from`` — pre-0072 intermediate edits are honestly unrecoverable (the head kept no
    history), so the earliest resolvable view of an old book is its state at backfill.
    PROPRIETARY, symmetric FORCE RLS, ``irp_prevent_mutation`` trigger + the ORM guard below (the
    ``transaction`` belt-and-braces variant — ENT-075 shipped without the ORM half and only the
    PG trigger caught its first mutation)."""

    __tablename__ = "portfolio_hierarchy_version"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # Review fold: two concurrent amends of one node would otherwise both append the same
        # (node, version) — the duplicate must be LOUD (one transaction fails), because the
        # as-of tie-break orders by record_version.
        UniqueConstraint(
            "portfolio_id", "record_version", name="uq_portfolio_hierarchy_version_node_version"
        ),
        # The as-of read's access path (declared here too so the OD-052 drift gate sees the
        # model and the migration agree — CI caught the migration-only index as drift).
        Index(
            "ix_portfolio_hierarchy_version_tenant_effective",
            "tenant_id",
            "portfolio_id",
            "effective_at",
        ),
    )

    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    #: The post-edit parent (NULL = root). NOT an FK: the parent referenced by a HISTORY row may
    #: legitimately predate/outlive constraints the head enforces; membership is resolved
    #: tenant-filtered at read time.
    parent_portfolio_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    base_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    #: The head's record_version AFTER the edit this row captures.
    record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The as-of axis: when this state became the head's state (write wall-clock; backfill uses
    #: the head's valid_from).
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: BINDER (written by create/update at edit time), 0072_BACKFILL (reconstructed from the
    #: head at migration — review fold: a reader must be able to tell recorded history from the
    #: backfill's honest fabrication), or 0073_BACKFILL (the DP-11 root-currency declaration).
    source: Mapped[str] = mapped_column(String(20), nullable=False)


def _block_hierarchy_version_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


event.listen(PortfolioHierarchyVersion, "before_update", _block_hierarchy_version_mutation)
event.listen(PortfolioHierarchyVersion, "before_delete", _block_hierarchy_version_mutation)
