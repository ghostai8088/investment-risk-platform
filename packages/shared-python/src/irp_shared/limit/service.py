"""Limit/breach service (LIM-1) — the metric map + guards, the breach predicate, the evaluator,
and the audited limit CRUD.

Layers:
- **The hardcoded metric map** (``_METRIC_MAP``) — the ONLY thing that disarms the unit landmine
  (OD-C): a ``(run_type, metric_type)`` resolves to a FIXED result column + unit + benchmark-need,
  never a user column. The evaluator asserts ``spec.unit == limit.threshold_unit`` fail-closed.
- **The breach predicate** (``_breaches``) — ``breach_direction`` names the BREACH condition
  directly (ABOVE ⟺ observed > threshold; BELOW ⟺ observed < threshold; strict boundary — OD-D).
- **The evaluator** (``evaluate_limit``) — discovery via ``calc/reads`` over ``calculation_run``
  (NOT ``scheduled_run`` — so MANUAL runs are limit-checked too, Fable demand #1); idempotent on
  ``(limit_id, calculation_run_id)``; appends a SELF-DESCRIBING ``breach`` + ``BREACH.DETECT``.
- **Audited CRUD** (``create_limit``/``update_limit``) — EV in place; ``LIMIT.DEFINE``/
  ``LIMIT.CHANGE`` emitted caller-side to the FROZEN ``record_event``. Identity frozen (OD-I).
- **``limit_health``** (OD-L) — a read distinguishing IN_APPETITE / NEVER_EVALUABLE / BREACHED
  so an un-evaluable limit is never silently green.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from irp_shared.audit.actions import (
    ACTION_CREATE,
    ACTION_RECORD,
    ACTION_STATUS_CHANGE,
    ACTION_UPDATE,
)
from irp_shared.audit.payload import json_safe
from irp_shared.audit.service import record_event
from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION
from irp_shared.concentration.models import (
    CONCENTRATION_DIMENSION_KINDS,
    CONCENTRATION_METRIC_TYPES,
    DENOMINATOR_BASES,
    DIMENSION_KIND_ISSUER,
    METRIC_TYPE_SHARE,
    ROW_KIND_DETAIL,
)
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_BELOW,
    BREACH_DETECT_EVENT,
    BREACH_DIRECTIONS,
    BREACH_STATUS_DETECTED,
    ENTITY_BREACH,
    ENTITY_LIMIT_DEFINITION,
    LIMIT_APPROVE_EVENT,
    LIMIT_CHANGE_EVENT,
    LIMIT_DEFINE_EVENT,
    LIMIT_KIND_HARD,
    LIMIT_KINDS,
    LIMIT_STATUS_ACTIVE,
    LIMIT_STATUS_DRAFT,
    LIMIT_STATUS_SUSPENDED,
    LIMIT_STATUSES,
    SOURCE_MODULE_LIMIT,
    THRESHOLD_UNIT_CURRENCY,
    THRESHOLD_UNIT_FRACTION,
    LimitActor,
)
from irp_shared.limit.models import Breach, LimitDefinition
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.risk.active_risk_service import latest_active_risk_for_portfolio
from irp_shared.risk.events import (
    METRIC_TYPE_ES_HISTORICAL,
    METRIC_TYPE_ES_PARAMETRIC,
    METRIC_TYPE_TRACKING_ERROR,
    METRIC_TYPE_VAR_HISTORICAL,
    METRIC_TYPE_VAR_PARAMETRIC,
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    RUN_TYPE_ACTIVE_RISK,
    RUN_TYPE_VAR,
)
from irp_shared.risk.var_service import latest_var_for_portfolio

#: The audit ``entity_type`` tags (re-exported from events for the emit helpers).
_ENTITY_LIMIT = ENTITY_LIMIT_DEFINITION
_ENTITY_BREACH = ENTITY_BREACH


class LimitError(ValueError):
    """A limit config or evaluation precondition failure (fail-closed)."""


class LimitSodError(LimitError):
    """A person-level SoD violation on a limit approval (the approver is the draft's own maker —
    SOD-02 / REQ-LIM-001; the MG-2 ``BreachSodError`` analog applied to a scalar maker)."""


class DuplicateLimitError(LimitError):
    """A limit with the same ``(tenant, code)`` already exists (the pre-check twin of the
    ``uq_limit_definition_tenant_code`` race — API-2 maps both to a uniform 409)."""


class LimitStateError(LimitError):
    """An illegal lifecycle transition from the current state (approve a non-DRAFT; set/clear DRAFT
    via update; the double-approve loser) — a STATE CONFLICT, not a validation error (API-2 maps it
    to 409, uniform with the SoD conflict; verifier MED-1)."""


def _threshold(value: Decimal | str) -> Decimal:
    """Parse a threshold to Decimal, fail-closed to a clean ``LimitError`` (422 at the API) on a
    malformed string — never a raw ``InvalidOperation`` (a 500). Accepts the API's string input."""
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise LimitError(f"threshold_value {value!r} is not a valid decimal") from None


@dataclass(frozen=True)
class MetricSpec:
    """The FIXED (result column, unit, benchmark-need) a ``(run_type, metric_type)`` thresholds."""

    result_attr: str
    unit: str
    requires_benchmark: bool


#: The HARDCODED metric map (OD-C) — the single defense that disarms the unit landmine. NOT
#: user-choosable: a ``(run_type, metric_type)`` maps to exactly ONE column + unit. VaR flavors
#: (incl. ES_* rows, whose ``var_value`` holds the ES) are CURRENCY; tracking error is a FRACTION.
_METRIC_MAP: dict[tuple[str, str], MetricSpec] = {
    (RUN_TYPE_VAR, METRIC_TYPE_VAR_PARAMETRIC): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_VAR_HISTORICAL): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_VAR_PARAMETRIC_TOTAL): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_VAR_PARAMETRIC_UNIFIED): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_ES_PARAMETRIC): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_ES_HISTORICAL): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_ACTIVE_RISK, METRIC_TYPE_TRACKING_ERROR): MetricSpec(
        "te_value", THRESHOLD_UNIT_FRACTION, True
    ),
    # LIM-2 registers CON-1's family (the OQ-CON-1-15 deferral discharged). DERIVED from
    # ``CONCENTRATION_METRIC_TYPES`` rather than retyped, so the map can never drift from the
    # metric vocabulary it thresholds; `test_metric_map_concentration_census` then pins the
    # EXPECTED ten names literally, so adding a metric to CON-1 fails HERE and forces a decision
    # about whether it should be limit-bindable, instead of silently becoming so.
    #
    # Every concentration metric is a dimensionless ratio in [0,1] — `max_share` and `cr_n` are
    # sums of fractional shares, `hhi` a sum of their squares — so FRACTION covers the family and
    # no threshold unit is minted. DETAIL rows carry the value in ``share_invested_long`` and
    # SUMMARY rows in ``metric_value``; that per-metric split is exactly what MetricSpec is for.
    **{
        (RUN_TYPE_CONCENTRATION, metric): MetricSpec(
            "share_invested_long" if metric == METRIC_TYPE_SHARE else "metric_value",
            THRESHOLD_UNIT_FRACTION,
            False,
        )
        for metric in CONCENTRATION_METRIC_TYPES
    },
}

