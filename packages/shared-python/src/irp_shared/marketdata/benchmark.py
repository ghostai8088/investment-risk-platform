"""Benchmark binder + governed-write provenance (P2-6, ENT-009) — the captured benchmark/index data.

``benchmark`` (EV definition header) + ``benchmark_constituent`` (FR bitemporal membership) are
**captured vendor benchmark/index data** (OD-P2-6-*). The governance family is **split by temporal
class** (OQ-P2-6-11 Option A; the ratified ``p2_implementation_plan.md``:118 contract + ENT-009's
Reference/Security-Master home):

- The **EV definition** (``benchmark``) is reference data → audited ``REFERENCE.CREATE`` /
  ``REFERENCE.UPDATE`` (entity-versioned in place via ``record_version``).
- The **FR membership** (``benchmark_constituent``) is captured market/index data that re-versions
  over time → audited ``MARKET.BENCHMARK_CONSTITUENT_CREATE`` / ``_UPDATE`` / ``_CORRECTION`` at the
  EVT-200 block, captured/superseded/corrected **as a set** per ``(benchmark, effective_date)`` (the
  ``curve`` node-set atomicity, over FR rows rather than IA children).

Entitlement reuses ``marketdata.view``/``.ingest``; lineage is ``VENDOR_BENCHMARK`` ORIGIN (the
``VENDOR_CURVE`` sibling) — the definition is NOT moved into ``MARKET.*``.

Invariants: ONE ``now = utcnow()`` per op; CLOSE-FIRST ordering on a membership re-version; a prior
membership row's CONTENT is NEVER mutated (only ``valid_to``/``system_to``); the constituent
``tenant_id`` is server-stamped from the resolved parent ``benchmark`` header. **ONE event per
metadata op / per membership-set op** (set-grained — the constituents fold into the one set write).
Currency via the hybrid-aware ``resolve_currency``; ``instrument_id`` via ``resolve_instrument``
(NOT-NULL FK, fail-closed). A non-empty set is binder-enforced (``BenchmarkValueError`` -> 422). The
**DQ gate** (required-field NOT_NULL + weight ``RANGE [0, 1]``) is fail-closed + co-transactional;
the ``(params, dataset)`` Protocol is UNTOUCHED. **Captured, never computed:** NO performance,
active return/risk, tracking error, attribution, factor/covariance, VaR/ES, scenario, return
calculation; ``methodology_label`` is an inert label. A VENDOR (``VENDOR_BENCHMARK``)
``data_source`` ORIGIN edge per NEW benchmark version + per captured membership-set version
(benchmark-row-targeted; the edge carries NO ``effective_date`` — ``record_lineage`` reused
UNCHANGED). No mid-call commit (CTRL-032). ``audit/service.py`` is FROZEN; **no emit on read**.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL, RULE_TYPE_RANGE
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.marketdata.models import Benchmark, BenchmarkConstituent
from irp_shared.reference.events import REFERENCE_CREATE_EVENT, REFERENCE_UPDATE_EVENT
from irp_shared.reference.instrument import resolve_instrument
from irp_shared.reference.service import resolve_currency

# --- audit / provenance constants ---
# The EV definition uses the REFERENCE.* family (EVT-140/141; the canonical constants are imported
# from reference/events.py — a single source of truth, the corporate_action/instrument precedent);
# the FR membership uses the MARKET.* family (EVT-200; the fourth MARKET.* member after
# FX/PRICE/CURVE). OQ-P2-6-11 Option A. (REFERENCE_*_EVENT imported above.)
MARKET_BENCHMARK_CONSTITUENT_CREATE_EVENT = "MARKET.BENCHMARK_CONSTITUENT_CREATE"
MARKET_BENCHMARK_CONSTITUENT_UPDATE_EVENT = "MARKET.BENCHMARK_CONSTITUENT_UPDATE"
MARKET_BENCHMARK_CONSTITUENT_CORRECTION_EVENT = "MARKET.BENCHMARK_CONSTITUENT_CORRECTION"
VENDOR_BENCHMARK_SOURCE_TYPE = "VENDOR_BENCHMARK"
VENDOR_BENCHMARK_SOURCE_CODE = "VENDOR_BENCHMARK"
VENDOR_BENCHMARK_SOURCE_NAME = "Vendor benchmark/index data"
ENTITY_BENCHMARK = "benchmark"
ENTITY_BENCHMARK_CONSTITUENT = "benchmark_constituent"
SOURCE_MODULE = "marketdata"

#: Attributes ``update_benchmark`` may change in place (NOT the identity key code/source).
_UPDATABLE_BENCHMARK = (
    "benchmark_currency",
    "benchmark_name",
    "index_family",
    "vendor_code",
    "methodology_label",
)

#: Per-tenant governed DQ rule codes (resolve-or-register; the ``curve`` pattern).
_REQUIRED_RULE_CODE = "benchmark.required_fields"
_WEIGHT_RULE_CODE = "benchmark.weight_sanity"


@dataclass(frozen=True)
class ConstituentInput:
    """One captured membership constituent supplied to the binder. ``entity_id`` is the
    deterministic-injection seam (default-None => prod unchanged)."""

    instrument_id: str
    weight: Decimal
    constituent_currency: str | None = None
    entity_id: str | None = None


@dataclass(frozen=True)
class BenchmarkActor:
    """Actor/correlation context threaded into every benchmark audit emission (BR-16 ready)."""

    actor_id: str
    actor_type: str = "user"
    agent_model: str | None = None
    agent_model_version: str | None = None
    on_behalf_of: str | None = None
    correlation_id: str | None = None


class BenchmarkValueError(Exception):
    """Raised for an empty membership set or other binder-side value breach — caught BEFORE any
    write (fail-closed; maps to 422)."""


class BenchmarkNotVisible(Exception):
    """Raised when a ``benchmark`` id is not visible in the acting tenant scope (cross-tenant)."""

    def __init__(self, benchmark_id: str) -> None:
        super().__init__(f"benchmark {benchmark_id} is not visible in the current tenant context")
        self.benchmark_id = str(benchmark_id)


class NoCurrentMembership(Exception):
    """Raised when a membership supersede/correct is requested but the (benchmark, effective_date)
    set has no open membership."""

    def __init__(self, benchmark_id: str, effective_date: date) -> None:
        super().__init__(
            f"benchmark {benchmark_id} has no current (open) membership for {effective_date}"
        )
        self.benchmark_id = str(benchmark_id)
        self.effective_date = effective_date


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


# --- binder-side value checks (BenchmarkValueError -> 422, BEFORE any write; not the DQ gate) ---


def _validate_constituents(constituents: list[ConstituentInput]) -> None:
    if not constituents:
        raise BenchmarkValueError("a benchmark membership must have at least one constituent")


def _resolve_membership_refs(
    session: Session, constituents: list[ConstituentInput], *, acting_tenant: str
) -> None:
    """Resolve every constituent instrument (NOT-NULL FK; ``InstrumentNotVisible`` -> 404) and any
    non-null constituent currency (hybrid-aware; ``CurrencyNotVisible`` -> 404) under the acting
    tenant — fails closed BEFORE any write."""
    for constituent in constituents:
        resolve_instrument(session, constituent.instrument_id, acting_tenant=acting_tenant)
        if constituent.constituent_currency is not None:
            resolve_currency(session, constituent.constituent_currency, acting_tenant=acting_tenant)


# --- governed DQ gate (membership; the ``curve`` pattern — Protocol UNTOUCHED) ---


def _ensure_rule(
    session: Session,
    *,
    tenant_id: str,
    actor: BenchmarkActor,
    code: str,
    name: str,
    rule_type: str,
    params: dict[str, Any],
) -> DataQualityRule:
    """Resolve-or-register a per-tenant governed DQ rule (audited; the ``curve`` pattern)."""
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
        target_entity_type=ENTITY_BENCHMARK,
        severity=SEVERITY_ERROR,
        actor_type=actor.actor_type,
    )


def _run_membership_dq_gate(
    session: Session,
    *,
    acting_tenant: str,
    actor: BenchmarkActor,
    benchmark: Benchmark,
    constituents: list[ConstituentInput],
) -> None:
    """Fail-closed DQ gate (co-transactional; ``DATA.VALIDATE``) over the captured membership set:
    (1) required-field NOT_NULL (each constituent ``instrument_id``/``weight``); (2) a weight sanity
    ``RANGE [0, 1]`` (one ordinary single-column RANGE over the constituent weights — the
    ``(params, dataset)`` Protocol is UNTOUCHED). A failure -> ``DataQualityError`` -> the caller's
    whole unit rolls back (CTRL-032). Weight-sum completeness + staleness are DEFERRED (OQ-P2-6-8).
    The set is non-empty (binder-validated), so the RANGE gate is non-vacuous."""
    missing = any(
        getattr(constituent, field) is None
        for constituent in constituents
        for field in ("instrument_id", "weight")
    )
    required_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_REQUIRED_RULE_CODE,
        name="Benchmark constituent required fields present",
        rule_type=RULE_TYPE_NOT_NULL,
        params={"column": "present"},
    )
    run_quality_check(
        session,
        rule=required_rule,
        dataset=[{"present": None if missing else True}],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_BENCHMARK,
        target_entity_id=benchmark.id,
        actor_type=actor.actor_type,
    )

    weight_rule = _ensure_rule(
        session,
        tenant_id=acting_tenant,
        actor=actor,
        code=_WEIGHT_RULE_CODE,
        name="Benchmark constituent weight sanity band",
        rule_type=RULE_TYPE_RANGE,
        params={"column": "weight", "min": 0, "max": 1},
    )
    run_quality_check(
        session,
        rule=weight_rule,
        dataset=[{"weight": constituent.weight} for constituent in constituents],
        actor_id=actor.actor_id,
        target_entity_type=ENTITY_BENCHMARK,
        target_entity_id=benchmark.id,
        actor_type=actor.actor_type,
    )


# --- provenance: VENDOR data_source + caller-side emitters (split audit family) ---


def ensure_vendor_source(session: Session, tenant_id: str, actor_id: str) -> DataSource:
    """Idempotently resolve-or-register the acting tenant's shared ``VENDOR_BENCHMARK``
    ``data_source`` (governed provenance root; the ``VENDOR_CURVE`` precedent). Module-local."""
    existing = session.execute(
        select(DataSource).where(
            DataSource.tenant_id == str(tenant_id),
            DataSource.code == VENDOR_BENCHMARK_SOURCE_CODE,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return register_data_source(
        session,
        tenant_id=str(tenant_id),
        code=VENDOR_BENCHMARK_SOURCE_CODE,
        name=VENDOR_BENCHMARK_SOURCE_NAME,
        source_type=VENDOR_BENCHMARK_SOURCE_TYPE,
        actor_id=actor_id,
    )


def _origin_edge(session: Session, *, benchmark: Benchmark, actor: BenchmarkActor) -> None:
    """Root one ORIGIN lineage edge (VENDOR_BENCHMARK source) targeting the ``benchmark`` row (the
    definition origin, OR a captured membership-set version — constituents covered transitively)."""
    source = ensure_vendor_source(session, benchmark.tenant_id, actor.actor_id)
    record_lineage(
        session,
        source=source,
        target_entity_type=ENTITY_BENCHMARK,
        target_entity_id=benchmark.id,
        edge_kind=EDGE_KIND_ORIGIN,
    )


def _emit(
    session: Session,
    *,
    benchmark: Benchmark,
    event_type: str,
    action: str,
    after_value: dict[str, Any],
    actor: BenchmarkActor,
    before_value: dict[str, Any] | None = None,
    justification: str | None = None,
    now: datetime | None = None,
) -> None:
    """Emit one audit event to the FROZEN record_event (per-tenant chain; DC-2 metadata; anchored on
    the benchmark row for both the definition and the set-grained membership)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=benchmark.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_BENCHMARK,
        entity_id=benchmark.id,
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


