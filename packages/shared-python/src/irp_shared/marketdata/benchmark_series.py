"""Benchmark time-series binder (P2-7, ENT-052) — captured index levels + vendor-published returns.

``benchmark_level`` + ``benchmark_return`` are captured-INPUT FR bitemporal series under the
existing ENT-009 ``benchmark`` EV header (the ``factor_return`` single-row FR protocol: capture /
effective-dated supersede / as-known correction / both-axes reconstruct). **Captured, NEVER
computed:** ``benchmark_return`` is captured vendor-published values ONLY — NO return calculation
from levels (OQ-P2-6-9; a level-derived return is a methodology choice needing a registered
``model_version``, DEFERRED). No analytics, no ``calculation_run``/``model_version``/snapshot pin
(an INPUT, not a governed derived number). REUSE the ``benchmark`` ``VENDOR_BENCHMARK`` data_source
(``ensure_vendor_source``) + ``resolve_benchmark`` + ``marketdata.view``/``.ingest`` (no new source,
no new permission).

The two tables share the FR mechanics — parameterized by a small ``_SeriesSpec`` (the tables are
near-identical, differing only in logical-key arity, the value column, the controlled vocab, the DQ
band, and the audit codes; the P3-C1/P3-4-R0 "extract the stable shared shape" spirit rather than a
second copy). Thin public wrappers per table sit over the generic core.

The DQ resolve-or-register is **RACE-SAFE FROM BIRTH** (the P3-C2 OD-E savepoint pattern:
``begin_nested()`` + ``except IntegrityError`` re-SELECT) — a NEW binder must not inherit the older
``SELECT``-then-``INSERT`` first-registration race.

Invariants (the ``factor``/``fx_rate`` precedent): ONE ``now = utcnow()`` per op; CLOSE-FIRST
ordering on a re-version; a prior version's CONTENT is NEVER mutated (only ``valid_to``/
``system_to``); vocab + a finiteness (level: + positivity) guard are binder-side
``BenchmarkSeriesValueError`` (-> 422) BEFORE any write; the DQ gate (required NOT_NULL + an
economic-sanity RANGE) is fail-closed + co-transactional; the ``(params, dataset)`` Protocol is
UNTOUCHED. No mid-call commit (CTRL-032). ``audit/service.py`` is FROZEN; **no emit on read**.
Per-op audit grain (single-row, the ``factor_return`` precedent): capture=1 CREATE; supersede=2
(UPDATE close-out + CREATE); correct=2 (UPDATE + CORRECTION).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL, RULE_TYPE_RANGE
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.lineage.models import EDGE_KIND_ORIGIN
from irp_shared.lineage.service import record_lineage
from irp_shared.marketdata.benchmark import (
    BenchmarkActor,
    ensure_vendor_source,
    resolve_benchmark,
)
from irp_shared.marketdata.models import (
    BENCHMARK_LEVEL_TYPES,
    BENCHMARK_RETURN_BASES,
    BENCHMARK_RETURN_TYPES,
    RETURN_TYPE_SIMPLE,
    Benchmark,
    BenchmarkLevel,
    BenchmarkReturn,
)

SOURCE_MODULE = "marketdata"

# --- audit constants (MARKET.* family, EVT-200 block; caller-side strings; audit/service.py FROZEN)
MARKET_BENCHMARK_LEVEL_CREATE_EVENT = "MARKET.BENCHMARK_LEVEL_CREATE"
MARKET_BENCHMARK_LEVEL_UPDATE_EVENT = "MARKET.BENCHMARK_LEVEL_UPDATE"
MARKET_BENCHMARK_LEVEL_CORRECTION_EVENT = "MARKET.BENCHMARK_LEVEL_CORRECTION"
MARKET_BENCHMARK_RETURN_CREATE_EVENT = "MARKET.BENCHMARK_RETURN_CREATE"
MARKET_BENCHMARK_RETURN_UPDATE_EVENT = "MARKET.BENCHMARK_RETURN_UPDATE"
MARKET_BENCHMARK_RETURN_CORRECTION_EVENT = "MARKET.BENCHMARK_RETURN_CORRECTION"

ENTITY_BENCHMARK_LEVEL = "benchmark_level"
ENTITY_BENCHMARK_RETURN = "benchmark_return"


class BenchmarkSeriesValueError(Exception):
    """Out-of-vocab type/basis, a non-finite (level: non-positive) value, or an empty key — caught
    BEFORE any write (fail-closed; maps to 422)."""


class NoCurrentBenchmarkSeries(Exception):
    """A supersede/correct was requested but the (benchmark, date, type[, basis]) has no open
    current head (maps to 409 CONFLICT — the ``factor_return`` precedent). Carries ``entity_type``
    (level vs return)."""

    def __init__(self, entity_type: str, benchmark_id: str, keys: dict[str, Any]) -> None:
        super().__init__(
            f"{entity_type} for benchmark {benchmark_id} has no current head at {keys}"
        )
        self.entity_type = entity_type
        self.benchmark_id = str(benchmark_id)
        self.keys = dict(keys)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


# --- the per-table spec: the only differences between the two FR series ---


@dataclass(frozen=True)
class _SeriesSpec:
    # A union of the two model types so mypy resolves the shared FR/tenant column access in the
    # generic core (both carry tenant_id/benchmark_id/valid_*/system_* via the mixins + FK).
    table: type[BenchmarkLevel] | type[BenchmarkReturn]
    entity_type: str
    value_attr: str  # "level_value" / "return_value"
    key_attrs: tuple[str, ...]  # logical-key cols beyond benchmark_id (ORDER = the row key order)
    create_event: str
    update_event: str
    correction_event: str
    required_rule_code: str
    required_rule_name: str
    value_rule_code: str
    value_rule_name: str
    value_rule_params: dict[str, Any]
    validate_keys: Callable[..., None]  # (**keys) -> None; raises BenchmarkSeriesValueError
    validate_value: Callable[[Decimal], None]  # finiteness (+ positivity for level); raises


def _validate_level_keys(*, level_type: str, **_: Any) -> None:
    if level_type not in BENCHMARK_LEVEL_TYPES:
        raise BenchmarkSeriesValueError(f"level_type {level_type!r} not in {BENCHMARK_LEVEL_TYPES}")


def _validate_return_keys(*, return_type: str, return_basis: str, **_: Any) -> None:
    if return_type not in BENCHMARK_RETURN_TYPES:
        raise BenchmarkSeriesValueError(
            f"return_type {return_type!r} not in {BENCHMARK_RETURN_TYPES}"
        )
    if return_basis not in BENCHMARK_RETURN_BASES:
        raise BenchmarkSeriesValueError(
            f"return_basis {return_basis!r} not in {BENCHMARK_RETURN_BASES}"
        )


def _validate_level_value(level_value: Decimal) -> None:
    """Finiteness + positivity: reject NaN/±Inf (the DQ ``> 0`` RANGE does not catch +Inf) and a
    non-positive level (an index level is positive by construction)."""
    if not isinstance(level_value, Decimal) or not level_value.is_finite():
        raise BenchmarkSeriesValueError(
            f"level_value must be a finite Decimal (got {level_value!r})"
        )
    if level_value <= 0:
        raise BenchmarkSeriesValueError(f"level_value must be > 0 (got {level_value})")


def _validate_return_value(return_value: Decimal) -> None:
    """Finiteness: reject NaN/±Inf BEFORE write (the DQ min-only ``> -1`` RANGE does not catch
    +Inf)."""
    if not isinstance(return_value, Decimal) or not return_value.is_finite():
        raise BenchmarkSeriesValueError(
            f"return_value must be a finite Decimal (got {return_value!r})"
        )


_LEVEL_SPEC = _SeriesSpec(
    table=BenchmarkLevel,
    entity_type=ENTITY_BENCHMARK_LEVEL,
    value_attr="level_value",
    key_attrs=("level_date", "level_type"),
    create_event=MARKET_BENCHMARK_LEVEL_CREATE_EVENT,
    update_event=MARKET_BENCHMARK_LEVEL_UPDATE_EVENT,
    correction_event=MARKET_BENCHMARK_LEVEL_CORRECTION_EVENT,
    required_rule_code="benchmark_level.required_fields",
    required_rule_name="Benchmark level required fields present",
    value_rule_code="benchmark_level.value_sanity",
    value_rule_name="Benchmark level economic sanity (> 0)",
    value_rule_params={"column": "level_value", "min": 0, "min_inclusive": False},
    validate_keys=_validate_level_keys,
    validate_value=_validate_level_value,
)

_RETURN_SPEC = _SeriesSpec(
    table=BenchmarkReturn,
    entity_type=ENTITY_BENCHMARK_RETURN,
    value_attr="return_value",
    key_attrs=("return_date", "return_type", "return_basis"),
    create_event=MARKET_BENCHMARK_RETURN_CREATE_EVENT,
    update_event=MARKET_BENCHMARK_RETURN_UPDATE_EVENT,
    correction_event=MARKET_BENCHMARK_RETURN_CORRECTION_EVENT,
    required_rule_code="benchmark_return.required_fields",
    required_rule_name="Benchmark return required fields present",
    value_rule_code="benchmark_return.value_sanity",
    value_rule_name="Benchmark return economic sanity (> -1)",
    value_rule_params={"column": "return_value", "min": -1, "min_inclusive": False},
    validate_keys=_validate_return_keys,
    validate_value=_validate_return_value,
)


# --- governed DQ gate (RACE-SAFE resolve-or-register; the Protocol is UNTOUCHED) ---


def _ensure_rule(
    session: Session,
    *,
    tenant_id: str,
    actor: BenchmarkActor,
    entity_type: str,
    code: str,
    name: str,
    rule_type: str,
    params: dict[str, Any],
) -> DataQualityRule:
    """Resolve-or-register a per-tenant governed DQ rule, RACE-SAFE (P3-C2 OD-E): two concurrent
    first captures both SELECT-miss then both INSERT the same ``(tenant, code)`` → one hits
    ``uq_data_quality_rule_tenant_code``. The INSERT is wrapped in a SAVEPOINT so IntegrityError
    rolls back ONLY that INSERT (not the whole co-transactional write); the loser re-SELECTs the
    peer's committed rule. ``register_dq_rule`` flushes the rule BEFORE its audit event, so the
    loser leaves NO dangling audit row (the savepoint unwinds it)."""
    q = select(DataQualityRule).where(
        DataQualityRule.tenant_id == str(tenant_id),
        DataQualityRule.code == code,
    )
    rule = session.execute(q).scalar_one_or_none()
    if rule is not None:
        return rule
    try:
        with session.begin_nested():
            return register_dq_rule(
                session,
                tenant_id=str(tenant_id),
                code=code,
                name=name,
                rule_type=rule_type,
                actor_id=actor.actor_id,
                params=params,
                target_entity_type=entity_type,
                severity=SEVERITY_ERROR,
                actor_type=actor.actor_type,
            )
    except IntegrityError:
        peer = session.execute(q).scalar_one_or_none()
        if peer is None:  # not the unique-collision we handle — re-raise loudly
            raise
        return peer


def _run_dq_gate(
    session: Session,
    spec: _SeriesSpec,
    *,
    acting_tenant: str,
    actor: BenchmarkActor,
    row: Any,
    value: Decimal,
) -> None:
    """Fail-closed DQ gate (co-transactional; ``DATA.VALIDATE``): (1) required-field NOT_NULL over
    the row's logical key + value; (2) an economic-sanity single-column RANGE (level ``> 0`` /
    return ``> -1``). A failure -> ``DataQualityError`` -> the caller's whole unit rolls back
    (CTRL-032). Finiteness is the binder guard (BEFORE this gate)."""
    required_fields = ("benchmark_id", *spec.key_attrs, spec.value_attr)
    missing = any(getattr(row, f) is None for f in required_fields)
    required_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        entity_type=spec.entity_type,
        code=spec.required_rule_code,
        name=spec.required_rule_name,
        rule_type=RULE_TYPE_NOT_NULL,
        params={"column": "present"},
    )
    run_quality_check(
        session,
        rule=required_rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=spec.entity_type,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )
    value_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        entity_type=spec.entity_type,
        code=spec.value_rule_code,
        name=spec.value_rule_name,
        rule_type=RULE_TYPE_RANGE,
        params=spec.value_rule_params,
    )
    run_quality_check(
        session,
        rule=value_rule,
        dataset=[{spec.value_attr: value}],
        actor_id=actor.actor_id,
        target_entity_type=spec.entity_type,
        target_entity_id=row.id,
        actor_type=actor.actor_type,
    )


# --- provenance + audit (REUSE the benchmark VENDOR_BENCHMARK data_source) ---


def _origin_edge(
    session: Session, *, tenant_id: str, entity_type: str, entity_id: str, actor: BenchmarkActor
) -> None:
    """Root one ORIGIN lineage edge (the shared VENDOR_BENCHMARK source) targeting a NEW physical
    version row."""
    source = ensure_vendor_source(session, tenant_id, actor.actor_id)
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
    action: str,
    after_value: dict[str, Any],
    actor: BenchmarkActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    """Emit one audit event to the FROZEN record_event (per-tenant chain; DC-2 metadata)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_value=before_value,
        after_value=after_value,
        justification=justification,
        correlation_id=actor.correlation_id,
        agent_model=actor.agent_model,
        agent_model_version=actor.agent_model_version,
        on_behalf_of=actor.on_behalf_of,
        data_classification="DC-2",
        event_time=now,
    )