#: In-place editable head attributes (OD-I): the config knobs. The IDENTITY fields
#: (``target_run_type``/``metric_type``/``scope_portfolio_id``/``benchmark_id``/``threshold_unit``)
#: are FROZEN — a re-target is a NEW limit (keeps a breach's echo meaningful).
_UPDATABLE = ("name", "threshold_value", "limit_kind", "breach_direction", "status")

#: The MATERIAL governing fields (MG-3, OQ-MG-3-5=A): a real change to any of these on a
#: previously-approved limit (ACTIVE **or** SUSPENDED) re-enters the maker-checker gate (the limit
#: returns to DRAFT for a non-maker re-approval — REQ-LIM-001 "limit CHANGES are maker-checked").
#: ``name`` is cosmetic and does NOT trigger it; ``status`` is the lifecycle toggle
#: (suspend/resume), which may not be combined with a governing change in one edit (ambiguous).
_GOVERNING_FIELDS = ("threshold_value", "limit_kind", "breach_direction")


def _governing_value_changed(limit: LimitDefinition, changes: dict[str, Any]) -> bool:
    """True iff a governing field's NEW value actually differs from the current one — presence in
    ``changes`` is not enough (a no-op re-save of the same value must not demote a live limit)."""
    for key in _GOVERNING_FIELDS:
        if key not in changes:
            continue
        if key == "threshold_value":
            if Decimal(changes[key]) != Decimal(getattr(limit, key)):
                return True
        elif changes[key] != getattr(limit, key):
            return True
    return False


# --- breach predicate ---------------------------------------------------------------------
def _breaches(observed: Decimal, threshold: Decimal, breach_direction: str) -> bool:
    """The safety-critical predicate (OD-D). ``breach_direction`` names the BREACH condition; strict
    boundary (``observed == threshold`` is COMPLIANT)."""
    if breach_direction == BREACH_ABOVE:
        return observed > threshold
    if breach_direction == BREACH_BELOW:
        return observed < threshold
    raise LimitError(f"unknown breach_direction {breach_direction!r}")


# --- discovery ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Resolution:
    """What a family resolver found — richer than the ``(run_id, value)`` tuple it replaces.

    Three outcomes are now distinguishable, and conflating any two of them was a real defect:

    - **resolved** (``run_id`` + ``observed``): compare it.
    - **nothing to evaluate** (all fields None): no COMPLETED run covers this selector — the
      metric-cold / NEVER_EVALUABLE case.
    - **REFUSED** (``refusal`` set): a run WAS found and the resolver declined to compare against
      it. Distinct from "nothing found" on purpose: a refusal means a governed number exists and
      is being deliberately not-thresholded, which an operator must see rather than read as a cold
      metric.

    ``resolved_scheme_id`` carries the taxonomy VERSION the resolved run actually used, so
    ``limit_health`` can report drift against the limit's ``authored_scheme_id`` (OQ-LIM-2-1=C).
    """

    run_id: str | None = None
    observed: Decimal | None = None
    resolved_scheme_id: str | None = None
    refusal: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.run_id is not None and self.observed is not None and self.refusal is None


def _resolve_var(session: Session, limit: LimitDefinition, spec: MetricSpec) -> Resolution:
    rows = latest_var_for_portfolio(
        session,
        acting_tenant=limit.tenant_id,
        portfolio_id=limit.scope_portfolio_id,
        metric_type=limit.metric_type,
    )
    return _first_matching(rows, limit, spec)


def _resolve_active_risk(session: Session, limit: LimitDefinition, spec: MetricSpec) -> Resolution:
    rows = latest_active_risk_for_portfolio(
        session,
        acting_tenant=limit.tenant_id,
        portfolio_id=limit.scope_portfolio_id,
        benchmark_id=limit.benchmark_id,
    )
    return _first_matching(rows, limit, spec)


def _first_matching(rows: list[Any], limit: LimitDefinition, spec: MetricSpec) -> Resolution:
    """The shared body of the two non-dimensional families: one row per metric per run."""
    matching = [r for r in rows if r.metric_type == limit.metric_type]
    if not matching:
        return Resolution()
    row = matching[0]
    return Resolution(
        run_id=str(row.calculation_run_id), observed=Decimal(getattr(row, spec.result_attr))
    )


def _resolve_concentration(
    session: Session, limit: LimitDefinition, spec: MetricSpec
) -> Resolution:
    """Resolve a concentration limit against the latest COMPLETED run for its scope.

    Two behaviors here are load-bearing and neither is obvious:

    **1. The EVALUATION-TIME half of the basis discipline (OQ-LIM-2-4).** The definition-time CHECK
    only proves the declared basis is a known value. This compares it to the basis the resolved
    number was actually computed on, and REFUSES rather than thresholds on a mismatch. With one
    value in the v1 vocabulary this cannot currently fire — which is precisely the shape CON-1
    shipped as a structurally-unfireable guard and had to reimplement, so it is written against
    the ROW rather than against the vocabulary, and its test forces the mismatch by writing a row
    with a different basis directly. The day a NAV basis is added, this is what stops an
    INVESTED_LONG threshold from silently adjudicating a NAV-denominated share.

    **2. A named bucket with no row resolves to ZERO, not to "nothing found".** If the run covers
    the dimension, the kernel emitted a row for every bucket carrying long exposure; a missing
    bucket therefore means the book holds none of it. That is an OBSERVED zero, not an absent
    number. Reporting NEVER_EVALUABLE instead would make "tech <= 20%" cry wolf on precisely the
    healthiest possible book — and a control that alarms when nothing is wrong gets ignored, which
    is the same end state as one that stays silent when something is. The distinction the resolver
    still refuses to guess: if the run covers the dimension NOT AT ALL, nothing is resolved.
    """
    from irp_shared.concentration.service import latest_concentration

    rows = latest_concentration(
        session,
        acting_tenant=limit.tenant_id,
        portfolio_id=limit.scope_portfolio_id,
        # The EVALUATION path, deliberately unfenced: the issuer split is a READ-SURFACE control
        # over what a human caller receives, not a restriction on what the tick may adjudicate. A
        # fenced evaluation would silently stop enforcing every issuer limit.
        include_issuer_detail=True,
    )
    in_dimension = [r for r in rows if r.dimension_kind == limit.dimension_kind]
    if not in_dimension:
        return Resolution()  # no COMPLETED run covers this dimension — genuinely nothing to compare

    def _refused_or(row: Any, observed: Decimal) -> Resolution:
        if row.denominator_basis != limit.denominator_basis:
            return Resolution(
                refusal=(
                    f"basis mismatch: the limit was written against "
                    f"{limit.denominator_basis!r} but run {row.calculation_run_id} computed "
                    f"{row.denominator_basis!r} — refusing to compare"
                )
            )
        return Resolution(
            run_id=str(row.calculation_run_id),
            observed=observed,
            resolved_scheme_id=str(row.scheme_id) if row.scheme_id else None,
        )

    if limit.bucket_code is None:
        # A run-level (summary-metric) limit: exactly one row per metric per run.
        summary = [r for r in in_dimension if r.metric_type == limit.metric_type]
        if not summary:
            return Resolution()
        return _refused_or(summary[0], Decimal(getattr(summary[0], spec.result_attr)))

    named = [
        r
        for r in in_dimension
        if r.row_kind == ROW_KIND_DETAIL and r.bucket_code == limit.bucket_code
    ]
    if named:
        return _refused_or(named[0], Decimal(getattr(named[0], spec.result_attr)))
    # See (2) above: the dimension WAS computed and this bucket carries no long exposure.
    return _refused_or(in_dimension[0], Decimal(0))


