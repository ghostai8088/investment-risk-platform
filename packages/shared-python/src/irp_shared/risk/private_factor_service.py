"""Pure-private factor-return run service (PPF-1, ENT-060) — the EIGHTEENTH governed number and the
FIRST slice of the §2.1 public+private unification arc.

``run_pure_private_factor_return`` pools, for one PRIVATE segment factor, its members' DESMOOTHED
appraisal returns MINUS their proxy-implied returns into one appraisal-period return series (the
MSCI PE Factor Model "pure private" leg; Shepard 2014/2025): per member per period
``pp_i,t = desmoothed_i,t - SUM_f w_i,f * R_f,t`` (the current-head REGRESSION blend weights; the
public factor returns compounded over ``(period_start, period_end]`` by the shared alignment
helper), pooled EQUAL-WEIGHT across members that share the EXACT interval (OQ-PPF-1-2/3 = A).
Persists
one ``PURE_PRIVATE_PERIOD`` row per pooled period + one ``PURE_PRIVATE_SUMMARY`` row.

Build-in-request (``segment_factor_id`` + ``member_desmoothed_run_ids`` → builds a
``PRIVATE_FACTOR_RETURN_INPUT`` snapshot) or consume-existing (``snapshot_id``); BOTH paths
adjudicate the PINNED content pre-create (AD-014 — never a live read; a later mark/return/weight
supersede cannot move a historical pooled return, TR-09).

Failure model (the established governed-run shape):
- **Pre-create refusal (422, ``PurePrivateFactorInputError``)** — missing prerequisite, wrong-code /
  wrong-purpose / cross-tenant snapshot, malformed pinned content, a member below the desmoothing
  floor, fewer than ``min_members`` members, a grid mismatch across members (the named-gap rule),
  or a member/blend/return coverage gap. NO run.
- **Post-create FAILED (magnitude gate)** — a committed FAILED run + ZERO rows + a naming
  ``failure_reason`` when a pooled return clears the ``Numeric(20,12)`` envelope.

Reuses ``risk.run``/``risk.view`` (no mint) + ``CALC.RUN_*``. One-way imports: ``risk -> {snapshot,
calc, model, marketdata.models}``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.reads import latest_run_rows, list_governed_results
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata.models import FACTOR_FAMILY_PRIVATE, MAPPING_METHOD_REGRESSION
from irp_shared.model.service import assert_model_version_of
from irp_shared.risk.bootstrap import (
    PURE_PRIVATE_MODEL_CODE,
    declared_pure_private_parameters,
)
from irp_shared.risk.events import RUN_TYPE_PURE_PRIVATE_FACTOR, PurePrivateFactorActor
from irp_shared.risk.models import (
    METRIC_TYPE_PURE_PRIVATE_PERIOD,
    METRIC_TYPE_PURE_PRIVATE_SUMMARY,
    PrivateFactorReturnResult,
)
from irp_shared.risk.period_alignment import compound_over_window
from irp_shared.risk.private_factor_kernel import (
    member_pure_private_return,
    pool_equal_weight,
    sample_stdev,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_DESMOOTHED_RETURN,
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FACTOR_RETURN,
    COMPONENT_KIND_PROXY_MAPPING,
    PURPOSE_PRIVATE_FACTOR_RETURN_INPUT,
    SnapshotActor,
    build_private_factor_return_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the established pattern).
_COMPLETENESS_RULE_CODE = "risk.pure_private.completeness"
#: The Numeric(20,12) ceiling is |value| < 1E8; bounds EVERY persisted pooled return / stdev.
_MAX_RESULT_ABS = Decimal("1E8")
#: Column quantum (quantize at assign so SQLite + PG persist byte-identical values).
_RESULT_QUANTUM = Decimal("1E-12")


class PurePrivateFactorInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class. Maps to 422."""


class PurePrivateFactorResultNotVisible(Exception):
    """Raised when a ``private_factor_return_result`` id is not visible in the acting tenant."""

    def __init__(self, result_id: str) -> None:
        super().__init__(f"private_factor_return_result {result_id} is not visible in the tenant")
        self.result_id = str(result_id)


