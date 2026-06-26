"""FX-rate binder (P2-2, ENT-024) — the FR (full-reproducible / bitemporal) protocol + DQ gate.

FX rates are **captured vendor market data** (OD-P2-E), reusing the P1C-4 ``valuation`` protocol
verbatim. Full version history in-table on BOTH axes; ``(base_currency, quote_currency, rate_date,
rate_type)`` is the logical key (``rate_date``/``rate_type`` are immutable key components, carried
verbatim; the FR axes version the *rate* for a fixed key). Three governed operations + the as-of
read:

- ``capture_fx_rate`` — the first open rate for a ``(base, quote, rate_date, rate_type)``.
- ``supersede_fx_rate`` — a new *valid-time* rate for the SAME key: close the head's ``valid_to``
  (``MARKET.FX_UPDATE``), then insert a new open version (``MARKET.FX_CREATE``).
- ``correct_fx_rate`` — an as-known *system-time* vendor restatement (TR-08): close the prior row's
  ``system_to`` (``MARKET.FX_UPDATE``), then insert a corrected version over the SAME valid period +
  same key (``MARKET.FX_CORRECTION``).
- ``reconstruct_fx_rate_as_of`` — the bitemporal read (current view when ``known_at`` defaults to
now);
  the seam the future P2-3 snapshot binder will call to pin an FX component.

Invariants (verbatim from ``valuation``): ONE ``now = utcnow()`` per op; CLOSE-FIRST ordering; a
prior
version's CONTENT columns (incl. ``rate_date``/``rate_type``) are NEVER mutated — only
``valid_to``/``system_to``. Currencies are resolved via the **hybrid-aware** ``resolve_currency``
(own
OR SYSTEM; fail-closed cross-tenant). ``rate`` is captured (never computed); ``rate_source`` is an
inert LABEL. A governed **DQ gate** (required-field NOT_NULL + strictly-positive RANGE, fail-closed,
``DATA.VALIDATE``) runs co-transactionally. NO conversion analytics, NO exposure, NO
``calculation_run``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL, RULE_TYPE_RANGE
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.marketdata.events import (
    ENTITY_FX_RATE,
    FxRateActor,
    record_fx_correction,
    record_fx_create,
    record_fx_update,
)
from irp_shared.marketdata.models import FX_RATE_TYPES, RATE_TYPE_MID, FxRate
from irp_shared.reference.service import resolve_currency

#: The captured rate fields the binder carries-forward (inert; ``rate`` required, ``rate_source``
#: optional). ``rate_date``/``rate_type`` are LOGICAL-KEY components, NOT here.
FX_RATE_FIELDS = ("rate", "rate_source")
#: Fields that must be present for a governed capture (the required-field DQ gate universe).
REQUIRED_FX_FIELDS = ("base_currency", "quote_currency", "rate_date", "rate", "rate_type")

#: Per-tenant governed DQ rule codes (resolve-or-register; the P2-1 ``ensure_completeness_rule``
# pattern).
_REQUIRED_RULE_CODE = "fx.required_fields"
_POSITIVE_RULE_CODE = "fx.positive_rate"


class FxRateValueError(Exception):
    """Raised for an out-of-vocab ``rate_type`` or a degenerate pair (``base == quote``) — a value
    error caught before any write (fail-closed; maps to 422)."""


class FxRateNotVisible(Exception):
    """Raised when an ``fx_rate_id`` is not visible in the acting tenant scope
    (cross-tenant/unknown)."""

    def __init__(self, fx_rate_id: str) -> None:
        super().__init__(f"fx_rate {fx_rate_id} is not visible in the current tenant context")
        self.fx_rate_id = str(fx_rate_id)


class NoCurrentFxRate(Exception):
    """Raised when a supersede is requested but the (base, quote, rate_date, rate_type) has no open
    head."""

    def __init__(self, base: str, quote: str, rate_date: date, rate_type: str) -> None:
        super().__init__(
            f"fx_rate {base}/{quote} {rate_type} for {rate_date} has no current (open) version"
        )
        self.base_currency, self.quote_currency = base, quote
        self.rate_date, self.rate_type = rate_date, rate_type


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def _summary(row: FxRate, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A DC-2 FX-summary dict (metadata only) for the audit after_value (never bulk vendor data)."""
    data: dict[str, Any] = {field: _json_safe(getattr(row, field)) for field in FX_RATE_FIELDS}
    data["base_currency"] = row.base_currency
    data["quote_currency"] = row.quote_currency
    data["rate_date"] = _json_safe(row.rate_date)
    data["rate_type"] = row.rate_type
    data["valid_from"] = _json_safe(row.valid_from)
    data["valid_to"] = _json_safe(row.valid_to)
    data["system_from"] = _json_safe(row.system_from)
    if extra:
        data.update(extra)
    return data


