"""Capital-call / distribution governed-write service (CC-1, ENT-016) — captured IA events.

THE READ RULE (OD-CC-1-D): an ENT-016 event does NOT feed TWR/Dietz or backtest realized
P&L — those chains read EXCLUSIVELY ``transaction.TRANSFER_IN/TRANSFER_OUT``. A call or
distribution that also moves cash in a return-modeled book must be separately posted as
a transaction; nothing auto-bridges in v1 (the reconciliation bridge is the named v2).

Truly-immutable append-only event rows (the transaction protocol): capture appends; a
correction is a **FULL REVERSAL** append — ``amount`` = the EXACT NEGATION of the
reversed amount (the ``reverse_transaction`` sign convention: a naive Σ(amount) is
self-correcting — capture 100 → reverse −100 → recapture 100 sums to 100 with no
consumer exclusion contract), every other economic field (type / currency /
``event_date``) echoed byte-for-byte; knowledge time lives in ``system_from``. A real
clawback is a NEW economic event, never a reversal. One reversal per event — validated
here AND race-closed by the partial-unique index (the concurrent loser surfaces as
IntegrityError → 409 via ``is_unique_violation``).

Events key on the STABLE commitment identity ``(portfolio_id, instrument_id)`` (the
verifier's structural HIGH — FR version-row ids are not stable link targets); capture
requires a CURRENT commitment for the pair (fail-closed) and validates the event
``currency_code`` against that commitment's chain-immutable currency.
``commitment_version_id`` is stamped as a PROVENANCE-ONLY echo of the version row
current at capture — never the aggregation key (aggregate by the pair).

Rails: per-table NOT_NULL-only DQ gates (race-safe; NO economic RANGE); a ``MANUAL``
ORIGIN lineage edge per row; ``PRIVATE.CAPITAL_CALL_CREATE/_REVERSE`` +
``PRIVATE.DISTRIBUTION_CREATE/_REVERSE`` at the EVT-240 block (a reversal emits the
distinct REVERSE verb — the TRANSACTION.REVERSE precedent — with ``reverses_id`` in the
payload). ``audit/service.py`` FROZEN; no emit on read; no mid-call commit (CTRL-032).
NO snapshot, NO calculation run, NO model version (captured input).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE
from irp_shared.audit.payload import json_safe as _json_safe
from irp_shared.audit.service import record_event
from irp_shared.db.integrity import resolve_or_insert
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.lineage.models import EDGE_KIND_ORIGIN
from irp_shared.lineage.service import record_lineage
from irp_shared.private_capital.commitment_service import (
    AMOUNT_QUANTUM,
    MAX_AMOUNT,
    NoCurrentCommitment,
    current_commitment,
    ensure_manual_source,
)
from irp_shared.private_capital.events import (
    ENTITY_CAPITAL_CALL,
    ENTITY_DISTRIBUTION,
    PRIVATE_CAPITAL_CALL_CREATE_EVENT,
    PRIVATE_CAPITAL_CALL_REVERSE_EVENT,
    PRIVATE_DISTRIBUTION_CREATE_EVENT,
    PRIVATE_DISTRIBUTION_REVERSE_EVENT,
    SOURCE_MODULE,
)
from irp_shared.private_capital.models import (
    CALL_TYPES,
    DISTRIBUTION_TYPES,
    CapitalCall,
    Distribution,
)

#: Per-tenant governed DQ rule codes (resolve-or-register; the proxy_mapping pattern).
_REQUIRED_RULE_CODES = {
    ENTITY_CAPITAL_CALL: "capital_call.required_fields",
    ENTITY_DISTRIBUTION: "distribution.required_fields",
}


@dataclass(frozen=True)
class CapitalFlowActor:
    """Actor/correlation context threaded into every capital-flow audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class CapitalFlowValueError(Exception):
    """Raised for an invalid amount/currency/vocab/reversal target — caught BEFORE any write
    (fail-closed; maps to 422)."""


class CapitalFlowNotVisible(Exception):
    """Raised when a capital-call/distribution id is not visible in the acting tenant scope."""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        super().__init__(f"{entity_type} {entity_id} is not visible in the current tenant context")
        self.entity_type = entity_type
        self.entity_id = str(entity_id)


def _validate_amount(amount: Decimal) -> None:
    """Ordinary captures are strictly positive finite INSIDE the (20,6) envelope, judged
    at the canonical quantum (the review fold — the persisted value is the HALF_UP
    quantization, so validation must see it: a sub-quantum input would mint a PERMANENT
    zero-amount immutable row; an oversized one would 500 at bind). Reversal rows are
    minted internally as exact negations — never caller-supplied."""
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise CapitalFlowValueError(f"amount must be a finite Decimal (got {amount!r})")
    try:
        quantized = amount.quantize(AMOUNT_QUANTUM)
    except InvalidOperation:
        raise CapitalFlowValueError(
            f"amount {amount} does not fit the (20,6) envelope — refused"
        ) from None
    if quantized <= 0:
        raise CapitalFlowValueError(
            f"amount must be strictly positive at the 6dp canonical scale (got {amount})"
        )
    if quantized > MAX_AMOUNT:
        raise CapitalFlowValueError(f"amount {amount} exceeds the (20,6) maximum — refused")