def _summary(spec: _SeriesSpec, benchmark: Benchmark, row: Any) -> dict[str, Any]:
    """A DC-2 summary dict (metadata only — code/source + the logical key + record_version; NEVER
    the captured value payload — the ``factor_return`` precedent keeps vendor-licensed values out of
    the audit trail)."""
    out: dict[str, Any] = {
        "benchmark_code": benchmark.benchmark_code,
        "benchmark_source": benchmark.benchmark_source,
    }
    for k in spec.key_attrs:
        out[k] = _json_safe(getattr(row, k))
    out["record_version"] = row.record_version
    return out


# --- generic FR core (keyed by spec + a logical-key dict) ---


def _current_open(
    session: Session,
    spec: _SeriesSpec,
    *,
    acting_tenant: str,
    benchmark_id: str,
    keys: dict[str, Any],
) -> Any:
    """The single version OPEN ON BOTH axes for a logical key (the bitemporal current head), or
    ``None``. Tenant-predicated."""
    conds = [
        spec.table.tenant_id == str(acting_tenant),
        spec.table.benchmark_id == str(benchmark_id),
        spec.table.valid_to.is_(None),
        spec.table.system_to.is_(None),
    ]
    conds += [getattr(spec.table, k) == v for k, v in keys.items()]
    return session.execute(select(spec.table).where(*conds)).scalar_one_or_none()