@dataclass(frozen=True)
class PurePrivateFactorRunResult:
    """The outcome of ``run_pure_private_factor_return``: the run + status + result rows."""

    run: CalculationRun
    status: str
    rows: list[PrivateFactorReturnResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _MemberPeriod:
    """One member instrument's adjudicated appraisal period + its pure-private return."""

    period_start: date
    period_end: date
    pure_private_return: Decimal


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pins: the segment id + per-member period series (keyed by instrument)."""

    segment_factor_id: str
    members: dict[str, tuple[_MemberPeriod, ...]]


def _parse_pins(
    components: list[Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Split the pinned components into (segment_factor, public_factors, factor_returns, desmoothed,
    proxy_mappings) raw content. The segment is the sole PRIVATE-family FACTOR pin."""
    factors = [
        json.loads(c.captured_content)
        for c in components
        if c.component_kind == COMPONENT_KIND_FACTOR
    ]
    factor_returns = [
        json.loads(c.captured_content)
        for c in components
        if c.component_kind == COMPONENT_KIND_FACTOR_RETURN
    ]
    desmoothed = [
        json.loads(c.captured_content)
        for c in components
        if c.component_kind == COMPONENT_KIND_DESMOOTHED_RETURN
    ]
    proxy = [
        json.loads(c.captured_content)
        for c in components
        if c.component_kind == COMPONENT_KIND_PROXY_MAPPING
    ]
    private_factors = [f for f in factors if f.get("factor_family") == FACTOR_FAMILY_PRIVATE]
    public_factors = [f for f in factors if f.get("factor_family") != FACTOR_FAMILY_PRIVATE]
    if len(private_factors) != 1:
        raise PurePrivateFactorInputError(
            f"expected exactly one PRIVATE segment factor pin, got {len(private_factors)}; refused"
        )
    return private_factors[0], public_factors, factor_returns, desmoothed, proxy


def _adjudicate_pins(
    segment_raw: dict[str, Any],
    public_factor_raw: list[dict[str, Any]],
    factor_return_raw: list[dict[str, Any]],
    desmoothed_raw: list[dict[str, Any]],
    proxy_raw: list[dict[str, Any]],
    *,
    min_members: int,
) -> _ParsedInput:
    """Adjudicate the pinned content pre-create (fail-closed, NO imputation): reconstruct each
    member's pure-private period series; enforce the min-members floor + identical-interval pooling
    (a grid mismatch is a named-gap refusal). Raises :class:`PurePrivateFactorInputError`."""
    segment_id = str(segment_raw["id"]).lower()

    # Public factor returns, keyed by factor id (each a sorted (date, value) list).
    returns_by_factor: dict[str, list[tuple[date, Decimal]]] = {}
    for fr in factor_return_raw:
        fid = str(fr["factor_id"]).lower()
        rows = [
            (
                date.fromisoformat(str(r["return_date"])),
                parse_strict_decimal(
                    r["return_value"], error=PurePrivateFactorInputError, field="return_value"
                ),
            )
            for r in fr["rows"]
        ]
        returns_by_factor[fid] = sorted(rows, key=lambda x: x[0])
    public_factor_ids = {str(f["id"]).lower() for f in public_factor_raw}

    # Desmoothed period series, grouped by member instrument.
    periods_by_member: dict[str, list[tuple[date, date, Decimal, str]]] = {}
    for row in desmoothed_raw:
        instrument_id = str(row["instrument_id"]).lower()
        p_start = date.fromisoformat(str(row["period_start"]))
        p_end = date.fromisoformat(str(row["period_end"]))
        y = parse_strict_decimal(
            row["metric_value"], error=PurePrivateFactorInputError, field="metric_value"
        )
        currency = str(row["mark_currency"] or "")
        periods_by_member.setdefault(instrument_id, []).append((p_start, p_end, y, currency))
    if not periods_by_member:
        raise PurePrivateFactorInputError("no pinned member desmoothed periods — refused")

    # Per member: its REGRESSION blend (weights onto public factors) + its membership row.
    blend_by_member: dict[str, list[tuple[str, Decimal]]] = {}
    membership_members: set[str] = set()
    for row in proxy_raw:
        instrument_id = str(row["private_instrument_id"]).lower()
        fid = str(row["factor_id"]).lower()
        method = str(row["mapping_method"])
        weight = parse_strict_decimal(
            row["weight"], error=PurePrivateFactorInputError, field="weight"
        )
        if fid == segment_id:
            membership_members.add(instrument_id)  # the MANUAL membership row onto the segment
        elif method == MAPPING_METHOD_REGRESSION:
            blend_by_member.setdefault(instrument_id, []).append((fid, weight))

    members: dict[str, tuple[_MemberPeriod, ...]] = {}
    interval_signature: tuple[tuple[date, date], ...] | None = None
    for instrument_id, member_rows in sorted(periods_by_member.items()):
        if instrument_id not in membership_members:
            raise PurePrivateFactorInputError(
                f"member {instrument_id} has no pinned segment membership row — refused"
            )
        blend = blend_by_member.get(instrument_id)
        if not blend:
            raise PurePrivateFactorInputError(
                f"member {instrument_id} has no pinned REGRESSION blend — the proxy-implied return "
                f"cannot be subtracted (named gap); refused"
            )
        for fid, _w in blend:
            if fid not in public_factor_ids or fid not in returns_by_factor:
                raise PurePrivateFactorInputError(
                    f"member {instrument_id} blend factor {fid} has no pinned return window"
                )
        currencies = {c for (_s, _e, _y, c) in member_rows}
        if len(currencies) != 1 or len(next(iter(currencies))) != 3:
            raise PurePrivateFactorInputError(
                f"member {instrument_id} desmoothed series spans multiple/malformed currencies"
            )
        member_periods: list[_MemberPeriod] = []
        seen_starts: set[date] = set()
        for p_start, p_end, y, _c in sorted(member_rows, key=lambda t: t[0]):
            if p_start in seen_starts:
                raise PurePrivateFactorInputError(
                    f"member {instrument_id} has a duplicate period_start {p_start} — refused"
                )
            seen_starts.add(p_start)
            period_blend = [
                (
                    w,
                    compound_over_window(
                        returns_by_factor[fid], period_start=p_start, period_end=p_end
                    ),
                )
                for (fid, w) in blend
            ]
            # Every blend factor must cover the period (NO zero-fill — the P3-7 named-gap rule).
            for fid, _w in blend:
                covering = [v for (rdate, v) in returns_by_factor[fid] if p_start < rdate <= p_end]
                if not covering:
                    raise PurePrivateFactorInputError(
                        f"blend factor {fid} has no return covering member {instrument_id} period "
                        f"({p_start}..{p_end}] — refused (NO zero-fill)"
                    )
            pp = member_pure_private_return(y, period_blend)
            member_periods.append(
                _MemberPeriod(period_start=p_start, period_end=p_end, pure_private_return=pp)
            )
        signature = tuple((mp.period_start, mp.period_end) for mp in member_periods)
        if interval_signature is None:
            interval_signature = signature
        elif signature != interval_signature:
            raise PurePrivateFactorInputError(
                f"member {instrument_id} has a DIFFERENT appraisal-period grid than its peers — "
                f"identical-interval pooling required (cross-calendar interp is a v2); refused"
            )
        members[instrument_id] = tuple(member_periods)

    if len(members) < int(min_members):
        raise PurePrivateFactorInputError(
            f"{len(members)} qualifying member(s) for the segment — need >= min_members="
            f"{min_members}; refused"
        )
    return _ParsedInput(segment_factor_id=segment_id, members=members)


def run_pure_private_factor_return(
    session: Session,
    *,
    acting_tenant: str,
    actor: PurePrivateFactorActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    segment_factor_id: str | None = None,
    member_desmoothed_run_ids: list[str] | None = None,
    snapshot_id: str | None = None,
) -> PurePrivateFactorRunResult:
    """Run a governed pure-private factor-return pooling. Build-in-request (default —
    ``segment_factor_id`` + ``member_desmoothed_run_ids``) or consume-existing (``snapshot_id``).
    BOTH paths adjudicate the pinned content pre-create."""
    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise PurePrivateFactorInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise PurePrivateFactorInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise PurePrivateFactorInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise PurePrivateFactorInputError(
            "model_version_id is required (CTRL-003 inventory-before-use)"
        )
    build_args = (segment_factor_id, member_desmoothed_run_ids)
    if snapshot_id is not None and any(a is not None for a in build_args):
        raise PurePrivateFactorInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(segment_factor_id/member_desmoothed_run_ids), not both"
        )
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=PURE_PRIVATE_MODEL_CODE,
    )
    params = declared_pure_private_parameters(session, version)

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_PRIVATE_FACTOR_RETURN_INPUT:
            raise PurePrivateFactorInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} "
                f"!= {PURPOSE_PRIVATE_FACTOR_RETURN_INPUT}"
            )
    else:
        if segment_factor_id is None or member_desmoothed_run_ids is None:
            raise PurePrivateFactorInputError(
                "segment_factor_id + member_desmoothed_run_ids are both required to build a "
                "pure-private factor snapshot"
            )
        snapshot = build_private_factor_return_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            segment_factor_id=str(segment_factor_id),
            member_desmoothed_run_ids=list(member_desmoothed_run_ids),
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths). ---
    try:
        segment_raw, public_raw, factor_return_raw, desmoothed_raw, proxy_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_pins(
            segment_raw,
            public_raw,
            factor_return_raw,
            desmoothed_raw,
            proxy_raw,
            min_members=params.min_members,
        )
    except PurePrivateFactorInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise PurePrivateFactorInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # Pool across members per shared interval (identical-interval — the grid was signature-checked).
    any_member = next(iter(parsed.members.values()))
    intervals = [(mp.period_start, mp.period_end) for mp in any_member]
    member_count = len(parsed.members)
    pooled: list[tuple[date, date, Decimal]] = []
    for p_start, p_end in intervals:
        per_member = [
            mp.pure_private_return
            for periods in parsed.members.values()
            for mp in periods
            if mp.period_start == p_start and mp.period_end == p_end
        ]
        pooled.append((p_start, p_end, pool_equal_weight(per_member)))
    span_start = min(p for (p, _e, _v) in pooled)
    span_end = max(e for (_p, e, _v) in pooled)
    stdev = sample_stdev([v for (_p, _e, v) in pooled])

    def _compute(run: CalculationRun) -> tuple[list[PrivateFactorReturnResult], list[str]]:
        gaps: list[str] = []
        raw_values = [v for (_p, _e, v) in pooled] + [stdev]
        if any(abs(v) >= _MAX_RESULT_ABS for v in raw_values):
            gaps.append("magnitude-out-of-range:pooled-return-or-stdev")
            return [], gaps

        def _base(**kw: Any) -> PrivateFactorReturnResult:
            return PrivateFactorReturnResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                segment_factor_id=parsed.segment_factor_id,
                pooling_convention=params.pooling_convention,
                intercept_convention=params.intercept_convention,
                min_members=int(params.min_members),
                **kw,
            )

        rows: list[PrivateFactorReturnResult] = [
            _base(
                metric_type=METRIC_TYPE_PURE_PRIVATE_PERIOD,
                period_start=p_start,
                period_end=p_end,
                metric_value=value.quantize(_RESULT_QUANTUM),
                member_count=member_count,
                period_count=None,
            )
            for (p_start, p_end, value) in pooled
        ]
        rows.append(
            _base(
                metric_type=METRIC_TYPE_PURE_PRIVATE_SUMMARY,
                period_start=span_start,
                period_end=span_end,
                metric_value=stdev.quantize(_RESULT_QUANTUM),
                member_count=member_count,
                period_count=len(pooled),
            )
        )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_PURE_PRIVATE_FACTOR,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="pure-private factor sanity (values within the Numeric(20,12) scale)",
        rule_target_entity_type="private_factor_return_result",
        result_entity_type="private_factor_return_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return PurePrivateFactorRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=list(outcome.rows),
        failure_reason=outcome.failure_reason,
    )


