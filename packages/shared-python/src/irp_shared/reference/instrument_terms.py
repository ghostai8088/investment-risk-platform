"""Instrument-terms binder — the FR (full-reproducible / bitemporal) protocol (ENT-001 terms).

The platform's FIRST real bitemporal usage (OD-P1B-A; temporal standard §2A). ``instrument_terms``
keeps
full version history in-table on BOTH axes — ``valid_from/valid_to`` (valid time, TR-01) and
``system_from/system_to`` (system/knowledge time, TR-02). Three governed operations, plus the as-of
read:

- ``create_instrument_terms`` — the first open version (``valid_to``/``system_to`` NULL).
- ``supersede_instrument_terms`` — a new *valid-time* version effective at ``effective_at``: close
the
  current head's ``valid_to`` (``REFERENCE.UPDATE``), then insert a new open version
  (``REFERENCE.CREATE``).
- ``correct_instrument_terms`` — an as-known *system-time* restatement (TR-08): close the prior
row's
  ``system_to`` (``REFERENCE.UPDATE``), then insert a corrected version with the SAME valid period,
  ``restatement_reason`` + ``supersedes_id`` (``REFERENCE.CORRECTION`` / EVT-142).
- ``reconstruct_terms_as_of`` — the bitemporal read (current view when ``known_at`` defaults to now,
TR-04).

Invariants: ONE ``now = utcnow()`` per supersede/correction (so a prior close-out and the new row's
open
boundary share the instant — no inter-row gap); CLOSE-FIRST ordering (mutate+flush the prior close-
out
column before adding the new version) so the dual-open current-head partial-unique is never
transiently
violated; a prior version's economic columns are NEVER mutated in place. Every resolver carries the
explicit ``tenant_id == acting_tenant`` predicate (fail-closed cross-tenant). NO pricing/cashflow/
day-count/valuation math.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.audit.payload import json_safe as _json_safe
from irp_shared.db.bitemporal import assert_supersede_effective_at
from irp_shared.db.mixins import utcnow
from irp_shared.reference.instrument import resolve_instrument
from irp_shared.reference.models import InstrumentTerms
from irp_shared.reference.service import (
    ENTITY_INSTRUMENT_TERMS,
    ReferenceActor,
    record_reference_correction,
    record_reference_create,
    record_reference_update,
)

#: Economic/legal term columns the binder accepts/carries-forward (inert placeholders — no math).
TERM_FIELDS = (
    "coupon_rate",
    "coupon_frequency",
    "issue_date",
    "maturity_date",
    "day_count",
    "denomination_currency",
    "face_value",
    "term_source",
)


class InstrumentTermsValueError(Exception):
    """Raised for a binder-side value breach (e.g. a window-incoherent supersede ``effective_at``)
    — caught BEFORE any write (fail-closed; maps to 422). The marketdata *ValueError precedent."""


class NoCurrentTerms(Exception):
    """Raised when a supersede is requested but the instrument has no dual-open current terms."""

    def __init__(self, instrument_id: str) -> None:
        super().__init__(f"instrument {instrument_id} has no current (open) terms to supersede")
        self.instrument_id = str(instrument_id)


def _summary(row: InstrumentTerms, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A DC-2 terms-summary dict (metadata only — never raw payload) for the audit after_value."""
    data: dict[str, Any] = {field: _json_safe(getattr(row, field)) for field in TERM_FIELDS}
    data["valid_from"] = _json_safe(row.valid_from)
    data["valid_to"] = _json_safe(row.valid_to)
    data["system_from"] = _json_safe(row.system_from)
    if extra:
        data.update(extra)
    return data


def _check_term_kwargs(terms: dict[str, Any]) -> None:
    unknown = set(terms) - set(TERM_FIELDS)
    if unknown:
        raise ValueError(f"non-term instrument_terms attributes: {sorted(unknown)}")


def _current_open(
    session: Session, instrument_id: str, acting_tenant: str
) -> InstrumentTerms | None:
    """The single version OPEN ON BOTH axes for an instrument (``valid_to IS NULL AND system_to
    IS NULL``) — the bitemporal current head — or ``None``."""
    return session.execute(
        select(InstrumentTerms).where(
            InstrumentTerms.instrument_id == str(instrument_id),
            InstrumentTerms.tenant_id == str(acting_tenant),
            InstrumentTerms.valid_to.is_(None),
            InstrumentTerms.system_to.is_(None),
        )
    ).scalar_one_or_none()


def create_instrument_terms(
    session: Session,
    *,
    instrument_id: str,
    acting_tenant: str,
    actor: ReferenceActor,
    valid_from: datetime | None = None,
    **terms: Any,
) -> InstrumentTerms:
    """Create the first open terms version (governed: MANUAL-source lineage + ``REFERENCE.CREATE``).
    The ``instrument_id`` is resolved tenant-filtered (cross-tenant/unknown → fails closed)."""
    resolve_instrument(session, instrument_id, acting_tenant=acting_tenant)
    _check_term_kwargs(terms)
    now = utcnow()
    row = InstrumentTerms(
        tenant_id=str(acting_tenant),
        instrument_id=str(instrument_id),
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        system_to=None,
        record_version=1,
        **terms,
    )
    session.add(row)
    session.flush()
    record_reference_create(
        session,
        entity=row,
        entity_type=ENTITY_INSTRUMENT_TERMS,
        after_value=_summary(row),
        actor=actor,
    )
    return row


