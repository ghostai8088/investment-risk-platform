"""Portfolio-return (time-weighted, Modified-Dietz) binder (PM-1, ENT-053 — the SEVENTH governed
number and the FIRST non-risk one; the risk binders' PEER, not a descendant).

``run_portfolio_return`` produces the ``portfolio_return_result`` series (``n`` ``DIETZ_PERIOD``
sub-period rows + ONE ``TWR_LINKED`` summary row) ONLY when bound to a ``dataset_snapshot``
(``RETURN_INPUT`` — pinning the EXPOSURE atoms of the ``N >= 2`` boundary runs + the in-window
``transaction`` rows + the per-flow FX legs) + a complete ``calculation_run`` + a **REGISTERED
``model_version`` OF THE PORTFOLIO-RETURN MODEL** (``perf.return.twr`` v1; AD-014 / FW-RUN / TR-15 /
CTRL-003 — the ``run_active_risk`` exemplar). The model carries NO free numeric parameter
(OD-PM-1-D): the registered ``code_version`` + the fixed v1 conventions ARE the identity.

The number is the chain-linked time-weighted return (``irp_shared.perf.return_kernel``): per
sub-period ``r_i = (EMV_i - BMV_i - F_i) / (BMV_i + Σ_j w_ij·F_ij)`` (Modified Dietz, end-of-day
weights) and
``R = Π_i(1 + r_i) - 1`` (geometric linking). The binder's own arithmetic over the PINNED content
(PURE — no live read, the AD-014 invariant): market values are the summed pinned ``exposure_amount``
per boundary run; external flows are the pinned ``TRANSFER_IN``/``TRANSFER_OUT`` transactions,
gross-amount converted to base currency via the pinned FX legs at each flow's ``trade_date``.

**v1 scope: a SINGLE-portfolio book.** All pinned atoms must resolve to ONE ``portfolio_id`` (a
multi-portfolio / subtree book is refused — deferred, because an intra-subtree transfer between two
child portfolios is INTERNAL, not an external flow, and that classification is its own slice). The
boundary VALUATION DATES are read from each boundary run's IMMUTABLE ``EXPOSURE_INPUT`` snapshot
(pre-create, drift-free by construction — the ``run_active_risk`` run re-resolution pattern), so the
result reproduces from the pinned content + those immutable headers.

Reproducibility (AD-014): the COMPUTE reads ONLY the snapshot's pinned content — a later exposure
re-run OR a transaction appended after the snapshot cannot move a historical return (test-proven,
TR-09).

Failure model (the P3-7 precedent — UNIFORM across BOTH entry paths):
- **Pre-create refusal** (missing prerequisites; an unregistered or WRONG-MODEL version; a
  non-COMPLETED / cross-tenant / non-exposure boundary run; a wrong-purpose snapshot; **pinned
  content that is not a well-formed v1 input** — fewer than two boundaries, DUPLICATE boundary
  dates (the binder ORDERS boundaries by valuation date, so caller order is irrelevant; only equal
  dates — a zero-length sub-period — refuse), a multi-portfolio book, a NULL/blank flow currency or
  amount, a missing FX leg for
  a flow, a non-positive begin MV or Modified-Dietz denominator, or JSON-null/non-object fields):
  **raise BEFORE ``create_run``** => ZERO run + ZERO rows + ZERO run-audit. **NO imputation, ever.**
- **Post-create FAILED** (a column-legal-but-extreme pin whose per-sub-period or linked return
  exceeds the ``Numeric(20,12)`` column envelope ``|value| < 1E8`` — REACHABLE via a hand-minted
  snapshot, e.g. BMV 1 -> EMV 1E10 => return ~1E10; the compute checks ``abs(return) >=
  _MAX_RESULT_ABS`` and ``abs(total_flow) >= _MAX_EVIDENCE_ABS`` explicitly, since the kernel's
  12dp-quantize guard bounds only the SCALE and trips ~1E38, far above the column): a committed
  FAILED run (``outcome='failure'``) + ``DATA.VALIDATE`` DQ evidence + ZERO rows + a
  magnitude-naming ``failure_reason``.
- **Emit-path** raises propagate => the whole unit rolls back co-transactionally (CTRL-032).

One-way imports: ``perf -> {snapshot, marketdata, calc, model, lineage, dq, audit, db}`` + a
models-only ``portfolio.models`` read (the measured-book tenant re-resolution — the snapshot
``exposure``/``transaction`` models-only precedent); imports NO ``risk`` symbol and NO ``exposure``
symbol (the boundary-run ``run_type`` is a fence-kept local constant, sync-tested); nothing imports
``perf``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata import DEFAULT_BASE, compose_effective_rate
from irp_shared.model.service import assert_model_version_of
from irp_shared.perf.bootstrap import PORTFOLIO_RETURN_MODEL_CODE
from irp_shared.perf.events import (
    EXTERNAL_FLOW_TXN_TYPES,
    FLOW_TXN_TYPE_TRANSFER_IN,
    RUN_TYPE_PORTFOLIO_RETURN,
    PortfolioReturnActor,
)
from irp_shared.perf.models import (
    METRIC_TYPE_DIETZ_PERIOD,
    METRIC_TYPE_TWR_LINKED,
    PortfolioReturnResult,
)
from irp_shared.perf.return_kernel import (
    ReturnKernelError,
    compute_dietz_period,
    dietz_denominator,
    link_periods,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_EXPOSURE,
    COMPONENT_KIND_FX,
    COMPONENT_KIND_TRANSACTION,
    PURPOSE_RETURN_INPUT,
    SnapshotActor,
    build_return_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the P3-1/3/4/5/7 pattern).
_COMPLETENESS_RULE_CODE = "perf.portfolio_return.completeness"
#: The boundary runs' ``calculation_run.run_type``. A fence-kept LOCAL copy of
#: ``exposure.events.RUN_TYPE_EXPOSURE_AGGREGATE`` — ``perf`` must not import ``exposure`` (the
#: peer-family fence); a sync test asserts the two strings stay equal.
_EXPOSURE_RUN_TYPE = "EXPOSURE_AGGREGATE"
#: Source-column magnitude bounds: a pinned value EXCEEDING its origin column's envelope cannot be a
#: genuine governed/captured row (exposure_amount Numeric(28,6) < 1E22; gross_amount Numeric(20,6) <
#: 1E14) — refused pre-create so the summed MV / net-flow EVIDENCE never overflows its Numeric(28,6)
#: column (the P3-7 precedent).
_MAX_EXPOSURE_ABS = Decimal("1E22")
_MAX_FLOW_ABS = Decimal("1E14")
#: The Numeric(28,6) evidence-column envelope (begin_mv/end_mv/net_external_flow): the summed value
#: is refused pre-create if it exceeds the column so the stored evidence never overflows.
_MAX_EVIDENCE_ABS = Decimal("1E22")
#: The return_value column envelope (Numeric(20,12) => |value| < 1E8): a column-legal-but-extreme
#: pin (e.g. BMV 1 -> EMV 1E10) can drive a per-sub-period OR linked return past the column WITHOUT
#: the kernel's 12dp-quantize guard firing (that guard only trips at ~1E38, the prec-50 ceiling).
#: Gate it into a committed FAILED run (the P3-7 _MAX_RESULT_ABS precedent), never a PG overflow.
_MAX_RESULT_ABS = Decimal("1E7")
#: Compute precision for the MV/flow accumulation + active-capital construction (the kernel's
#: 50-digit precedent, so the aggregates are derived at the same fidelity).
_COMPUTE_PREC = 50


class PortfolioReturnInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class (a perf number never borrows a risk error). Maps to
    422."""


