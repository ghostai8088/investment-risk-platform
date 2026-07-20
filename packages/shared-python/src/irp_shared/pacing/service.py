"""Governed commitment-pacing binder (CC-2, ENT-059 — the SEVENTEENTH governed number).

``run_pacing_projection`` projects a private-fund commitment's FUTURE capital calls, distributions,
and NAV over the CC-1 captured substrate, reading ONLY the pinned snapshot content (AD-014). The
pipeline: pre-create prerequisite gate → ``assert_model_version_of`` (REGISTERED + OF the pacing
model) → resolve the ``PACING_INPUT`` snapshot → parse the pins (ONE commitment head + ALL
call/distribution events + 0-or-1 valuation mark) → assemble the anchor FROM THE PIN (Sum of calls;
Sum of recallable distributions restoring unfunded; the latest mark, currency-checked; the
PIN-derived current age from the snapshot ``as_of_valuation_date`` — a deterministic age, never the
wall clock) → the pre-create refusals (currency mismatch; incoherent unfunded; funded-without-mark;
past fund life) → the kernel projection → the shared governed-run scaffold (rows + ORIGIN lineage +
COMPLETED, or a magnitude-gate FAILED run).

THE READ RULE (OD-CC-1-D) is upstream: this binder consumes commitment/call/distribution rows for
PACING only; those events do not feed TWR/backtest P&L. Imports NO ``risk``/``perf`` symbol; reads
``private_capital``/``valuation`` content only through the PIN (never a live read).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.runs import resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.model.service import assert_model_version_of
from irp_shared.pacing.bootstrap import PACING_MODEL_CODE, declared_pacing_parameters
from irp_shared.pacing.events import RUN_TYPE_PACING_PROJECTION, PacingActor
from irp_shared.pacing.models import PacingProjectionResult
from irp_shared.pacing.pacing_kernel import (
    PacingAnchor,
    PacingKernelError,
    anniversary_window,
    project_commitment,
)
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.snapshot.models import (
    COMPONENT_KIND_CAPITAL_CALL,
    COMPONENT_KIND_COMMITMENT,
    COMPONENT_KIND_DISTRIBUTION,
    COMPONENT_KIND_VALUATION,
    PURPOSE_PACING_INPUT,
)
from irp_shared.snapshot.service import list_components, resolve_snapshot


class PacingInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class (a pacing number borrows no risk/perf error).
    Maps to 422."""


class PacingNotVisible(Exception):
    """Raised when a ``pacing_projection_result`` id is not visible in the acting tenant scope."""

    def __init__(self, result_id: str) -> None:
        super().__init__(
            f"pacing_projection_result {result_id} is not visible in the current tenant"
        )
        self.result_id = str(result_id)


