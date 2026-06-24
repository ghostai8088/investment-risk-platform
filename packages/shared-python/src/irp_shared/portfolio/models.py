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

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
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
