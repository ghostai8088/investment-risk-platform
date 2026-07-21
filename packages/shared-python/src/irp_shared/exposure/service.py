"""Exposure binder (P2-3, ENT-014) — the first governed derived number, run-bound + snapshot-gated.

``run_exposure`` produces ``exposure_aggregate`` rows ONLY when bound to a ``dataset_snapshot`` + a
complete ``calculation_run`` (AD-014 / FW-RUN §5 / TR-15). **Signed market value v1** =
``signed_quantity x captured mark_value x effective captured FX rate``, grouped at the per-holding
atom ``(portfolio_id, instrument_id, base_currency)``. **NOT risk** — a deterministic captured-mark
rollup (no VaR/ES/factor/scenario/pricing/valuation model).

Reproducibility (the load-bearing AD-014 invariant): the compute reads **ONLY the snapshot's pinned
components' captured content** (positions, valuations, FX as ``COMPONENT_KIND_FX``) — it makes
**NO**
live ``reconstruct_*`` / ``resolve_position`` / ``resolve_valuation`` /
``reconstruct_fx_rate_as_of``
read. The FX is the **effective composite** of the pinned legs via the PURE
``compose_effective_rate`` (no DB read), so a later vendor correction cannot change a historical
exposure.

Failure model (OD-P2-3-F, split by timing):
- **Pre-create refusal** (a missing prerequisite — ``code_version``/``environment_id``/initiator, or
  an unbuildable/cross-tenant/incomplete/FX-missing snapshot): **raise BEFORE ``create_run``** ⇒
  ZERO
  run + ZERO exposure + ZERO audit.
- **Post-create FAILED** (a gate failing AFTER the run is RUNNING — a markless position or a missing
  pinned FX leg in a *consumed* snapshot): mark the run FAILED (``outcome='failure'``) and
  **return**
  a FAILED result ⇒ a committed FAILED run + ``CALC.RUN_STATUS_CHANGE`` + ZERO exposure rows.
- **Emit-path** (``record_event``/``record_*_lineage`` raising on a good run): propagates ⇒ the
whole
  unit rolls back co-transactionally (CTRL-032).

One-way imports: ``exposure -> {snapshot, marketdata(pure legs), calc, lineage, dq, portfolio,
audit, db}``; imports **no** live position/valuation/FX resolver into the compute; imports no
risk/factor/scenario symbol; nothing imports ``exposure``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.reads import latest_run_rows, list_governed_results
from irp_shared.calc.runs import resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.exposure.events import RUN_TYPE_EXPOSURE_AGGREGATE, ExposureActor
from irp_shared.exposure.models import EXPOSURE_TYPE_MARKET_VALUE, ExposureAggregate
from irp_shared.marketdata import DEFAULT_BASE, compose_effective_rate
from irp_shared.portfolio import resolve_portfolio
from irp_shared.snapshot import (
    COMPONENT_KIND_FX,
    COMPONENT_KIND_POSITION,
    COMPONENT_KIND_VALUATION,
    SnapshotActor,
    build_snapshot,
    list_components,
    resolve_snapshot,
)
from irp_shared.snapshot.models import PURPOSE_EXPOSURE_INPUT

#: Quantizers: fx_rate at the FX scale 12; exposure_amount at the money scale 6 (ROUND_HALF_UP — the
#: canonical-serialization convention; QS-04 registered exception, so the self-audit is exact).
_FX_QUANTUM = Decimal(1).scaleb(-12)
_MONEY_QUANTUM = Decimal(1).scaleb(-6)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the snapshot/fx pattern).
_COMPLETENESS_RULE_CODE = "exposure.completeness"


class ExposureInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no exposure, no audit). Maps to 422."""


class ExposureNotVisible(Exception):
    """Raised when an ``exposure_aggregate`` id is not visible in the acting tenant scope."""

    def __init__(self, exposure_id: str) -> None:
        super().__init__(f"exposure_aggregate {exposure_id} is not visible in the current tenant")
        self.exposure_id = str(exposure_id)


