"""Transaction endpoints (P1C-2, REQ-PPM-003 transaction half) — IA append-only, CAPTURE-ONLY.

Thin layer over the ``irp_shared.transaction`` binder. PROPRIETARY tenant-scoped (NEVER hybrid),
immutable append-only. Each write is gated deny-by-default; ``tenant_id`` is server-stamped from the
principal; ``portfolio_id``/``instrument_id`` are resolved tenant-filtered (cross-tenant/unknown ->
indistinguishable 404); a single end-of-request ``db.commit()``.

There is **no PUT/PATCH/DELETE** — a transaction is immutable. A correction is ``POST
/{id}/reverse``,
which books a NEW reversal record (``reverses_transaction_id`` set) and never mutates the original.
**No position/valuation/holdings/aggregate endpoint** (capture-only; no derivation, no cashflow
engine).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.portfolio import PortfolioNotVisible
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.transaction import (
    Transaction,
    TransactionActor,
    TransactionNotVisible,
    record_transaction,
    resolve_transaction,
    reverse_transaction,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_record = require_permission("transaction.record")
_require_view = require_permission("transaction.view")


def _actor(principal: Principal) -> TransactionActor:
    return TransactionActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


class TransactionIn(BaseModel):
    portfolio_id: uuid.UUID  # malformed -> 422
    instrument_id: uuid.UUID
    txn_type: str
    trade_date: date
    quantity: Decimal
    settle_date: date | None = None
    price: Decimal | None = None
    gross_amount: Decimal | None = None
    currency_code: str | None = None
    external_ref: str | None = None
    description: str | None = None


class TransactionReverseIn(BaseModel):
    trade_date: date | None = None
    reason: str | None = None
    external_ref: str | None = None
    description: str | None = None


class TransactionOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str
    txn_type: str
    trade_date: date
    settle_date: date | None
    quantity: Decimal
    price: Decimal | None
    gross_amount: Decimal | None
    currency_code: str | None
    external_ref: str | None
    reverses_transaction_id: str | None
    description: str | None


def _out(txn: Transaction) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        portfolio_id=txn.portfolio_id,
        instrument_id=txn.instrument_id,
        txn_type=txn.txn_type,
        trade_date=txn.trade_date,
        settle_date=txn.settle_date,
        quantity=txn.quantity,
        price=txn.price,
        gross_amount=txn.gross_amount,
        currency_code=txn.currency_code,
        external_ref=txn.external_ref,
        reverses_transaction_id=txn.reverses_transaction_id,
        description=txn.description,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TransactionOut)
def record_transaction_endpoint(
    body: TransactionIn,
    principal: Principal = Depends(_require_record),
    db: Session = Depends(get_tenant_session),
) -> TransactionOut:
    try:
        txn = record_transaction(
            db,
            tenant_id=principal.tenant_id,  # server-stamped; body has no tenant_id
            portfolio_id=str(body.portfolio_id),
            instrument_id=str(body.instrument_id),
            txn_type=body.txn_type,
            trade_date=body.trade_date,
            quantity=body.quantity,
            actor=_actor(principal),
            settle_date=body.settle_date,
            price=body.price,
            gross_amount=body.gross_amount,
            currency_code=body.currency_code,
            external_ref=body.external_ref,
            description=body.description,
        )
    except (
        PortfolioNotVisible,
        InstrumentNotVisible,
    ):  # cross-tenant/unknown -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio or instrument not found"
        ) from None
    db.commit()
    return _out(txn)


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    portfolio_id: uuid.UUID | None = Query(None),
    instrument_id: uuid.UUID | None = Query(None),
    txn_type: str | None = Query(None),
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[TransactionOut]:
    stmt = select(Transaction).order_by(Transaction.system_from)
    if portfolio_id is not None:
        stmt = stmt.where(Transaction.portfolio_id == str(portfolio_id))
    if instrument_id is not None:
        stmt = stmt.where(Transaction.instrument_id == str(instrument_id))
    if txn_type is not None:
        stmt = stmt.where(Transaction.txn_type == txn_type)
    rows = db.execute(stmt).scalars().all()
    return [_out(txn) for txn in rows]


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> TransactionOut:
    txn = db.get(Transaction, str(transaction_id))
    if txn is None:  # not found OR RLS-hidden cross-tenant -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")
    return _out(txn)


@router.post(
    "/{transaction_id}/reverse", status_code=status.HTTP_201_CREATED, response_model=TransactionOut
)
def reverse_transaction_endpoint(
    transaction_id: uuid.UUID,
    body: TransactionReverseIn,
    principal: Principal = Depends(_require_record),
    db: Session = Depends(get_tenant_session),
) -> TransactionOut:
    """Book a reversal record against the original (immutable — the original is never mutated)."""
    try:
        original = resolve_transaction(db, str(transaction_id), acting_tenant=principal.tenant_id)
        reversal = reverse_transaction(
            db,
            original,
            actor=_actor(principal),
            trade_date=body.trade_date,
            reason=body.reason,
            external_ref=body.external_ref,
            description=body.description,
        )
    except TransactionNotVisible:  # cross-tenant/unknown original -> indistinguishable 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found"
        ) from None
    db.commit()
    return _out(reversal)