@dataclass(frozen=True)
class LimitFamily:
    """One thresholdable family (OQ-LIM-2-6), mirroring SCH-2's ``ScheduledFamily``.

    Declares ONLY what has a consumer. ``requires_benchmark`` deliberately stays on ``MetricSpec``
    where it already lives — it is a per-METRIC property, not a per-family one, and SCH-2 removed
    ``produces_run_on_failure`` on the finding that *a false declaration with no consumer is worse
    than no declaration*.
    """

    target_run_type: str
    resolve: Callable[[Session, LimitDefinition, MetricSpec], Resolution]
    #: The family's metrics are selected by a dimension/bucket, so a limit MUST carry one.
    requires_dimension: bool
    #: The family's numbers carry a ``denominator_basis`` a limit must declare and match.
    requires_basis: bool


#: The dispatch registry. Before LIM-2 this was a two-branch ``if/else`` whose ``else`` asserted
#: "the only other admitted family" in a COMMENT — while ``_METRIC_MAP``, edited in a different
#: place, is what actually admits families. Registering concentration there without touching the
#: dispatch would have routed it into the active-risk resolver, which accepts ``benchmark_id=None``
#: happily and returns no matching rows: a SILENT false NEVER_EVALUABLE, not a crash.
#: ``test_every_metric_map_family_has_a_resolver`` makes that divergence impossible by set equality.
LIMIT_FAMILY_REGISTRY: dict[str, LimitFamily] = {
    RUN_TYPE_VAR: LimitFamily(RUN_TYPE_VAR, _resolve_var, False, False),
    RUN_TYPE_ACTIVE_RISK: LimitFamily(RUN_TYPE_ACTIVE_RISK, _resolve_active_risk, False, False),
    RUN_TYPE_CONCENTRATION: LimitFamily(RUN_TYPE_CONCENTRATION, _resolve_concentration, True, True),
}

#: DERIVED from the registry — never a hand-maintained second list (the SCH-2 pattern).
LIMITABLE_RUN_TYPES = frozenset(LIMIT_FAMILY_REGISTRY)


def _resolve_latest(session: Session, limit: LimitDefinition) -> Resolution:
    """Resolve the latest COMPLETED result for the limit's selector. Discovery is
    ``calculation_run``-driven (demand #1), so a MANUAL run is limit-checked like a scheduled
    one — which is load-bearing for concentration, whose family is not schedulable (OQ-CON-1-17)."""
    spec = _spec_for(limit)
    if spec.unit != limit.threshold_unit:
        # Defense-in-depth (identity is frozen, so the create-time guard normally holds): a
        # CURRENCY threshold must NEVER be compared against a FRACTION metric (or vice versa).
        raise LimitError(
            f"unit drift: threshold_unit {limit.threshold_unit!r} != metric unit {spec.unit!r}"
        )
    family = LIMIT_FAMILY_REGISTRY.get(limit.target_run_type)
    if family is None:
        # FAIL-CLOSED, replacing the comment that used to stand here. Defense in depth behind the
        # set-equality census: if both were ever wrong at once, refusing beats adjudicating a
        # governed threshold through some other family's resolver.
        raise LimitError(
            f"no resolver is registered for family {limit.target_run_type!r} — refusing to "
            "evaluate (a registered metric with no resolver is a configuration error)"
        )
    return family.resolve(session, limit, spec)


def _spec_for(limit: LimitDefinition) -> MetricSpec:
    spec = _METRIC_MAP.get((limit.target_run_type, limit.metric_type))
    if spec is None:
        raise LimitError(
            f"({limit.target_run_type}, {limit.metric_type}) is not a schedulable v1 metric"
        )
    return spec


# --- evaluation ---------------------------------------------------------------------------
def select_active_limits(session: Session, *, acting_tenant: str) -> list[LimitDefinition]:
    """Tenant-scoped: ACTIVE limits (explicit tenant predicate + RLS — belt-and-suspenders).
    Ordered by id: a DETERMINISTIC cross-tick iteration order so two concurrent same-tenant
    ticks acquire their breach-insert unique-index entries in the same sequence (4-finder fold —
    divergent heap-scan order could cycle a uq_breach_limit_run tuple-wait against the audit
    advisory lock; benign/self-healing, but determinism removes it)."""
    return list(
        session.execute(
            select(LimitDefinition)
            .where(
                LimitDefinition.status == LIMIT_STATUS_ACTIVE,
                LimitDefinition.tenant_id == str(acting_tenant),
            )
            .order_by(LimitDefinition.id)
        ).scalars()
    )


