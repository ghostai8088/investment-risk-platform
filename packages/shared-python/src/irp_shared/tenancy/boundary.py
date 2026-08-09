"""The tenant boundary check — a claimed tenant must be REGISTERED and ADMITTED (ONBOARD-1a).

Before this slice, any well-formed UUID in a token's tenant claim armed an RLS context. That was
not exploitable on its own (RLS then admitted only that tenant's rows, and no user existed there
to resolve), but it meant the platform could not answer "is this a tenant?" — and the day the
platform operator became authenticatable, an unanswerable question became a fence with nothing
behind it.

**DIALECT-GATED, deliberately, and said out loud rather than left to be inferred.** The check runs
on PostgreSQL and is a no-op on SQLite — the same shape as ``set_tenant_context`` and
``_lock_chain``. That means the unit tier is exempt **by mechanism**, not by accident: the ~2,500
SQLite suites mint arbitrary uuid4 tenants and would otherwise all fail closed against an empty
registry. An earlier draft of the decision record justified the exemption as "the unit tier has no
tenant rows", which is backwards — under a fail-closed check an empty registry means REFUSE
EVERYTHING. The verifier pass caught that; the mechanism, not the emptiness, is the exemption.

The consequence, stated because FK-1's lesson was exactly this: **SQLite suites are structurally
outside this control's reach.** Its proofs live at the PG tier and in the deployed stack, and a
census would be dishonest if it counted unit-tier greens as coverage.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.db.tenant import _is_postgres
from irp_shared.tenancy.models import ADMITTED_TENANT_STATUSES, Tenant


class TenantNotAdmitted(Exception):
    """The claimed tenant is unregistered, or registered with a non-admitted status.

    ONE exception for both cases on purpose: the caller (an auth boundary) must return an opaque
    401 either way. "No such tenant" and "that tenant is suspended" are different facts for an
    operator reading logs and the SAME fact for an unauthenticated stranger — telling them apart at
    the wire is a tenant-enumeration oracle.
    """

    def __init__(self, tenant_id: str, reason: str) -> None:
        super().__init__(f"tenant {tenant_id} not admitted: {reason}")
        self.tenant_id = tenant_id
        self.reason = reason


def assert_tenant_admitted(session: Session, tenant_id: str) -> None:
    """Raise :class:`TenantNotAdmitted` unless the tenant is registered AND admitted.

    No-op on non-PostgreSQL engines (see the module docstring). The read runs BEFORE any tenant
    context is armed and touches only ``tenant``, which is PLATFORM-GLOBAL and carries no RLS — so
    it cannot itself be hidden by the very isolation it is about to authorize.
    """
    if not _is_postgres(session):
        return
    status = session.execute(
        select(Tenant.status).where(Tenant.id == tenant_id)
    ).scalar_one_or_none()
    if status is None:
        raise TenantNotAdmitted(tenant_id, "not registered")
    if status not in ADMITTED_TENANT_STATUSES:
        raise TenantNotAdmitted(tenant_id, f"status {status}")


__all__ = ["TenantNotAdmitted", "assert_tenant_admitted"]