def _check_field_kwargs(fields: dict[str, Any]) -> None:
    unknown = set(fields) - set(FX_RATE_FIELDS)
    if unknown:
        raise ValueError(f"non-fx_rate attributes: {sorted(unknown)}")


def _validate_pair(base_currency: str, quote_currency: str, rate_type: str) -> None:
    """Pre-write value checks: ``rate_type`` in the v1 vocab (MID only) + non-degenerate pair."""
    if rate_type not in FX_RATE_TYPES:
        raise FxRateValueError(f"rate_type {rate_type!r} not in {FX_RATE_TYPES} (MID only in v1)")
    if base_currency == quote_currency:
        raise FxRateValueError(f"base_currency == quote_currency ({base_currency}) is degenerate")


def _resolve_currencies(session: Session, base: str, quote: str, *, acting_tenant: str) -> None:
    """Validate BOTH currency codes via the hybrid-aware ``resolve_currency`` (own OR SYSTEM;
    foreign-tenant/unknown → ``CurrencyNotVisible``)."""
    resolve_currency(session, base, acting_tenant=acting_tenant)
    resolve_currency(session, quote, acting_tenant=acting_tenant)


def _ensure_rule(
    session: Session,
    *,
    tenant_id: str,
    actor: FxRateActor,
    code: str,
    name: str,
    rule_type: str,
    params: dict[str, Any],
) -> DataQualityRule:
    """Resolve-or-register a per-tenant governed DQ rule (audited; the P2-1 pattern)."""
    rule = session.execute(
        select(DataQualityRule).where(
            DataQualityRule.tenant_id == str(tenant_id),
            DataQualityRule.code == code,
        )
    ).scalar_one_or_none()
    if rule is not None:
        return rule
    return register_dq_rule(
        session,
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        rule_type=rule_type,
        actor_id=actor.actor_id,
        params=params,
        target_entity_type=ENTITY_FX_RATE,
        severity=SEVERITY_ERROR,
        actor_type=actor.actor_type,
    )


