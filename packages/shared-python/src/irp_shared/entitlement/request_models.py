"""ENT-075 ``entitlement_request`` — SOD-04's four-eyes, given a place to live (ONBOARD-1b).

`entitlement_sod_model.md` §7 has said "Four-eyes is mandatory for: … entitlement changes
(SOD-04)" since P0.5, and CTRL-025 ("Entitlement changes maker-checked + audited") has been
*Planned* with no code for as long. ONBOARD-1's first design draft contradicted both — a single
admin granting directly, with only self-grant refused — and the verifier pass called it: a rule
that mandates the sync while leaving the contradiction is aspirational, not ratified.

**The shape, ratified at OQ-ONB-9A.** An entitlement-affecting act by an admin is born ``PENDING``
when the tenant has **≥1 currently-valid OTHER admin**, and needs a second admin's approval. With
no other admin it executes directly, stamped as such. The threshold is "≥1 OTHER", not "≥2 other":
four-eyes engages the moment an approver *exists*, which is at two admins. (The design's own
first fix said "≥2 other" and thereby exempted every two-admin tenant — precisely the tenants
where four-eyes first becomes possible. Verifier pass 2, finding B3.)

**What counts as an entitlement change is broader than "grant".** Grant, revoke, role END-DATING,
and **deactivating a user who currently holds ``tenant_admin``** all ride this table. Deactivation
is not a grant verb, and that is exactly why it had to be named: `user.manage` deactivation would
otherwise be a one-step bypass of the whole flow — remove the other admin, then act alone in the
bootstrap window (verifier pass 2, finding B2, CONFIRMED).

**Append-only, with the MG-2 ordering apparatus — and this is enforced, not merely intended.** A
request's life is a sequence of facts, not a mutable row: the resolution is a **NEW row**
referencing the request via ``resolves_request_id``, exactly the ``breach_action`` lifecycle shape.
An approval can therefore never be edited into existence after the fact.

The first implementation of this module described that design in this docstring and then recorded
approval by MUTATING the request row — which every SQLite test accepted and PostgreSQL's
``irp_prevent_mutation`` trigger refused outright. The docstring was right and the code was wrong;
the trigger is why that is a two-line note rather than a shipped defect.

The per-tenant monotonic ``seq`` is app-assigned under the tenant advisory lock (the MG-2
pattern), because a state machine over an append-only log needs a DB-monotonic ordering key — a
wall-clock timestamp ties, and two admins acting in the same millisecond is exactly the case this
table exists to adjudicate.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.temporal import TemporalClass

#: What the request would DO. A total enumeration with a DB CHECK (the 0053 pattern): an
#: unenumerated action must fail CLOSED, because an action nobody enumerated is an action nobody
#: decided needed four eyes.
ACTION_GRANT_ROLE = "GRANT_ROLE"
ACTION_REVOKE_ROLE = "REVOKE_ROLE"
ACTION_DEACTIVATE_USER = "DEACTIVATE_USER"
REQUEST_ACTIONS: tuple[str, ...] = (
    ACTION_GRANT_ROLE,
    ACTION_REVOKE_ROLE,
    ACTION_DEACTIVATE_USER,
)

#: Where the request is. PENDING → APPROVED; DIRECT is terminal at birth (the bootstrap window —
#: recorded as its own state rather than as a PENDING row auto-approved by nobody, because "no
#: second admin existed" and "a second admin agreed" are different facts and an auditor must be
#: able to count them separately).
#:
#: There is deliberately NO ``REJECTED``: the record ratified approval (OQ-ONB-9A) and nothing
#: else — a checker's refusal is inaction, and the request stays PENDING for someone to approve
#: or for nobody to. The first build minted the status anyway, with no code path able to produce
#: it — the review struck it as the LQ-1 inert-state class (a state an auditor can read in the
#: CHECK and infer a flow that does not exist). A reject/withdraw verb is a DECISION for a future
#: gate, not a status to pre-mint.
STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_DIRECT = "DIRECT"
REQUEST_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_DIRECT,
)

#: Statuses in which the requested act has actually TAKEN EFFECT.
EFFECTIVE_STATUSES: frozenset[str] = frozenset({STATUS_APPROVED, STATUS_DIRECT})


class EntitlementRequest(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One entitlement-affecting act, and its four-eyes resolution (ENT-075).

    IA append-only + symmetric tenant-scoped FORCE RLS: this is governed evidence of who asked for
    what authority and who agreed. A row that could be edited after the fact would make the
    approval unfalsifiable, which is the only property that matters here.
    """

    __tablename__ = "entitlement_request"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # The per-tenant monotonic ordering key, app-assigned under the tenant advisory lock.
        UniqueConstraint("tenant_id", "seq", name="uq_entitlement_request_seq"),
        CheckConstraint(
            "action IN ('" + "', '".join(REQUEST_ACTIONS) + "')",
            name="ck_entitlement_request_action",
        ),
        CheckConstraint(
            "status IN ('" + "', '".join(REQUEST_STATUSES) + "')",
            name="ck_entitlement_request_status",
        ),
        # A resolved row NAMES its resolver, and a PENDING row does not. The one CHECK that
        # keeps the control non-decorative: "approved by nobody" is unrepresentable.
        CheckConstraint(
            "(status = 'PENDING' AND resolved_by IS NULL AND resolved_at IS NULL) "
            "OR (status <> 'PENDING' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_entitlement_request_resolution",
        ),
        # A RESOLUTION row points at the request it resolves; an originating row does not. Both
        # directions matter: a resolution with no parent is an orphan claim, and a PENDING row
        # that points at something is a request pretending to be a decision.
        CheckConstraint(
            "(resolves_request_id IS NULL AND status IN ('PENDING', 'DIRECT')) "
            "OR (resolves_request_id IS NOT NULL AND status = 'APPROVED')",
            name="ck_entitlement_request_resolution_link",
        ),
        Index("ix_entitlement_request_tenant_status", "tenant_id", "status"),
    )

    #: Per-tenant monotonic sequence (1-based) — the deterministic ordering key. Wall-clock ties.
    seq: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    #: WHO asked. The person-level SoD compares this to ``resolved_by`` (the MG-3 pattern).
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: WHAT it targets. ``role_id`` is NULL for DEACTIVATE_USER (there is no role in that act) —
    #: nullable by necessity, and the action CHECK plus the service's own guard keep the
    #: combinations honest.
    target_user_id: Mapped[str] = mapped_column(
        ForeignKey("app_user.id"), nullable=False, index=True
    )
    target_role_id: Mapped[str | None] = mapped_column(
        ForeignKey("role.id"), nullable=True, index=True
    )

    #: WHO agreed, and when. NULL only while PENDING (enforced by the CHECK above).
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Set on a RESOLUTION row: the request this row decides. NULL on an originating row.
    resolves_request_id: Mapped[str | None] = mapped_column(
        ForeignKey("entitlement_request.id"), nullable=True, index=True
    )

    #: Free-text reason supplied by the requester — DC-2 metadata, never a credential.
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


__all__ = [
    "ACTION_DEACTIVATE_USER",
    "ACTION_GRANT_ROLE",
    "ACTION_REVOKE_ROLE",
    "EFFECTIVE_STATUSES",
    "REQUEST_ACTIONS",
    "REQUEST_STATUSES",
    "STATUS_APPROVED",
    "STATUS_DIRECT",
    "STATUS_PENDING",
    "EntitlementRequest",
]