class PacingRunNotVisible(Exception):
    """Raised when a pacing ``calculation_run`` id is not visible in the acting tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"pacing run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class PacingRunResult:
    """The outcome of ``run_pacing_projection``: the run + status + the projected period rows.
    ``status`` is ``COMPLETED`` (``rows`` = the future-period projection) or ``FAILED`` (the
    magnitude gate: a committed FAILED run + ZERO rows + a naming ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[PacingProjectionResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _Anchor:
    """The adjudicated projection anchor + the pair identity, all derived from the pinned
    content."""

    portfolio_id: str
    instrument_id: str
    currency_code: str
    commitment_date: date
    as_of: date
    current_age: int
    unfunded: Decimal
    nav: Decimal


def _content(comp) -> dict:  # noqa: ANN001
    parsed = json.loads(comp.captured_content)
    if not isinstance(parsed, dict):
        raise ValueError("captured_content is not an object")
    return parsed


def _complete_annual_periods(vintage: date, as_of: date) -> int:
    """Complete ANNUAL periods (anniversaries) elapsed from ``vintage`` to ``as_of`` — the
    deterministic current age (a wall-clock age would break pin-reproducibility)."""
    years = as_of.year - vintage.year
    if (as_of.month, as_of.day) < (vintage.month, vintage.day):
        years -= 1
    return years


def _adjudicate_anchor(session: Session, snapshot, *, acting_tenant: str) -> _Anchor:  # noqa: ANN001
    """Parse the pins + assemble the coherent projection anchor (all pre-create refusals)."""
    comps = list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
    commitments = [c for c in comps if c.component_kind == COMPONENT_KIND_COMMITMENT]
    calls = [c for c in comps if c.component_kind == COMPONENT_KIND_CAPITAL_CALL]
    dists = [c for c in comps if c.component_kind == COMPONENT_KIND_DISTRIBUTION]
    marks = [c for c in comps if c.component_kind == COMPONENT_KIND_VALUATION]
    if len(commitments) != 1:
        raise PacingInputError(
            f"a PACING_INPUT snapshot pins exactly ONE commitment (got {len(commitments)})"
        )
    if len(marks) > 1:
        raise PacingInputError(f"at most ONE valuation mark may be pinned (got {len(marks)})")

    try:
        commitment = _content(commitments[0])
        portfolio_id = str(commitment["portfolio_id"])
        instrument_id = str(commitment["instrument_id"])
        currency = commitment["currency_code"]
        committed = Decimal(commitment["committed_amount"])
        commitment_date = date.fromisoformat(commitment["commitment_date"])
        paid_in = Decimal("0")
        for c in calls:
            paid_in += Decimal(_content(c)["amount"])  # reversals self-correct (signed)
        recallable_returned = Decimal("0")
        for d in dists:
            body = _content(d)
            if bool(body["is_recallable"]):
                recallable_returned += Decimal(body["amount"])  # reversals self-correct
        nav_seed: Decimal | None = None
        if marks:
            mark = _content(marks[0])
            nav_seed = Decimal(mark["mark_value"])
            if mark["currency_code"] != currency:
                raise PacingInputError(
                    f"the pinned mark currency {mark['currency_code']!r} != the commitment "
                    f"currency {currency!r} — a funded projection needs a same-currency NAV anchor"
                )
    except PacingInputError:
        raise
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise PacingInputError(
            f"pinned content is not a well-formed pacing input ({type(exc).__name__})"
        ) from exc

    # Re-resolve the pair FK targets under the acting tenant BEFORE they are stamped into NOT-NULL
    # FKs (PG FK checks bypass RLS — the P3-5 principal finding; the return-binder precedent).
    from irp_shared.reference.guards import assert_instrument_in_tenant  # no service cycle

    assert_portfolio_in_tenant(
        session, portfolio_id, acting_tenant=acting_tenant, error=PacingInputError
    )
    assert_instrument_in_tenant(
        session, instrument_id, acting_tenant=acting_tenant, error=PacingInputError
    )

    unfunded = committed - paid_in + recallable_returned
    if unfunded < 0 or unfunded > committed:
        raise PacingInputError(
            f"incoherent book: unfunded {unfunded} is outside [0, committed {committed}] "
            f"(paid-in {paid_in}, recallable-returned {recallable_returned}) — refused"
        )
    if nav_seed is None:
        # The canonical TA new-commitment case anchors NAV(0)=0 iff nothing has been called; a
        # funded position with no mark would fabricate the anchor — the honesty refusal.
        if paid_in != 0:
            raise PacingInputError(
                f"a funded commitment (paid-in {paid_in}) has no pinned valuation mark — cannot "
                f"anchor NAV without fabricating it; capture a mark first"
            )
        nav_seed = Decimal("0")

    as_of = snapshot.as_of_valuation_date
    if as_of < commitment_date:
        raise PacingInputError(
            f"the snapshot as-of {as_of} predates the commitment date {commitment_date} — "
            f"incoherent projection anchor"
        )
    current_age = _complete_annual_periods(commitment_date, as_of)
    return _Anchor(
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        currency_code=currency,
        commitment_date=commitment_date,
        as_of=as_of,
        current_age=current_age,
        unfunded=unfunded,
        nav=nav_seed,
    )


#: The magnitude envelope: a projected value beyond this is the post-create FAILED gate (a declared
#: parameter set can compound NAV past any sane book — a committed FAILED run + a named reason).
_MAX_ABS = Decimal("1e26")


def run_pacing_projection(
    session: Session,
    *,
    acting_tenant: str,
    actor: PacingActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    snapshot_id: str,
) -> PacingRunResult:
    """Run a governed commitment-pacing projection over a ``PACING_INPUT`` snapshot. Consume-only
    (the caller builds the snapshot via ``build_pacing_snapshot``). Adjudicates the pinned content
    + the anchor pre-create; past-fund-life is a pre-create refusal (nothing to project); the
    magnitude envelope is the sole post-create FAILED gate."""
    if not code_version:
        raise PacingInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise PacingInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise PacingInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise PacingInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    if not snapshot_id:
        raise PacingInputError("snapshot_id is required (consume-only)")

    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=PACING_MODEL_CODE,
    )
    params = declared_pacing_parameters(session, version)

    snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
    if snapshot.purpose != PURPOSE_PACING_INPUT:
        raise PacingInputError(
            f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_PACING_INPUT}"
        )

    anchor = _adjudicate_anchor(session, snapshot, acting_tenant=acting_tenant)
    if anchor.current_age >= params.fund_life:
        raise PacingInputError(
            f"commitment is past fund life (age {anchor.current_age} >= L {params.fund_life}) — "
            f"nothing to project"
        )

    kernel_anchor = PacingAnchor(
        current_age=anchor.current_age, unfunded=anchor.unfunded, nav=anchor.nav
    )
    try:
        periods = project_commitment(params, kernel_anchor)
    except (
        PacingKernelError
    ) as exc:  # defense-in-depth (the registrar already validated the domain)
        raise PacingInputError(f"pacing projection domain error: {exc}") from exc

    def _compute(run: CalculationRun) -> tuple[list[PacingProjectionResult], list[str]]:
        gaps: list[str] = []
        rows: list[PacingProjectionResult] = []
        for p in periods:
            for name, val in (
                ("projected_call", p.projected_call),
                ("projected_distribution", p.projected_distribution),
                ("projected_nav", p.projected_nav),
                ("unfunded_end", p.unfunded_end),
            ):
                if abs(val) > _MAX_ABS:
                    gaps.append(
                        f"period {p.period_index} {name} magnitude {val} exceeds the "
                        f"reproducible envelope (declared growth/bow compound NAV out of range)"
                    )
            start, end = anniversary_window(anchor.commitment_date, p.period_index)
            rows.append(
                PacingProjectionResult(
                    tenant_id=str(acting_tenant),
                    calculation_run_id=run.run_id,
                    input_snapshot_id=snapshot.id,
                    model_version_id=str(model_version_id),
                    portfolio_id=anchor.portfolio_id,
                    instrument_id=anchor.instrument_id,
                    period_index=p.period_index,
                    period_start=start,
                    period_end=end,
                    projected_call=p.projected_call,
                    projected_distribution=p.projected_distribution,
                    projected_nav=p.projected_nav,
                    unfunded_end=p.unfunded_end,
                    currency_code=anchor.currency_code,
                )
            )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=acting_tenant,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_PACING_PROJECTION,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code="pacing.projection.presence",
        rule_name="pacing projection produced in-envelope rows",
        rule_target_entity_type="pacing_projection_result",
        result_entity_type="pacing_projection_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return PacingRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