def _new_row(
    spec: _SeriesSpec,
    *,
    benchmark: Benchmark,
    keys: dict[str, Any],
    value: Decimal,
    valid_from: datetime,
    valid_to: datetime | None,
    system_from: datetime,
    record_version: int,
    supersedes_id: str | None = None,
    restatement_reason: str | None = None,
    entity_id: str | None = None,
) -> Any:
    row = spec.table(
        tenant_id=benchmark.tenant_id,
        benchmark_id=benchmark.id,
        valid_from=valid_from,
        valid_to=valid_to,
        system_from=system_from,
        system_to=None,
        record_version=record_version,
        supersedes_id=supersedes_id,
        restatement_reason=restatement_reason,
        **keys,
        **{spec.value_attr: value},
    )
    if entity_id is not None:
        row.id = entity_id
    return row


def _capture(
    session: Session,
    spec: _SeriesSpec,
    benchmark: Benchmark,
    *,
    keys: dict[str, Any],
    value: Decimal,
    acting_tenant: str,
    actor: BenchmarkActor,
    valid_from: datetime | None,
    entity_id: str | None,
    now: datetime | None,
) -> Any:
    """First open capture for a (benchmark, key) as ONE governed unit (FR row + VENDOR ORIGIN edge +
    CREATE audit + the DQ gate). Vocab + finiteness are validated by the caller BEFORE any write."""
    now = now or utcnow()
    row = _new_row(
        spec,
        benchmark=benchmark,
        keys=keys,
        value=value,
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        record_version=1,
        entity_id=entity_id,
    )
    session.add(row)
    session.flush()
    _run_dq_gate(session, spec, acting_tenant=acting_tenant, actor=actor, row=row, value=value)
    _origin_edge(
        session,
        tenant_id=row.tenant_id,
        entity_type=spec.entity_type,
        entity_id=row.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=row.tenant_id,
        entity_type=spec.entity_type,
        entity_id=row.id,
        event_type=spec.create_event,
        action="create",
        after_value=_summary(spec, benchmark, row),
        actor=actor,
        now=now,
    )
    return row


