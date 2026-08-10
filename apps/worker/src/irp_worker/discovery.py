"""Which tenants does the worker tick? (REPRO-2, ratified 2026-08-10 — OQ-REP2-1.)

**The supersession.** CAD-1's OQ-2=A ratified "config, NOT a DB sweep", and the circumstance that
decision was made under no longer holds: at CAD-1 there WAS no tenant registry, so "a DB sweep"
meant an app-side cross-tenant read with no legitimate home. ONBOARD-1a built ENT-074 as a
deliberately PLATFORM-GLOBAL table (no ``tenant_id``, no RLS) that every authenticated request
already reads — so the worker can ask it who exists with no BYPASSRLS and no RLS bypass of any
kind. **OQ-SCH-1-1=B is NOT reopened:** dispatch stays per-tenant and the app stays 100%
non-BYPASSRLS.

**What CAD-1 FOLD-2 was actually protecting, and how it survives.** Its recorded reason was not
"an empty list is probably a typo" — it was *"a silently-idle engine is the exact failure this
slice exists to prevent."* That property is preserved exactly, by splitting the states config
could not tell apart:

* the filter is UNSET and the registry truthfully has no ACTIVE tenants — a fresh platform, and
  the honest answer is to idle LOUDLY and re-poll (a crash-looping worker would make ONBOARD-1's
  ignition depend on restart orchestration);
* the filter is SET but names a tenant the registry does not know (a fortiori: intersects to
  nothing) — a definite misconfiguration, and this REFUSES, exactly as FOLD-2 did;
* the filter is SET with a malformed entry — REFUSES (see ``parse_tenant_ids``: skip-and-continue
  would silently widen the filter to every tenant);
* the registry cannot be READ — never mistaken for "zero tenants"; the cycle is skipped and a
  consecutive-failure streak escalates.

Nothing here can be silent. The only quiet state is a platform with nothing to do, and it says so
every cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.tenancy.models import TENANT_STATUS_ACTIVE, Tenant
from irp_worker.tenants import canonical_tenant_id

log = logging.getLogger("irp_worker.discovery")


class TenantDiscoveryError(RuntimeError):
    """The tenant registry could not be READ. Never the same thing as 'there are no tenants'."""


@dataclass(frozen=True)
class DiscoveryConfig:
    """The optional RESTRICTION filter. ``None`` (the unset case) means no restriction."""

    #: Canonical tenant ids from ``IRP_TENANT_IDS``; ``None`` when unset/blank.
    restrict_to: tuple[str, ...] | None = None

    @property
    def is_restricted(self) -> bool:
        return self.restrict_to is not None and len(self.restrict_to) > 0


def active_tenant_ids(session: Session) -> list[str]:
    """Every ACTIVE tenant in the ENT-074 registry, canonical and ordered.

    SYSTEM and SUSPENDED are excluded by the status filter: the SYSTEM tenant is the platform
    operator's, holds no governed books, and is refused on every data router already; a SUSPENDED
    tenant is one somebody decided should stop.

    A read failure RAISES rather than returning ``[]`` — the two are opposite facts and the caller
    must not be able to confuse them.
    """
    try:
        rows = session.execute(
            select(Tenant.id).where(Tenant.status == TENANT_STATUS_ACTIVE).order_by(Tenant.id)
        ).scalars()
        return [canonical_tenant_id(row) for row in rows]
    except Exception as exc:  # noqa: BLE001 - re-raised as the typed failure the caller handles
        raise TenantDiscoveryError(f"the tenant registry could not be read: {exc}") from exc


def resolve_tick_tenants(session: Session, config: DiscoveryConfig) -> list[str]:
    """The tenants this cycle should tick. Raises ``TenantDiscoveryError`` if the registry is
    unreadable; raises ``ValueError`` if the restriction names a tenant the registry does not know.

    The restriction can PIN A SUBSET; it can no longer INVENT a tenant. That is the whole change
    in what the environment variable means, and it is why an id the registry does not know is a
    refusal rather than a tenant.

    A pinned tenant the registry KNOWS but does not list as ACTIVE is neither: the ratified table
    keeps two separate rows for a reason. "Unknown to the registry" is a definite misconfiguration
    and refuses; "SUSPENDED → never ticked" is a governed act somebody performed, and it must be
    honored the same way it is without a filter — the tenant drops out of the tick set, loudly,
    every cycle, and comes back within one cycle of reactivation. Conflating the two (the review
    caught the first draft doing exactly that) turns a legitimate mid-run suspension of ONE pinned
    tenant into a refusal that kills the engine for every OTHER pinned tenant.
    """
    discovered = active_tenant_ids(session)
    if not config.is_restricted:
        return discovered

    try:
        registered = {
            canonical_tenant_id(row) for row in session.execute(select(Tenant.id)).scalars()
        }
    except Exception as exc:  # noqa: BLE001 - same typed failure as the ACTIVE read
        raise TenantDiscoveryError(f"the tenant registry could not be read: {exc}") from exc

    unknown = [t for t in (config.restrict_to or ()) if t not in registered]
    if unknown:
        raise ValueError(
            "IRP_TENANT_IDS names tenant(s) the registry does not know: "
            f"{', '.join(sorted(unknown))} — refusing to start rather than ticking a subset "
            "the operator did not ask for (a filter that silently shrinks is the "
            "looks-configured-but-isn't state)"
        )
    active = set(discovered)
    inactive_pinned = [t for t in (config.restrict_to or ()) if t not in active]
    if inactive_pinned:
        log.warning(
            "the IRP_TENANT_IDS restriction pins tenant(s) the registry knows but does not list "
            "as ACTIVE — they will NOT be ticked until reactivated: %s",
            ", ".join(sorted(inactive_pinned)),
        )
    # Preserve the REGISTRY's order, restricted to the pinned set.
    pinned = set(config.restrict_to or ())
    return [t for t in discovered if t in pinned]
