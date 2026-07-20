"""Private-capital endpoints (CC-1, ENT-015/016) — captured commitments, calls, distributions.

Thin layer over the ``irp_shared.private_capital`` services. PROPRIETARY tenant-scoped
(NEVER hybrid). Commitment (FR): capture / supersede / correct / as-of / list under the
``commitment.edit`` maker verb (+ ``commitment.view`` reads). Capital calls and
distributions (IA, truly immutable): capture + REVERSE + list under the
``commitment.record`` maker verb — there is **no PUT/PATCH/DELETE anywhere**; an event
correction is a FULL-reversal APPEND (exact negation, Σ self-correcting).

THE READ RULE (OD-CC-1-D): these events do NOT feed TWR/Dietz or backtest realized P&L —
those chains read exclusively ``transaction.TRANSFER_IN/TRANSFER_OUT``; a cash movement
in a return-modeled book must be separately posted as a transaction; nothing
auto-bridges in v1.

All three list reads take optional ``portfolio_id``/``instrument_id`` query filters —
the entity-filtered read shipped from birth (roadmap Part-4 rule 7; the
positions/valuations shape). ``tenant_id`` is server-stamped from the principal; a
single end-of-request ``db.commit()``; exact-type error maps through the shared
``raise_mapped_write``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_backend.api.write_errors import raise_mapped_write
from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.service import Principal
from irp_shared.private_capital.capital_flow_service import (
    CapitalFlowActor,
    CapitalFlowNotVisible,
    CapitalFlowValueError,
    capture_capital_call,
    capture_distribution,
    list_capital_calls,
    list_distributions,
    reverse_capital_call,
    reverse_distribution,
)
from irp_shared.private_capital.commitment_service import (
    CommitmentActor,
    CommitmentValueError,
    NoCurrentCommitment,
    capture_commitment,
    correct_commitment,
    list_commitments,
    reconstruct_commitment_as_of,
    supersede_commitment,
)
from irp_shared.private_capital.models import CapitalCall, Commitment, Distribution

router = APIRouter(tags=["private-capital"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_edit = require_permission("commitment.edit")  # the FR maker (commitment ops)
_require_record = require_permission("commitment.record")  # the IA maker (events)
_require_view = require_permission("commitment.view")


def _commitment_actor(principal: Principal) -> CommitmentActor:
    return CommitmentActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


def _flow_actor(principal: Principal) -> CapitalFlowActor:
    return CapitalFlowActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


# --- DTOs ---


class CommitmentIn(BaseModel):
    portfolio_id: uuid.UUID  # malformed -> 422
    instrument_id: uuid.UUID
    committed_amount: Decimal
    currency_code: str
    commitment_date: date
    valid_from: datetime | None = None


class CommitmentSupersedeIn(BaseModel):
    # Deliberately NOT inheriting CommitmentIn: its optional valid_from would be advertised
    # in the OpenAPI schema as a silent no-op here — the supersede window start IS
    # effective_at (the adversarial-review fold).
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    committed_amount: Decimal
    currency_code: str
    commitment_date: date
    effective_at: datetime


class CommitmentCorrectIn(BaseModel):
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    committed_amount: Decimal
    restatement_reason: str
    commitment_date: date | None = None


class CommitmentOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str
    committed_amount: Decimal
    currency_code: str
    commitment_date: date
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    supersedes_id: str | None
    restatement_reason: str | None
    record_version: int


class CommitmentListOut(BaseModel):
    items: list[CommitmentOut]


class CapitalCallIn(BaseModel):
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    event_date: date
    amount: Decimal
    currency_code: str
    call_type: str
    external_ref: str | None = None


class DistributionIn(BaseModel):
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    event_date: date
    amount: Decimal
    currency_code: str
    distribution_type: str
    is_recallable: bool = False
    external_ref: str | None = None


class ReversalIn(BaseModel):
    event_id: uuid.UUID  # the capital-call / distribution row being reversed
    reason: str


class CapitalCallOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str
    commitment_version_id: str
    event_date: date
    amount: Decimal  # signed: negative on a reversal row (Σ self-correcting)
    currency_code: str
    call_type: str
    external_ref: str | None
    reverses_id: str | None
    system_from: datetime


class DistributionOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str
    commitment_version_id: str
    event_date: date
    amount: Decimal
    currency_code: str
    distribution_type: str
    is_recallable: bool
    external_ref: str | None
    reverses_id: str | None
    system_from: datetime


class CapitalCallListOut(BaseModel):
    items: list[CapitalCallOut]


class DistributionListOut(BaseModel):
    items: list[DistributionOut]


def _commitment_out(row: Commitment) -> CommitmentOut:
    return CommitmentOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        committed_amount=row.committed_amount,
        currency_code=row.currency_code,
        commitment_date=row.commitment_date,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        system_from=row.system_from,
        system_to=row.system_to,
        supersedes_id=row.supersedes_id,
        restatement_reason=row.restatement_reason,
        record_version=row.record_version,
    )


def _call_out(row: CapitalCall) -> CapitalCallOut:
    return CapitalCallOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        commitment_version_id=row.commitment_version_id,
        event_date=row.event_date,
        amount=row.amount,
        currency_code=row.currency_code,
        call_type=row.call_type,
        external_ref=row.external_ref,
        reverses_id=row.reverses_id,
        system_from=row.system_from,
    )


def _dist_out(row: Distribution) -> DistributionOut:
    return DistributionOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        commitment_version_id=row.commitment_version_id,
        event_date=row.event_date,
        amount=row.amount,
        currency_code=row.currency_code,
        distribution_type=row.distribution_type,
        is_recallable=row.is_recallable,
        external_ref=row.external_ref,
        reverses_id=row.reverses_id,
        system_from=row.system_from,
    )


# --- exact-type governed-write error maps (fail-closed; whole-unit rollback) ---

_COMMITMENT_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    CommitmentValueError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid commitment input",
    ),
    NoCurrentCommitment: (
        status.HTTP_409_CONFLICT,
        "no current commitment for the (portfolio, instrument) pair to supersede/correct",
    ),
    DataQualityError: (
        status.HTTP_409_CONFLICT,
        "commitment failed a data-quality gate",
    ),
    IntegrityError: (
        status.HTTP_409_CONFLICT,
        "a current open commitment already exists for this (portfolio, instrument) pair",
    ),
}

_CAPITAL_FLOW_WRITE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    CapitalFlowValueError: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid capital-call/distribution input",
    ),
    CapitalFlowNotVisible: (
        status.HTTP_404_NOT_FOUND,
        "capital-call/distribution not found",
    ),
    NoCurrentCommitment: (
        status.HTTP_409_CONFLICT,
        "no current commitment for the (portfolio, instrument) pair — capture one first",
    ),
    DataQualityError: (
        status.HTTP_409_CONFLICT,
        "capital-call/distribution failed a data-quality gate",
    ),
    IntegrityError: (
        status.HTTP_409_CONFLICT,
        "this event is already reversed",
    ),
}

_COMMITMENT_EXCS = (CommitmentValueError, NoCurrentCommitment, DataQualityError, IntegrityError)
_FLOW_EXCS = (
    CapitalFlowValueError,
    CapitalFlowNotVisible,
    NoCurrentCommitment,
    DataQualityError,
    IntegrityError,
)


# --- commitment endpoints (FR; commitment.edit) ---


@router.post("/commitments", response_model=CommitmentOut, status_code=status.HTTP_201_CREATED)
def capture_commitment_endpoint(
    body: CommitmentIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> CommitmentOut:
    """Capture the first open commitment for a (portfolio, fund-instrument) pair — a MANUAL
    ORIGIN edge + PRIVATE.COMMITMENT_CREATE + the DQ gate. Both FK targets re-resolved
    tenant-filtered pre-write (a foreign/absent portfolio or instrument is a 422)."""
    try:
        row = capture_commitment(
            db,
            portfolio_id=str(body.portfolio_id),
            instrument_id=str(body.instrument_id),
            committed_amount=body.committed_amount,
            currency_code=body.currency_code,
            commitment_date=body.commitment_date,
            acting_tenant=principal.tenant_id,
            actor=_commitment_actor(principal),
            valid_from=body.valid_from,
        )
    except _COMMITMENT_EXCS as exc:
        raise_mapped_write(db, exc, _COMMITMENT_WRITE_ERRORS)
    out = _commitment_out(row)
    db.commit()
    return out


@router.post(
    "/commitments/supersede", response_model=CommitmentOut, status_code=status.HTTP_201_CREATED
)
def supersede_commitment_endpoint(
    body: CommitmentSupersedeIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> CommitmentOut:
    """Effective-dated re-capture (a successive close / amendment) for the SAME pair.
    ``currency_code`` is chain-immutable — a differing currency is a 422."""
    try:
        row = supersede_commitment(
            db,
            portfolio_id=str(body.portfolio_id),
            instrument_id=str(body.instrument_id),
            committed_amount=body.committed_amount,
            currency_code=body.currency_code,
            commitment_date=body.commitment_date,
            acting_tenant=principal.tenant_id,
            actor=_commitment_actor(principal),
            effective_at=body.effective_at,
        )
    except _COMMITMENT_EXCS as exc:
        raise_mapped_write(db, exc, _COMMITMENT_WRITE_ERRORS)
    out = _commitment_out(row)
    db.commit()
    return out


@router.post(
    "/commitments/correct", response_model=CommitmentOut, status_code=status.HTTP_201_CREATED
)
def correct_commitment_endpoint(
    body: CommitmentCorrectIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> CommitmentOut:
    """As-known restatement over the SAME valid window (requires ``restatement_reason``;
    emits PRIVATE.COMMITMENT_CORRECTION with the symmetric old→new payload). The currency
    cannot be re-denominated (no such field exists on this body — chain-immutable)."""
    try:
        row = correct_commitment(
            db,
            portfolio_id=str(body.portfolio_id),
            instrument_id=str(body.instrument_id),
            committed_amount=body.committed_amount,
            restatement_reason=body.restatement_reason,
            acting_tenant=principal.tenant_id,
            actor=_commitment_actor(principal),
            commitment_date=body.commitment_date,
        )
    except _COMMITMENT_EXCS as exc:
        raise_mapped_write(db, exc, _COMMITMENT_WRITE_ERRORS)
    out = _commitment_out(row)
    db.commit()
    return out


@router.get("/commitments/as-of", response_model=CommitmentOut)
def reconstruct_commitment_endpoint(
    portfolio_id: uuid.UUID,
    instrument_id: uuid.UUID,
    valid_at: datetime,
    known_at: datetime,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> CommitmentOut:
    """The commitment true at ``valid_at`` as KNOWN at ``known_at`` (both-axes bitemporal
    read; read-only, no aggregation). 404 if no version covers both instants."""
    row = reconstruct_commitment_as_of(
        db,
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        valid_at=valid_at,
        known_at=known_at,
        acting_tenant=principal.tenant_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="commitment not found")
    return _commitment_out(row)


@router.get("/commitments", response_model=CommitmentListOut)
def list_commitments_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    instrument_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> CommitmentListOut:
    """Current-head commitments, optionally filtered by portfolio and/or instrument (the
    rule-7 entity-filtered read)."""
    rows = list_commitments(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        instrument_id=(str(instrument_id) if instrument_id is not None else None),
    )
    return CommitmentListOut(items=[_commitment_out(r) for r in rows])


# --- capital-call endpoints (IA; commitment.record) ---


@router.post("/capital-calls", response_model=CapitalCallOut, status_code=status.HTTP_201_CREATED)
def capture_capital_call_endpoint(
    body: CapitalCallIn,
    principal: Principal = Depends(_require_record),
    db: Session = Depends(get_tenant_session),
) -> CapitalCallOut:
    """Record one capital-call event (requires a CURRENT commitment for the pair; the event
    currency must equal the commitment's). Append-only — there is no edit/delete.
    THE READ RULE (OD-CC-1-D): this event does NOT feed
    TWR/Dietz or backtest realized P&L; a cash movement in a return-modeled book must be
    separately posted as a transaction — nothing auto-bridges."""
    try:
        row = capture_capital_call(
            db,
            portfolio_id=str(body.portfolio_id),
            instrument_id=str(body.instrument_id),
            event_date=body.event_date,
            amount=body.amount,
            currency_code=body.currency_code,
            call_type=body.call_type,
            acting_tenant=principal.tenant_id,
            actor=_flow_actor(principal),
            external_ref=body.external_ref,
        )
    except _FLOW_EXCS as exc:
        raise_mapped_write(db, exc, _CAPITAL_FLOW_WRITE_ERRORS)
    out = _call_out(row)
    db.commit()
    return out


@router.post(
    "/capital-calls/reverse", response_model=CapitalCallOut, status_code=status.HTTP_201_CREATED
)
def reverse_capital_call_endpoint(
    body: ReversalIn,
    principal: Principal = Depends(_require_record),
    db: Session = Depends(get_tenant_session),
) -> CapitalCallOut:
    """Append the FULL reversal of a capital call (amount = the exact negation; emits
    PRIVATE.CAPITAL_CALL_REVERSE). A reversal cannot be reversed; one reversal per event.
    THE READ RULE (OD-CC-1-D): this event does NOT feed
    TWR/Dietz or backtest realized P&L; a cash movement in a return-modeled book must be
    separately posted as a transaction — nothing auto-bridges."""
    try:
        row = reverse_capital_call(
            db,
            capital_call_id=str(body.event_id),
            acting_tenant=principal.tenant_id,
            actor=_flow_actor(principal),
            reason=body.reason,
        )
    except _FLOW_EXCS as exc:
        raise_mapped_write(db, exc, _CAPITAL_FLOW_WRITE_ERRORS)
    out = _call_out(row)
    db.commit()
    return out


@router.get("/capital-calls", response_model=CapitalCallListOut)
def list_capital_calls_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    instrument_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> CapitalCallListOut:
    """Capital-call events (reversal rows included — Σ(amount) is self-correcting),
    optionally filtered by portfolio and/or instrument (rule 7).
    THE READ RULE (OD-CC-1-D): this event does NOT feed
    TWR/Dietz or backtest realized P&L; a cash movement in a return-modeled book must be
    separately posted as a transaction — nothing auto-bridges."""
    rows = list_capital_calls(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        instrument_id=(str(instrument_id) if instrument_id is not None else None),
    )
    return CapitalCallListOut(items=[_call_out(r) for r in rows])


# --- distribution endpoints (IA; commitment.record) ---


@router.post("/distributions", response_model=DistributionOut, status_code=status.HTTP_201_CREATED)
def capture_distribution_endpoint(
    body: DistributionIn,
    principal: Principal = Depends(_require_record),
    db: Session = Depends(get_tenant_session),
) -> DistributionOut:
    """Record one distribution event (``is_recallable`` is captured as data; its unfunded
    interpretation is the CC-2 projection's, not this capture's).
    THE READ RULE (OD-CC-1-D): this event does NOT feed
    TWR/Dietz or backtest realized P&L; a cash movement in a return-modeled book must be
    separately posted as a transaction — nothing auto-bridges."""
    try:
        row = capture_distribution(
            db,
            portfolio_id=str(body.portfolio_id),
            instrument_id=str(body.instrument_id),
            event_date=body.event_date,
            amount=body.amount,
            currency_code=body.currency_code,
            distribution_type=body.distribution_type,
            acting_tenant=principal.tenant_id,
            actor=_flow_actor(principal),
            is_recallable=body.is_recallable,
            external_ref=body.external_ref,
        )
    except _FLOW_EXCS as exc:
        raise_mapped_write(db, exc, _CAPITAL_FLOW_WRITE_ERRORS)
    out = _dist_out(row)
    db.commit()
    return out


@router.post(
    "/distributions/reverse", response_model=DistributionOut, status_code=status.HTTP_201_CREATED
)
def reverse_distribution_endpoint(
    body: ReversalIn,
    principal: Principal = Depends(_require_record),
    db: Session = Depends(get_tenant_session),
) -> DistributionOut:
    """Append the FULL reversal of a distribution (incl. the ``is_recallable`` echo).
    THE READ RULE (OD-CC-1-D): this event does NOT feed
    TWR/Dietz or backtest realized P&L; a cash movement in a return-modeled book must be
    separately posted as a transaction — nothing auto-bridges."""
    try:
        row = reverse_distribution(
            db,
            distribution_id=str(body.event_id),
            acting_tenant=principal.tenant_id,
            actor=_flow_actor(principal),
            reason=body.reason,
        )
    except _FLOW_EXCS as exc:
        raise_mapped_write(db, exc, _CAPITAL_FLOW_WRITE_ERRORS)
    out = _dist_out(row)
    db.commit()
    return out


@router.get("/distributions", response_model=DistributionListOut)
def list_distributions_endpoint(
    portfolio_id: uuid.UUID | None = Query(default=None),
    instrument_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> DistributionListOut:
    """Distribution events, optionally filtered by portfolio and/or instrument (rule 7).
    THE READ RULE (OD-CC-1-D): this event does NOT feed
    TWR/Dietz or backtest realized P&L; a cash movement in a return-modeled book must be
    separately posted as a transaction — nothing auto-bridges."""
    rows = list_distributions(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=(str(portfolio_id) if portfolio_id is not None else None),
        instrument_id=(str(instrument_id) if instrument_id is not None else None),
    )
    return DistributionListOut(items=[_dist_out(r) for r in rows])
