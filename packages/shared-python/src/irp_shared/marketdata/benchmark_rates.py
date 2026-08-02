"""Benchmark published-RATE binder (DATA-1, ENT-070) — captured verbatim, NEVER re-expressed.

``benchmark_rate`` is the third series-observation table under the ENT-009 ``benchmark`` EV header
(the 0029 level/return FR protocol, parameterized by the SAME ``_SeriesSpec`` core — one
implementation, three series; a convention split between near-identical rails is the recorded
hazard). The vendor's annualized rate is captured VERBATIM as a decimal fraction: the ONLY
transformation at capture is the pure units change percent→fraction (``0.0366`` = 3.66%);
an annualized→period-return conversion is a METHODOLOGY choice needing a registered
``model_version`` — the named DATA-1 carry (OQ-DATA-1-1). REUSE ``VENDOR_BENCHMARK`` +
``resolve_benchmark`` + ``marketdata.view``/``.ingest`` (no new source, no new permission).

``refresh_benchmark_rates`` is the governed bulk rail (the CAL-1a ``refresh_calendar_holidays``
pattern on the marketdata rail, OQ-DATA-1-6/7):

- **ADD-ONLY** (intra-call duplicates dedupe first-spec-wins; a supplied date already captured
  with a DIFFERENT value REFUSES loudly naming ``correct_benchmark_rate`` — a silent skip would
  hide a vendor revision; identical re-supply is skipped silently). NO removal path.
- **FORWARD-ONLY** ``benchmark.rates_complete_through`` advance (a regression refuses; a horizon
  beyond the month of the last captured/supplied rate refuses — the declared horizon may not
  outrun the data). ONE series per head: a second ``(rate_type, quote_basis)`` on a
  horizon-carrying head refuses (the recorded v1 coverage-grain limitation, OQ-DATA-1-3).
- **Completeness fires only on an EFFECTIVE refresh** (additions > 0 or the horizon advanced) —
  a true no-op returns before the DQ leg, so the verb is idempotent-silent. The expected month
  set derives from TWO DECLARATIONS (``series_start`` → the horizon; never from the data), the
  persisted ``COMPLETENESS`` rule's params are advanced first (``update_dq_rule``, so the rule
  always says what was last expected), and the check runs through ``run_quality_check``.
- **FAIL evidence COMMITS while the data rolls back** (OQ-DATA-1-6): the batch's writes live in a
  ``begin_nested()`` savepoint; a completeness FAIL rolls the savepoint back (zero rate rows,
  horizon unmoved, the head's ``REFERENCE.UPDATE`` unwound) and the FAIL
  ``data_quality_result`` + ``DATA.VALIDATE`` audit persist OUTSIDE it before
  ``DataQualityError`` propagates — the gate's ANY-FAIL arm is reachable, not vacuous.

Audit grain: per-row ``MARKET.BENCHMARK_RATE_*`` (capture=1 CREATE; supersede=2; correct=2 — the
ENT-052 grain) + ONE ``REFERENCE.UPDATE`` on the ``benchmark`` head per effective refresh (the
CAL-1a parent-update pattern; ``record_version`` bumped). ``audit/service.py`` is FROZEN; no emit
on read. DC-2 metadata only — never the captured value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_UPDATE
from irp_shared.audit.payload import json_safe as _json_safe
from irp_shared.dq.rules import RULE_TYPE_COMPLETENESS, evaluate_rule
from irp_shared.dq.service import run_quality_check, update_dq_rule
from irp_shared.marketdata.benchmark import BenchmarkActor, resolve_benchmark
from irp_shared.marketdata.benchmark_series import (
    BenchmarkSeriesValueError,
    _capture,
    _correct,
    _emit,
    _ensure_rule,
    _list,
    _reconstruct,
    _SeriesSpec,
    _supersede,
)
from irp_shared.marketdata.models import (
    BENCHMARK_RATE_OBSERVATION_CONVENTIONS,
    BENCHMARK_RATE_QUOTE_BASES,
    BENCHMARK_RATE_TYPES,
    RATE_TYPE_ALLOWED_QUOTE_BASES,
    Benchmark,
    BenchmarkRate,
)
from irp_shared.reference.events import REFERENCE_UPDATE_EVENT

# --- audit constants (MARKET.* family; caller-side strings; the taxonomy row IS the mint record)
MARKET_BENCHMARK_RATE_CREATE_EVENT = "MARKET.BENCHMARK_RATE_CREATE"
MARKET_BENCHMARK_RATE_UPDATE_EVENT = "MARKET.BENCHMARK_RATE_UPDATE"
MARKET_BENCHMARK_RATE_CORRECTION_EVENT = "MARKET.BENCHMARK_RATE_CORRECTION"

ENTITY_BENCHMARK_RATE = "benchmark_rate"

#: The series-scoped completeness rule (RULE_TYPE_COMPLETENESS, DATA-1). Params carry the expected
#: month-key set LITERALLY (the REF-1 trigger wording) and advance with the declared horizon.
COMPLETENESS_RULE_CODE = "benchmark_rate.monthly_completeness"
COMPLETENESS_RULE_NAME = "Benchmark rate series monthly completeness (declared start → horizon)"
_COMPLETENESS_KEY_COLUMN = "month"


def _validate_rate_keys(
    *, rate_type: str, quote_basis: str, observation_convention: str, **_: Any
) -> None:
    if rate_type not in BENCHMARK_RATE_TYPES:
        raise BenchmarkSeriesValueError(f"rate_type {rate_type!r} not in {BENCHMARK_RATE_TYPES}")
    if quote_basis not in BENCHMARK_RATE_QUOTE_BASES:
        raise BenchmarkSeriesValueError(
            f"quote_basis {quote_basis!r} not in {BENCHMARK_RATE_QUOTE_BASES}"
        )
    allowed = RATE_TYPE_ALLOWED_QUOTE_BASES[rate_type]
    if quote_basis not in allowed:
        raise BenchmarkSeriesValueError(
            f"quote_basis {quote_basis!r} is incoherent for rate_type {rate_type!r} "
            f"(allowed: {allowed})"
        )
    if observation_convention not in BENCHMARK_RATE_OBSERVATION_CONVENTIONS:
        raise BenchmarkSeriesValueError(
            f"observation_convention {observation_convention!r} not in "
            f"{BENCHMARK_RATE_OBSERVATION_CONVENTIONS}"
        )


def _validate_rate_value(rate_value: Decimal) -> None:
    """Finiteness: reject NaN/±Inf BEFORE write (the DQ min-only ``> -1`` RANGE does not catch
    +Inf; the ``-1`` floor is loose house-pattern inheritance, recorded at OQ-DATA-1-3)."""
    if not isinstance(rate_value, Decimal) or not rate_value.is_finite():
        raise BenchmarkSeriesValueError(f"rate_value must be a finite Decimal (got {rate_value!r})")


_RATE_SPEC = _SeriesSpec(
    table=BenchmarkRate,
    entity_type=ENTITY_BENCHMARK_RATE,
    value_attr="rate_value",
    key_attrs=("rate_date", "rate_type", "quote_basis", "observation_convention"),
    create_event=MARKET_BENCHMARK_RATE_CREATE_EVENT,
    update_event=MARKET_BENCHMARK_RATE_UPDATE_EVENT,
    correction_event=MARKET_BENCHMARK_RATE_CORRECTION_EVENT,
    required_rule_code="benchmark_rate.required_fields",
    required_rule_name="Benchmark rate required fields present",
    value_rule_code="benchmark_rate.value_sanity",
    value_rule_name="Benchmark rate economic sanity (> -1)",
    value_rule_params={"column": "rate_value", "min": -1, "min_inclusive": False},
    validate_keys=_validate_rate_keys,
    validate_value=_validate_rate_value,
)


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _expected_months(series_start: date, horizon: date) -> list[str]:
    """Every month key from ``series_start``'s month through ``horizon``'s month, inclusive —
    computed from the two DECLARATIONS only (OQ-DATA-1-4)."""
    if horizon < series_start:
        raise BenchmarkSeriesValueError(
            f"rates_complete_through {horizon} precedes series_start {series_start}"
        )
    out: list[str] = []
    year, month = series_start.year, series_start.month
    while (year, month) <= (horizon.year, horizon.month):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _series_heads(
    session: Session, *, acting_tenant: str, benchmark_id: str
) -> list[BenchmarkRate]:
    """ALL current-head rate rows for a benchmark head (any type/basis — the series-uniformity and
    completeness reads)."""
    return list(
        session.execute(
            select(BenchmarkRate)
            .where(
                BenchmarkRate.tenant_id == str(acting_tenant),
                BenchmarkRate.benchmark_id == str(benchmark_id),
                BenchmarkRate.valid_to.is_(None),
                BenchmarkRate.system_to.is_(None),
            )
            .order_by(BenchmarkRate.rate_date)
        )
        .scalars()
        .all()
    )


# --- per-row public API (the ENT-052 wrapper shape) ---


def capture_benchmark_rate(
    session: Session,
    benchmark: Benchmark,
    *,
    rate_date: date,
    rate_type: str,
    quote_basis: str,
    observation_convention: str,
    rate_value: Decimal,
    acting_tenant: str,
    actor: BenchmarkActor,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkRate:
    """Capture the first open published rate for a (benchmark, rate_date, rate_type, quote_basis).
    Captured verbatim — the value is the published rate as a DECIMAL FRACTION; NEVER a re-expressed
    period return."""
    _validate_rate_keys(
        rate_type=rate_type,
        quote_basis=quote_basis,
        observation_convention=observation_convention,
    )
    _validate_rate_value(rate_value)
    return _capture(
        session,
        _RATE_SPEC,
        benchmark,
        keys={
            "rate_date": rate_date,
            "rate_type": rate_type,
            "quote_basis": quote_basis,
            "observation_convention": observation_convention,
        },
        value=rate_value,
        acting_tenant=acting_tenant,
        actor=actor,
        valid_from=valid_from,
        entity_id=entity_id,
        now=now,
    )


def supersede_benchmark_rate(
    session: Session,
    benchmark: Benchmark,
    *,
    rate_date: date,
    rate_type: str,
    quote_basis: str,
    observation_convention: str,
    rate_value: Decimal,
    acting_tenant: str,
    actor: BenchmarkActor,
    effective_at: datetime,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkRate:
    _validate_rate_keys(
        rate_type=rate_type,
        quote_basis=quote_basis,
        observation_convention=observation_convention,
    )
    _validate_rate_value(rate_value)
    return _supersede(
        session,
        _RATE_SPEC,
        benchmark,
        keys={
            "rate_date": rate_date,
            "rate_type": rate_type,
            "quote_basis": quote_basis,
            "observation_convention": observation_convention,
        },
        value=rate_value,
        acting_tenant=acting_tenant,
        actor=actor,
        effective_at=effective_at,
        entity_id=entity_id,
        now=now,
    )


def correct_benchmark_rate(
    session: Session,
    benchmark: Benchmark,
    *,
    rate_date: date,
    rate_type: str,
    quote_basis: str,
    observation_convention: str,
    rate_value: Decimal,
    restatement_reason: str,
    acting_tenant: str,
    actor: BenchmarkActor,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkRate:
    """As-known restatement — the path for the Board's rare documented historical corrections
    (the H.15 correction page; row-scoped)."""
    _validate_rate_keys(
        rate_type=rate_type,
        quote_basis=quote_basis,
        observation_convention=observation_convention,
    )
    _validate_rate_value(rate_value)
    return _correct(
        session,
        _RATE_SPEC,
        benchmark,
        keys={
            "rate_date": rate_date,
            "rate_type": rate_type,
            "quote_basis": quote_basis,
            "observation_convention": observation_convention,
        },
        value=rate_value,
        restatement_reason=restatement_reason,
        acting_tenant=acting_tenant,
        actor=actor,
        entity_id=entity_id,
        now=now,
    )


def reconstruct_benchmark_rate_as_of(
    session: Session,
    *,
    acting_tenant: str,
    benchmark_id: str,
    rate_date: date,
    rate_type: str,
    quote_basis: str,
    observation_convention: str,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> BenchmarkRate | None:
    return _reconstruct(
        session,
        _RATE_SPEC,
        acting_tenant=acting_tenant,
        benchmark_id=benchmark_id,
        keys={
            "rate_date": rate_date,
            "rate_type": rate_type,
            "quote_basis": quote_basis,
            "observation_convention": observation_convention,
        },
        valid_at=valid_at,
        known_at=known_at,
    )


def list_benchmark_rates(
    session: Session, *, acting_tenant: str, benchmark_id: str
) -> list[BenchmarkRate]:
    return _list(session, _RATE_SPEC, acting_tenant=acting_tenant, benchmark_id=benchmark_id)


# --- the governed bulk rail (OQ-DATA-1-6/7) ---


def refresh_benchmark_rates(
    session: Session,
    benchmark: Benchmark,
    *,
    rates: Mapping[date, Decimal] | Iterable[tuple[date, Decimal]],
    rate_type: str,
    quote_basis: str,
    observation_convention: str,
    series_start: date,
    acting_tenant: str,
    actor: BenchmarkActor,
    complete_through: date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """ADD-ONLY refresh + FORWARD-ONLY coverage advance + the effective-refresh completeness gate.
    Returns ``{"added": int, "rates_complete_through": date | None, "completeness_ran": bool}``.
    Semantics per the module docstring; every refusal is fail-closed BEFORE any surviving write."""
    _validate_rate_keys(
        rate_type=rate_type,
        quote_basis=quote_basis,
        observation_convention=observation_convention,
    )

    # Intra-call dedupe: FIRST-spec-wins (the CAL-1a refresh semantic).
    supplied: dict[date, Decimal] = {}
    items = rates.items() if isinstance(rates, Mapping) else rates
    for day, value in items:
        if day not in supplied:
            _validate_rate_value(value)
            supplied[day] = value

    heads = _series_heads(session, acting_tenant=acting_tenant, benchmark_id=benchmark.id)
    # ONE series per head (the v1 coverage-grain refusal, OQ-DATA-1-3).
    foreign = [h for h in heads if (h.rate_type, h.quote_basis) != (rate_type, quote_basis)]
    if foreign:
        raise BenchmarkSeriesValueError(
            f"benchmark {benchmark.benchmark_code!r} already carries a "
            f"({foreign[0].rate_type}, {foreign[0].quote_basis}) rate series — one "
            "(rate_type, quote_basis) series per head in v1 (the head-level "
            "rates_complete_through cannot say WHICH series is complete)"
        )
    existing: dict[date, BenchmarkRate] = {h.rate_date: h for h in heads}

    # ADD-ONLY diff; a differing value for a captured date is a vendor revision → the correct verb.
    additions: dict[date, Decimal] = {}
    for day, value in supplied.items():
        head = existing.get(day)
        if head is None:
            additions[day] = value
        elif head.rate_value != value:
            raise BenchmarkSeriesValueError(
                f"rate for {day} is already captured with a different value "
                f"({head.rate_value} vs supplied {value}) — a vendor revision goes through "
                "correct_benchmark_rate with a restatement reason, never a silent refresh"
            )

    # FORWARD-ONLY horizon; may not outrun the data (OQ-DATA-1-6).
    prior_horizon = benchmark.rates_complete_through
    new_horizon = prior_horizon
    if complete_through is not None:
        if prior_horizon is not None and complete_through < prior_horizon:
            raise BenchmarkSeriesValueError(
                f"rates_complete_through may only advance (forward-only): "
                f"{complete_through} < declared {prior_horizon}"
            )
        all_dates = set(existing) | set(additions)
        if all_dates:
            last = max(all_dates)
            if last.month == 12:
                last_month_end = date(last.year + 1, 1, 1)
            else:
                last_month_end = date(last.year, last.month + 1, 1)
            if complete_through >= last_month_end:
                raise BenchmarkSeriesValueError(
                    f"rates_complete_through {complete_through} is beyond the month of the last "
                    f"rate ({last}) — a declared horizon may not outrun the captured data"
                )
        new_horizon = complete_through

    advanced = new_horizon is not None and new_horizon != prior_horizon
    if not additions and not advanced:
        return {  # idempotent no-op: NOTHING written, NOTHING emitted, no DQ leg (OQ-DATA-1-6).
            "added": 0,
            "rates_complete_through": prior_horizon,
            "completeness_ran": False,
        }

    # --- the DATA savepoint: rate rows + the horizon advance + the head event live and die
    # together; a completeness FAIL unwinds them while the FAIL evidence (below) commits.
    savepoint = session.begin_nested()
    try:
        for day in sorted(additions):
            capture_benchmark_rate(
                session,
                benchmark,
                rate_date=day,
                rate_type=rate_type,
                quote_basis=quote_basis,
                observation_convention=observation_convention,
                rate_value=additions[day],
                acting_tenant=acting_tenant,
                actor=actor,
                now=now,
            )
        before = {
            "rates_complete_through": _json_safe(prior_horizon),
            "record_version": benchmark.record_version,
        }
        benchmark.rates_complete_through = new_horizon
        benchmark.record_version += 1
        session.flush()
        _emit(
            session,
            tenant_id=benchmark.tenant_id,
            entity_type="benchmark",
            entity_id=benchmark.id,
            event_type=REFERENCE_UPDATE_EVENT,
            action=ACTION_UPDATE,
            before_value=before,
            after_value={
                "rates_complete_through": _json_safe(new_horizon),
                "record_version": benchmark.record_version,
                "rates_added": len(additions),
            },
            actor=actor,
            now=now,
        )
        month_rows = [
            {_COMPLETENESS_KEY_COLUMN: _month_key(h.rate_date)}
            for h in _series_heads(session, acting_tenant=acting_tenant, benchmark_id=benchmark.id)
        ]
    except Exception:
        savepoint.rollback()
        raise

    if new_horizon is None:
        # No declared horizon → nothing to gate against (the un-gated state is downstream-refused
        # exactly like a NULL calendar coverage). The data commits.
        savepoint.commit()
        return {
            "added": len(additions),
            "rates_complete_through": None,
            "completeness_ran": False,
        }

    params = {
        "key_column": _COMPLETENESS_KEY_COLUMN,
        "expected": _expected_months(series_start, new_horizon),
    }
    evaluation = evaluate_rule(RULE_TYPE_COMPLETENESS, params, month_rows)  # pure pre-check
    if evaluation.passed:
        savepoint.commit()
    else:
        savepoint.rollback()  # the batch is GONE; the FAIL evidence below persists (OQ-DATA-1-6)

    rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        entity_type=ENTITY_BENCHMARK_RATE,
        code=COMPLETENESS_RULE_CODE,
        name=COMPLETENESS_RULE_NAME,
        rule_type=RULE_TYPE_COMPLETENESS,
        params=params,
    )
    if rule.params != params:  # advance the persisted expected set (the rule says what was
        update_dq_rule(session, rule, actor_id=actor.actor_id, params=params)  # last expected)
    run_quality_check(  # persists PASS or FAIL evidence + DATA.VALIDATE; raises on FAIL
        session,
        rule=rule,
        dataset=month_rows,
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_BENCHMARK_RATE,
        target_entity_id=str(benchmark.id),
        actor_type=actor.actor_type,
    )
    return {
        "added": len(additions),
        "rates_complete_through": new_horizon,
        "completeness_ran": True,
    }


__all__ = [
    "resolve_benchmark",  # re-exported for endpoint convenience (parent resolution)
    "BenchmarkActor",
    "MARKET_BENCHMARK_RATE_CREATE_EVENT",
    "MARKET_BENCHMARK_RATE_UPDATE_EVENT",
    "MARKET_BENCHMARK_RATE_CORRECTION_EVENT",
    "COMPLETENESS_RULE_CODE",
    "capture_benchmark_rate",
    "supersede_benchmark_rate",
    "correct_benchmark_rate",
    "reconstruct_benchmark_rate_as_of",
    "list_benchmark_rates",
    "refresh_benchmark_rates",
]
