"""Transaction ORM model (P1C-2, ENT-012, IA) — the immutable append-only trade/cashflow event log.

The platform's first **domain IA** entity. PROPRIETARY, tenant-scoped, **NEVER hybrid** (symmetric
RLS
only, migration 0013). **Truly immutable** (unlike the IA-status-mutable ``ingestion_batch``/
``calculation_run``): a ``transaction`` row is NEVER updated or deleted — enforced two-layer by the
``irp_prevent_mutation`` P0001 DB trigger (``transaction`` is in ``APPEND_ONLY_TABLES``) AND the ORM
``before_update``/``before_delete`` guard below (``AppendOnlyViolation``). A correction is an
**append**
(a reversal record with ``reverses_transaction_id``), never a mutation.

``ImmutableAppendOnlyMixin`` records knowledge time only (``system_from``); there is NO ``valid_*``/
``system_to`` (not EV/FR), NO ``record_version`` and NO ``status``/``is_active`` (an immutable event
has
no versioning/lifecycle). ``txn_type`` is a controlled-vocab **plain String** (no enum/CHECK; extend
by
value — MG-01). ``portfolio_id``/``instrument_id`` are intra-tenant FKs resolved fail-closed in the
binder; ``reverses_transaction_id`` is a nullable self-FK (set on a reversal record). Numeric
``quantity``/``price``/``gross_amount`` are **inert** captured values — never recomputed (no calc).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    event,
    text,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass


class Transaction(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Trade/cashflow event (ENT-012, IA append-only). PROPRIETARY/symmetric; truly immutable."""

    __tablename__ = "transaction"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # Idempotency: a supplied external_ref is unique per tenant (re-post rejected); NULLs
        # coexist
        # (partial-unique, the LEI precedent). PG uses the partial WHERE; SQLite's plain unique
        # index
        # is NULL-distinct, giving the same coexist-NULLs / reject-dup behaviour.
        Index(
            "uq_transaction_tenant_external_ref",
            "tenant_id",
            "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
    )

    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    # Controlled-vocab plain string (no enum/CHECK): BUY/SELL/DIVIDEND/INTEREST/FEE/TRANSFER_IN/
    # TRANSFER_OUT/REVERSAL/...; extend by value.
    txn_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)  # business event date (inert)
    settle_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # inert
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)  # signed; inert
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)  # inert
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)  # inert
    currency_code: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )  # plain ISO str, inert
    external_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)  # idempotency key
    # Self-FK: set on a REVERSAL record (NULL = an original). Intra-tenant; resolved fail-closed.
    reverses_transaction_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("transaction.id"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# Transaction is truly immutable — the ORM guard (paired with the migration-0013 P0001 trigger)
# forbids update/delete. A correction is a NEW reversal row, never a mutation.
event.listen(Transaction, "before_update", _block_mutation)
event.listen(Transaction, "before_delete", _block_mutation)