def _supersede(
    session: Session,
    spec: _SeriesSpec,
    benchmark: Benchmark,
    *,
    keys: dict[str, Any],
    value: Decimal,
    acting_tenant: str,
    actor: BenchmarkActor,
    effective_at: datetime,
    entity_id: str | None,
    now: datetime | None,
) -> Any:
    """Effective-dated (valid-time) re-capture for the SAME key: close the head's ``valid_to``
    (UPDATE), then insert a new version (CREATE + its own ORIGIN edge + the DQ gate)."""
    prior = _current_open(
        session, spec, acting_tenant=acting_tenant, benchmark_id=benchmark.id, keys=keys
    )
    if prior is None:
        raise NoCurrentBenchmarkSeries(spec.entity_type, benchmark.id, keys)
    now = now or utcnow()
    before = {"valid_to": _json_safe(prior.valid_to)}
    prior.valid_to = effective_at  # CLOSE-FIRST (valid-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_type=spec.entity_type,
        entity_id=prior.id,
        event_type=spec.update_event,
        action="update",
        before_value=before,
        after_value={"valid_to": _json_safe(prior.valid_to)},
        actor=actor,
        now=now,
    )
    new = _new_row(
        spec,
        benchmark=benchmark,
        keys=keys,
        value=value,
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        record_version=prior.record_version + 1,
        supersedes_id=prior.id,
        entity_id=entity_id,
    )
    session.add(new)
    session.flush()
    _run_dq_gate(session, spec, acting_tenant=acting_tenant, actor=actor, row=new, value=value)
    _origin_edge(
        session,
        tenant_id=new.tenant_id,
        entity_type=spec.entity_type,
        entity_id=new.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=new.tenant_id,
        entity_type=spec.entity_type,
        entity_id=new.id,
        event_type=spec.create_event,
        action="create",
        after_value=_summary(spec, benchmark, new),
        actor=actor,
        now=now,
    )
    return new