def _benchmark_summary(row: Benchmark) -> dict[str, Any]:
    """A DC-2 benchmark-definition-summary dict (metadata only)."""
    return {
        "benchmark_code": row.benchmark_code,
        "benchmark_source": row.benchmark_source,
        "benchmark_currency": row.benchmark_currency,
        "index_family": row.index_family,
        "record_version": row.record_version,
    }


def _membership_summary(
    benchmark: Benchmark, *, effective_date: date, constituent_count: int
) -> dict[str, Any]:
    """A DC-2 membership-set-summary dict (metadata only — never the full constituent payload)."""
    return {
        "benchmark_code": benchmark.benchmark_code,
        "benchmark_source": benchmark.benchmark_source,
        "benchmark_currency": benchmark.benchmark_currency,
        "effective_date": _json_safe(effective_date),
        "constituent_count": constituent_count,
    }


# --- benchmark DEFINITION (EV; REFERENCE.* audit; VENDOR_BENCHMARK lineage) ---


def resolve_benchmark(session: Session, benchmark_id: str, *, acting_tenant: str) -> Benchmark:
    """Resolve a ``benchmark`` by id with an EXPLICIT ``tenant_id == acting_tenant`` predicate
    (fail-closed). Raises :class:`BenchmarkNotVisible` on a hidden id."""
    row = session.execute(
        select(Benchmark).where(
            Benchmark.id == str(benchmark_id), Benchmark.tenant_id == str(acting_tenant)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BenchmarkNotVisible(str(benchmark_id))
    return row


def capture_benchmark(
    session: Session,
    *,
    benchmark_code: str,
    benchmark_source: str,
    benchmark_currency: str,
    acting_tenant: str,
    actor: BenchmarkActor,
    benchmark_name: str | None = None,
    index_family: str | None = None,
    vendor_code: str | None = None,
    methodology_label: str | None = None,
    valid_from: datetime | None = None,
    entity_id: str | None = None,
    now: datetime | None = None,
) -> Benchmark:
    """Capture a benchmark DEFINITION (EV): resolve the denomination currency (hybrid-aware), create
    the row, root one VENDOR_BENCHMARK ORIGIN edge + emit ``REFERENCE.CREATE``. The definition is
    reference data (OQ-P2-6-11 Option A) — NOT market analytics. ``entity_id``/``now`` are
    the deterministic-injection seam."""
    resolve_currency(session, benchmark_currency, acting_tenant=acting_tenant)
    now = now or utcnow()
    row = Benchmark(
        tenant_id=str(acting_tenant),
        benchmark_code=benchmark_code,
        benchmark_source=benchmark_source,
        benchmark_currency=benchmark_currency,
        benchmark_name=benchmark_name,
        index_family=index_family,
        vendor_code=vendor_code,
        methodology_label=methodology_label,  # inert metadata (no engine)
        valid_from=(valid_from or now),
        valid_to=None,
        record_version=1,
    )
    if entity_id is not None:
        row.id = entity_id
    session.add(row)
    session.flush()
    _origin_edge(session, benchmark=row, actor=actor)
    _emit(
        session,
        benchmark=row,
        event_type=REFERENCE_CREATE_EVENT,
        action="create",
        after_value=_benchmark_summary(row),
        actor=actor,
        now=now,
    )
    return row


def update_benchmark(
    session: Session,
    benchmark: Benchmark,
    *,
    acting_tenant: str,
    actor: BenchmarkActor,
    now: datetime | None = None,
    **changes: Any,
) -> Benchmark:
    """Apply mutable ATTRIBUTE changes to a benchmark definition in place (EV — one physical row),
    bump ``record_version``, emit ``REFERENCE.UPDATE`` (NO new lineage edge — the row retains its
    ORIGIN edge; the identity key code/source is NOT updatable). ``benchmark`` must already be
    tenant-resolved (via ``resolve_benchmark``)."""
    unknown = set(changes) - set(_UPDATABLE_BENCHMARK)
    if unknown:
        raise BenchmarkValueError(f"non-updatable benchmark attributes: {sorted(unknown)}")
    if not changes:
        return benchmark  # no-op: no version bump, no REFERENCE.UPDATE (review fold — audit LOW)
    if "benchmark_currency" in changes:
        # benchmark_currency is NOT NULL — reject an explicit null fail-closed (422), never let it
        # reach the DB constraint as an unmapped 500 (review fold — architect).
        if changes["benchmark_currency"] is None:
            raise BenchmarkValueError("benchmark_currency may not be set to null")
        resolve_currency(session, changes["benchmark_currency"], acting_tenant=acting_tenant)
    now = now or utcnow()
    before = {key: _json_safe(getattr(benchmark, key)) for key in changes}
    for key, value in changes.items():
        setattr(benchmark, key, value)
    benchmark.record_version = benchmark.record_version + 1
    session.flush()
    _emit(
        session,
        benchmark=benchmark,
        event_type=REFERENCE_UPDATE_EVENT,
        action="update",
        before_value=before,
        after_value={key: _json_safe(getattr(benchmark, key)) for key in changes},
        actor=actor,
        now=now,
    )
    return benchmark


# --- benchmark MEMBERSHIP (FR set-grained; MARKET.BENCHMARK_CONSTITUENT_* audit) ---


def _current_open_set(
    session: Session, *, acting_tenant: str, benchmark_id: str, effective_date: date
) -> list[BenchmarkConstituent]:
    """The constituent rows OPEN ON BOTH axes for a (benchmark, effective_date) — the current
    membership set. Tenant-predicated."""
    return list(
        session.execute(
            select(BenchmarkConstituent).where(
                BenchmarkConstituent.tenant_id == str(acting_tenant),
                BenchmarkConstituent.benchmark_id == str(benchmark_id),
                BenchmarkConstituent.effective_date == effective_date,
                BenchmarkConstituent.valid_to.is_(None),
                BenchmarkConstituent.system_to.is_(None),
            )
        )
        .scalars()
        .all()
    )


def _write_set(
    session: Session,
    *,
    benchmark: Benchmark,
    effective_date: date,
    constituents: list[ConstituentInput],
    valid_from: datetime,
    valid_to: datetime | None,
    system_from: datetime,
    record_version: int,
    prior_by_instrument: dict[str, BenchmarkConstituent],
    restatement_reason: str | None,
) -> list[BenchmarkConstituent]:
    """Insert one FR constituent row per supplied constituent (tenant_id server-stamped from the
    header; ``supersedes_id`` links the matching prior same-instrument row, else None)."""
    rows: list[BenchmarkConstituent] = []
    for constituent in constituents:
        prior = prior_by_instrument.get(str(constituent.instrument_id))
        row = BenchmarkConstituent(
            tenant_id=benchmark.tenant_id,
            benchmark_id=benchmark.id,
            instrument_id=str(constituent.instrument_id),
            effective_date=effective_date,
            weight=constituent.weight,
            constituent_currency=constituent.constituent_currency,
            valid_from=valid_from,
            valid_to=valid_to,
            system_from=system_from,
            system_to=None,
            restatement_reason=restatement_reason,
            supersedes_id=(prior.id if prior is not None else None),
            record_version=record_version,
        )
        if constituent.entity_id is not None:
            row.id = constituent.entity_id
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def capture_membership(
    session: Session,
    benchmark: Benchmark,
    *,
    effective_date: date,
    constituents: list[ConstituentInput],
    acting_tenant: str,
    actor: BenchmarkActor,
    valid_from: datetime | None = None,
    now: datetime | None = None,
) -> list[BenchmarkConstituent]:
    """Capture the first membership set for a (benchmark, effective_date) as ONE governed unit (FR
    rows + a VENDOR ORIGIN edge + ``MARKET.BENCHMARK_CONSTITUENT_CREATE`` + the DQ gate). The
    instruments/currencies are resolved BEFORE any write; weights captured verbatim. ``benchmark``
    must already be tenant-resolved (via ``resolve_benchmark``)."""
    _validate_constituents(constituents)
    _resolve_membership_refs(session, constituents, acting_tenant=acting_tenant)
    now = now or utcnow()
    rows = _write_set(
        session,
        benchmark=benchmark,
        effective_date=effective_date,
        constituents=constituents,
        valid_from=(valid_from or now),
        valid_to=None,
        system_from=now,
        record_version=1,
        prior_by_instrument={},
        restatement_reason=None,
    )
    _run_membership_dq_gate(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        benchmark=benchmark,
        constituents=constituents,
    )
    _origin_edge(session, benchmark=benchmark, actor=actor)
    _emit(
        session,
        benchmark=benchmark,
        event_type=MARKET_BENCHMARK_CONSTITUENT_CREATE_EVENT,
        action="create",
        after_value=_membership_summary(
            benchmark, effective_date=effective_date, constituent_count=len(rows)
        ),
        actor=actor,
        now=now,
    )
    return rows


def supersede_membership(
    session: Session,
    benchmark: Benchmark,
    *,
    effective_date: date,
    constituents: list[ConstituentInput],
    acting_tenant: str,
    actor: BenchmarkActor,
    effective_at: datetime,
    now: datetime | None = None,
) -> list[BenchmarkConstituent]:
    """Effective-dated (valid-time) re-capture of the membership for a (benchmark, effective_date):
    close ALL open rows' ``valid_to`` (``MARKET.BENCHMARK_CONSTITUENT_UPDATE``), then insert a FRESH
    set (``MARKET.BENCHMARK_CONSTITUENT_CREATE`` + its own ORIGIN edge + the DQ gate). The prior set
    is sourced via the tenant-predicated ``_current_open_set`` (never a caller-supplied id)."""
    _validate_constituents(constituents)
    _resolve_membership_refs(session, constituents, acting_tenant=acting_tenant)
    prior = _current_open_set(
        session,
        acting_tenant=acting_tenant,
        benchmark_id=benchmark.id,
        effective_date=effective_date,
    )
    if not prior:
        raise NoCurrentMembership(benchmark.id, effective_date)

    now = now or utcnow()
    for row in prior:  # CLOSE-FIRST (valid-time)
        row.valid_to = effective_at
    session.flush()
    _emit(
        session,
        benchmark=benchmark,
        event_type=MARKET_BENCHMARK_CONSTITUENT_UPDATE_EVENT,
        action="update",
        before_value=_membership_summary(
            benchmark, effective_date=effective_date, constituent_count=len(prior)
        ),
        after_value={"valid_to": _json_safe(effective_at)},
        actor=actor,
        now=now,
    )

    prior_by_instrument = {str(row.instrument_id): row for row in prior}
    next_version = max(row.record_version for row in prior) + 1
    rows = _write_set(
        session,
        benchmark=benchmark,
        effective_date=effective_date,
        constituents=constituents,
        valid_from=effective_at,
        valid_to=None,
        system_from=now,
        record_version=next_version,
        prior_by_instrument=prior_by_instrument,
        restatement_reason=None,
    )
    _run_membership_dq_gate(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        benchmark=benchmark,
        constituents=constituents,
    )
    _origin_edge(session, benchmark=benchmark, actor=actor)
    _emit(
        session,
        benchmark=benchmark,
        event_type=MARKET_BENCHMARK_CONSTITUENT_CREATE_EVENT,
        action="create",
        after_value=_membership_summary(
            benchmark, effective_date=effective_date, constituent_count=len(rows)
        ),
        actor=actor,
        now=now,
    )
    return rows


def correct_membership(
    session: Session,
    benchmark: Benchmark,
    *,
    effective_date: date,
    constituents: list[ConstituentInput],
    restatement_reason: str,
    acting_tenant: str,
    actor: BenchmarkActor,
    now: datetime | None = None,
) -> list[BenchmarkConstituent]:
    """As-known restatement (TR-08) of the membership for a (benchmark, effective_date): close ALL
    open rows' ``system_to`` (``MARKET.BENCHMARK_CONSTITUENT_UPDATE``), then insert a corrected set
    over the SAME valid period (``MARKET.BENCHMARK_CONSTITUENT_CORRECTION`` + its own ORIGIN edge +
    the DQ gate). The prior rows' CONTENT columns are NEVER mutated — only ``system_to``."""
    _validate_constituents(constituents)
    _resolve_membership_refs(session, constituents, acting_tenant=acting_tenant)
    prior = _current_open_set(
        session,
        acting_tenant=acting_tenant,
        benchmark_id=benchmark.id,
        effective_date=effective_date,
    )
    if not prior:
        raise NoCurrentMembership(benchmark.id, effective_date)

    now = now or utcnow()
    valid_from_prior = prior[0].valid_from  # the set shares one valid period (written together)
    valid_to_prior = prior[0].valid_to
    for row in prior:  # CLOSE-FIRST (system-time)
        row.system_to = now
    session.flush()
    _emit(
        session,
        benchmark=benchmark,
        event_type=MARKET_BENCHMARK_CONSTITUENT_UPDATE_EVENT,
        action="update",
        before_value=_membership_summary(
            benchmark, effective_date=effective_date, constituent_count=len(prior)
        ),
        after_value={"system_to": _json_safe(now)},
        actor=actor,
        now=now,
    )

    prior_by_instrument = {str(row.instrument_id): row for row in prior}
    next_version = max(row.record_version for row in prior) + 1
    rows = _write_set(
        session,
        benchmark=benchmark,
        effective_date=effective_date,
        constituents=constituents,
        valid_from=valid_from_prior,  # SAME valid period (as-known correction)
        valid_to=valid_to_prior,
        system_from=now,
        record_version=next_version,
        prior_by_instrument=prior_by_instrument,
        restatement_reason=restatement_reason,
    )
    _run_membership_dq_gate(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        benchmark=benchmark,
        constituents=constituents,
    )
    _origin_edge(session, benchmark=benchmark, actor=actor)
    _emit(
        session,
        benchmark=benchmark,
        event_type=MARKET_BENCHMARK_CONSTITUENT_CORRECTION_EVENT,
        action="correct",
        after_value=_membership_summary(
            benchmark, effective_date=effective_date, constituent_count=len(rows)
        ),
        actor=actor,
        justification=restatement_reason,
        now=now,
    )
    return rows


def reconstruct_membership_as_of(
    session: Session,
    *,
    acting_tenant: str,
    benchmark_id: str,
    effective_date: date,
    valid_at: datetime,
    known_at: datetime | None = None,
) -> list[BenchmarkConstituent]:
    """As-of read: the membership set for (benchmark, effective_date) true at ``valid_at``
    as-known-at ``known_at`` (``known_at`` defaults to now -> the current view), ordered by
    instrument. Captured membership only — NO active weight / return / risk."""
    known = known_at or utcnow()
    return list(
        session.execute(
            select(BenchmarkConstituent)
            .where(
                BenchmarkConstituent.tenant_id == str(acting_tenant),
                BenchmarkConstituent.benchmark_id == str(benchmark_id),
                BenchmarkConstituent.effective_date == effective_date,
                BenchmarkConstituent.valid_from <= valid_at,
                or_(
                    BenchmarkConstituent.valid_to.is_(None),
                    BenchmarkConstituent.valid_to > valid_at,
                ),
                BenchmarkConstituent.system_from <= known,
                or_(
                    BenchmarkConstituent.system_to.is_(None),
                    BenchmarkConstituent.system_to > known,
                ),
            )
            .order_by(BenchmarkConstituent.instrument_id)
        )
        .scalars()
        .all()
    )


def list_benchmarks(session: Session, *, acting_tenant: str) -> list[Benchmark]:
    """All current benchmark definitions for the acting tenant (ordered by code/source)."""
    return list(
        session.execute(
            select(Benchmark)
            .where(Benchmark.tenant_id == str(acting_tenant))
            .order_by(Benchmark.benchmark_code, Benchmark.benchmark_source)
        )
        .scalars()
        .all()
    )
