"""Commitment governed-write service (CC-1, ENT-015) — captured FR private-capital INPUTS.

THE READ RULE (OD-CC-1-D): a commitment (and its ENT-016 events) does NOT feed TWR/Dietz
or backtest realized P&L — those chains read EXCLUSIVELY ``transaction.TRANSFER_IN/
TRANSFER_OUT``. A commitment-related cash movement in a return-modeled book must be
separately posted as a transaction; nothing auto-bridges in v1.

The PA-0 five-op FR set (capture / supersede / correct / reconstruct / list) on the
``(portfolio_id, instrument_id)`` logical key — under the current-row partial-unique
that PAIR is the stable commitment identity (FR re-versioning mints a new row id per
version). Invariants (the proxy_mapping protocol verbatim): ONE ``now = utcnow()`` per
op; CLOSE-FIRST ordering on a re-version; a prior version's CONTENT is never mutated
(TR-08); fail-closed validators BEFORE any write (strictly-positive finite
``committed_amount``; 3-letter ``currency_code`` shape; BOTH FK targets re-resolved
tenant-filtered — the P3-5 cross-tenant-FK guard); **``currency_code`` is
CHAIN-IMMUTABLE** — supersede and correct REFUSE a currency differing from the prior
version's (the immutable ENT-016 event rows validate against it; a re-denominated
commitment is a recorded v1 limitation: close out and re-capture). A supersede may set
``committed_amount`` below the sum of captured calls — the capture layer does not
adjudicate economics (funded/unfunded arithmetic is CC-2's, OD-CC-1-E).

Governed-write rails: the co-transactional fail-closed DQ gate (required-field NOT_NULL
only — NO economic RANGE, the OD-PA-0-D posture); a ``MANUAL`` ORIGIN lineage edge per
new version (the shared per-tenant root); ``PRIVATE.COMMITMENT_*`` audit at the EVT-240
block (per-op grain: capture=1 CREATE; supersede=2 UPDATE+CREATE; correct=2
UPDATE+CORRECTION with ``action="correct"`` and the SYMMETRIC old→new payload — the two
PA-0 review-fold lessons). ``audit/service.py`` is FROZEN; no emit on read; no mid-call
commit (CTRL-032). NO snapshot, NO calculation run, NO model version (captured input).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CORRECT, ACTION_CREATE, ACTION_UPDATE
from irp_shared.audit.payload import json_safe as _json_safe
from irp_shared.audit.service import record_event
from irp_shared.db.bitemporal import assert_supersede_effective_at
from irp_shared.db.integrity import resolve_or_insert
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.private_capital.events import (
    ENTITY_COMMITMENT,
    PRIVATE_COMMITMENT_CORRECTION_EVENT,
    PRIVATE_COMMITMENT_CREATE_EVENT,
    PRIVATE_COMMITMENT_UPDATE_EVENT,
    SOURCE_MODULE,
)
from irp_shared.private_capital.models import Commitment
from irp_shared.reference.guards import assert_instrument_in_tenant

#: The shared per-tenant MANUAL provenance root (the transaction/valuation precedent —
#: a commitment is a manually captured book fact, not a vendor feed; NO new source type).
MANUAL_SOURCE_TYPE = "MANUAL"
MANUAL_SOURCE_CODE = "MANUAL"
MANUAL_SOURCE_NAME = "Manual reference entry"

#: Per-tenant governed DQ rule code (resolve-or-register; the proxy_mapping pattern).
_REQUIRED_RULE_CODE = "commitment.required_fields"


@dataclass(frozen=True)
class CommitmentActor:
    """Actor/correlation context threaded into every commitment audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class CommitmentValueError(Exception):
    """Raised for an invalid amount/currency/target — caught BEFORE any write (fail-closed;
    maps to 422)."""


class CommitmentNotVisible(Exception):
    """Raised when a ``commitment`` id is not visible in the acting tenant scope."""

    def __init__(self, commitment_id: str) -> None:
        super().__init__(f"commitment {commitment_id} is not visible in the current tenant context")
        self.commitment_id = str(commitment_id)


class NoCurrentCommitment(Exception):
    """Raised when an op needs the (portfolio, instrument) pair's open current head and none
    exists."""

    def __init__(self, portfolio_id: str, instrument_id: str) -> None:
        super().__init__(
            f"portfolio {portfolio_id} has no current (open) commitment to instrument "
            f"{instrument_id}"
        )
        self.portfolio_id = str(portfolio_id)
        self.instrument_id = str(instrument_id)