def _correct(
    session: Session,
    spec: _SeriesSpec,
    benchmark: Benchmark,
    *,
    keys: dict[str, Any],
    value: Decimal,
    restatement_reason: str,
    acting_tenant: str,
    actor: BenchmarkActor,
    entity_id: str | None,
    now: datetime | None,
) -> Any:
    """As-known restatement (TR-08): close the head's ``system_to`` (UPDATE) then insert a corrected
    version over the SAME valid period + same key (CORRECTION + its own ORIGIN edge + the DQ gate).
    The prior version's content columns are NEVER mutated — only ``system_to``."""
    prior = _current_open(
        session, spec, acting_tenant=acting_tenant, benchmark_id=benchmark.id, keys=keys
    )
    if prior is None:
        raise NoCurrentBenchmarkSeries(spec.entity_type, benchmark.id, keys)
    now = now or utcnow()
    before = {"system_to": _json_safe(prior.system_to)}
    valid_from_prior = prior.valid_from
    valid_to_prior = prior.valid_to
    prior.system_to = now  # CLOSE-FIRST (system-time)
    session.flush()
    _emit(
        session,
        tenant_id=prior.tenant_id,
        entity_type=spec.entity_type,
        entity_id=prior.id,
        event_type=spec.update_event,
        action="update",
        before_value=before,
        after_value={"system_to": _json_safe(prior.system_to)},
        actor=actor,
        now=now,
    )
    corrected = _new_row(
        spec,
        benchmark=benchmark,
        keys=keys,
        value=value,
        valid_from=valid_from_prior,  # SAME valid period (as-known correction)
        valid_to=valid_to_prior,
        system_from=now,  # one `now` — equals the prior head's system_to
        record_version=prior.record_version + 1,
        supersedes_id=prior.id,
        restatement_reason=restatement_reason,
        entity_id=entity_id,
    )
    session.add(corrected)
    session.flush()
    _run_dq_gate(
        session, spec, acting_tenant=acting_tenant, actor=actor, row=corrected, value=value
    )
    _origin_edge(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=spec.entity_type,
        entity_id=corrected.id,
        actor=actor,
    )
    _emit(
        session,
        tenant_id=corrected.tenant_id,
        entity_type=spec.entity_type,
        entity_id=corrected.id,
        event_type=spec.correction_event,
        action="correct",
        after_value=_summary(spec, benchmark, corrected),
        actor=actor,
        justification=restatement_reason,
        now=now,
    )
    return corrected


