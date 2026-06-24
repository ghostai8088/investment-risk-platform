"""Transaction domain package (P1C-2) — the immutable append-only trade/cashflow event log.

``transaction`` (ENT-012) is the platform's first **domain IA** entity: an immutable append-only
event log keyed to a ``portfolio`` + an ``instrument``. CAPTURE-ONLY — recorded, never applied:
**no position derivation, no cashflow engine, no valuation, no exposure aggregation, no
corporate-action application.** Corrections are **explicit reversal records** (a new row with
``reverses_transaction_id``), never updates — immutability is enforced two-layer (the
``irp_prevent_mutation`` P0001 DB trigger AND the ORM ``before_update``/``before_delete`` guard).

The first entity depending on **two** upstream packages — it imports ``resolve_portfolio`` (from
``portfolio``) + ``resolve_instrument`` (from ``reference``) + the rails
(lineage/audit/db/temporal);
it never imports ``irp_backend`` or ``irp_shared.models`` (the aggregator) — enforced by an
import-direction test. One-way: ``transaction -> {portfolio, reference, rails}``.
"""

from __future__ import annotations

from irp_shared.transaction.events import (
    TRANSACTION_RECORD_EVENT,
    TRANSACTION_REVERSE_EVENT,
)
from irp_shared.transaction.models import Transaction
from irp_shared.transaction.service import TransactionActor
from irp_shared.transaction.transaction import (
    TransactionNotVisible,
    record_transaction,
    resolve_transaction,
    reverse_transaction,
)

__all__ = [
    "Transaction",
    "TransactionActor",
    "TransactionNotVisible",
    "TRANSACTION_RECORD_EVENT",
    "TRANSACTION_REVERSE_EVENT",
    "resolve_transaction",
    "record_transaction",
    "reverse_transaction",
]