class ExposureRunNotVisible(Exception):
    """Raised when an exposure ``calculation_run`` id is not visible in the acting tenant scope."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"exposure run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class ExposureRunResult:
    """The outcome of ``run_exposure``: the ``calculation_run`` + its status + the rows produced.

    ``status`` is ``COMPLETED`` (with ``rows``) or ``FAILED`` (a post-create gate failure: a
    committed
    FAILED run + ZERO rows + ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[ExposureAggregate] = field(default_factory=list)
    failure_reason: str | None = None


def _resolve_base_currency(
    session: Session, *, portfolio_id: str, acting_tenant: str, base_currency: str | None
) -> str:
    """The reporting/base currency: the explicit arg → the bound portfolio's ``base_currency_code``
    →
    ``DEFAULT_BASE`` (USD). Resolving the portfolio also fails closed cross-tenant
    (PortfolioNotVisible
    ⇒ pre-create refusal)."""
    if base_currency:
        # Still resolve the portfolio so a cross-tenant/unknown scope fails closed pre-create.
        resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)
        return base_currency
    pf = resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)
    return pf.base_currency_code or DEFAULT_BASE


def _read_components(
    comps: list[Any],
) -> tuple[
    dict[tuple[str, str], Decimal],
    dict[tuple[str, str], tuple[Decimal, str]],
    dict[tuple[str, str], tuple[str, Decimal]],
]:
    """Parse the snapshot's pinned components' captured content (PURE — no live read): positions
    ``(pf,inst)->qty``, marks ``(pf,inst)->(mark,ccy)``, fx ``(base,quote)->(id,rate)``."""
    positions: dict[tuple[str, str], Decimal] = {}
    marks: dict[tuple[str, str], tuple[Decimal, str]] = {}
    rate_map: dict[tuple[str, str], tuple[str, Decimal]] = {}
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_POSITION:
            positions[(data["portfolio_id"], data["instrument_id"])] = Decimal(data["quantity"])
        elif comp.component_kind == COMPONENT_KIND_VALUATION:
            marks[(data["portfolio_id"], data["instrument_id"])] = (
                Decimal(data["mark_value"]),
                data["currency_code"],
            )
        elif comp.component_kind == COMPONENT_KIND_FX:
            rate_map[(data["base_currency"], data["quote_currency"])] = (
                data["id"],
                Decimal(data["rate"]),
            )
    return positions, marks, rate_map


def _build_rows(
    *,
    positions: dict[tuple[str, str], Decimal],
    marks: dict[tuple[str, str], tuple[Decimal, str]],
    rate_map: dict[tuple[str, str], tuple[str, Decimal]],
    base_currency: str,
    acting_tenant: str,
    run: CalculationRun,
    snapshot_id: str,
) -> tuple[list[ExposureAggregate], list[str]]:
    """Compute one exposure row per ``(portfolio, instrument)`` with a mark + a resolvable FX path.
    Returns ``(rows, gaps)`` — ``gaps`` names every holding lacking a mark or a pinned FX path (the
    fail-closed DQ signal; rows are NOT written when gaps exist)."""
    rows: list[ExposureAggregate] = []
    gaps: list[str] = []
    for (pf, inst), qty in sorted(positions.items()):
        mark = marks.get((pf, inst))
        if mark is None:
            gaps.append(f"missing-mark:{pf}/{inst}")
            continue
        mark_value, mark_ccy = mark
        composed = compose_effective_rate(
            rate_map, from_currency=mark_ccy, to_currency=base_currency, base=DEFAULT_BASE
        )
        if composed is None:
            gaps.append(f"missing-fx:{mark_ccy}->{base_currency}")
            continue
        effective, legs = composed
        fx_rate = effective.quantize(_FX_QUANTUM, rounding=ROUND_HALF_UP)
        # Signed market value v1; exact-by-construction from the stored, rounded fx_rate.
        amount = (qty * mark_value * fx_rate).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        rows.append(
            ExposureAggregate(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=str(snapshot_id),
                portfolio_id=pf,
                instrument_id=inst,
                base_currency=base_currency,
                mark_currency=mark_ccy,
                signed_quantity=qty,
                mark_value=mark_value,
                fx_rate=fx_rate,
                fx_legs=json.dumps([leg.as_dict() for leg in legs]),
                exposure_amount=amount,
                exposure_type=EXPOSURE_TYPE_MARKET_VALUE,
            )
        )
    return rows, gaps


