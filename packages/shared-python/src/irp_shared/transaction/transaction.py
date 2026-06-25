"""Transaction binder (P1C-2, ENT-012) — record + reverse + tenant-filtered resolution.

CAPTURE-ONLY governed writes on an immutable append-only event log:

- ``resolve_transaction`` resolves a row by id with an EXPLICIT ``tenant_id == acting_tenant``
  predicate (fail-closed on SQLite AND PG) — a cross-tenant/unknown id raises
  ``TransactionNotVisible``.
- ``record_transaction`` resolves ``portfolio_id`` + ``instrument_id`` tenant-filtered (cross-tenant
  fails closed via ``PortfolioNotVisible`` / ``InstrumentNotVisible`` pre-commit), then appends one
  immutable row + emits ``TRANSACTION.RECORD`` + one MANUAL-source ORIGIN edge.
- ``reverse_transaction`` appends a NEW reversal row (``reverses_transaction_id`` = the original;
  negated ``quantity``/``gross_amount``) + emits ``TRANSACTION.REVERSE`` + its own ORIGIN edge.
  **The
  original row is NEVER mutated** — a reversal is an append, not an update (the user's special
  focus).

**No derivation:** a transaction/reversal is a bare event — it does NOT compute or unwind a
position,
valuation, holding, or exposure (there are none in P1C-2; positions are captured directly in P1C-3,
OD-P1C-E). Numeric fields are inert captures. The package imports one-way: ``transaction ->
{portfolio, reference, rails}`` (neither portfolio nor reference imports transaction).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.portfolio import resolve_portfolio
from irp_shared.reference.instrument import resolve_instrument
from irp_shared.transaction.models import Transaction
from irp_shared.transaction.service import (
    TransactionActor,
    record_transaction_record,
    record_transaction_reverse,
)

#: ``txn_type`` for a reversal record (a controlled-vocab value; extend by value).
REVERSAL_TXN_TYPE = "REVERSAL"


class TransactionNotVisible(Exception):
    """Raised when a ``transaction_id`` (e.g. a reversal target) is not visible in the acting tenant
    scope (cross-tenant id hidden, or unknown) — the dependent reverse/resolve fails closed."""

    def __init__(self, transaction_id: str) -> None:
        super().__init__(
            f"transaction {transaction_id} is not visible in the current tenant context"
        )
        self.transaction_id = str(transaction_id)


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _after(txn: Transaction) -> dict[str, object]:
    """DC-2 metadata for the audit event (identifying + controlled-vocab fields only)."""
    return {
        "portfolio_id": txn.portfolio_id,
        "instrument_id": txn.instrument_id,
        "txn_type": txn.txn_type,
        "trade_date": _json_safe(txn.trade_date),
        "quantity": _json_safe(txn.quantity),
        "currency_code": txn.currency_code,
        "external_ref": txn.external_ref,
        "reverses_transaction_id": txn.reverses_transaction_id,
    }


def resolve_transaction(
    session: Session, transaction_id: str, *, acting_tenant: str
) -> Transaction:
    """Resolve a ``transaction`` by id with an EXPLICIT ``tenant_id == acting_tenant`` predicate
    (fail-closed on SQLite AND PG). Raises :class:`TransactionNotVisible` on a hidden/unknown id."""
    txn = session.execute(
        select(Transaction).where(
            Transaction.id == str(transaction_id),
            Transaction.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if txn is None:
        raise TransactionNotVisible(str(transaction_id))
    return txn


def record_transaction(
    session: Session,
    *,
    tenant_id: str,
    portfolio_id: str,
    instrument_id: str,
    txn_type: str,
    trade_date: date,
    quantity: Decimal,
    actor: TransactionActor,
    settle_date: date | None = None,
    price: Decimal | None = None,
    gross_amount: Decimal | None = None,
    currency_code: str | None = None,
    external_ref: str | None = None,
    description: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Transaction:
    """Append one immutable ``transaction`` event (governed: MANUAL-source ORIGIN lineage +
    ``TRANSACTION.RECORD``). ``portfolio_id`` + ``instrument_id`` are resolved tenant-filtered —
    a cross-tenant/unknown reference fails closed (``PortfolioNotVisible`` /
    ``InstrumentNotVisible``)
    pre-commit (RLS WITH CHECK only gates the writing row's own ``tenant_id``).

    ``entity_id``/``now`` are the deterministic-injection seam (keyword-only, default-None): when
    None (every production call site) behavior is unchanged (server `uuid4` id + the mixin's
    wall-clock `system_from`); only the synthetic seed passes them for `uuid5` + a fixed clock."""
    resolve_portfolio(session, portfolio_id, acting_tenant=tenant_id)
    resolve_instrument(session, instrument_id, acting_tenant=tenant_id)

    txn = Transaction(
        tenant_id=str(tenant_id),
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        txn_type=txn_type,
        trade_date=trade_date,
        settle_date=settle_date,
        quantity=quantity,
        price=price,
        gross_amount=gross_amount,
        currency_code=currency_code,
        external_ref=external_ref,
        description=description,
    )
    if now is not None:
        txn.system_from = now  # seam: fixed clock (else the IA mixin default stamps wall-clock)
    if entity_id is not None:
        txn.id = entity_id  # seam: deterministic uuid5 id (skips the `default=new_uuid`)
    session.add(txn)
    session.flush()
    record_transaction_record(session, entity=txn, after_value=_after(txn), actor=actor, now=now)
    return txn


def reverse_transaction(
    session: Session,
    original: Transaction,
    *,
    actor: TransactionActor,
    trade_date: date | None = None,
    reason: str | None = None,
    external_ref: str | None = None,
    description: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Transaction:
    """Append a NEW reversal record against ``original`` (sets ``reverses_transaction_id``),
    same portfolio/instrument/currency, **negated** ``quantity``/``gross_amount`` — and emit
    ``TRANSACTION.REVERSE`` + its own ORIGIN edge. **The original row is NEVER mutated** (a reversal
    is an append, not an update; the P0001 trigger + ORM guard enforce it). A reversal may itself
    be reversed; the chain is append-only. NO position/valuation is unwound (capture-only).
    ``entity_id``/``now`` are the deterministic-injection seam (default-None ⇒ prod unchanged)."""
    reversal = Transaction(
        tenant_id=original.tenant_id,
        portfolio_id=original.portfolio_id,
        instrument_id=original.instrument_id,
        txn_type=REVERSAL_TXN_TYPE,
        trade_date=(trade_date if trade_date is not None else original.trade_date),
        settle_date=original.settle_date,
        quantity=-original.quantity,
        price=original.price,
        gross_amount=(None if original.gross_amount is None else -original.gross_amount),
        currency_code=original.currency_code,
        external_ref=external_ref,
        description=description,
        reverses_transaction_id=original.id,
    )
    if now is not None:
        reversal.system_from = (
            now  # seam: fixed clock (else the IA mixin default stamps wall-clock)
        )
    if entity_id is not None:
        reversal.id = entity_id  # seam: deterministic uuid5 id for the reversal record
    session.add(reversal)
    session.flush()
    record_transaction_reverse(
        session, entity=reversal, after_value=_after(reversal), actor=actor, reason=reason, now=now
    )
    return reversal