def _require_current_commitment(
    session: Session, *, acting_tenant: str, portfolio_id: str, instrument_id: str
):  # noqa: ANN202
    """A CURRENT (both-axes-open) commitment must exist for the (portfolio, instrument)
    identity — the fail-closed anchor every event validates against."""
    prior = current_commitment(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
    )
    if prior is None:
        raise NoCurrentCommitment(portfolio_id, instrument_id)
    return prior


def _validate_event_currency(commitment_currency: str, currency_code: str) -> None:
    if currency_code != commitment_currency:
        raise CapitalFlowValueError(
            f"event currency_code {currency_code!r} must equal the commitment's chain-immutable "
            f"currency {commitment_currency!r} — refused"
        )


# --- governed DQ gate (required-field NOT_NULL only; NO economic RANGE) ---


def _ensure_required_rule(
    session: Session, *, tenant_id: str, entity_type: str, actor: CapitalFlowActor
) -> DataQualityRule:
    code = _REQUIRED_RULE_CODES[entity_type]
    return resolve_or_insert(
        session,
        resolve=lambda: session.execute(
            select(DataQualityRule).where(
                DataQualityRule.tenant_id == str(tenant_id),
                DataQualityRule.code == code,
            )
        ).scalar_one_or_none(),
        insert=lambda: register_dq_rule(
            session,
            tenant_id=str(tenant_id),
            code=code,
            name=f"{entity_type} required fields present",
            rule_type=RULE_TYPE_NOT_NULL,
            actor_id=actor.actor_id,
            params={"column": "present"},
            target_entity_type=entity_type,
            severity=SEVERITY_ERROR,
            actor_type=actor.actor_type,
        ),
    )


def _run_dq_gate(
    session: Session,
    *,
    acting_tenant: str,
    actor: CapitalFlowActor,
    entity_type: str,
    row: CapitalCall | Distribution,
    fields: tuple[str, ...],
) -> None:
    missing = any(getattr(row, f) is None for f in fields)
    rule = _ensure_required_rule(
        session, tenant_id=acting_tenant, entity_type=entity_type, actor=actor
    )
    run_quality_check(
        session,
        rule=rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=entity_type,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )


def _origin_edge(
    session: Session, *, tenant_id: str, entity_type: str, entity_id: str, actor: CapitalFlowActor
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
    after_value: dict[str, Any],
    actor: CapitalFlowActor,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    """Emit one audit event to the FROZEN record_event. IA rows are create-only, so the
    row-level ``action`` is always "create" — the REVERSE semantics live in the distinct
    ``event_type`` (the TRANSACTION.REVERSE precedent) + the ``reverses_id`` payload."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=entity_type,
        entity_id=entity_id,
        action=ACTION_CREATE,
        before_value=None,
        after_value=after_value,
        justification=justification,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
        event_time=now,
    )


def _summary(row: CapitalCall | Distribution, type_field: str) -> dict[str, Any]:
    """A DC-2 event-summary dict (metadata only)."""
    out = {
        "portfolio_id": _json_safe(row.portfolio_id),
        "instrument_id": _json_safe(row.instrument_id),
        "commitment_version_id": _json_safe(row.commitment_version_id),
        "event_date": _json_safe(row.event_date),
        "currency_code": row.currency_code,
        type_field: getattr(row, type_field),
    }
    if row.reverses_id is not None:
        out["reverses_id"] = _json_safe(row.reverses_id)
    return out


# --- capture (ordinary events) ---


def capture_capital_call(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    event_date: date,
    amount: Decimal,
    currency_code: str,
    call_type: str,
    acting_tenant: str,
    actor: CapitalFlowActor,
    external_ref: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> CapitalCall:
    """Capture one capital-call event as ONE governed unit (IA row + MANUAL ORIGIN edge +
    ``PRIVATE.CAPITAL_CALL_CREATE`` + the DQ gate). A CURRENT commitment for the
    (portfolio, instrument) pair must exist; the event currency must equal its
    chain-immutable currency; ``call_type`` is vocab-validated; the amount is captured at
    the canonical 6dp scale (HALF_UP at bind — AD-011; strictly positive at that scale).
    ``event_date`` ordering vs the commitment/other events is deliberately NOT adjudicated
    (inert business date — the capture layer does not adjudicate economics, OD-CC-1-E)."""
    _validate_amount(amount)
    if call_type not in CALL_TYPES:
        raise CapitalFlowValueError(f"call_type {call_type!r} not in {CALL_TYPES}")
    commitment = _require_current_commitment(
        session, acting_tenant=acting_tenant, portfolio_id=portfolio_id, instrument_id=instrument_id
    )
    _validate_event_currency(commitment.currency_code, currency_code)
    now = now or utcnow()
    row = CapitalCall(
        tenant_id=str(acting_tenant),
        portfolio_id=commitment.portfolio_id,
        instrument_id=commitment.instrument_id,
        commitment_version_id=commitment.id,
        event_date=event_date,
        amount=amount,
        currency_code=currency_code,
        call_type=call_type,
        external_ref=external_ref,
        system_from=now,
    )
    if entity_id is not None:
        row.id = entity_id
    session.add(row)
    session.flush()
    _run_dq_gate(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        entity_type=ENTITY_CAPITAL_CALL,
        row=row,
        fields=(
            "portfolio_id",
            "instrument_id",
            "event_date",
            "amount",
            "currency_code",
            "call_type",
        ),
    )
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CAPITAL_CALL,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CAPITAL_CALL,
        entity_id=row.id,
        event_type=PRIVATE_CAPITAL_CALL_CREATE_EVENT,
        after_value=_summary(row, "call_type"),
        actor=actor,
        now=now,
    )
    return row


def capture_distribution(
    session: Session,
    *,
    portfolio_id: str,
    instrument_id: str,
    event_date: date,
    amount: Decimal,
    currency_code: str,
    distribution_type: str,
    acting_tenant: str,
    actor: CapitalFlowActor,
    is_recallable: bool = False,
    external_ref: str | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Distribution:
    """Capture one distribution event as ONE governed unit (IA row + MANUAL ORIGIN edge +
    ``PRIVATE.DISTRIBUTION_CREATE`` + the DQ gate). ``is_recallable`` is captured as DATA
    (the unfunded arithmetic interpreting it is CC-2's, OD-CC-1-E; a partial-recallable
    distribution is captured as two rows)."""
    _validate_amount(amount)
    if distribution_type not in DISTRIBUTION_TYPES:
        raise CapitalFlowValueError(
            f"distribution_type {distribution_type!r} not in {DISTRIBUTION_TYPES}"
        )
    commitment = _require_current_commitment(
        session, acting_tenant=acting_tenant, portfolio_id=portfolio_id, instrument_id=instrument_id
    )
    _validate_event_currency(commitment.currency_code, currency_code)
    now = now or utcnow()
    row = Distribution(
        tenant_id=str(acting_tenant),
        portfolio_id=commitment.portfolio_id,
        instrument_id=commitment.instrument_id,
        commitment_version_id=commitment.id,
        event_date=event_date,
        amount=amount,
        currency_code=currency_code,
        distribution_type=distribution_type,
        is_recallable=is_recallable,
        external_ref=external_ref,
        system_from=now,
    )
    if entity_id is not None:
        row.id = entity_id
    session.add(row)
    session.flush()
    _run_dq_gate(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        entity_type=ENTITY_DISTRIBUTION,
        row=row,
        fields=(
            "portfolio_id",
            "instrument_id",
            "event_date",
            "amount",
            "currency_code",
            "distribution_type",
            "is_recallable",
        ),
    )
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_DISTRIBUTION,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_DISTRIBUTION,
        entity_id=row.id,
        event_type=PRIVATE_DISTRIBUTION_CREATE_EVENT,
        after_value=_summary(row, "distribution_type"),
        actor=actor,
        now=now,
    )
    return row


# --- reversal (the append-only correction path) ---


def _resolve_event(
    session: Session,
    model: type[CapitalCall] | type[Distribution],
    entity_type: str,
    event_id: str,
    *,
    acting_tenant: str,
):  # noqa: ANN202
    row = session.execute(
        select(model).where(
            model.id == str(event_id),
            model.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise CapitalFlowNotVisible(entity_type, str(event_id))
    return row


def _validate_reversal_target(
    session: Session,
    model: type[CapitalCall] | type[Distribution],
    entity_type: str,
    target: CapitalCall | Distribution,
) -> None:
    """FULL-reversal-only fences: never reverse a reversal; never double-reverse (also
    race-closed by the partial-unique index — the concurrent loser 409s)."""
    if target.reverses_id is not None:
        raise CapitalFlowValueError(
            f"{entity_type} {target.id} is itself a reversal — a reversal cannot be reversed "
            f"(recapture the correct event instead); refused"
        )
    existing = session.execute(
        select(model.id).where(
            model.reverses_id == str(target.id),
            model.tenant_id == target.tenant_id,  # predicated (the one-unpredicated-query fold)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise CapitalFlowValueError(
            f"{entity_type} {target.id} is already reversed (by {existing}) — refused"
        )


def reverse_capital_call(
    session: Session,
    *,
    capital_call_id: str,
    acting_tenant: str,
    actor: CapitalFlowActor,
    reason: str,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> CapitalCall:
    """Append the FULL reversal of a capital call: ``amount`` = the exact negation;
    type/currency/``event_date``/identity echoed byte-for-byte; emits
    ``PRIVATE.CAPITAL_CALL_REVERSE`` with ``reverses_id`` in the payload."""
    if not reason:
        raise CapitalFlowValueError("reason is required for a reversal (TR-08)")
    target = _resolve_event(
        session, CapitalCall, ENTITY_CAPITAL_CALL, capital_call_id, acting_tenant=acting_tenant
    )
    _validate_reversal_target(session, CapitalCall, ENTITY_CAPITAL_CALL, target)
    now = now or utcnow()
    row = CapitalCall(
        tenant_id=target.tenant_id,
        portfolio_id=target.portfolio_id,
        instrument_id=target.instrument_id,
        commitment_version_id=target.commitment_version_id,
        event_date=target.event_date,
        amount=-target.amount,  # the EXACT NEGATION (Σ self-correcting)
        currency_code=target.currency_code,
        call_type=target.call_type,
        external_ref=None,
        reverses_id=target.id,
        system_from=now,
    )
    if entity_id is not None:
        row.id = entity_id
    session.add(row)
    session.flush()
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CAPITAL_CALL,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_CAPITAL_CALL,
        entity_id=row.id,
        event_type=PRIVATE_CAPITAL_CALL_REVERSE_EVENT,
        after_value=_summary(row, "call_type"),
        actor=actor,
        justification=reason,
        now=now,
    )
    return row


def reverse_distribution(
    session: Session,
    *,
    distribution_id: str,
    acting_tenant: str,
    actor: CapitalFlowActor,
    reason: str,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Distribution:
    """Append the FULL reversal of a distribution (incl. the ``is_recallable`` echo);
    emits ``PRIVATE.DISTRIBUTION_REVERSE``."""
    if not reason:
        raise CapitalFlowValueError("reason is required for a reversal (TR-08)")
    target = _resolve_event(
        session, Distribution, ENTITY_DISTRIBUTION, distribution_id, acting_tenant=acting_tenant
    )
    _validate_reversal_target(session, Distribution, ENTITY_DISTRIBUTION, target)
    now = now or utcnow()
    row = Distribution(
        tenant_id=target.tenant_id,
        portfolio_id=target.portfolio_id,
        instrument_id=target.instrument_id,
        commitment_version_id=target.commitment_version_id,
        event_date=target.event_date,
        amount=-target.amount,  # the EXACT NEGATION (Σ self-correcting)
        currency_code=target.currency_code,
        distribution_type=target.distribution_type,
        is_recallable=target.is_recallable,
        external_ref=None,
        reverses_id=target.id,
        system_from=now,
    )
    if entity_id is not None:
        row.id = entity_id
    session.add(row)
    session.flush()
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_DISTRIBUTION,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=ENTITY_DISTRIBUTION,
        entity_id=row.id,
        event_type=PRIVATE_DISTRIBUTION_REVERSE_EVENT,
        after_value=_summary(row, "distribution_type"),
        actor=actor,
        justification=reason,
        now=now,
    )
    return row


# --- reads (rule-7 entity-filtered lists; event order) ---


def list_capital_calls(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
) -> list[CapitalCall]:
    """Capital-call events (tenant-predicated; reversal rows included — Σ(amount) is
    self-correcting by the negation convention), optionally filtered by ``portfolio_id``
    and/or ``instrument_id`` (roadmap Part-4 rule 7). Ordered by (event_date,
    system_from) for a stable stream."""
    stmt = select(CapitalCall).where(CapitalCall.tenant_id == str(acting_tenant))
    if portfolio_id is not None:
        stmt = stmt.where(CapitalCall.portfolio_id == str(portfolio_id))
    if instrument_id is not None:
        stmt = stmt.where(CapitalCall.instrument_id == str(instrument_id))
    stmt = stmt.order_by(CapitalCall.event_date, CapitalCall.system_from)
    return list(session.execute(stmt).scalars().all())


def list_distributions(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
) -> list[Distribution]:
    """Distribution events (tenant-predicated; reversal rows included), optionally
    filtered by ``portfolio_id`` and/or ``instrument_id`` (roadmap Part-4 rule 7)."""
    stmt = select(Distribution).where(Distribution.tenant_id == str(acting_tenant))
    if portfolio_id is not None:
        stmt = stmt.where(Distribution.portfolio_id == str(portfolio_id))
    if instrument_id is not None:
        stmt = stmt.where(Distribution.instrument_id == str(instrument_id))
    stmt = stmt.order_by(Distribution.event_date, Distribution.system_from)
    return list(session.execute(stmt).scalars().all())