def run_exposure(
    session: Session,
    *,
    acting_tenant: str,
    actor: ExposureActor,
    code_version: str,
    environment_id: str,
    portfolio_id: str | None = None,
    as_of_valid_at: datetime | None = None,
    base_currency: str | None = None,
    as_of_known_at: datetime | None = None,
    snapshot_id: str | None = None,
) -> ExposureRunResult:
    """Run a governed exposure aggregation. Build-in-request (default — ``portfolio_id`` +
    ``as_of_valid_at``: builds an ``EXPOSURE_INPUT`` snapshot with FX pinned) or consume-existing
    (``snapshot_id``). See the module docstring for the failure model + the AD-014 invariant."""
    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/exposure/audit) ---
    if not code_version:
        raise ExposureInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise ExposureInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise ExposureInputError("initiator is required (FW-RUN/TR-15)")

    # --- Bind the snapshot (cross-tenant/unknown/incomplete/FX-missing ⇒ pre-create refusal) ---
    if snapshot_id is not None and (
        portfolio_id is not None or as_of_valid_at is not None or as_of_known_at is not None
    ):
        # P3-C1 (OD-G): passing BOTH input modes previously preferred snapshot_id SILENTLY —
        # an ambiguous request must be refused, never guessed. base_currency is deliberately
        # EXCLUDED: it IS honored on the snapshot path (the recompute base), not ignored.
        raise ExposureInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(portfolio_id/as_of_*), not both"
        )
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        # Snapshot-gating by CONTRACT, not by FX-coincidence: a consumed snapshot MUST be one built
        # FOR exposure (an all-base-currency ADHOC/TEST snapshot would otherwise slip the FX gate
        # via the identity path). Pre-create refusal (review fold — product #1).
        if snapshot.purpose != PURPOSE_EXPOSURE_INPUT:
            raise ExposureInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_EXPOSURE_INPUT}"
            )
        base = base_currency or DEFAULT_BASE
    else:
        if portfolio_id is None or as_of_valid_at is None:
            raise ExposureInputError(
                "portfolio_id + as_of_valid_at are required to build an exposure snapshot"
            )
        base = _resolve_base_currency(
            session,
            portfolio_id=portfolio_id,
            acting_tenant=acting_tenant,
            base_currency=base_currency,
        )
        snapshot = build_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            purpose=PURPOSE_EXPOSURE_INPUT,
            portfolio_id=portfolio_id,
            as_of_valid_at=as_of_valid_at,
            as_of_known_at=as_of_known_at,
            base_currency=base,
        )

    # --- The shared governed-run lifecycle (P3-C2: adopt the P3-C1 scaffold — the model-less
    # fifth variant). Two INTENDED improvements over the prior hand-rolled tail: the FAILED run
    # now PERSISTS its ``failure_reason`` (was returned-only ⇒ the GET showed None), and the
    # snapshot->run DEPENDS_ON edge is recorded BEFORE the DQ gate (a committed FAILED run keeps
    # its input-lineage link — the P3-1 lineage fold, extended to the exposure family). The
    # compute stays a pure callback over the pinned content; the reason format is preserved
    # verbatim (bare ``str(gate)`` — the P3-1 format exposure already used). ---
    def _compute(run: CalculationRun) -> tuple[list[ExposureAggregate], list[str]]:
        positions, marks, rate_map = _read_components(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        return _build_rows(
            positions=positions,
            marks=marks,
            rate_map=rate_map,
            base_currency=base,
            acting_tenant=acting_tenant,
            run=run,
            snapshot_id=snapshot.id,
        )

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_EXPOSURE_AGGREGATE,
        snapshot_id=snapshot.id,
        model_version_id=None,  # a model-less deterministic rollup
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="Exposure run input completeness (mark + FX)",
        rule_target_entity_type="exposure_aggregate",
        result_entity_type="exposure_aggregate",
        compute=_compute,
        format_reason=lambda gate, gaps: str(gate),  # verbatim pre-P3-C2 exposure format
        # API-1b (OD-API-1b-B): the ROOT is the build-path portfolio_id (the subtree this run
        # aggregates). The snapshot-consume path did NOT take a root → NULL (honest, OD-API-1b-D).
        scope_portfolio_id=(None if snapshot_id is not None else portfolio_id),
    )
    return ExposureRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_exposure(session: Session, *, run_id: str, acting_tenant: str) -> list[ExposureAggregate]:
    """The exposure rows of a run (tenant-scoped, stable order)."""
    return list(
        session.execute(
            select(ExposureAggregate)
            .where(
                ExposureAggregate.calculation_run_id == str(run_id),
                ExposureAggregate.tenant_id == str(acting_tenant),
            )
            .order_by(ExposureAggregate.portfolio_id, ExposureAggregate.instrument_id)
        )
        .scalars()
        .all()
    )