def _reconstruct(
    session: Session,
    spec: _SeriesSpec,
    *,
    acting_tenant: str,
    benchmark_id: str,
    keys: dict[str, Any],
    valid_at: datetime,
    known_at: datetime | None,
) -> Any:
    """Bitemporal as-of read: the single version true at ``valid_at`` as-known-at ``known_at``
    (defaults to now -> current view), or ``None``, for the logical key. Captured only — NO
    analytics."""
    known = known_at or utcnow()
    conds = [
        spec.table.tenant_id == str(acting_tenant),
        spec.table.benchmark_id == str(benchmark_id),
        spec.table.valid_from <= valid_at,
        or_(spec.table.valid_to.is_(None), spec.table.valid_to > valid_at),
        spec.table.system_from <= known,
        or_(spec.table.system_to.is_(None), spec.table.system_to > known),
    ]
    conds += [getattr(spec.table, k) == v for k, v in keys.items()]
    return session.execute(select(spec.table).where(*conds)).scalar_one_or_none()


def _list(
    session: Session,
    spec: _SeriesSpec,
    *,
    acting_tenant: str,
    benchmark_id: str,
) -> list[Any]:
    """The current-head (open on both axes) series for a benchmark, ordered by the logical key. A
    captured series only — NO analytics."""
    order_cols = [getattr(spec.table, k) for k in spec.key_attrs]
    return list(
        session.execute(
            select(spec.table)
            .where(
                spec.table.tenant_id == str(acting_tenant),
                spec.table.benchmark_id == str(benchmark_id),
                spec.table.valid_to.is_(None),
                spec.table.system_to.is_(None),
            )
            .order_by(*order_cols)
        )
        .scalars()
        .all()
    )


# --- benchmark_level public API ---