def list_pure_private_factor_results(
    session: Session, run_id: str, *, acting_tenant: str
) -> list[PrivateFactorReturnResult]:
    """The ``private_factor_return_result`` rows of a run (tenant-scoped; stable
    ``(metric_type, period_start)`` order)."""
    return list(
        session.execute(
            select(PrivateFactorReturnResult)
            .where(
                PrivateFactorReturnResult.calculation_run_id == str(run_id),
                PrivateFactorReturnResult.tenant_id == str(acting_tenant),
            )
            .order_by(PrivateFactorReturnResult.metric_type, PrivateFactorReturnResult.period_start)
        )
        .scalars()
        .all()
    )


def list_pure_private_factor_results_by_segment(
    session: Session,
    *,
    acting_tenant: str,
    segment_factor_id: str | None = None,
    as_of: datetime | None = None,
) -> list[PrivateFactorReturnResult]:
    """Rule-7 entity read: the pure-private return rows for a segment factor across COMPLETED runs
    (tenant-scoped; the shared ``calc/reads.py`` helper — ``segment_factor_id`` equality)."""
    return list_governed_results(
        session,
        PrivateFactorReturnResult,
        acting_tenant=acting_tenant,
        filters=((PrivateFactorReturnResult.segment_factor_id, segment_factor_id),),
        run_type=RUN_TYPE_PURE_PRIVATE_FACTOR,
        as_of=as_of,
        order_by=PrivateFactorReturnResult.metric_type,
    )


def latest_pure_private_factor_for_segment(
    session: Session,
    *,
    acting_tenant: str,
    segment_factor_id: str,
    as_of: datetime | None = None,
) -> list[PrivateFactorReturnResult]:
    """Rule-7 latest-resolver: the rows of the NEWEST COMPLETED pure-private run for a segment
    factor (the ``calc/reads.py`` ``latest_run_rows`` resolver)."""
    return latest_run_rows(
        list_pure_private_factor_results_by_segment(
            session,
            acting_tenant=acting_tenant,
            segment_factor_id=segment_factor_id,
            as_of=as_of,
        )
    )