class PortfolioReturnNotVisible(Exception):
    """Raised when a ``portfolio_return_result`` id is not visible in the acting tenant scope."""

    def __init__(self, result_id: str) -> None:
        super().__init__(
            f"portfolio_return_result {result_id} is not visible in the current tenant"
        )
        self.result_id = str(result_id)


class PortfolioReturnRunNotVisible(Exception):
    """Raised when a portfolio-return ``calculation_run`` id is not visible in the acting tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"portfolio-return run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class PortfolioReturnRunResult:
    """The outcome of ``run_portfolio_return``: the ``calculation_run`` + status + the series rows.
    ``status`` is ``COMPLETED`` (``rows`` = the ``n`` DIETZ_PERIOD rows + the TWR_LINKED row) or
    ``FAILED`` (the magnitude gate: a committed FAILED run + ZERO rows + a naming
    ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[PortfolioReturnResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _SubPeriod:
    """One adjudicated Modified-Dietz sub-period: the kernel arguments (``begin_mv``/``end_mv``/
    ``flows`` as ``(day_offset, signed_base_amount)``/``period_days``) + the row evidence."""

    period_start: date
    period_end: date
    begin_mv: Decimal
    end_mv: Decimal
    flows: list[tuple[int, Decimal]]
    period_days: int
    net_external_flow: Decimal
    n_flows: int


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned input: the ordered sub-periods + the run-uniform descriptors + the
    linked-row evidence."""

    sub_periods: list[_SubPeriod]
    portfolio_id: str
    base_currency: str


def _is_present_currency(value: Any) -> bool:
    """A captured currency is PRESENT only if it is a non-blank string (NULL and empty/whitespace
    are the same named-gap refusal — the P3-7 ``_is_present_currency`` rule; no imputation)."""
    return isinstance(value, str) and bool(value.strip())


def _parse_pins(
    comps: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw exposure/transaction/fx row dicts (PURE — no
    live read; the AD-014 invariant)."""
    exposure_raw: list[dict[str, Any]] = []
    transaction_raw: list[dict[str, Any]] = []
    fx_raw: list[dict[str, Any]] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_EXPOSURE:
            exposure_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_TRANSACTION:
            transaction_raw.append(data)
        elif comp.component_kind == COMPONENT_KIND_FX:
            fx_raw.append(data)
    return exposure_raw, transaction_raw, fx_raw


def _convert_flow_to_base(
    amount: Decimal,
    ccy: str,
    trade_date_iso: str,
    base_currency: str,
    fx_raw: list[dict[str, Any]],
) -> Decimal:
    """Convert one flow's ``gross_amount`` (in ``ccy``) to ``base_currency`` PURELY over the pinned
    FX legs whose ``rate_date`` == the flow's ``trade_date`` (the builder pinned the full conversion
    path at that date). Identity when ``ccy == base_currency``. Raises
    :class:`PortfolioReturnInputError`
    if no pinned path exists for that date (a missing FX leg fails closed — no imputation)."""
    if ccy == base_currency:
        return amount
    rate_map: dict[tuple[str, str], tuple[str, Decimal]] = {}
    for d in fx_raw:
        if d["rate_date"] != trade_date_iso:
            continue
        rate_map[(d["base_currency"], d["quote_currency"])] = (str(d["id"]), Decimal(d["rate"]))
    composed = compose_effective_rate(
        rate_map, from_currency=ccy, to_currency=base_currency, base=DEFAULT_BASE
    )
    if composed is None:
        raise PortfolioReturnInputError(
            f"no pinned FX leg converts {ccy} -> {base_currency} on {trade_date_iso} — refused "
            f"(no imputation)"
        )
    effective, _legs = composed
    return amount * effective


def _adjudicate_pins(
    exposure_raw: list[dict[str, Any]],
    transaction_raw: list[dict[str, Any]],
    fx_raw: list[dict[str, Any]],
    boundary_dates: dict[str, date],
) -> _ParsedInput:
    """PRE-CREATE adjudication of the FULL pinned input (both entry paths): a single-portfolio book;
    ``N >= 2`` boundary runs mapped to STRICTLY-ORDERED distinct valuation dates; the per-run market
    values (summed pinned ``exposure_amount``); the in-window ``TRANSFER_IN``/``TRANSFER_OUT`` flows
    bucketed into sub-periods and FX-converted to base; and the Modified-Dietz preconditions
    (``begin_mv > 0`` and the average-capital denominator ``> 0``) per sub-period. Raises
    :class:`PortfolioReturnInputError` on any ill-formed input. ``boundary_dates`` maps each
    boundary run id (lowercase) to its (immutable) valuation date, resolved pre-create by the
    caller."""
    if not exposure_raw:
        raise PortfolioReturnInputError(
            "the snapshot pins no EXPOSURE atoms — not a portfolio-return input"
        )

    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        # --- Market value per boundary run + single-portfolio / single-base scope. ---
        mv_by_run: dict[str, Decimal] = {}
        exposure_ids_seen: set[str] = set()
        portfolio_ids: set[str] = set()
        base_currencies: set[str] = set()
        for r in exposure_raw:
            rid = str(r["id"]).lower()
            if rid in exposure_ids_seen:  # a duplicated pin would double-count a boundary MV
                raise PortfolioReturnInputError(f"duplicate pinned exposure atom {rid} — refused")
            exposure_ids_seen.add(rid)
            run_id = str(r["calculation_run_id"]).lower()
            amount = Decimal(r["exposure_amount"])
            if abs(amount) >= _MAX_EXPOSURE_ABS:
                raise PortfolioReturnInputError(
                    "a pinned exposure_amount exceeds its source-column envelope — refused"
                )
            mv_by_run[run_id] = mv_by_run.get(run_id, Decimal(0)) + amount
            portfolio_ids.add(str(r["portfolio_id"]))
            base_currencies.add(r["base_currency"])

        if len(portfolio_ids) != 1:
            raise PortfolioReturnInputError(
                f"the pinned atoms span {len(portfolio_ids)} portfolios — v1 measures a SINGLE "
                f"portfolio (a subtree book is deferred; refused)"
            )
        portfolio_id = next(iter(portfolio_ids))
        if len(base_currencies) != 1:
            raise PortfolioReturnInputError(
                f"the pinned atoms carry mixed base currencies {sorted(base_currencies)} — refused"
            )
        base_currency = next(iter(base_currencies))
        if not isinstance(base_currency, str) or len(base_currency) != 3:
            raise PortfolioReturnInputError(
                "the pinned exposure base_currency is not a 3-letter code — refused"
            )

        # --- The N boundaries: each pinned run needs a resolved valuation date; order strictly. ---
        if len(mv_by_run) < 2:
            raise PortfolioReturnInputError(
                f"a portfolio return needs >= 2 boundary runs (got {len(mv_by_run)}) — refused"
            )
        for run_id, mv in mv_by_run.items():
            if run_id not in boundary_dates:
                raise PortfolioReturnInputError(
                    f"boundary run {run_id} has no resolved valuation date — refused"
                )
            if abs(mv) >= _MAX_EVIDENCE_ABS:
                raise PortfolioReturnInputError(
                    "a boundary market value exceeds its evidence-column envelope — refused"
                )
        # Order boundaries by valuation date; a duplicate date = a zero-length sub-period = refused.
        ordered = sorted(mv_by_run.keys(), key=lambda rid: boundary_dates[rid])
        ordered_dates = [boundary_dates[rid] for rid in ordered]
        if len(set(ordered_dates)) != len(ordered_dates):
            raise PortfolioReturnInputError(
                "two boundary runs share a valuation date — a zero-length sub-period; refused"
            )

        # --- Bucket the external flows into sub-periods (half-open (start, end]); FX-convert. ---
        n_periods = len(ordered) - 1
        flows_by_period: dict[int, list[tuple[int, Decimal]]] = {i: [] for i in range(n_periods)}
        for t in transaction_raw:
            if t["txn_type"] not in EXTERNAL_FLOW_TXN_TYPES:
                continue  # internal to the book (BUY/SELL/DIVIDEND/INTEREST/FEE/REVERSAL/...)
            trade_date = date.fromisoformat(t["trade_date"])
            # Find the sub-period i with ordered_dates[i] < trade_date <= ordered_dates[i+1].
            period_idx: int | None = None
            for i in range(n_periods):
                if ordered_dates[i] < trade_date <= ordered_dates[i + 1]:
                    period_idx = i
                    break
            if period_idx is None:
                continue  # outside the measured span (the builder pins (first, last]; be robust)
            gross = t["gross_amount"]
            ccy = t["currency_code"]
            if gross is None or not _is_present_currency(ccy):
                raise PortfolioReturnInputError(
                    f"external flow {t['id']} has a NULL/blank amount or currency — refused "
                    f"(no imputation)"
                )
            amount = Decimal(gross)
            if abs(amount) >= _MAX_FLOW_ABS:
                raise PortfolioReturnInputError(
                    "a pinned flow gross_amount exceeds its source-column envelope — refused"
                )
            signed = amount if t["txn_type"] == FLOW_TXN_TYPE_TRANSFER_IN else -amount
            signed_base = _convert_flow_to_base(signed, ccy, t["trade_date"], base_currency, fx_raw)
            day_offset = (trade_date - ordered_dates[period_idx]).days  # 1..period_days (half-open)
            flows_by_period[period_idx].append((day_offset, signed_base))

        # --- Build + precondition-check each sub-period (BMV > 0; avg-capital denominator > 0). ---
        sub_periods: list[_SubPeriod] = []
        for i in range(n_periods):
            begin_mv = mv_by_run[ordered[i]]
            end_mv = mv_by_run[ordered[i + 1]]
            period_days = (ordered_dates[i + 1] - ordered_dates[i]).days
            flows = flows_by_period[i]
            if begin_mv <= 0:
                raise PortfolioReturnInputError(
                    f"sub-period {ordered_dates[i]}..{ordered_dates[i + 1]} has a non-positive "
                    f"begin market value ({begin_mv}) — a return over zero/negative capital is "
                    f"undefined; refused"
                )
            try:
                denom = dietz_denominator(begin_mv, flows, period_days)
            except ReturnKernelError as exc:
                raise PortfolioReturnInputError(
                    f"sub-period {ordered_dates[i]}..{ordered_dates[i + 1]} is ill-formed ({exc})"
                ) from exc
            if denom <= 0:
                raise PortfolioReturnInputError(
                    f"sub-period {ordered_dates[i]}..{ordered_dates[i + 1]} has a non-positive "
                    f"Modified-Dietz denominator ({denom}) — undefined; refused"
                )
            net_flow = sum((amt for _off, amt in flows), Decimal(0))
            if abs(net_flow) >= _MAX_EVIDENCE_ABS:
                raise PortfolioReturnInputError(
                    "a sub-period net external flow exceeds its evidence-column envelope — refused"
                )
            sub_periods.append(
                _SubPeriod(
                    period_start=ordered_dates[i],
                    period_end=ordered_dates[i + 1],
                    begin_mv=begin_mv,
                    end_mv=end_mv,
                    flows=flows,
                    period_days=period_days,
                    net_external_flow=net_flow,
                    n_flows=len(flows),
                )
            )

    return _ParsedInput(
        sub_periods=sub_periods, portfolio_id=portfolio_id, base_currency=base_currency
    )


def _assert_portfolio_in_tenant(session: Session, portfolio_id: str, *, acting_tenant: str) -> None:
    """Re-resolve the measured book's ``portfolio_id`` under the acting tenant with an EXPLICIT
    tenant predicate (models-only import — the snapshot ``exposure``/``transaction`` precedent; the
    ``portfolio`` SERVICE is not imported, keeping the perf fence). Raises
    :class:`PortfolioReturnInputError` if the id is not visible in the acting tenant — a
    FOREIGN/non-existent portfolio_id (from a hand-minted snapshot's atom JSON) must never be
    stamped into the NOT-NULL ``portfolio`` FK (P3-5 principal finding)."""
    from irp_shared.portfolio.models import Portfolio  # models-only (no cycle / fence-safe)

    row = session.execute(
        select(Portfolio).where(
            Portfolio.id == str(portfolio_id),
            Portfolio.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise PortfolioReturnInputError(
            f"the measured portfolio {portfolio_id} is not visible in the acting tenant — refused"
        )


def _resolve_boundary_dates(
    session: Session, run_ids: set[str], *, acting_tenant: str
) -> dict[str, date]:
    """Re-resolve each distinct boundary ``calculation_run`` (tenant + ``run_type`` EXPOSURE +
    COMPLETED) and read its IMMUTABLE input snapshot's ``as_of_valuation_date`` (pre-create — the
    security gate against a hand-minted snapshot referencing a FOREIGN tenant's runs AND the
    boundary-date source; PG FK checks bypass RLS). Returns run id (lowercase) -> valuation date.
    Raises :class:`PortfolioReturnInputError` on a hidden/non-exposure/non-COMPLETED run."""
    dates: dict[str, date] = {}
    for run_id in run_ids:
        run = session.execute(
            select(CalculationRun).where(
                CalculationRun.run_id == str(run_id),
                CalculationRun.tenant_id == str(acting_tenant),
                CalculationRun.run_type == _EXPOSURE_RUN_TYPE,
            )
        ).scalar_one_or_none()
        if run is None:
            raise PortfolioReturnInputError(
                f"boundary run {run_id} is not a visible COMPLETED exposure run — refused"
            )
        if run.status != RunStatus.COMPLETED.value:
            raise PortfolioReturnInputError(
                f"boundary exposure run {run_id} status {run.status!r} != COMPLETED — refused"
            )
        if run.input_snapshot_id is None:
            raise PortfolioReturnInputError(
                f"boundary exposure run {run_id} has no input snapshot — refused"
            )
        boundary = resolve_snapshot(
            session, str(run.input_snapshot_id), acting_tenant=acting_tenant
        )
        dates[str(run_id).lower()] = boundary.as_of_valuation_date
    return dates


def run_portfolio_return(
    session: Session,
    *,
    acting_tenant: str,
    actor: PortfolioReturnActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    exposure_run_ids: list[str] | None = None,
    snapshot_id: str | None = None,
) -> PortfolioReturnRunResult:
    """Run a governed portfolio-return calculation. Build-in-request (default —
    ``exposure_run_ids``: an ORDERED list of ``N >= 2`` COMPLETED exposure runs, builds a
    ``RETURN_INPUT`` snapshot pinning their atoms + the in-window transactions + the flow FX legs)
    or consume-existing (``snapshot_id``).
    BOTH paths adjudicate the pinned content pre-create. See the module docstring for the failure
    model + the AD-014 / CTRL-003 invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise PortfolioReturnInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise PortfolioReturnInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise PortfolioReturnInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise PortfolioReturnInputError(
            "model_version_id is required (CTRL-003 inventory-before-use)"
        )
    if snapshot_id is not None and exposure_run_ids is not None:
        # An ambiguous request (both input modes) must be refused, never silently preferred (the
        # P3-C1 OD-G lesson).
        raise PortfolioReturnInputError(
            "ambiguous input — pass either snapshot_id or exposure_run_ids, not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3): the version must be REGISTERED and OF
    # the portfolio-return model. The v1 model carries NO numeric parameter (OD-PM-1-D).
    assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=PORTFOLIO_RETURN_MODEL_CODE,
    )

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_RETURN_INPUT:
            raise PortfolioReturnInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != {PURPOSE_RETURN_INPUT}"
            )
    else:
        if not exposure_run_ids or len(exposure_run_ids) < 2:
            raise PortfolioReturnInputError(
                "exposure_run_ids (>= 2 boundary runs) are required to build a return snapshot"
            )
        # Validate each boundary run pre-build (COMPLETED + visible + an exposure run).
        _resolve_boundary_dates(
            session, {str(rid) for rid in exposure_run_ids}, acting_tenant=acting_tenant
        )
        snapshot = build_return_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            exposure_run_ids=[str(rid) for rid in exposure_run_ids],
            flow_txn_types=EXTERNAL_FLOW_TXN_TYPES,
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths). ---
    try:
        exposure_raw, transaction_raw, fx_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        # Re-resolve the boundary runs FROM the pinned atoms (security gate + boundary dates). On
        # the build path this is an idempotent tautology.
        boundary_run_ids = {str(r["calculation_run_id"]).lower() for r in exposure_raw}
        boundary_dates = _resolve_boundary_dates(
            session, boundary_run_ids, acting_tenant=acting_tenant
        )
        parsed = _adjudicate_pins(exposure_raw, transaction_raw, fx_raw, boundary_dates)
    except PortfolioReturnInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content (missing keys, non-decimal/JSON-null values, bad
        # dates, non-object captured_content) is the SAME refusal class as a semantically ill-formed
        # input — a governed 422, never a raw parse 500 (the P3-7 TypeError-inclusive wrapper).
        raise PortfolioReturnInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # The measured book's ``portfolio_id`` comes from the pinned atom JSON — re-resolve it under the
    # acting tenant BEFORE it is stamped into the NOT-NULL ``portfolio`` FK. PG FK checks bypass
    # RLS, so a hand-minted snapshot carrying a FOREIGN/non-existent portfolio_id would durably
    # reference another tenant's row (+ a cross-tenant existence oracle) or 500 at flush — the P3-5
    # principal finding, extended to this FK (the active-risk run re-resolution precedent).
    _assert_portfolio_in_tenant(session, parsed.portfolio_id, acting_tenant=acting_tenant)

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[PortfolioReturnResult], list[str]]:
        gaps: list[str] = []
        period_returns: list[Decimal] = []
        rows: list[PortfolioReturnResult] = []
        try:
            for sp in parsed.sub_periods:
                estimate = compute_dietz_period(sp.begin_mv, sp.end_mv, sp.flows, sp.period_days)
                # The kernel's 12dp-quantize guard bounds the SCALE, not the integer magnitude, so
                # it only trips at ~1E38 (the prec-50 ceiling) — far above the Numeric(20,12) column
                # (|value| < 1E8). Gate the column envelope HERE so a column-legal-but-extreme pin
                # (e.g. BMV 1 -> EMV 1E10 => return ~1E10) is a committed FAILED run, never a PG
                # NUMERIC-overflow 500 / a silent SQLite garbage row (the ultrareview finding).
                if abs(estimate.return_value) >= _MAX_RESULT_ABS:
                    gaps.append(f"magnitude-out-of-range:period:{estimate.return_value:E}")
                    return [], gaps
                period_returns.append(estimate.return_value)
                rows.append(
                    PortfolioReturnResult(
                        tenant_id=str(acting_tenant),
                        calculation_run_id=run.run_id,
                        input_snapshot_id=snapshot.id,
                        model_version_id=str(model_version_id),
                        portfolio_id=parsed.portfolio_id,
                        metric_type=METRIC_TYPE_DIETZ_PERIOD,
                        period_start=sp.period_start,
                        period_end=sp.period_end,
                        begin_mv=sp.begin_mv,
                        end_mv=sp.end_mv,
                        net_external_flow=sp.net_external_flow,
                        return_value=estimate.return_value,
                        n_flows=sp.n_flows,
                        n_periods=1,
                        base_currency=parsed.base_currency,
                    )
                )
            linked = link_periods(period_returns)
        except ReturnKernelError as exc:
            # The prec-50 quantize backstop: a genuinely astronomical (>= ~1E38) swing that even the
            # column-envelope gate above did not pre-empt — a committed FAILED run, never a 500.
            gaps.append(f"magnitude-out-of-range:{exc}")
            return [], gaps
        first, last = parsed.sub_periods[0], parsed.sub_periods[-1]
        # Sum at compute precision (a column-legal per-period flow can carry 22 sig digits; the
        # default 28-digit context could silently round an N-period aggregate).
        with localcontext() as ctx:
            ctx.prec = _COMPUTE_PREC
            total_flow = sum((sp.net_external_flow for sp in parsed.sub_periods), Decimal(0))
        # Gate the linked magnitude + the aggregate net-flow evidence into a FAILED run, never a
        # column overflow (the per-period values are gated pre-create; their SUM/link is not).
        if abs(linked) >= _MAX_RESULT_ABS:
            gaps.append(f"magnitude-out-of-range:linked:{linked:E}")
            return [], gaps
        if abs(total_flow) >= _MAX_EVIDENCE_ABS:
            gaps.append(f"magnitude-out-of-range:total-flow:{total_flow:E}")
            return [], gaps
        rows.append(
            PortfolioReturnResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                portfolio_id=parsed.portfolio_id,
                metric_type=METRIC_TYPE_TWR_LINKED,
                period_start=first.period_start,
                period_end=last.period_end,
                begin_mv=first.begin_mv,
                end_mv=last.end_mv,
                net_external_flow=total_flow,
                return_value=linked,
                n_flows=sum(sp.n_flows for sp in parsed.sub_periods),
                n_periods=len(parsed.sub_periods),
                base_currency=parsed.base_currency,
            )
        )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_PORTFOLIO_RETURN,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="portfolio-return run output sanity (return within the Numeric(20,12) scale)",
        rule_target_entity_type="portfolio_return_result",
        result_entity_type="portfolio_return_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return PortfolioReturnRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_portfolio_returns(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[PortfolioReturnResult]:
    """The ``portfolio_return_result`` rows of a run (tenant-scoped; the DIETZ_PERIOD series then
    the TWR_LINKED row, ordered by (metric_type, period_start))."""
    return list(
        session.execute(
            select(PortfolioReturnResult)
            .where(
                PortfolioReturnResult.calculation_run_id == str(run_id),
                PortfolioReturnResult.tenant_id == str(acting_tenant),
            )
            .order_by(PortfolioReturnResult.metric_type, PortfolioReturnResult.period_start)
        )
        .scalars()
        .all()
    )


def resolve_portfolio_return_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a portfolio-return ``calculation_run`` by ``run_id`` with an EXPLICIT tenant
    predicate + ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable
    refusal
    evidence). Raises :class:`PortfolioReturnRunNotVisible` on a hidden/unknown/non-return run."""
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_PORTFOLIO_RETURN,
        )
    ).scalar_one_or_none()
    if run is None:
        raise PortfolioReturnRunNotVisible(str(run_id))
    return run


def resolve_portfolio_return(
    session: Session, result_id: str, *, acting_tenant: str
) -> PortfolioReturnResult:
    """Resolve one ``portfolio_return_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(PortfolioReturnResult).where(
            PortfolioReturnResult.id == str(result_id),
            PortfolioReturnResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise PortfolioReturnNotVisible(str(result_id))
    return row