def capture_benchmark_level(
    session: Session,
    benchmark: Benchmark,
    *,
    level_date: date,
    level_type: str,
    level_value: Decimal,
    acting_tenant: str,
    actor: BenchmarkActor,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkLevel:
    """Capture the first open level for a (benchmark, level_date, level_type). ``benchmark`` must
    already be tenant-resolved (via ``resolve_benchmark``)."""
    _validate_level_keys(level_type=level_type)
    _validate_level_value(level_value)
    return _capture(
        session,
        _LEVEL_SPEC,
        benchmark,
        keys={"level_date": level_date, "level_type": level_type},
        value=level_value,
        acting_tenant=acting_tenant,
        actor=actor,
        valid_from=valid_from,
        entity_id=entity_id,
        now=now,
    )


def supersede_benchmark_level(
    session: Session,
    benchmark: Benchmark,
    *,
    level_date: date,
    level_type: str,
    level_value: Decimal,
    acting_tenant: str,
    actor: BenchmarkActor,
    effective_at: datetime,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkLevel:
    _validate_level_keys(level_type=level_type)
    _validate_level_value(level_value)
    return _supersede(
        session,
        _LEVEL_SPEC,
        benchmark,
        keys={"level_date": level_date, "level_type": level_type},
        value=level_value,
        acting_tenant=acting_tenant,
        actor=actor,
        effective_at=effective_at,
        entity_id=entity_id,
        now=now,
    )


def correct_benchmark_level(
    session: Session,
    benchmark: Benchmark,
    *,
    level_date: date,
    level_type: str,
    level_value: Decimal,
    restatement_reason: str,
    acting_tenant: str,
    actor: BenchmarkActor,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkLevel:
    _validate_level_keys(level_type=level_type)
    _validate_level_value(level_value)
    return _correct(
        session,
        _LEVEL_SPEC,
        benchmark,
        keys={"level_date": level_date, "level_type": level_type},
        value=level_value,
        restatement_reason=restatement_reason,
        acting_tenant=acting_tenant,
        actor=actor,
        entity_id=entity_id,
        now=now,
    )


def reconstruct_benchmark_level_as_of(
    session: Session,
    *,
    acting_tenant: str,
    benchmark_id: str,
    level_date: date,
    level_type: str,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> BenchmarkLevel | None:
    return _reconstruct(
        session,
        _LEVEL_SPEC,
        acting_tenant=acting_tenant,
        benchmark_id=benchmark_id,
        keys={"level_date": level_date, "level_type": level_type},
        valid_at=valid_at,
        known_at=known_at,
    )


def list_benchmark_levels(
    session: Session, *, acting_tenant: str, benchmark_id: str
) -> list[BenchmarkLevel]:
    return _list(session, _LEVEL_SPEC, acting_tenant=acting_tenant, benchmark_id=benchmark_id)


# --- benchmark_return public API ---


def capture_benchmark_return(
    session: Session,
    benchmark: Benchmark,
    *,
    return_date: date,
    return_basis: str,
    return_value: Decimal,
    acting_tenant: str,
    actor: BenchmarkActor,
    return_type: str = RETURN_TYPE_SIMPLE,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkReturn:
    """Capture the first open vendor-published return for a (benchmark, return_date, return_type,
    return_basis). Captured verbatim — NEVER computed from levels."""
    _validate_return_keys(return_type=return_type, return_basis=return_basis)
    _validate_return_value(return_value)
    return _capture(
        session,
        _RETURN_SPEC,
        benchmark,
        keys={
            "return_date": return_date,
            "return_type": return_type,
            "return_basis": return_basis,
        },
        value=return_value,
        acting_tenant=acting_tenant,
        actor=actor,
        valid_from=valid_from,
        entity_id=entity_id,
        now=now,
    )


def supersede_benchmark_return(
    session: Session,
    benchmark: Benchmark,
    *,
    return_date: date,
    return_basis: str,
    return_value: Decimal,
    acting_tenant: str,
    actor: BenchmarkActor,
    effective_at: datetime,
    return_type: str = RETURN_TYPE_SIMPLE,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkReturn:
    _validate_return_keys(return_type=return_type, return_basis=return_basis)
    _validate_return_value(return_value)
    return _supersede(
        session,
        _RETURN_SPEC,
        benchmark,
        keys={
            "return_date": return_date,
            "return_type": return_type,
            "return_basis": return_basis,
        },
        value=return_value,
        acting_tenant=acting_tenant,
        actor=actor,
        effective_at=effective_at,
        entity_id=entity_id,
        now=now,
    )


def correct_benchmark_return(
    session: Session,
    benchmark: Benchmark,
    *,
    return_date: date,
    return_basis: str,
    return_value: Decimal,
    restatement_reason: str,
    acting_tenant: str,
    actor: BenchmarkActor,
    return_type: str = RETURN_TYPE_SIMPLE,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> BenchmarkReturn:
    _validate_return_keys(return_type=return_type, return_basis=return_basis)
    _validate_return_value(return_value)
    return _correct(
        session,
        _RETURN_SPEC,
        benchmark,
        keys={
            "return_date": return_date,
            "return_type": return_type,
            "return_basis": return_basis,
        },
        value=return_value,
        restatement_reason=restatement_reason,
        acting_tenant=acting_tenant,
        actor=actor,
        entity_id=entity_id,
        now=now,
    )


def reconstruct_benchmark_return_as_of(
    session: Session,
    *,
    acting_tenant: str,
    benchmark_id: str,
    return_date: date,
    return_basis: str,
    valid_at: datetime,
    return_type: str = RETURN_TYPE_SIMPLE,
    known_at: datetime | None = None,
) -> BenchmarkReturn | None:
    return _reconstruct(
        session,
        _RETURN_SPEC,
        acting_tenant=acting_tenant,
        benchmark_id=benchmark_id,
        keys={
            "return_date": return_date,
            "return_type": return_type,
            "return_basis": return_basis,
        },
        valid_at=valid_at,
        known_at=known_at,
    )


def list_benchmark_returns(
    session: Session, *, acting_tenant: str, benchmark_id: str
) -> list[BenchmarkReturn]:
    return _list(session, _RETURN_SPEC, acting_tenant=acting_tenant, benchmark_id=benchmark_id)


__all__ = [
    "resolve_benchmark",  # re-exported for endpoint convenience (parent resolution)
    "BenchmarkActor",
    "BenchmarkSeriesValueError",
    "NoCurrentBenchmarkSeries",
    "MARKET_BENCHMARK_LEVEL_CREATE_EVENT",
    "MARKET_BENCHMARK_LEVEL_UPDATE_EVENT",
    "MARKET_BENCHMARK_LEVEL_CORRECTION_EVENT",
    "MARKET_BENCHMARK_RETURN_CREATE_EVENT",
    "MARKET_BENCHMARK_RETURN_UPDATE_EVENT",
    "MARKET_BENCHMARK_RETURN_CORRECTION_EVENT",
    "capture_benchmark_level",
    "supersede_benchmark_level",
    "correct_benchmark_level",
    "reconstruct_benchmark_level_as_of",
    "list_benchmark_levels",
    "capture_benchmark_return",
    "supersede_benchmark_return",
    "correct_benchmark_return",
    "reconstruct_benchmark_return_as_of",
    "list_benchmark_returns",
]