def list_exposure_by_entity(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
    as_of=None,  # noqa: ANN001  (datetime | None — the API-1 run cutoff)
) -> list[ExposureAggregate]:
    """API-1 entity/time read (Class A): ``exposure_aggregate`` rows across COMPLETED runs for a
    (portfolio, instrument). A run's rows SPAN the portfolio SUBTREE, so the ``portfolio_id`` filter
    row-filters to the queried book's own rows. Silent-empty on a foreign id; ``as_of=None`` =
    now."""
    return list_governed_results(
        session,
        ExposureAggregate,
        acting_tenant=acting_tenant,
        filters=(
            (ExposureAggregate.portfolio_id, portfolio_id),
            (ExposureAggregate.instrument_id, instrument_id),
        ),
        as_of=as_of,
        order_by=ExposureAggregate.instrument_id,
    )


def latest_exposure(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    instrument_id: str | None = None,
    as_of=None,  # noqa: ANN001  (datetime | None)
) -> list[ExposureAggregate]:
    """API-1 latest-resolver (Class A): the newest COMPLETED exposure run's rows for the portfolio
    (the run may be rooted at an ancestor — rows returned are the portfolio's own; empty when
    none)."""
    return latest_run_rows(
        list_exposure_by_entity(
            session,
            acting_tenant=acting_tenant,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            as_of=as_of,
        )
    )


def resolve_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve an EXPOSURE ``calculation_run`` by ``run_id`` with an EXPLICIT tenant predicate +
    ``run_type`` filter (fail-closed). Returns the REAL run (its true ``status`` —
    ``COMPLETED``/``FAILED`` — + ``code_version``/``environment_id``/``initiated_by``/
    ``input_snapshot_id``), so a reader surfaces a committed FAILED run (the durable refusal
    evidence a 3L auditor reviews) rather than synthesizing the envelope from rows. Raises
    :class:`ExposureRunNotVisible` on a hidden/unknown id or a non-exposure run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_EXPOSURE_AGGREGATE,
        not_visible=ExposureRunNotVisible,
    )


def resolve_exposure(
    session: Session, exposure_id: str, *, acting_tenant: str
) -> ExposureAggregate:
    """Resolve one ``exposure_aggregate`` row by id with an EXPLICIT tenant predicate
    (fail-closed)."""
    row = session.execute(
        select(ExposureAggregate).where(
            ExposureAggregate.id == str(exposure_id),
            ExposureAggregate.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ExposureNotVisible(str(exposure_id))
    return row
