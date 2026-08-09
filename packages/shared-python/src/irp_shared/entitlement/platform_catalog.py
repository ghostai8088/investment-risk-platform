"""The PLATFORM entitlement catalog — authority that must never reach a tenant (ONBOARD-1a).

**This module exists because of a trap five independent verifier lanes found in the same draft.**
The obvious design — mint ``tenant.create`` into ``entitlement.bootstrap.PERMISSIONS`` and grant it
to a system operator — hands it to every customer tenant, by three composed steps each of which is
individually correct:

1. ``ALL_CODES`` is derived from ``PERMISSIONS``, so a new code enters it automatically;
2. the ``platform_admin`` TEMPLATE is ``list(ALL_CODES)``, so the code enters that template;
3. tenant onboarding CLONES templates into the tenant, and ``require_permission`` checks the
   caller's OWN tenant — so a tenant's own admin would hold ``tenant.create`` and could create
   tenants.

No single review step is wrong; the composition is. So the fix is structural rather than careful:
platform authority lives in a **different constant**, held by a **role that is not a template and
is never cloned**, and a census asserts the two catalogs are disjoint *in the database after an
onboarding* — not merely in the constants, because the constants were never the thing that leaked.

**Delivery.** These rows are inserted by migration ``0067`` inline, and ``sync_catalog`` gains a
platform arm so a future platform code has the same delivery story as a tenant code (P17: a
permission is not minted until a migration delivers it to running databases).

**The gates that would have missed this.** ``test_entitlement_mint_delivery.py`` (P17) and the
route census (P11) walk ``ALL_CODES`` only — proven by execution at planning that a platform code
escapes both silently. Both are extended to walk BOTH catalogs in the same commit that creates
this module; that ordering is not stylistic, it is the difference between a gate and a decoration.
"""

from __future__ import annotations

import uuid

from irp_shared.entitlement.bootstrap import _NS, SYSTEM_TENANT_ID

#: Platform-scope permission catalog: (code, description). Deliberately NOT ``PERMISSIONS``.
PLATFORM_PERMISSIONS: list[tuple[str, str]] = [
    (
        "tenant.create",
        "Create a tenant: its registry row, role clones and first administrator",
    ),
]

#: All platform codes, in catalog order.
PLATFORM_CODES: list[str] = [code for code, _ in PLATFORM_PERMISSIONS]

#: The system-only role holding them. NOT in ``ROLE_TEMPLATES`` — that constant is the set of
#: things tenant onboarding clones, and membership in it is exactly what must not happen here.
PLATFORM_OPERATOR_ROLE = "platform_operator"

#: Platform roles and their grants. One role today; the shape generalizes without inviting a
#: second platform role by accident (adding one is a governed R-07 act like any other).
PLATFORM_ROLES: dict[str, list[str]] = {PLATFORM_OPERATOR_ROLE: list(PLATFORM_CODES)}


def platform_permission_id(code: str) -> str:
    """Deterministic id, sharing ``permission``'s namespace because it shares its TABLE.

    The platform catalog is a separate CONSTANT, not a separate table: ``permission`` rows are
    global already, and a second permission table would mean two answers to "does this code
    exist". The separation that matters is which rows any TEMPLATE grants, and that is enforced by
    ``PLATFORM_ROLES`` being outside ``ROLE_TEMPLATES`` plus the disjointness census.
    """
    return str(uuid.uuid5(_NS, f"permission:{code}"))


def platform_role_id(name: str) -> str:
    """Deterministic id for a platform role, under the SYSTEM tenant (``role`` is tenant-scoped)."""
    return str(uuid.uuid5(_NS, f"role:{SYSTEM_TENANT_ID}:{name}"))


def platform_role_permission_id(role: str, code: str) -> str:
    return str(uuid.uuid5(_NS, f"role_permission:{role}:{code}"))


__all__ = [
    "PLATFORM_CODES",
    "PLATFORM_OPERATOR_ROLE",
    "PLATFORM_PERMISSIONS",
    "PLATFORM_ROLES",
    "platform_permission_id",
    "platform_role_id",
    "platform_role_permission_id",
]