# --- reads (API-2) ------------------------------------------------------------------------
def list_limits(
    session: Session,
    *,
    acting_tenant: str,
    status: str | None = None,
    include_issuer_detail: bool = False,
) -> list[LimitDefinition]:
    """Tenant-scoped limit list, optionally filtered by status (``status=DRAFT`` = the approval
    queue). Explicit tenant predicate atop RLS (belt-and-suspenders, the ``select_active_limits``
    pattern). Ordered by code for a stable read surface.

    **The issuer-identity split is STRUCTURAL here, not a router courtesy (OQ-LIM-2-3=B).** With
    ``include_issuer_detail=False`` — the plain ``limit.view`` shape — limits naming an ISSUER are
    excluded AT THE QUERY. This extends CON-1's fence to a surface its own scope did not cover:
    ``auditor_3l`` holds ``limit.view`` and ``breach.view`` but is DELIBERATELY excluded from
    ``concentration.issuer.view``, so a named-issuer limit would otherwise route fenced identity
    to exactly the role the fence exists to exclude. The predicate is ``issuer_id IS NOT NULL``,
    which 0058's ``issuer_only`` CHECK makes reliable: identity cannot exist on any other row.
    """
    if status is not None and status not in LIMIT_STATUSES:
        raise LimitError(f"status {status!r} is invalid")
    stmt = select(LimitDefinition).where(LimitDefinition.tenant_id == str(acting_tenant))
    if status is not None:
        stmt = stmt.where(LimitDefinition.status == status)
    if not include_issuer_detail:
        stmt = stmt.where(LimitDefinition.issuer_id.is_(None))
    return list(session.execute(stmt.order_by(LimitDefinition.code)).scalars())


def get_limit(
    session: Session,
    *,
    acting_tenant: str,
    limit_id: str,
    include_issuer_detail: bool = False,
) -> LimitDefinition | None:
    """Read ONE limit by id, tenant-filtered atop RLS (the P3-5 doctrine: PG FK checks bypass RLS,
    so an explicit tenant predicate is load-bearing for a caller-supplied id). Returns None on a
    missing/cross-tenant id (the API maps that to an indistinguishable 404). Doubles as the
    load-for-mutation step (``update_limit``/``approve_limit`` take the object, not an id).

    The issuer fence applies here too and returns None — the SAME answer as a missing id, so a
    caller without ``concentration.issuer.view`` cannot distinguish "no such limit" from "a limit
    exists and names an issuer you may not see". A 403 here would itself be the disclosure.

    ``include_issuer_detail=True`` is REQUIRED for the mutation paths: ``update_limit`` and
    ``approve_limit`` take the loaded object, and a fenced load would silently make every
    named-issuer limit unapprovable and uneditable. The router passes the caller's entitlement for
    reads and ``True`` for the maker/checker verbs, which are separately gated on
    ``limit.manage``/``limit.approve``.
    """
    stmt = select(LimitDefinition).where(
        LimitDefinition.id == str(limit_id),
        LimitDefinition.tenant_id == str(acting_tenant),
    )
    if not include_issuer_detail:
        stmt = stmt.where(LimitDefinition.issuer_id.is_(None))
    return session.execute(stmt).scalar_one_or_none()