# --- reads: run-centric (by id) + the rule-7 entity/time-centric (portfolio/instrument/as-of) ---


def list_pacing_rows(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[PacingProjectionResult]:
    """The projected period rows of ONE run (tenant-scoped, ordered by ``period_index``)."""
    return list(
        session.execute(
            select(PacingProjectionResult)
            .where(
                PacingProjectionResult.calculation_run_id == str(run_id),
                PacingProjectionResult.tenant_id == str(acting_tenant),
            )
            .order_by(PacingProjectionResult.period_index)
        )
        .scalars()
        .all()
    )


def resolve_pacing_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve a pacing ``calculation_run`` by id (tenant-predicate + run_type filter). Surfaces a
    committed FAILED run. Raises :class:`PacingRunNotVisible`."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_PACING_PROJECTION,
        not_visible=PacingRunNotVisible,
    )


def resolve_pacing_row(
    session: Session, result_id: str, *, acting_tenant: str
) -> PacingProjectionResult:
    row = session.execute(
        select(PacingProjectionResult).where(
            PacingProjectionResult.id == str(result_id),
            PacingProjectionResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise PacingNotVisible(str(result_id))
    return row


def list_pacing_projections(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
    as_of=None,  # noqa: ANN001  (datetime | None — the rule-7 time filter)
) -> list[PacingProjectionResult]:
    """The rule-7 entity/time-centric read (OD-CC-2-F): projected rows across COMPLETED runs for the
    (portfolio, instrument) pair, optionally as of a run cutoff. FLAT rows each carrying
    ``calculation_run_id`` + ``model_version_id``; total ordering (run ``system_from`` DESC, run_id
    DESC, ``period_index`` ASC). Cross-run aggregation is a CONSUMER ERROR (a pair may hold several
    runs, e.g. successive versions). Silent-empty on an unknown/foreign id (the positions/valuations
    entity-filter precedent). ``as_of=None`` means now."""
    stmt = (
        select(PacingProjectionResult)
        .join(
            CalculationRun,
            CalculationRun.run_id == PacingProjectionResult.calculation_run_id,
        )
        .where(
            PacingProjectionResult.tenant_id == str(acting_tenant),
            CalculationRun.status == "COMPLETED",
        )
    )
    if portfolio_id is not None:
        stmt = stmt.where(PacingProjectionResult.portfolio_id == str(portfolio_id))
    if instrument_id is not None:
        stmt = stmt.where(PacingProjectionResult.instrument_id == str(instrument_id))
    if as_of is not None:
        stmt = stmt.where(CalculationRun.system_from <= as_of)
    stmt = stmt.order_by(
        CalculationRun.system_from.desc(),
        CalculationRun.run_id.desc(),
        PacingProjectionResult.period_index.asc(),
    )
    return list(session.execute(stmt).scalars().all())


def latest_pacing_projection(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    instrument_id: str,
    as_of=None,  # noqa: ANN001  (datetime | None)
) -> list[PacingProjectionResult]:
    """The platform's FIRST latest-resolver (OD-CC-2-F): the newest COMPLETED projection run for the
    pair (across ALL model versions — "current" = the latest run), as of an optional run cutoff, as
    its period rows ordered by ``period_index``. Empty when none. The ``as_of``-aware read IS the
    latest-resolver — ``as_of=None`` means now (ONE code path via ``list_pacing_projections``)."""
    rows = list_pacing_projections(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        as_of=as_of,
    )
    if not rows:
        return []
    latest_run_id = rows[0].calculation_run_id  # rows are run-DESC ordered; the first is newest
    return [r for r in rows if r.calculation_run_id == latest_run_id]