def _validate_amount(committed_amount: Decimal) -> None:
    """Strictly-positive finite Decimal — rejects NaN/±Inf/zero/negative BEFORE any write."""
    if not isinstance(committed_amount, Decimal) or not committed_amount.is_finite():
        raise CommitmentValueError(
            f"committed_amount must be a finite Decimal (got {committed_amount!r})"
        )
    if committed_amount <= 0:
        raise CommitmentValueError(
            f"committed_amount must be strictly positive (got {committed_amount})"
        )


def _validate_currency(currency_code: str) -> None:
    if (
        not isinstance(currency_code, str)
        or len(currency_code) != 3
        or not currency_code.isalpha()
        or currency_code != currency_code.upper()
    ):
        raise CommitmentValueError(
            f"currency_code must be a 3-letter uppercase ISO code (got {currency_code!r})"
        )


def _assert_chain_currency(prior: Commitment, currency_code: str) -> None:
    """The chain-immutability refusal (OD-CC-1-A, the verifier's HIGH-2): the immutable
    ENT-016 events validate against the commitment's currency, so no version may change it."""
    if currency_code != prior.currency_code:
        raise CommitmentValueError(
            f"currency_code is chain-immutable on a commitment (current {prior.currency_code!r}, "
            f"got {currency_code!r}) — a re-denominated commitment is out of scope in v1; "
            f"close out and re-capture; refused"
        )


# --- governed DQ gate (required-field NOT_NULL only; NO economic RANGE) ---


def _ensure_required_rule(
    session: Session, *, tenant_id: str, actor: CommitmentActor
) -> DataQualityRule:
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataQualityRule).where(
                DataQualityRule.tenant_id == str(tenant_id),
                DataQualityRule.code == _REQUIRED_RULE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_dq_rule(
            session,
            tenant_id=str(tenant_id),
            code=_REQUIRED_RULE_CODE,
            name="commitment required fields present",
            rule_type=RULE_TYPE_NOT_NULL,
            actor_id=actor.actor_id,
            params={"column": "present"},
            target_entity_type=ENTITY_COMMITMENT,
            severity=SEVERITY_ERROR,
            actor_type=actor.actor_type,
        ),
    )


def _run_dq_gate(
    session: Session, *, acting_tenant: str, actor: CommitmentActor, row: Commitment
) -> None:
    missing = any(
        getattr(row, f) is None
        for f in (
            "portfolio_id",
            "instrument_id",
            "committed_amount",
            "currency_code",
            "commitment_date",
        )
    )
    rule = _ensure_required_rule(session, tenant_id=acting_tenant, actor=actor)
    run_quality_check(
        session,
        rule=rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_COMMITMENT,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )


# --- provenance (shared MANUAL ORIGIN lineage) + audit emit ---


def ensure_manual_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's shared ``MANUAL`` ``data_source``."""
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataSource).where(
                DataSource.tenant_id == str(tenant_id),
                DataSource.code == MANUAL_SOURCE_CODE,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_data_source(
            session,
            tenant_id=str(tenant_id),
            code=MANUAL_SOURCE_CODE,
            name=MANUAL_SOURCE_NAME,
            source_type=MANUAL_SOURCE_TYPE,
            actor_id=actor_id,
        ),
    )


def _origin_edge(
    session: Session, *, tenant_id: str, entity_type: str, entity_id: str, actor: CommitmentActor
) -> None:
    source = ensure_manual_source(session, tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=entity_type,
        target_entity_id=entity_id,
        edge_kind=EDGE_KIND_ORIGIN,
    )