def _run_fx_dq_gate(
    session: Session, *, acting_tenant: str, actor: FxRateActor, row: FxRate
) -> None:
    """Fail-closed governed DQ gate (co-transactional; ``DATA.VALIDATE``): (1) required-field
    NOT_NULL via the sentinel-null derived dataset; (2) strictly-positive RANGE on ``rate``. A
    failure raises ``DataQualityError`` → the caller's whole unit rolls back (CTRL-032; no row)."""
    missing = any(getattr(row, f) is None for f in REQUIRED_FX_FIELDS)
    required_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_REQUIRED_RULE_CODE,
        name="FX required fields present",
        rule_type=RULE_TYPE_NOT_NULL,
        params={"column": "present"},
    )
    run_quality_check(
        session,
        rule=required_rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_FX_RATE,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )
    positive_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_POSITIVE_RULE_CODE,
        name="FX rate strictly positive",
        rule_type=RULE_TYPE_RANGE,
        params={"column": "rate", "min": 0, "min_inclusive": False},
    )
    run_quality_check(
        session,
        rule=positive_rule,
        dataset=[{"rate": row.rate}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_FX_RATE,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )


def _current_open(
    session: Session,
    *,
    acting_tenant: str,
    base_currency: str,
    quote_currency: str,
    rate_date: date,
    rate_type: str,
) -> FxRate | None:
    """The single version OPEN ON BOTH axes for a logical key — the bitemporal current head — or
    ``None``. Tenant-predicated."""
    return session.execute(
        select(FxRate).where(
            FxRate.tenant_id == str(acting_tenant),
            FxRate.base_currency == base_currency,
            FxRate.quote_currency == quote_currency,
            FxRate.rate_date == rate_date,
            FxRate.rate_type == rate_type,
            FxRate.valid_to.is_(None),
            FxRate.system_to.is_(None),
        )
    ).scalar_one_or_none()


def resolve_fx_rate(session: Session, fx_rate_id: str, *, acting_tenant: str) -> FxRate:
    """Resolve an ``fx_rate`` version by id with an EXPLICIT ``tenant_id == acting_tenant``
    predicate
    (fail-closed on SQLite + PG). Raises :class:`FxRateNotVisible` on a hidden id."""
    row = session.execute(
        select(FxRate).where(
            FxRate.id == str(fx_rate_id),
            FxRate.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise FxRateNotVisible(str(fx_rate_id))
    return row


def capture_fx_rate(
    session: Session,
    *,
    base_currency: str,
    quote_currency: str,
    rate_date: date,
    rate: Decimal,
    acting_tenant: str,
    actor: FxRateActor,
    rate_type: str = RATE_TYPE_MID,
    valid_from: datetime | None = None,
    rate_source: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> FxRate:
    """Capture the first open rate for a ``(base, quote, rate_date, rate_type)`` (governed:
    VENDOR-source ORIGIN lineage + ``MARKET.FX_CREATE`` + the DQ gate). Both currencies are resolved
    hybrid-aware (own OR SYSTEM; cross-tenant/unknown → ``CurrencyNotVisible``); ``rate`` is
    captured,
    never computed. ``entity_id``/``now`` are the deterministic-injection seam (default-None ⇒
    prod unchanged)."""
    _validate_pair(base_currency, quote_currency, rate_type)
    _resolve_currencies(session, base_currency, quote_currency, acting_tenant=acting_tenant)
    now = now or utcnow()
    row = FxRate(
        tenant_id=str(acting_tenant),
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate_date=rate_date,  # immutable logical-key component (NOT the valid_from axis)
        rate_type=rate_type,
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        system_to=None,
        rate=rate,
        rate_source=rate_source,
        record_version=1,
    )
    if entity_id is not None:
        row.id = entity_id  # seam: deterministic uuid5 id
    session.add(row)
    session.flush()
    _run_fx_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=row)
    record_fx_create(session, entity=row, after_value=_summary(row), actor=actor, now=now)
    return row


def supersede_fx_rate(
    session: Session,
    *,
    base_currency: str,
    quote_currency: str,
    rate_date: date,
    rate_type: str,
    acting_tenant: str,
    actor: FxRateActor,
    effective_at: datetime,
    entity_id: str | None = None,
    now: datetime | None = None,
    **new_fields: Any,
) -> FxRate:
    """Effective-dated (valid-time) re-quote for the SAME key: close the head's ``valid_to``
    (``MARKET.FX_UPDATE``), then insert a new open version (``MARKET.FX_CREATE`` + its own ORIGIN
    edge
    + the DQ gate). Prior fields are carried forward and ``new_fields`` override; the head is
    sourced
    via the tenant-predicated ``_current_open`` (never a caller-supplied id)."""
    _validate_pair(base_currency, quote_currency, rate_type)
    _resolve_currencies(session, base_currency, quote_currency, acting_tenant=acting_tenant)
    _check_field_kwargs(new_fields)
    prior = _current_open(
        session,
        acting_tenant=acting_tenant,
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate_date=rate_date,
        rate_type=rate_type,
    )
    if prior is None:
        raise NoCurrentFxRate(base_currency, quote_currency, rate_date, rate_type)

    now = now or utcnow()
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at  # CLOSE-FIRST
    session.flush()
    record_fx_update(
        session,
        entity=prior,
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )

    carried = {field: getattr(prior, field) for field in FX_RATE_FIELDS}
    new = FxRate(
        tenant_id=str(acting_tenant),
        base_currency=prior.base_currency,
        quote_currency=prior.quote_currency,
        rate_date=prior.rate_date,  # carried verbatim (immutable logical key)
        rate_type=prior.rate_type,
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        system_to=None,
        supersedes_id=prior.id,
        record_version=prior.record_version + 1,
        **{**carried, **new_fields},
    )
    if entity_id is not None:
        new.id = entity_id
    session.add(new)
    session.flush()
    _run_fx_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=new)
    record_fx_create(session, entity=new, after_value=_summary(new), actor=actor, now=now)
    return new


def correct_fx_rate(
    session: Session,
    fx_rate_row: FxRate,
    *,
    restatement_reason: str,
    acting_tenant: str,
    actor: FxRateActor,
    entity_id: str | None = None,
    now: datetime | None = None,
    **corrected: Any,
) -> FxRate:
    """As-known vendor restatement (TR-08): close the prior row's ``system_to = now`` then insert a
    corrected version over the SAME valid period + same key with ``restatement_reason`` +
    ``supersedes_id`` (``MARKET.FX_CORRECTION`` + its own ORIGIN edge + the DQ gate). The prior
    row's
    content columns are NEVER mutated — only its ``system_to``. ``fx_rate_row`` must already be
    tenant-resolved (via ``resolve_fx_rate``)."""
    _resolve_currencies(
        session, fx_rate_row.base_currency, fx_rate_row.quote_currency, acting_tenant=acting_tenant
    )
    _check_field_kwargs(corrected)

    now = now or utcnow()
    before = {"system_to": _json_safe(fx_rate_row.system_to)}
    fx_rate_row.system_to = now  # CLOSE-FIRST
    session.flush()
    record_fx_update(
        session,
        entity=fx_rate_row,
        before_value=before,
        after_value={"system_to": _json_safe(fx_rate_row.system_to)},
        actor=actor,
        now=now,
    )

    carried = {field: getattr(fx_rate_row, field) for field in FX_RATE_FIELDS}
    corrected_row = FxRate(
        tenant_id=str(acting_tenant),
        base_currency=fx_rate_row.base_currency,
        quote_currency=fx_rate_row.quote_currency,
        rate_date=fx_rate_row.rate_date,  # carried verbatim (immutable logical key)
        rate_type=fx_rate_row.rate_type,
        valid_from=fx_rate_row.valid_from,  # SAME valid period (as-known correction)
        valid_to=fx_rate_row.valid_to,
        system_from=now,  # one `now` — equals the prior row's system_to
        system_to=None,
        restatement_reason=restatement_reason,
        supersedes_id=fx_rate_row.id,
        record_version=fx_rate_row.record_version + 1,
        **{**carried, **corrected},
    )
    if entity_id is not None:
        corrected_row.id = entity_id
    session.add(corrected_row)
    session.flush()
    _run_fx_dq_gate(session, acting_tenant=acting_tenant, actor=actor, row=corrected_row)
    record_fx_correction(
        session,
        entity=corrected_row,
        restatement_reason=restatement_reason,
        after_value=_summary(
            corrected_row,
            extra={
                "restatement_reason": restatement_reason,
                "supersedes_id": corrected_row.supersedes_id,
            },
        ),
        actor=actor,
        now=now,
    )
    return corrected_row


def reconstruct_fx_rate_as_of(
    session: Session,
    *,
    acting_tenant: str,
    base_currency: str,
    quote_currency: str,
    rate_date: date,
    valid_at: datetime,
    rate_type: str = RATE_TYPE_MID,
    known_at: datetime | None = None,
) -> FxRate | None:
    """Bitemporal as-of read: the single rate true at ``valid_at`` as-known-at ``known_at``
    (``known_at`` defaults to now → the current view), or ``None``, for the given logical key.
    Half-open intervals on both axes; the resolver carries the explicit tenant predicate. This is
    the
    seam the future P2-3 snapshot binder calls to pin an FX component. Single rate only — NO
    conversion / triangulation / aggregation (those are ``convert`` / P2-3)."""
    known = known_at or utcnow()
    return session.execute(
        select(FxRate).where(
            FxRate.tenant_id == str(acting_tenant),
            FxRate.base_currency == base_currency,
            FxRate.quote_currency == quote_currency,
            FxRate.rate_date == rate_date,
            FxRate.rate_type == rate_type,
            FxRate.valid_from <= valid_at,
            or_(FxRate.valid_to.is_(None), FxRate.valid_to > valid_at),
            FxRate.system_from <= known,
            or_(FxRate.system_to.is_(None), FxRate.system_to > known),
        )
    ).scalar_one_or_none()
