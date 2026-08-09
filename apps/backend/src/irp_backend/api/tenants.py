"""Tenant provisioning — the platform's ignition (ONBOARD-1a).

The Wave-16 close review found the platform had 251 API paths, 289 RBAC-protected operations, and
no way to create the tenant, user or role any of them requires. This router is that way.

**One route, and it is platform-scope.** ``tenant.create`` lives in the PLATFORM catalog
(``irp_shared.entitlement.platform_catalog``), NOT in ``PERMISSIONS`` — because a code in
``PERMISSIONS`` enters ``ALL_CODES``, which is the ``platform_admin`` template, which tenant
onboarding clones, which would hand every customer tenant the power to create tenants. Five
independent verifier lanes converged on that composition in the first draft of the design; the
separate catalog is the structural fix, and a census asserts the two are disjoint IN THE DATABASE
after an onboarding rather than merely in the constants.

**The guard is the ordinary ``require_permission``, deliberately.** A first draft called
``has_permission`` inline, reasoning that this route's session must be re-armed mid-request and so
could not use the shared dependency. That was wrong twice over: ``get_tenant_session`` arms the
CALLER's context, which for the operator is the SYSTEM tenant — exactly what the check needs — and
its own contract already permits a handler to re-arm afterwards. Worse, the inline version made
the route **invisible to the platform-wide route→permission census** (P11), which detects guards
by their dependency closure: the route would have read as unguarded, and the one route in the
platform with the most authority would have been the one the census could not see.

**The response tells the operator what is still owed.** A created tenant does NOT tick: the
worker's tenant membership is deploy-time config (``IRP_TENANT_IDS``, ratified at CAD-1 as
configuration rather than a database sweep), so a tenant is born with an HTTP surface and no
scheduled work until an operator edits the deployment. Saying so in the response body is the
difference between a documented consequence and a silent one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.platform_catalog import PLATFORM_CODES
from irp_shared.entitlement.service import Principal
from irp_shared.tenancy.service import TenantOnboardingError, onboard_tenant

router = APIRouter(prefix="/tenants", tags=["tenants"])

#: The single platform verb this router enforces. Read from the catalog rather than spelled as a
#: literal so a rename cannot leave the guard pointing at a code that no longer exists.
TENANT_CREATE = PLATFORM_CODES[0]

#: Module-level guard singleton (deny-by-default; built once, not in an argument default).
_require_create = require_permission(TENANT_CREATE)

#: Stated in the create response. The operator step that ONBOARD-1a does not perform.
WORKER_FOLLOWUP = (
    "This tenant has no scheduled work until its id is added to IRP_TENANT_IDS and the worker "
    "is rolled — the supervisor's tenant membership is deploy configuration (CAD-1)."
)


class TenantCreateIn(BaseModel):
    """``extra='forbid'``: an unexpected field is REFUSED, not ignored.

    The RPT-2 precedent, and it matters more here — a caller who thinks they supplied a
    ``status`` or a ``tenant_id`` and had it silently dropped would believe they provisioned
    something other than what exists.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=255)
    #: The first administrator's OIDC subject — the value their token's ``sub`` will carry. Not a
    #: password, not an email: this platform never holds a credential (SSO-1's boundary is the IdP).
    admin_external_subject: str = Field(min_length=1, max_length=255)
    admin_display_name: str = Field(min_length=1, max_length=255)


class TenantCreateOut(BaseModel):
    tenant_id: str
    code: str
    display_name: str
    status: str
    admin_user_id: str
    admin_role: str
    roles_cloned: list[str]
    grants_cloned: int
    roles_skipped: list[str]
    operator_followup: str


@router.post("", response_model=TenantCreateOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreateIn,
    principal: Principal = Depends(_require_create),
    db: Session = Depends(get_tenant_session),
) -> TenantCreateOut:
    """Create a tenant, clone its roles, seed its first administrator. One transaction.

    The dependency arms the CALLER's context (the SYSTEM tenant, for the platform operator) and
    checks ``tenant.create`` there — deny-by-default, like every other route.
    ``onboard_tenant`` then re-arms to the new tenant partway through, which is ratified behaviour
    and explicitly permitted by ``get_tenant_session``'s contract.
    """
    try:
        result = onboard_tenant(
            db,
            code=payload.code,
            display_name=payload.display_name,
            admin_external_subject=payload.admin_external_subject,
            admin_display_name=payload.admin_display_name,
            actor_id=principal.user_id,
        )
    except TenantOnboardingError as exc:
        # The service raises BEFORE anything is written (the duplicate-code probe is savepointed,
        # and every validation precedes the first INSERT), so the rollback here is belt-and-braces
        # rather than the thing that makes the refusal clean.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    db.commit()
    return TenantCreateOut(
        tenant_id=result.tenant_id,
        code=result.code,
        display_name=payload.display_name,
        status="ACTIVE",
        admin_user_id=result.admin_user_id,
        admin_role="tenant_admin",
        roles_cloned=list(result.roles_cloned),
        grants_cloned=result.grants_cloned,
        roles_skipped=list(result.roles_skipped),
        operator_followup=WORKER_FOLLOWUP,
    )
