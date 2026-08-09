"""ENT-074 ``tenant`` — the platform's tenant registry (ONBOARD-1a).

**Why this did not exist until Wave 17, and why that mattered.** For the platform's whole life a
"tenant" was a free-floating UUID: every tenant-scoped table carried a ``tenant_id``, RLS compared
it to a GUC armed from the caller's token claim, and nothing anywhere said which tenants EXIST.
The Wave-16 close review found the consequence — 251 API paths, 289 RBAC-protected operations, and
no way to create the tenant, user or role any of them requires; every deployment that had ever run
was seeded by a demo or proof script.

**PLATFORM-GLOBAL, and that is a named tenancy class now** (ratified OQ-ONB-1A). No ``tenant_id``,
no RLS — the class ``permission`` and ``role_permission`` already occupy. The alternative
(a SYSTEM-tenant hybrid row) was refused: the hybrid set exists for *globally shared vocabularies
every tenant reads*, and tenants do not read each other's registry rows. The chicken-and-egg also
dissolves this way — a row that DEFINES a tenant cannot be scoped to the tenant it defines.

**The status enum is a TOTAL enumeration** (the 0053 pattern): an unenumerated arm must fail
CLOSED at the database, not be admitted by an implication-form CHECK.

* ``SYSTEM``    — the reserved system tenant. Exists so the platform operator's own token passes
  the boundary exists-check without ever being a customer tenant (the verifier pass found that
  omission would have locked the operator out of the surface it exists to serve).
* ``ACTIVE``    — a real tenant.
* ``SUSPENDED`` — the boundary refuses its principals. The status ships ENFORCED and SETTER-LESS:
  ``tenant.suspend`` is deliberately not minted (a verb without a workflow is a dead guard, the
  SOD-08 half-mint precedent), so today only a direct administrative write reaches it. Enforced
  anyway, and tested, because a status the boundary ignores is a comment.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import PrimaryKeyMixin, TimestampMixin
from irp_shared.temporal import TemporalClass

#: The reserved arm for the system tenant itself.
TENANT_STATUS_SYSTEM = "SYSTEM"
#: A live customer tenant.
TENANT_STATUS_ACTIVE = "ACTIVE"
#: Registered, but its principals are refused at the boundary.
TENANT_STATUS_SUSPENDED = "SUSPENDED"

#: The TOTAL enumeration. The DB CHECK in migration 0067 is generated from this tuple, and a
#: parity test asserts the two cannot drift — one declaration, the REF-1 lesson about 31
#: hand-mirrored copies of an expected value.
TENANT_STATUSES: tuple[str, ...] = (
    TENANT_STATUS_SYSTEM,
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
)

#: Statuses whose principals the boundary ADMITS. Deliberately an allow-list, not a deny-list: a
#: status arm added later is refused until somebody decides it should be admitted (fail-closed).
ADMITTED_TENANT_STATUSES: frozenset[str] = frozenset({TENANT_STATUS_SYSTEM, TENANT_STATUS_ACTIVE})

#: How a registry row arrived. Recorded because migration 0067 backfills rows for tenants that
#: predate the registry, and "this tenant was inferred from existing app_user rows" is a different
#: fact from "an operator created this tenant" — a distinction an auditor will want and which no
#: later query could reconstruct.
PROVENANCE_BACKFILL = "0067_backfill"
PROVENANCE_SYSTEM = "0067_system"
PROVENANCE_ONBOARDED = "ONBOARDED"
PROVENANCES: tuple[str, ...] = (PROVENANCE_BACKFILL, PROVENANCE_SYSTEM, PROVENANCE_ONBOARDED)


class Tenant(PrimaryKeyMixin, TimestampMixin, Base):
    """A tenant of the platform (ENT-074). PLATFORM-GLOBAL: no ``tenant_id``, no RLS.

    ``id`` IS the tenant id every other table's ``tenant_id`` refers to — deliberately not a
    surrogate with a separate ``tenant_id`` column, because a second identifier for the same thing
    is how two of them eventually disagree.

    EV (effective-dated reference/config) by temporal class, matching ``permission``/``role``:
    this is configuration about the platform, not governed business evidence. No append-only
    trigger is fitted, and that is stated rather than implied — the IA machinery is for governed
    records, and claiming immutability a test cannot make fire is the shape P9 forbids.
    """

    __tablename__ = "tenant"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("code", name="uq_tenant_code"),
        CheckConstraint(
            "status IN ('" + "', '".join(TENANT_STATUSES) + "')",
            name="ck_tenant_status",
        ),
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provenance: Mapped[str] = mapped_column(String(40), nullable=False)


__all__ = [
    "ADMITTED_TENANT_STATUSES",
    "PROVENANCES",
    "PROVENANCE_BACKFILL",
    "PROVENANCE_ONBOARDED",
    "PROVENANCE_SYSTEM",
    "TENANT_STATUSES",
    "TENANT_STATUS_ACTIVE",
    "TENANT_STATUS_SUSPENDED",
    "TENANT_STATUS_SYSTEM",
    "Tenant",
]