def _emit(
    session: Session,
    *,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: CommitmentActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    """Emit one audit event to the FROZEN record_event (per-tenant chain; DC-2 metadata)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_value=before_value,
        after_value=after_value,
        justification=justification,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
        event_time=now,
    )


def _summary(row: Commitment) -> dict[str, Any]:
    """A DC-2 commitment-summary dict (metadata only — provenance, never bulk data)."""
    return {
        "portfolio_id": _json_safe(row.portfolio_id),
        "instrument_id": _json_safe(row.instrument_id),
        "currency_code": row.currency_code,
        "record_version": row.record_version,
    }


# --- resolution ---


def resolve_commitment(session: Session, commitment_id: str, *, acting_tenant: str) -> Commitment:
    """Resolve a ``commitment`` version by id with an EXPLICIT tenant predicate (fail-closed)."""
    row = session.execute(
        select(Commitment).where(
            Commitment.id == str(commitment_id),
            Commitment.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise CommitmentNotVisible(str(commitment_id))
    return row


def current_commitment(
    session: Session, *, acting_tenant: str, portfolio_id: str, instrument_id: str
) -> Commitment | None:
    """The single version OPEN ON BOTH axes for the (portfolio, instrument) identity, or
    ``None``. Tenant-predicated. The capital-flow services validate against THIS row."""
    return session.execute(
        select(Commitment).where(
            Commitment.tenant_id == str(acting_tenant),
            Commitment.portfolio_id == str(portfolio_id),
            Commitment.instrument_id == str(instrument_id),
            Commitment.valid_to.is_(None),
            Commitment.system_to.is_(None),
        )
    ).scalar_one_or_none()


# --- capture / supersede / correct (the FR bitemporal protocol) ---


def capture_commitment(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    committed_amount: Decimal,
    currency_code: str,
    commitment_date: date,
    acting_tenant: str,
    actor: CommitmentActor,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Commitment:
    """Capture the first open commitment for a (portfolio, fund-instrument) pair as ONE
    governed unit (FR row + MANUAL ORIGIN edge + ``PRIVATE.COMMITMENT_CREATE`` + the DQ
    gate). Validators + BOTH FK re-resolutions run BEFORE any write; the amount is captured
    verbatim (NEVER computed). NO asset_class gate (genericity — MG-01; the private-asset
    intent is the documented convention, not a schema constraint)."""
    _validate_amount(committed_amount)
    _validate_currency(currency_code)
    assert_portfolio_in_tenant(
        session, portfolio_id, acting_tenant=acting_tenant, error=CommitmentValueError
    )
    assert_instrument_in_tenant(
        session, instrument_id, acting_tenant=acting_tenant, error=CommitmentValueError
    )
    now = now or utcnow()
    row = Commitment(
        tenant_id=str(acting_tenant),
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        committed_amount=committed_amount,
        currency_code=currency_code,
        commitment_date=commitment_date,
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        system_to=None,
        record_version=1,
    )
    if entity_id is not None:
        row.id = entity_id
    session.add(row)
    session.flush()
    _run_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=row)
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_COMMITMENT,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_COMMITMENT,
        entity_id=row.id,
        event_type=PRIVATE_COMMITMENT_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_summary(row),
        actor=actor,
        now=now,
    )
    return row


def supersede_commitment(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    committed_amount: Decimal,
    currency_code: str,
    commitment_date: date,
    acting_tenant: str,
    actor: CommitmentActor,
    effective_at: datetime,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Commitment:
    """Effective-dated (valid-time) re-capture for the SAME identity (a successive close /
    amendment): close the head's ``valid_to`` (``PRIVATE.COMMITMENT_UPDATE``), then insert
    a new version (``PRIVATE.COMMITMENT_CREATE`` + its own ORIGIN edge + the DQ gate).
    ``currency_code`` is chain-immutable (refused if it differs from the head's). The head
    is sourced via the tenant-predicated ``current_commitment`` (never a caller id)."""
    _validate_amount(committed_amount)
    _validate_currency(currency_code)
    prior = current_commitment(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
    )
    if prior is None:
        raise NoCurrentCommitment(portfolio_id, instrument_id)
    _assert_chain_currency(prior, currency_code)

    assert_supersede_effective_at(prior.valid_from, effective_at, error=CommitmentValueError)
    now = now or utcnow()
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at  # CLOSE-FIRST (valid-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_type=ENTITY_COMMITMENT,
        entity_id=prior.id,
        event_type=PRIVATE_COMMITMENT_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )

    new = Commitment(
        tenant_id=prior.tenant_id,
        portfolio_id=prior.portfolio_id,
        instrument_id=prior.instrument_id,
        committed_amount=committed_amount,
        currency_code=prior.currency_code,  # chain-immutable (validated above)
        commitment_date=commitment_date,
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        system_to=None,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
    )
    if entity_id is not None:
        new.id = entity_id
    session.add(new)
    session.flush()
    _run_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=new)
    _origin_edge(
        session,
        tenant_id=new.tenant_id,
        entity_type=ENTITY_COMMITMENT,
        entity_id=new.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=new.tenant_id,
        entity_type=ENTITY_COMMITMENT,
        entity_id=new.id,
        event_type=PRIVATE_COMMITMENT_CREATE_EVENT,
        action=ACTION_CREATE,
        after_value=_summary(new),
        actor=actor,
        now=now,
    )
    return new


def correct_commitment(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    committed_amount: Decimal,
    restatement_reason: str,
    acting_tenant: str,
    actor: CommitmentActor,
    commitment_date: date | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Commitment:
    """As-known (system-time) correction for the SAME identity: close the head's
    ``system_to`` (``PRIVATE.COMMITMENT_UPDATE``), then insert a corrected version over the
    SAME valid window with ``restatement_reason`` (``PRIVATE.COMMITMENT_CORRECTION`` with
    ``action="correct"`` + the SYMMETRIC old→new payload + its own ORIGIN edge + the DQ
    gate). Currency is chain-immutable — a correction cannot re-denominate; the corrected
    ``commitment_date`` defaults to the prior's. A prior version's CONTENT is never mutated
    (TR-08)."""
    _validate_amount(committed_amount)
    if not restatement_reason:
        raise CommitmentValueError("restatement_reason is required for a correction (TR-08)")
    prior = current_commitment(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
    )
    if prior is None:
        raise NoCurrentCommitment(portfolio_id, instrument_id)

    now = now or utcnow()
    before = {"system_to": _json_safe(prior.system_to)}
    prior.system_to = now  # CLOSE-FIRST (system-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_type=ENTITY_COMMITMENT,
        entity_id=prior.id,
        event_type=PRIVATE_COMMITMENT_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={"system_to": _json_safe(prior.system_to)},
        actor=actor,
        now=now,
    )

    corrected = Commitment(
        tenant_id=prior.tenant_id,
        portfolio_id=prior.portfolio_id,
        instrument_id=prior.instrument_id,
        committed_amount=committed_amount,
        currency_code=prior.currency_code,  # chain-immutable (no parameter exists)
        commitment_date=(commitment_date if commitment_date is not None else prior.commitment_date),
        valid_from=prior.valid_from,  # SAME valid window (a knowledge-time restatement)
        valid_to=prior.valid_to,
        system_from=now,
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
    )
    if entity_id is not None:
        corrected.id = entity_id
    session.add(corrected)
    session.flush()
    _run_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=corrected)
    _origin_edge(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=ENTITY_COMMITMENT,
        entity_id=corrected.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=ENTITY_COMMITMENT,
        entity_id=corrected.id,
        event_type=PRIVATE_COMMITMENT_CORRECTION_EVENT,
        action=ACTION_CORRECT,  # the sibling FR-correction convention (not "update")
        # Symmetric old->new amount (the PA-0 review-fold lesson: a single scalar, NOT bulk).
        before_value={"committed_amount": _json_safe(prior.committed_amount)},
        after_value={
            **_summary(corrected),
            "committed_amount": _json_safe(corrected.committed_amount),
        },
        actor=actor,
        justification=restatement_reason,
        now=now,
    )
    return corrected


# --- reads (both-axes bitemporal reconstruct + entity-filtered current-head list) ---


def reconstruct_commitment_as_of(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    valid_at: datetime,
    known_at: datetime,
    acting_tenant: str,
) -> Commitment | None:
    """The commitment true at ``valid_at`` as KNOWN at ``known_at`` — the both-axes
    bitemporal read. Tenant-predicated; ``None`` if no version covers both instants."""
    return session.execute(
        select(Commitment).where(
            Commitment.tenant_id == str(acting_tenant),
            Commitment.portfolio_id == str(portfolio_id),
            Commitment.instrument_id == str(instrument_id),
            Commitment.valid_from <= valid_at,
            (Commitment.valid_to.is_(None)) | (Commitment.valid_to > valid_at),
            Commitment.system_from <= known_at,
            (Commitment.system_to.is_(None)) | (Commitment.system_to > known_at),
        )
        # No order_by: the bitemporal non-overlap invariant guarantees <= 1 covering version
        # (scalar_one_or_none raises on >1 — fail-loud; the reconstruct precedent).
    ).scalar_one_or_none()


def list_commitments(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
) -> list[Commitment]:
    """Current-head commitments (OPEN on both axes; tenant-predicated), optionally filtered
    by ``portfolio_id`` and/or ``instrument_id`` — the entity-filtered read shipped from
    birth (roadmap Part-4 rule 7; the positions/valuations read shape). Ordered by
    (portfolio_id, instrument_id) for a stable listing."""
    stmt = select(Commitment).where(
        Commitment.tenant_id == str(acting_tenant),
        Commitment.valid_to.is_(None),
        Commitment.system_to.is_(None),
    )
    if portfolio_id is not None:
        stmt = stmt.where(Commitment.portfolio_id == str(portfolio_id))
    if instrument_id is not None:
        stmt = stmt.where(Commitment.instrument_id == str(instrument_id))
    stmt = stmt.order_by(Commitment.portfolio_id, Commitment.instrument_id)
    return list(session.execute(stmt).scalars().all())
