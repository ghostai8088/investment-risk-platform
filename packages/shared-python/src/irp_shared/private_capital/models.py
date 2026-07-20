"""Private-capital ORM models (CC-1): ENT-015 ``commitment`` (FR) + ENT-016 events (IA).

All three tables are PROPRIETARY, tenant-scoped, symmetric FORCE RLS (migration 0044),
NEVER hybrid. Captured inputs — no snapshot/run/model binding anywhere in this module.

**Commitment (FR bitemporal, the position/valuation protocol):** an LP commitment of
``committed_amount`` in ``currency_code`` by a tenant ``portfolio`` to a private-fund
``instrument`` (an ORDINARY instrument row under the PA-0 private ``asset_class``
convention — no new fund schema). Under the current-row partial-unique, **the
(portfolio_id, instrument_id) pair IS the stable commitment identity** — FR
supersede/correct mints a NEW row id per version, so version-row ids are NOT stable
linkage targets (the CC-1 planning verifier's structural HIGH); the ENT-016 event tables
therefore key on the pair, never on a commitment-row FK. ``currency_code`` is
CHAIN-IMMUTABLE (service-enforced): supersede and correct refuse a currency differing
from the prior version's, because the immutable event rows validate against it. A
supersede may lower ``committed_amount`` below the sum of captured calls — the capture
layer does not adjudicate economics (funded/unfunded arithmetic is CC-2's, OD-CC-1-E).

**CapitalCall / Distribution (IA append-only, the transaction protocol):** truly
immutable event rows — the ``irp_prevent_mutation`` P0001 trigger (both tables in
``APPEND_ONLY_TABLES``, migration 0044) AND the ORM guard below. NO ``TimestampMixin``
(the transaction precedent: ``updated_*`` on a P0001-guarded table is dead from birth;
the DatasetSnapshot deviation is recorded in the decision record). A correction is a
FULL REVERSAL append (``reverses_id`` self-FK): ``amount`` = the EXACT NEGATION of the
reversed amount (the ``reverse_transaction`` sign convention — a naive sum is
self-correcting), every other economic field echoed byte-for-byte; knowledge time lives
in ``system_from``. ``commitment_version_id`` is a PROVENANCE-ONLY echo of the
commitment version row current at capture time — deliberately named "version" so no
consumer mistakes it for the aggregation key (aggregate by (portfolio_id,
instrument_id)); it is a plain GUID column, not an FK, because FR version rows are not
stable link targets.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, event, text
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    FullReproducibleMixin,
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass

#: Controlled-vocab plain strings (no enum/CHECK; extend by value — MG-01).
CALL_TYPES = ("DRAWDOWN", "EQUALIZATION", "FEE")
DISTRIBUTION_TYPES = ("RETURN_OF_CAPITAL", "CAPITAL_GAIN", "INCOME")


class Commitment(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """LP commitment to a private fund (ENT-015, FR bitemporal). PROPRIETARY/symmetric RLS."""

    __tablename__ = "commitment"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        # Exactly ONE open commitment per (portfolio, fund) on both axes — the stable
        # identity invariant the ENT-016 event tables key on. A successive close is an FR
        # supersede carrying the new total; genuinely separate same-fund commitments are a
        # recorded v1 limitation (OD-CC-1-A).
        Index(
            "uq_commitment_current",
            "tenant_id",
            "portfolio_id",
            "instrument_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    # Inert captured value (never recomputed); strictly positive (service-enforced).
    committed_amount: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 6), nullable=False)
    # Plain ISO string; CHAIN-IMMUTABLE across supersede/correct (service-enforced).
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    # The vintage anchor (CC-2 consumes it); vintage_year is DERIVED, never stored.
    commitment_date: Mapped[date] = mapped_column(Date, nullable=False)
    restatement_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # set ONLY on a correction (TR-08)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("commitment.id"), nullable=True
    )  # link to the superseded version (set on supersede + correction)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CapitalCall(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Capital-call event (ENT-016, IA append-only). PROPRIETARY/symmetric; truly immutable."""

    __tablename__ = "capital_call"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # One reversal per event, race-closed at the index (PG partial WHERE; SQLite's
        # plain unique index is NULL-distinct — same coexist-NULLs / reject-dup shape).
        Index(
            "uq_capital_call_reverses",
            "reverses_id",
            unique=True,
            postgresql_where=text("reverses_id IS NOT NULL"),
        ),
    )

    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    # Provenance-only echo of the commitment version row current at capture — NOT the
    # aggregation key and deliberately not an FK (see the module docstring).
    commitment_version_id: Mapped[str] = mapped_column(GUID, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)  # business date (inert)
    # Signed: strictly positive on an ordinary capture; the EXACT NEGATION on a reversal.
    amount: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    # Controlled-vocab plain string: DRAWDOWN/EQUALIZATION/FEE; extend by value.
    call_type: Mapped[str] = mapped_column(String(30), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Self-FK: set on a REVERSAL record (NULL = an original).
    reverses_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("capital_call.id"), nullable=True
    )


class Distribution(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Distribution event (ENT-016, IA append-only). PROPRIETARY/symmetric; truly immutable."""

    __tablename__ = "distribution"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        Index(
            "uq_distribution_reverses",
            "reverses_id",
            unique=True,
            postgresql_where=text("reverses_id IS NOT NULL"),
        ),
    )

    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("instrument.id"), nullable=False, index=True
    )
    commitment_version_id: Mapped[str] = mapped_column(GUID, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 6), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    # Controlled-vocab plain string: RETURN_OF_CAPITAL/CAPITAL_GAIN/INCOME; extend by value.
    distribution_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Captured as DATA; the unfunded arithmetic that interprets it is CC-2's (OD-CC-1-E).
    # A partial-recallable distribution is captured as two rows.
    is_recallable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    external_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)
    reverses_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("distribution.id"), nullable=True
    )


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# Both event tables are truly immutable — the ORM guard (paired with the migration-0044
# P0001 triggers) forbids update/delete. A correction is a NEW reversal row, never a mutation.
event.listen(CapitalCall, "before_update", _block_mutation)
event.listen(CapitalCall, "before_delete", _block_mutation)
event.listen(Distribution, "before_update", _block_mutation)
event.listen(Distribution, "before_delete", _block_mutation)
