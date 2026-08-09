"""Register a test tenant so it passes the ONBOARD-1a boundary check (PG suites only).

**Why any of this exists.** ONBOARD-1a added a check behind ``get_principal``: a token (or dev
header) whose tenant claim names no row in ``tenant`` is refused. It is dialect-gated — a no-op on
SQLite — so the ~2,600 unit-tier suites are unaffected by mechanism. But a PostgreSQL suite that
authenticates over HTTP with a freshly minted ``uuid4`` tenant now gets a **401**, because that
tenant is real everywhere except the registry.

That collision was predicted at the design's verifier pass and the record said the seeding paths
would be "enumerated in the implementation plan, not discovered". They were discovered — by the
full-PG battery, one suite, one 401 — so this helper exists to make the next one a one-line fix
rather than a debugging afternoon.

**Use it in any PG suite that drives HTTP as a tenant principal.** It is deliberately NOT autouse:
a fixture that silently registered every tenant would also hide the boundary check from the suites
that mean to test it, which is how a control ends up switched off in exactly the place it matters.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from irp_shared.tenancy.models import PROVENANCE_ONBOARDED, TENANT_STATUS_ACTIVE, Tenant


def register_test_tenant(session: Session, tenant_id: str, *, code: str | None = None) -> None:
    """Insert an ACTIVE registry row for ``tenant_id`` if it has none. Idempotent.

    ``tenant`` is PLATFORM-GLOBAL (no RLS), so this needs no tenant context armed — and the caller
    must hold INSERT on it (constrained-role suites: add ``"tenant"`` to the grant list).
    """
    if session.get(Tenant, tenant_id) is not None:
        return
    session.add(
        Tenant(
            id=tenant_id,
            code=code or f"test-{tenant_id[:8]}",
            display_name=f"Test tenant {tenant_id[:8]}",
            status=TENANT_STATUS_ACTIVE,
            provenance=PROVENANCE_ONBOARDED,
        )
    )
    session.flush()


__all__ = ["register_test_tenant"]
