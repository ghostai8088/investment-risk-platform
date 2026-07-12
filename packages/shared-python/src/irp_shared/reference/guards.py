"""Shared reference-entity guards — one implementation of the cross-family instrument
tenant-resolution check (the ``portfolio/guards.py`` twin; PA-1 review fold).

The P3-5 principal finding: PG FK checks BYPASS RLS, so an id lifted from a hand-minted snapshot's
pinned JSON must be re-resolved under the acting tenant BEFORE it is stamped into a NOT-NULL FK
column. Every binder/builder that stamps or pins an instrument FK applies the same guard; it lives
ONCE here, parameterized by the caller's own refusal error class (each family keeps its own error
vocabulary — the API maps them per family).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session


def assert_instrument_in_tenant(
    session: Session, instrument_id: str, *, acting_tenant: str, error: type[Exception]
) -> None:
    """Re-resolve ``instrument_id`` under the acting tenant with an EXPLICIT tenant predicate
    (models-only import — no service cycle). Raises ``error`` if the id is not visible in the
    acting tenant — a FOREIGN/non-existent instrument_id must never be stamped into a NOT-NULL
    ``instrument`` FK."""
    from irp_shared.reference.models import Instrument  # models-only (no cycle)

    row = session.execute(
        select(Instrument.id).where(
            Instrument.id == str(instrument_id),
            Instrument.tenant_id == str(acting_tenant),
        )
    ).one_or_none()
    if row is None:
        raise error(f"instrument {instrument_id} is not visible in the acting tenant — refused")