def evaluate_limit(session: Session, limit: LimitDefinition, now: datetime) -> Breach | None:
    """Evaluate ONE ACTIVE limit against its latest matching COMPLETED run; append a SELF-DESCRIBING
    ``breach`` (+ ``BREACH.DETECT``) if it breaches AND has not already been recorded for that run.
    Idempotent on ``(limit_id, calculation_run_id)`` (the unique constraint is the backstop)."""
    if limit.status != LIMIT_STATUS_ACTIVE:
        # Fail-closed backstop (MG-3): only an APPROVED, ACTIVE limit is ever evaluated. Production
        # callers already pre-filter via `select_active_limits`, but a DRAFT/SUSPENDED limit handed
        # here directly must NOT record a breach against an un-approved/suspended config.
        return None
    resolution = _resolve_latest(session, limit)
    if not resolution.is_resolved:
        # Covers BOTH "no matching COMPLETED run" and a REFUSAL (e.g. a basis mismatch). A refusal
        # must never fall through to a comparison: writing a breach off a number the resolver
        # declined to threshold is the false-breach harm into an append-only, non-withdrawable
        # lifecycle that the CON-1 descope exists to prevent. `limit_health` surfaces the refusal
        # so it is visible rather than silently indistinguishable from a cold metric.
        return None
    run_id = resolution.run_id
    observed = resolution.observed
    assert run_id is not None and observed is not None  # narrowed by is_resolved
    if not _breaches(observed, Decimal(limit.threshold_value), limit.breach_direction):
        return None  # within appetite

    existing = session.execute(
        select(Breach).where(
            Breach.limit_definition_id == limit.id,
            Breach.calculation_run_id == run_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing  # already recorded this (limit, run) — idempotent

    breach = Breach(
        tenant_id=limit.tenant_id,
        limit_definition_id=limit.id,
        calculation_run_id=run_id,
        detected_at=now,
        target_run_type=limit.target_run_type,
        metric_type=limit.metric_type,
        benchmark_id=limit.benchmark_id,
        observed_value=observed,
        threshold_value=Decimal(limit.threshold_value),
        threshold_unit=limit.threshold_unit,
        breach_direction=limit.breach_direction,
        limit_kind=limit.limit_kind,
        severity=limit.limit_kind,
        status=BREACH_STATUS_DETECTED,
        # LIM-2 echoes. `resolved_scheme_id` is what the EVALUATED run used, deliberately not the
        # limit's `authored_scheme_id`: the pair makes a scheme-drift breach provable from the two
        # rows alone, months later, rather than only flagged live in `limit_health`.
        dimension_kind=limit.dimension_kind,
        bucket_code=limit.bucket_code,
        issuer_id=limit.issuer_id,
        scheme_family=limit.scheme_family,
        resolved_scheme_id=resolution.resolved_scheme_id,
        denominator_basis=limit.denominator_basis,
        scope_portfolio_id=limit.scope_portfolio_id,
    )
    session.add(breach)
    session.flush()
    _record_breach_event(session, breach=breach, actor_id=f"limit-eval:{limit.id}")
    return breach


# --- limit CRUD ---------------------------------------------------------------------------
def _require_human(actor: LimitActor) -> None:
    """BR-15: AI/automation is NEVER an approver — a sign-off is a human act (MG-2/VW-1 guard)."""
    if actor.actor_type != "user":
        raise LimitError("a limit approval requires a human actor (BR-15)")


def _lock_limit(session: Session, limit_id: str, tenant_id: str) -> LimitDefinition:
    """Re-resolve the limit tenant-filtered AND take a row lock (linearizability backstop for the
    approve gate). The tenant filter is load-bearing (PG FK checks bypass RLS — the P3-5 doctrine).

    ``populate_existing`` is REQUIRED: ``LimitDefinition`` is EV and its ``status`` lives ON the row
    (unlike MG-2's recency-derived breach state), so an already-mapped instance would return a STALE
    ``status`` and defeat the lock's from-state check → a double-approve race. Refresh under lock.
    """
    limit = session.execute(
        select(LimitDefinition)
        .where(LimitDefinition.id == limit_id, LimitDefinition.tenant_id == tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if limit is None:
        raise LimitError(f"limit {limit_id} not found in tenant {tenant_id}")
    return limit


def _validate_dimensional_config(
    *,
    target_run_type: str,
    metric_type: str,
    dimension_kind: str | None,
    bucket_code: str | None,
    issuer_id: str | None,
    scheme_family: str | None,
    authored_scheme_id: str | None,
    denominator_basis: str | None,
) -> None:
    """The dimensional selector's definition-time rules (LIM-2).

    These MIRROR migration 0058's CHECK constraints rather than replacing them: the DB is the
    engine that cannot be bypassed, and this layer exists to turn a 23514 into a legible 422 for
    the maker. Two rules here have NO CHECK counterpart, because a CHECK cannot express them:
    the metric-vs-dimension agreement, and the issuer bucket_code identity.
    """
    family = LIMIT_FAMILY_REGISTRY.get(target_run_type)
    dimensional = family is not None and family.requires_dimension
    if not dimensional:
        stray = {
            "dimension_kind": dimension_kind,
            "bucket_code": bucket_code,
            "issuer_id": issuer_id,
            "scheme_family": scheme_family,
            "authored_scheme_id": authored_scheme_id,
            "denominator_basis": denominator_basis,
        }
        supplied = sorted(k for k, v in stray.items() if v is not None)
        if supplied:
            raise LimitError(
                f"{target_run_type} is not a dimensional family; it does not take {supplied}"
            )
        return

    if dimension_kind not in CONCENTRATION_DIMENSION_KINDS:
        raise LimitError(
            f"dimension_kind {dimension_kind!r} is invalid for {target_run_type} "
            f"(expected one of {sorted(CONCENTRATION_DIMENSION_KINDS)})"
        )
    if denominator_basis not in DENOMINATOR_BASES:
        # The DEFINITION-TIME half of the basis discipline: this is what refuses a
        # regulatory-shaped threshold today. No NAV/total-assets denominator is computable on this
        # schema, so a limit declaring one cannot be written at all (CON-1 descope).
        raise LimitError(
            f"denominator_basis {denominator_basis!r} is not a computable basis "
            f"(expected one of {sorted(DENOMINATOR_BASES)}); a threshold written against a "
            "denominator this platform cannot compute is refused rather than approximated"
        )

    is_issuer = dimension_kind == DIMENSION_KIND_ISSUER
    if is_issuer and (scheme_family or authored_scheme_id):
        raise LimitError("the ISSUER dimension carries no classification scheme")
    if not is_issuer and not scheme_family:
        raise LimitError(f"dimension {dimension_kind} requires a scheme_family")
    if issuer_id and not is_issuer:
        # The DISCLOSURE fence at the maker boundary (0058's `issuer_only` CHECK is the engine).
        raise LimitError("issuer_id may only be set on an ISSUER-dimension limit")

    # No CHECK counterpart #1: the summary metric names ENCODE their dimension, so a limit pairing
    # HHI_SECTOR_INDUSTRY with dimension ISSUER would resolve nothing and read as a permanently
    # cold metric. Fail closed at definition instead of shipping a limit that can never fire.
    if metric_type != METRIC_TYPE_SHARE and not metric_type.endswith(str(dimension_kind)):
        raise LimitError(
            f"metric {metric_type} does not belong to dimension {dimension_kind} — the summary "
            "metric names encode their own dimension"
        )
    if metric_type == METRIC_TYPE_SHARE and not bucket_code:
        raise LimitError("a SHARE limit thresholds a NAMED bucket and requires bucket_code")
    if metric_type != METRIC_TYPE_SHARE and bucket_code:
        raise LimitError(
            f"{metric_type} is a RUN-LEVEL metric and does not take a bucket_code "
            "(a named-bucket limit uses metric_type=SHARE)"
        )
    # No CHECK counterpart #2: CON-1's service invariant is `bucket_code == str(issuer_id)` on
    # ISSUER detail rows; a cross-column cast CHECK is not portable to the SQLite tier. Without
    # this, a named-issuer limit could carry a bucket_code that resolves a DIFFERENT issuer's row.
    if is_issuer and bucket_code and str(issuer_id) != str(bucket_code):
        raise LimitError("an ISSUER limit's bucket_code is the issuer id; it must equal issuer_id")


def _validate_config(
    *,
    target_run_type: str,
    metric_type: str,
    benchmark_id: str | None,
    threshold_unit: str,
    threshold_value: Decimal | str,
    breach_direction: str,
    limit_kind: str,
    status: str,
    dimension_kind: str | None = None,
    bucket_code: str | None = None,
    issuer_id: str | None = None,
    scheme_family: str | None = None,
    authored_scheme_id: str | None = None,
    denominator_basis: str | None = None,
) -> None:
    spec = _METRIC_MAP.get((target_run_type, metric_type))
    if spec is None:
        raise LimitError(f"({target_run_type}, {metric_type}) is not a v1 metric selector")
    _validate_dimensional_config(
        target_run_type=target_run_type,
        metric_type=metric_type,
        dimension_kind=dimension_kind,
        bucket_code=bucket_code,
        issuer_id=issuer_id,
        scheme_family=scheme_family,
        authored_scheme_id=authored_scheme_id,
        denominator_basis=denominator_basis,
    )
    if threshold_unit != spec.unit:
        raise LimitError(
            f"threshold_unit {threshold_unit!r} != the {metric_type} metric unit {spec.unit!r}"
        )
    if spec.requires_benchmark and not benchmark_id:
        raise LimitError(f"metric {metric_type} requires a benchmark_id")
    if not spec.requires_benchmark and benchmark_id:
        raise LimitError(f"metric {metric_type} does not take a benchmark_id")
    if breach_direction not in BREACH_DIRECTIONS:
        raise LimitError(f"breach_direction {breach_direction!r} is invalid")
    if limit_kind not in LIMIT_KINDS:
        raise LimitError(f"limit_kind {limit_kind!r} is invalid")
    if status not in LIMIT_STATUSES:
        raise LimitError(f"status {status!r} is invalid")
    if _threshold(threshold_value) <= 0:
        raise LimitError("threshold_value must be positive")


def create_limit(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    target_run_type: str,
    metric_type: str,
    scope_portfolio_id: str,
    threshold_value: Decimal | str,
    threshold_unit: str,
    breach_direction: str,
    limit_kind: str,
    actor: LimitActor,
    benchmark_id: str | None = None,
    dimension_kind: str | None = None,
    bucket_code: str | None = None,
    issuer_id: str | None = None,
    scheme_family: str | None = None,
    authored_scheme_id: str | None = None,
    denominator_basis: str | None = None,
) -> LimitDefinition:
    """Create a limit (2L-maker function); emit ``LIMIT.DEFINE`` (governed R-07).

    MG-3: a new limit is ALWAYS born ``DRAFT`` (never immediately ACTIVE) and is NOT evaluated until
    ``approve_limit`` — the maker-checker gate (REQ-LIM-001/BX-SOD). There is deliberately no public
    ``status=`` override: an ACTIVE-on-create seam would let the maker self-activate, the symmetric
    twin of the ``update_limit`` DRAFT bypass. ``created_by`` records the drafter for the SoD.
    """
    _validate_config(
        target_run_type=target_run_type,
        metric_type=metric_type,
        benchmark_id=benchmark_id,
        threshold_unit=threshold_unit,
        threshold_value=threshold_value,
        breach_direction=breach_direction,
        limit_kind=limit_kind,
        status=LIMIT_STATUS_DRAFT,
        dimension_kind=dimension_kind,
        bucket_code=bucket_code,
        issuer_id=issuer_id,
        scheme_family=scheme_family,
        authored_scheme_id=authored_scheme_id,
        denominator_basis=denominator_basis,
    )
    # Re-resolve the FK targets tenant-filtered BEFORE the write (the P3-5 doctrine — PG FK checks
    # BYPASS RLS, so a caller-supplied FOREIGN scope/benchmark id must be refused, not stamped).
    assert_portfolio_in_tenant(
        session, str(scope_portfolio_id), acting_tenant=str(tenant_id), error=LimitError
    )
    if benchmark_id and (
        # A tenant-filtered existence check via raw SQL — keeps ``limit`` off the marketdata import
        # fence (marketdata is a leaf) while still refusing a FOREIGN benchmark_id (the P3-5 guard).
        session.execute(
            text("SELECT 1 FROM benchmark WHERE id = :id AND tenant_id = :t"),
            {"id": str(benchmark_id), "t": str(tenant_id)},
        ).first()
        is None
    ):
        raise LimitError(f"benchmark {benchmark_id} is not visible in the tenant")
    if issuer_id and (
        # The same P3-5 guard for the issuer FK: PG referential checks BYPASS RLS, so a
        # caller-supplied FOREIGN issuer id would otherwise be accepted and stamped onto a governed
        # limit — and here that is a cross-tenant identity DISCLOSURE, not merely a bad reference.
        session.execute(
            text("SELECT 1 FROM issuer WHERE id = :id AND tenant_id = :t"),
            {"id": str(issuer_id), "t": str(tenant_id)},
        ).first()
        is None
    ):
        raise LimitError(f"issuer {issuer_id} is not visible in the tenant")
    # Refuse a duplicate (tenant, code) with a clean domain error (not a raw IntegrityError/500).
    if session.execute(
        select(LimitDefinition.id).where(
            LimitDefinition.tenant_id == str(tenant_id), LimitDefinition.code == code
        )
    ).first():
        raise DuplicateLimitError(f"a limit with code {code!r} already exists in the tenant")
    limit = LimitDefinition(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        target_run_type=target_run_type,
        metric_type=metric_type,
        benchmark_id=str(benchmark_id) if benchmark_id else None,
        scope_portfolio_id=str(scope_portfolio_id),
        threshold_value=_threshold(threshold_value),
        threshold_unit=threshold_unit,
        breach_direction=breach_direction,
        limit_kind=limit_kind,
        status=LIMIT_STATUS_DRAFT,
        created_by=actor.actor_id,
        record_version=1,
        dimension_kind=dimension_kind,
        bucket_code=bucket_code,
        issuer_id=str(issuer_id) if issuer_id else None,
        scheme_family=scheme_family,
        authored_scheme_id=str(authored_scheme_id) if authored_scheme_id else None,
        denominator_basis=denominator_basis,
    )
    session.add(limit)
    session.flush()
    _record_limit_event(
        session,
        limit=limit,
        event_type=LIMIT_DEFINE_EVENT,
        action=ACTION_CREATE,
        before_value=None,
        after_value=_limit_metadata(limit),
        actor=actor,
    )
    return limit


def update_limit(
    session: Session, limit: LimitDefinition, *, actor: LimitActor, **changes: Any
) -> LimitDefinition:
    """Apply an in-place head edit (``_UPDATABLE`` only — identity is frozen, OD-I), bump
    ``record_version``, emit ``LIMIT.CHANGE``. A re-target is a NEW limit.

    MG-3 maker-checker rules:
    - ``update_limit`` may NEVER set or clear ``DRAFT`` — DRAFT is entered only via ``create_limit``
      (or the auto-demotion below) and left only via ``approve_limit``. This closes the "activate a
      draft through the edit path" bypass (the twin of the create-side force-DRAFT).
    - A MATERIAL governing-field change to a previously-approved limit (ACTIVE **or** SUSPENDED)
      auto-demotes it to DRAFT and records the editor as a maker (``updated_by``); it is not
      evaluated until a NON-maker re-approves (REQ-LIM-001/BX-SOD, OQ-MG-3-5=A). Enforcing this for
      SUSPENDED too closes the suspend->loosen->resume laundering bypass.
    - A status toggle (suspend/resume) may NOT be combined with a governing change in one edit —
      that ambiguity was a demote-suppression bypass; make the two edits separately.
    """
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise LimitError(f"non-updatable limit attributes: {sorted(unknown)}")
    if "status" in changes and changes["status"] not in LIMIT_STATUSES:
        raise LimitError(f"status {changes['status']!r} is invalid")
    if "breach_direction" in changes and changes["breach_direction"] not in BREACH_DIRECTIONS:
        raise LimitError(f"breach_direction {changes['breach_direction']!r} is invalid")
    if "limit_kind" in changes and changes["limit_kind"] not in LIMIT_KINDS:
        raise LimitError(f"limit_kind {changes['limit_kind']!r} is invalid")
    if "threshold_value" in changes and _threshold(changes["threshold_value"]) <= 0:
        raise LimitError("threshold_value must be positive")
    # Take the row lock AND read the fresh status under it, so the DRAFT guard and the demote
    # decision can never act on a stale identity-map status that a concurrent approve invalidated
    # (verifier B-2 parity with approve_limit). A SCALAR select is used, not a whole-object refresh,
    # so in-flight Decimal columns keep their in-memory representation (the audit payload format).
    fresh_status = session.execute(
        select(LimitDefinition.status)
        .where(LimitDefinition.id == limit.id, LimitDefinition.tenant_id == limit.tenant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if fresh_status is None:
        raise LimitError(f"limit {limit.id} not found in tenant {limit.tenant_id}")
    limit.status = fresh_status  # sync the locked truth (only the status string)
    governing_changed = _governing_value_changed(limit, changes)
    if "status" in changes:
        if governing_changed:
            raise LimitError(
                "cannot combine a status change (suspend/resume) with a governing-field change in "
                "one edit — a config change requires re-approval; make the two edits separately"
            )
        if changes["status"] == LIMIT_STATUS_DRAFT or limit.status == LIMIT_STATUS_DRAFT:
            raise LimitStateError(
                "update_limit cannot set or clear DRAFT — a draft leaves only via approve_limit "
                "(the maker-checker gate); suspend/resume operate on ACTIVE<->SUSPENDED only"
            )
    # A material change to a previously-approved (non-DRAFT) limit re-enters the maker-checker gate.
    demote = governing_changed and limit.status != LIMIT_STATUS_DRAFT
    keys = list(changes) + (["status"] if demote else [])
    before = {key: json_safe(getattr(limit, key)) for key in keys}
    for key, value in changes.items():
        setattr(limit, key, Decimal(value) if key == "threshold_value" else value)
    if demote:
        limit.status = LIMIT_STATUS_DRAFT
    # Record the editor as a maker on EVERY edit — ``approve_limit`` refuses any approver in the SET
    # {created_by, updated_by}, so both the original author and the last editor are SoD-excluded.
    limit.updated_by = actor.actor_id
    limit.record_version += 1
    session.flush()
    _record_limit_event(
        session,
        limit=limit,
        event_type=LIMIT_CHANGE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={key: json_safe(getattr(limit, key)) for key in keys},
        actor=actor,
    )
    return limit


def approve_limit(
    session: Session, limit: LimitDefinition, *, actor: LimitActor, approval_ref: str
) -> LimitDefinition:
    """Approve a DRAFT limit into ACTIVE — the maker-checker gate (REQ-LIM-001/BX-SOD, SOD-02).

    The approver MUST be human (BR-15) and MUST NOT be in the SET of makers of this draft —
    ``{created_by, updated_by}`` (the author AND the last editor) — so neither signs off a limit
    they shaped (SOD-02). The from-state is re-read UNDER the row lock (``populate_existing``)
    so a stale read cannot double-approve. Emits ``LIMIT.APPROVE`` with the ``approval_ref``.
    """
    _require_human(actor)
    if not (approval_ref or "").strip():
        raise LimitError("approve_limit requires a non-empty approval_ref (the sign-off evidence)")
    locked = _lock_limit(session, limit.id, limit.tenant_id)
    if locked.status != LIMIT_STATUS_DRAFT:
        raise LimitStateError(
            f"only a DRAFT limit can be approved (limit {locked.id} is {locked.status})"
        )
    makers = {locked.created_by, locked.updated_by} - {None}
    if not makers:
        raise LimitSodError(
            f"limit {locked.id} is DRAFT with no recorded maker — cannot establish SoD (refused)"
        )
    if actor.actor_id in makers:
        raise LimitSodError(
            f"actor {actor.actor_id} shaped this limit (a maker); cannot approve it (SOD-02)"
        )
    before = {"status": locked.status}
    locked.status = LIMIT_STATUS_ACTIVE
    locked.record_version += 1
    session.flush()
    _record_limit_event(
        session,
        limit=locked,
        event_type=LIMIT_APPROVE_EVENT,
        action=ACTION_STATUS_CHANGE,
        before_value=before,
        # Record the makers the SoD was checked against so the two-person control is provable from
        # the immutable audit row alone (the maker columns are mutable EV state).
        after_value={
            "status": locked.status,
            "approved_by": actor.actor_id,
            "checked_makers": sorted(makers),
        },
        actor=actor,
        approval_ref=approval_ref,
    )
    return locked


def suspend_limit(
    session: Session, limit: LimitDefinition, *, actor: LimitActor
) -> LimitDefinition:
    """Suspend a limit (excluded from evaluation)."""
    return update_limit(session, limit, actor=actor, status=LIMIT_STATUS_SUSPENDED)


def resume_limit(session: Session, limit: LimitDefinition, *, actor: LimitActor) -> LimitDefinition:
    """Resume a limit (re-admitted to evaluation)."""
    return update_limit(session, limit, actor=actor, status=LIMIT_STATUS_ACTIVE)


# --- limit health -------------------------------------------------------------------------
@dataclass(frozen=True)
class LimitHealth:
    """Per-limit evaluation health (OD-L) — distinguishes green from un-evaluable.

    **``state`` is the APPETITE VERDICT; staleness and drift are ORTHOGONAL fields, deliberately.**
    OQ-LIM-2-1=C and OQ-LIM-2-5=A were both ratified as "a distinct health state", and implementing
    that literally would have been wrong: a limit can be breached AND evaluating a stale run AND
    drifting across scheme versions simultaneously, so a fourth enum value forces a false choice
    where reporting STALE hides a real breach. The ratified INTENT — never default to green, make
    both conditions visible — is preserved; only the shape differs, and it is recorded here rather
    than slipped in (LIM-2 record 3.5).
    """

    limit_id: str
    code: str
    state: str  # IN_APPETITE | NEVER_EVALUABLE | BREACHED | REFUSED
    latest_run_id: str | None
    latest_breach_id: str | None
    #: The newest run of this family+scope FAILED and the verdict above is computed from an older
    #: COMPLETED one. Platform-wide, not concentration-specific (OQ-LIM-2-5=A).
    latest_run_failed: bool = False
    #: ``(authored_scheme_id, resolved_scheme_id)`` when the resolved run used a different taxonomy
    #: VERSION than the threshold was written against (OQ-LIM-2-1=C).
    scheme_drift: tuple[str, str] | None = None
    #: Why the resolver declined to compare, when ``state`` is REFUSED.
    refusal_reason: str | None = None


HEALTH_IN_APPETITE = "IN_APPETITE"
HEALTH_NEVER_EVALUABLE = "NEVER_EVALUABLE"
HEALTH_BREACHED = "BREACHED"
#: A governed number EXISTS and the resolver declined to threshold it (today: a basis mismatch).
#: Distinct from NEVER_EVALUABLE, which means nothing was found at all.
HEALTH_REFUSED = "REFUSED"


def _latest_run_failed(session: Session, limit: LimitDefinition) -> bool:
    """True when the NEWEST run of this family+scope is FAILED — i.e. the verdict is being read off
    a superseded book.

    **This closes a shipped defect that is live for VaR and active-risk limits today, not a
    concentration novelty (LIM-2 Part 0 fact 4).** The shared scaffold commits a FAILED run with
    zero rows for EVERY family, and the governed reads filter to COMPLETED — so once the newest
    attempt fails, ``_resolve_latest`` keeps returning the previous run and this surface reported
    IN_APPETITE off it with no signal. ``calc/reads`` states the assumption in its own words
    ("FAILED runs have zero rows, so COMPLETED-filtering hides nothing readable"), which is true
    for a row read and false for a latest-resolver used as a CONTROL INPUT.

    Scope-filtered the same way the resolvers are, so an unrelated failed run elsewhere in the
    tenant does not raise a false staleness flag.
    """
    from irp_shared.calc.models import CalculationRun, RunStatus

    newest = session.execute(
        select(CalculationRun.status)
        .where(
            CalculationRun.tenant_id == str(limit.tenant_id),
            CalculationRun.run_type == limit.target_run_type,
            CalculationRun.scope_portfolio_id == str(limit.scope_portfolio_id),
        )
        .order_by(CalculationRun.system_from.desc(), CalculationRun.run_id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return newest == RunStatus.FAILED.value


def limit_health(session: Session, *, acting_tenant: str) -> list[LimitHealth]:
    """Report each ACTIVE limit's evaluation health — so an un-evaluable limit is never silently
    green (OD-L). Derived on demand from ``calc/reads`` (no new mutable state)."""
    out: list[LimitHealth] = []
    for limit in select_active_limits(session, acting_tenant=acting_tenant):
        resolution = _resolve_latest(session, limit)
        stale = _latest_run_failed(session, limit)
        if resolution.refusal is not None:
            out.append(
                LimitHealth(
                    limit.id,
                    limit.code,
                    HEALTH_REFUSED,
                    None,
                    None,
                    latest_run_failed=stale,
                    refusal_reason=resolution.refusal,
                )
            )
            continue
        if not resolution.is_resolved:
            out.append(
                LimitHealth(
                    limit.id,
                    limit.code,
                    HEALTH_NEVER_EVALUABLE,
                    None,
                    None,
                    latest_run_failed=stale,
                )
            )
            continue
        run_id = resolution.run_id
        observed = resolution.observed
        assert run_id is not None and observed is not None  # narrowed by is_resolved
        # RECOMPUTE the predicate from the latest observed — do NOT infer state from the breach
        # table (a breaching-but-not-yet-evaluated run, or a threshold loosened after a breach,
        # would otherwise misreport; the 4-finder false-green fold). The breach row is only the
        # evidence reference.
        breaching = _breaches(observed, Decimal(limit.threshold_value), limit.breach_direction)
        breach = session.execute(
            select(Breach).where(
                Breach.limit_definition_id == limit.id,
                Breach.calculation_run_id == run_id,
            )
        ).scalar_one_or_none()
        state = HEALTH_BREACHED if breaching else HEALTH_IN_APPETITE
        drift: tuple[str, str] | None = None
        if (
            limit.authored_scheme_id
            and resolution.resolved_scheme_id
            and str(limit.authored_scheme_id) != resolution.resolved_scheme_id
        ):
            drift = (str(limit.authored_scheme_id), resolution.resolved_scheme_id)
        out.append(
            LimitHealth(
                limit.id,
                limit.code,
                state,
                run_id,
                breach.id if breach else None,
                latest_run_failed=stale,
                scheme_drift=drift,
            )
        )
    return out


# --- audit emit ---------------------------------------------------------------------------
def _limit_metadata(limit: LimitDefinition) -> dict[str, Any]:
    """DC-2 metadata payload for a ``LIMIT.*`` event — identifying/vocab fields only."""
    return {
        "code": limit.code,
        "target_run_type": limit.target_run_type,
        "metric_type": limit.metric_type,
        "scope_portfolio_id": str(limit.scope_portfolio_id),
        "benchmark_id": str(limit.benchmark_id) if limit.benchmark_id else None,
        "threshold_value": str(limit.threshold_value),
        "threshold_unit": limit.threshold_unit,
        "breach_direction": limit.breach_direction,
        "limit_kind": limit.limit_kind,
        "status": limit.status,
        "record_version": limit.record_version,
        # LIM-2 selector fields. `issuer_id` is DC-2 identifying vocabulary here, which is
        # consistent with the payload already carrying `scope_portfolio_id` and `benchmark_id`:
        # the audit log records WHAT was governed. The disclosure fence governs the limit/breach
        # READ surfaces, not the immutable record of a maker's act.
        "dimension_kind": limit.dimension_kind,
        "bucket_code": limit.bucket_code,
        "issuer_id": str(limit.issuer_id) if limit.issuer_id else None,
        "scheme_family": limit.scheme_family,
        "authored_scheme_id": (str(limit.authored_scheme_id) if limit.authored_scheme_id else None),
        "denominator_basis": limit.denominator_basis,
    }


def _record_limit_event(
    session: Session,
    *,
    limit: LimitDefinition,
    event_type: str,
    action: str,
    before_value: dict[str, Any] | None,
    after_value: dict[str, Any],
    actor: LimitActor,
    approval_ref: str | None = None,
) -> None:
    """Emit a ``LIMIT.*`` audit event caller-side to the FROZEN ``record_event`` (DC-2 only).
    ``approval_ref`` carries the maker-checker sign-off reference for ``LIMIT.APPROVE``."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=limit.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE_LIMIT,
        entity_type=_ENTITY_LIMIT,
        entity_id=limit.id,
        action=action,
        before_value=before_value,
        after_value=after_value,
        approval_ref=approval_ref,
        data_classification="DC-2",
    )


def _record_breach_event(session: Session, *, breach: Breach, actor_id: str) -> None:
    """Emit ``BREACH.DETECT`` for a detected breach — a synthesized SYSTEM actor on the tick."""
    record_event(
        session,
        event_type=BREACH_DETECT_EVENT,
        tenant_id=breach.tenant_id,
        actor_type="SYSTEM",
        actor_id=actor_id,
        source_module=SOURCE_MODULE_LIMIT,
        entity_type=_ENTITY_BREACH,
        entity_id=breach.id,
        action=ACTION_RECORD,
        # A HARD breach is an incident — escalate the audit envelope severity (the domain
        # HARD/SOFT is also echoed in after_value["severity"]).
        severity="warning" if breach.limit_kind == LIMIT_KIND_HARD else "info",
        after_value={
            "limit_definition_id": str(breach.limit_definition_id),
            "calculation_run_id": str(breach.calculation_run_id),
            "target_run_type": breach.target_run_type,
            "metric_type": breach.metric_type,
            "observed_value": str(breach.observed_value),
            "threshold_value": str(breach.threshold_value),
            "breach_direction": breach.breach_direction,
            "severity": breach.severity,
        },
        data_classification="DC-2",
    )