def supersede_instrument_terms(
    session: Session,
    *,
    instrument_id: str,
    acting_tenant: str,
    actor: ReferenceActor,
    effective_at: datetime,
    **new_terms: Any,
) -> InstrumentTerms:
    """Effective-dated (valid-time) supersede: close the current head's ``valid_to = effective_at``
    (``REFERENCE.UPDATE``), then insert a new open version effective at ``effective_at``
    (``REFERENCE.CREATE`` + its own ORIGIN edge). Prior economic columns are carried forward and the
    supplied ``new_terms`` override them. No system-time close-out (both stay known)."""
    resolve_instrument(session, instrument_id, acting_tenant=acting_tenant)
    _check_term_kwargs(new_terms)
    prior = _current_open(session, instrument_id, acting_tenant)
    if prior is None:
        raise NoCurrentTerms(str(instrument_id))

    assert_supersede_effective_at(prior.valid_from, effective_at, error=InstrumentTermsValueError)
    now = utcnow()
    # CLOSE-FIRST: stamp + flush the prior valid_to close-out before adding the new open row.
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at
    session.flush()
    record_reference_update(
        session,
        entity=prior,
        entity_type=ENTITY_INSTRUMENT_TERMS,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
    )

    carried = {field: getattr(prior, field) for field in TERM_FIELDS}
    new = InstrumentTerms(
        tenant_id=str(acting_tenant),
        instrument_id=str(instrument_id),
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        system_to=None,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
        **{**carried, **new_terms},
    )
    session.add(new)
    session.flush()
    record_reference_create(
        session,
        entity=new,
        entity_type=ENTITY_INSTRUMENT_TERMS,
        after_value=_summary(new),
        actor=actor,
    )
    return new


def correct_instrument_terms(
    session: Session,
    terms_row: InstrumentTerms,
    *,
    restatement_reason: str,
    acting_tenant: str,
    actor: ReferenceActor,
    **corrected: Any,
) -> InstrumentTerms:
    """As-known restatement (TR-08): close the prior row's ``system_to = now``
    (``REFERENCE.UPDATE``), then insert a corrected version over the SAME valid period with
    ``restatement_reason`` + ``supersedes_id`` (``REFERENCE.CORRECTION`` / EVT-142 + its own ORIGIN
    edge). The prior row's economic columns are NEVER mutated — only its ``system_to`` close-out."""
    resolve_instrument(session, terms_row.instrument_id, acting_tenant=acting_tenant)
    _check_term_kwargs(corrected)

    now = utcnow()
    # CLOSE-FIRST: stamp + flush the prior system_to close-out before adding the corrected row.
    before = {"system_to": _json_safe(terms_row.system_to)}
    terms_row.system_to = now
    session.flush()
    record_reference_update(
        session,
        entity=terms_row,
        entity_type=ENTITY_INSTRUMENT_TERMS,
        before_value=before,
        after_value={"system_to": _json_safe(terms_row.system_to)},
        actor=actor,
    )

    carried = {field: getattr(terms_row, field) for field in TERM_FIELDS}
    corrected_row = InstrumentTerms(
        tenant_id=str(acting_tenant),
        instrument_id=terms_row.instrument_id,
        valid_from=terms_row.valid_from,  # SAME valid period (as-known correction)
        valid_to=terms_row.valid_to,
        system_from=now,  # one `now` — equals the prior row's system_to
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=terms_row.id,
        record_version=terms_row.record_version + 1,
        **{**carried, **corrected},
    )
    session.add(corrected_row)
    session.flush()
    record_reference_correction(
        session,
        entity=corrected_row,
        entity_type=ENTITY_INSTRUMENT_TERMS,
        restatement_reason=restatement_reason,
        after_value=_summary(
            corrected_row,
            extra={
                "restatement_reason": restatement_reason,
                "supersedes_id": corrected_row.supersedes_id,
            },
        ),
        actor=actor,
    )
    return corrected_row


def reconstruct_terms_as_of(
    session: Session,
    instrument_id: str,
    *,
    acting_tenant: str,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> InstrumentTerms | None:
    """Bitemporal as-of read: the single terms version true at ``valid_at`` as-known-at ``known_at``
    (``known_at`` defaults to now → the current view, TR-04), or ``None``. Half-open intervals on
    both
    axes; the resolver carries the explicit tenant predicate."""
    known = known_at or utcnow()
    return session.execute(
        select(InstrumentTerms).where(
            InstrumentTerms.instrument_id == str(instrument_id),
            InstrumentTerms.tenant_id == str(acting_tenant),
            InstrumentTerms.valid_from <= valid_at,
            or_(InstrumentTerms.valid_to.is_(None), InstrumentTerms.valid_to > valid_at),
            InstrumentTerms.system_from <= known,
            or_(InstrumentTerms.system_to.is_(None), InstrumentTerms.system_to > known),
        )
    ).scalar_one_or_none()
