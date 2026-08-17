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
risk/factor/scenario symbol. (The old "nothing imports ``exposure``" claim was retired in SCH-2 —
see the package docstring; the OUTBOUND fence stated here is the one that still holds.)
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
from irp_shared.exposure.models import (
    EXPOSURE_TYPE_MARKET_VALUE,
    EXPOSURE_TYPE_NOTIONAL,
    EXPOSURE_TYPES,
    ExposureAggregate,
)
from irp_shared.marketdata import (
    DEFAULT_BASE,
    compose_effective_rate,
    serialize_legs,
)
from irp_shared.portfolio import resolve_portfolio, resolve_reporting_currency
from irp_shared.snapshot import (
    COMPONENT_KIND_FX,
    COMPONENT_KIND_INSTRUMENT,
    COMPONENT_KIND_INSTRUMENT_TERMS,
    COMPONENT_KIND_PORTFOLIO,
    COMPONENT_KIND_POSITION,
    COMPONENT_KIND_VALUATION,
    NODE_FX_BINDING_PREDICATE,
    SUBTREE_BINDING_PREDICATE,
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

#: The mark_value column is Numeric(20,6) — 14 integer digits — while instrument_terms.face_value
#: is Numeric(20,4) — 16. A face value at or past this bound cannot be stored as the NOTIONAL
#: row's captured per-unit input; it is refused as a governed gap (P3-7 magnitude precedent).
_MAX_FACE_VALUE_ABS = Decimal("1E14")


class ExposureInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no exposure, no audit). Maps to 422."""


class UndeclaredReportingCurrencyError(ExposureInputError):
    """DP-11 (STRUCT-4, REQ-PPM-010): NOTHING up the scope's declaration chain names a reporting
    currency and no explicit ``base_currency`` was given. The pre-STRUCT-4 path silently computed
    such a book in USD — an undeclared ROOT now REFUSES, never defaults."""


class ReportingCurrencyConflictError(ExposureInputError):
    """STRUCT-4 (the planning row's override clause): an explicit ``base_currency`` on a
    node-scoped consume of a v3 snapshot CONTRADICTS the node's own declared reporting currency —
    refused rather than silently overriding a declaration the node carries."""


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
    """The build path's reporting/base currency (DP-11, STRUCT-4): the explicit arg (legal only
    when it MATCHES the declaration or nothing is declared — a contradicting override is refused
    on BOTH paths, or the consume-side conflict check makes the run irreproducible) → the scope
    node's DECLARED currency (its own ``base_currency_code``, else inherited from the nearest
    declared ancestor) → REFUSE. The pre-STRUCT-4 ``or DEFAULT_BASE`` tail is DEAD: an undeclared
    root never silently becomes a USD book. Resolving the portfolio also fails closed
    cross-tenant (PortfolioNotVisible ⇒ pre-create refusal)."""
    pf = resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)
    declared = resolve_reporting_currency(session, pf, acting_tenant=acting_tenant)
    if base_currency:
        # Review fold (the BLOCKING C9 class): the conflict refusal must be SYMMETRIC. A build
        # permitted to override a DECLARED root would mint a v3 run whose own CTRL-018
        # reproduction is then REFUSED by the consume-path conflict check (the adapter replays
        # the stored base at the stored node) — an irreproducible governed-run class. An
        # explicit base over an UNDECLARED scope stays legal (the pre-DP-11 books' path); a
        # different reporting view of a declared book is the READ-time translation's job.
        if declared is not None and declared != base_currency:
            raise ReportingCurrencyConflictError(
                f"base_currency {base_currency!r} contradicts the scope's declared reporting "
                f"currency {declared!r} — refused at build (REQ-PPM-010; the read-time "
                "translation serves other reporting views)"
            )
        return base_currency
    if declared is None:
        raise UndeclaredReportingCurrencyError(
            f"no reporting currency is declared on portfolio {portfolio_id} or any ancestor — "
            "an undeclared root REFUSES rather than defaulting (REQ-PPM-010/DP-11); declare "
            "base_currency_code on the root or pass base_currency explicitly"
        )
    return declared


@dataclass(frozen=True)
class _PinnedInputs:
    """The exposure compute's entire input surface, parsed from the snapshot's pinned components
    (PURE — no live read; AD-014). STRUCT-1 added the instrument identity/terms maps: a
    pre-STRUCT-1 snapshot simply has no INSTRUMENT/INSTRUMENT_TERMS components, so both maps are
    empty and the NOTIONAL producer emits nothing for it — which is what keeps the reproduction
    of pre-STRUCT-1 runs byte-identical (the measure is definitionally absent from their pinned
    inputs, never fabricated)."""

    positions: dict[tuple[str, str], Decimal]
    marks: dict[tuple[str, str], tuple[Decimal, str]]
    rate_map: dict[tuple[str, str], tuple[str, Decimal]]
    #: instrument_id -> asset_class (the pinned instrument EV identity; the DP-4 rule's input).
    asset_classes: dict[str, str]
    #: instrument_id -> (face_value | None, denomination_currency | None) from the pinned terms.
    terms: dict[str, tuple[Decimal | None, str | None]]
    #: STRUCT-4 (DP-12): the pivot a TRIANGULATED row's ``fx_legs`` should STATE — set only for a
    #: v3 snapshot. ``None`` reproduces the pre-STRUCT-4 byte shape exactly (fx_legs is a
    #: byte-compared reproduction field; legacy runs must re-emit identical bytes).
    stated_pivot: str | None = None


def _read_components(comps: list[Any], *, stated_pivot: str | None = None) -> _PinnedInputs:
    """Parse the snapshot's pinned components' captured content (PURE — no live read): positions
    ``(pf,inst)->qty``, marks ``(pf,inst)->(mark,ccy)``, fx ``(base,quote)->(id,rate)``, plus the
    STRUCT-1 instrument identity/terms maps. ``stated_pivot`` (STRUCT-4/DP-12) rides through to
    the emit path — the caller sets it ONLY for a v3 snapshot."""
    positions: dict[tuple[str, str], Decimal] = {}
    marks: dict[tuple[str, str], tuple[Decimal, str]] = {}
    rate_map: dict[tuple[str, str], tuple[str, Decimal]] = {}
    asset_classes: dict[str, str] = {}
    terms: dict[str, tuple[Decimal | None, str | None]] = {}
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
        elif comp.component_kind == COMPONENT_KIND_INSTRUMENT:
            asset_classes[data["id"]] = data["asset_class"]
        elif comp.component_kind == COMPONENT_KIND_INSTRUMENT_TERMS:
            terms[data["instrument_id"]] = (
                None if data["face_value"] is None else Decimal(data["face_value"]),
                data["denomination_currency"],
            )
    return _PinnedInputs(
        positions=positions,
        marks=marks,
        rate_map=rate_map,
        asset_classes=asset_classes,
        terms=terms,
        stated_pivot=stated_pivot,
    )


def _emit_row(
    *,
    exposure_type: str,
    unit_value: Decimal,
    unit_currency: str,
    pf: str,
    inst: str,
    qty: Decimal,
    inputs: _PinnedInputs,
    base_currency: str,
    acting_tenant: str,
    run: CalculationRun,
    snapshot_id: str,
    rows: list[ExposureAggregate],
    gaps: list[str],
) -> None:
    """The shared emit tail of both producers: compose the pinned FX path for ``unit_currency`` ->
    base, quantize, and append one row of ``exposure_type``. The self-audit identity holds for
    BOTH measures: ``exposure_amount = quantize(signed_quantity x mark_value x fx_rate, 6)`` —
    for NOTIONAL, ``mark_value`` carries the per-unit FACE VALUE and ``mark_currency`` the
    DENOMINATION currency (the captured inputs stay a faithful recompute recipe)."""
    composed = compose_effective_rate(
        inputs.rate_map, from_currency=unit_currency, to_currency=base_currency, base=DEFAULT_BASE
    )
    if composed is None:
        gaps.append(f"missing-fx:{unit_currency}->{base_currency}")
        return
    effective, legs = composed
    fx_rate = effective.quantize(_FX_QUANTUM, rounding=ROUND_HALF_UP)
    amount = (qty * unit_value * fx_rate).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    rows.append(
        ExposureAggregate(
            tenant_id=str(acting_tenant),
            calculation_run_id=run.run_id,
            input_snapshot_id=str(snapshot_id),
            portfolio_id=pf,
            instrument_id=inst,
            base_currency=base_currency,
            mark_currency=unit_currency,
            signed_quantity=qty,
            mark_value=unit_value,
            fx_rate=fx_rate,
            # DP-12: a v3 run's triangulated legs STATE their pivot; on v1/v2 snapshots
            # ``stated_pivot`` is None and the bytes are the pre-STRUCT-4 shape exactly.
            fx_legs=serialize_legs(legs, pivot=inputs.stated_pivot),
            exposure_amount=amount,
            exposure_type=exposure_type,
        )
    )


def _produce_market_value(
    *,
    inputs: _PinnedInputs,
    base_currency: str,
    acting_tenant: str,
    run: CalculationRun,
    snapshot_id: str,
    rows: list[ExposureAggregate],
    gaps: list[str],
) -> None:
    """MARKET_VALUE producer (the P2-3 v1 semantics, unchanged): one row per holding with a mark +
    a resolvable FX path; a markless holding is a fail-closed gap."""
    for (pf, inst), qty in sorted(inputs.positions.items()):
        mark = inputs.marks.get((pf, inst))
        if mark is None:
            gaps.append(f"missing-mark:{pf}/{inst}")
            continue
        mark_value, mark_ccy = mark
        _emit_row(
            exposure_type=EXPOSURE_TYPE_MARKET_VALUE,
            unit_value=mark_value,
            unit_currency=mark_ccy,
            pf=pf,
            inst=inst,
            qty=qty,
            inputs=inputs,
            base_currency=base_currency,
            acting_tenant=acting_tenant,
            run=run,
            snapshot_id=snapshot_id,
            rows=rows,
            gaps=gaps,
        )


def _produce_notional(
    *,
    inputs: _PinnedInputs,
    base_currency: str,
    acting_tenant: str,
    run: CalculationRun,
    snapshot_id: str,
    rows: list[ExposureAggregate],
    gaps: list[str],
) -> None:
    """NOTIONAL producer (STRUCT-1, REQ-PPM-006): ``face_value x signed_quantity x FX`` from the
    pinned terms, converted from the DENOMINATION currency (DP-4, ratified 2026-08-15).

    The DP-4 failure model, exactly:
    - instrument not pinned at all (a pre-STRUCT-1 snapshot): produce NOTHING — the measure is
      definitionally absent from the snapshot's pinned inputs (keeps old-run reproduction exact);
    - ``asset_class`` != BOND and no face value: SKIP — notional is defined only where a face
      value exists;
    - ``asset_class`` == BOND with no terms or a NULL ``face_value``: fail-closed GAP (a bond
      without a face value is a data defect, not an absent concept);
    - a face value with no denomination currency: fail-closed GAP (an amount without a currency
      cannot be converted — the platform-wide fail-closed default; DP-4 names the conversion
      currency and this is its missing-input case)."""
    for (pf, inst), qty in sorted(inputs.positions.items()):
        asset_class = inputs.asset_classes.get(inst)
        if asset_class is None:
            continue  # pre-STRUCT-1 snapshot: no instrument pin, measure absent by construction
        face_value, denomination = inputs.terms.get(inst, (None, None))
        if face_value is None:
            # Containment, not equality (review fold F-3): asset_class is a free string, and a
            # vocabulary variant ("CORP_BOND", "GOVT_BOND") must not silently downgrade the
            # fail-closed gap to a skip — the containment errs toward the gap, which is the
            # fail-closed direction.
            if "BOND" in asset_class.upper():
                gaps.append(f"missing-face-value:{pf}/{inst}")
            continue
        # Source-column envelope gate (review fold F-2, the P3-7 precedent): instrument_terms
        # lawfully stores 16 integer digits while mark_value holds 14 — an over-envelope face
        # value must be a governed gap, never a numeric-overflow 500 at flush.
        if abs(face_value) >= _MAX_FACE_VALUE_ABS:
            gaps.append(f"face-value-exceeds-envelope:{pf}/{inst}")
            continue
        if denomination is None:
            gaps.append(f"missing-denomination-currency:{pf}/{inst}")
            continue
        _emit_row(
            exposure_type=EXPOSURE_TYPE_NOTIONAL,
            unit_value=face_value,
            unit_currency=denomination,
            pf=pf,
            inst=inst,
            qty=qty,
            inputs=inputs,
            base_currency=base_currency,
            acting_tenant=acting_tenant,
            run=run,
            snapshot_id=snapshot_id,
            rows=rows,
            gaps=gaps,
        )


#: The producer registry (REQ-PPM-006: "at least TWO exposure measures, each with its own
#: producer ... checked against the producers"). The census (test_exposure) asserts EXACT SET
#: EQUALITY between these keys, ``EXPOSURE_TYPES``, and the DISTINCT ``exposure_type`` values an
#: EXECUTED demonstrating run emits — never an assertion over the vocabulary tuple alone.
EXPOSURE_PRODUCERS: dict[str, Any] = {
    EXPOSURE_TYPE_MARKET_VALUE: _produce_market_value,
    EXPOSURE_TYPE_NOTIONAL: _produce_notional,
}


def _build_rows(
    *,
    inputs: _PinnedInputs,
    base_currency: str,
    acting_tenant: str,
    run: CalculationRun,
    snapshot_id: str,
) -> tuple[list[ExposureAggregate], list[str]]:
    """Run every registered producer over the pinned inputs (deterministic registry order).
    Returns ``(rows, gaps)`` — ``gaps`` names every fail-closed input defect (missing mark, FX
    path, bond face value, denomination currency); rows are NOT written when gaps exist."""
    rows: list[ExposureAggregate] = []
    gaps: list[str] = []
    for measure in sorted(EXPOSURE_PRODUCERS):
        EXPOSURE_PRODUCERS[measure](
            inputs=inputs,
            base_currency=base_currency,
            acting_tenant=acting_tenant,
            run=run,
            snapshot_id=snapshot_id,
            rows=rows,
            gaps=gaps,
        )
    return rows, gaps


def _pinned_tree_and_position_portfolios(
    comps: list[Any],
) -> tuple[dict[str, str | None], set[str], dict[str, str | None]]:
    """The snapshot's stored tree view (portfolio_id -> parent, from pinned PORTFOLIO components),
    the set of portfolio ids that pinned POSITIONS live under, and each pinned node's DECLARED
    ``base_currency_code`` (STRUCT-4 — the pinned portfolio content has carried it since P2-1) —
    everything the consume-path node validation and the DP-11 resolution need, read from captured
    content only."""
    tree: dict[str, str | None] = {}
    position_pfs: set[str] = set()
    declared: dict[str, str | None] = {}
    for comp in comps:
        if comp.component_kind == COMPONENT_KIND_PORTFOLIO:
            data = json.loads(comp.captured_content)
            tree[str(data["id"])] = (
                str(data["parent_portfolio_id"]) if data.get("parent_portfolio_id") else None
            )
            declared[str(data["id"])] = data.get("base_currency_code")
        elif comp.component_kind == COMPONENT_KIND_POSITION:
            data = json.loads(comp.captured_content)
            position_pfs.add(str(data["portfolio_id"]))
    return tree, position_pfs, declared


def _pinned_reporting_currency(
    tree: dict[str, str | None], declared: dict[str, str | None], node_id: str
) -> str | None:
    """DP-11 resolution over PINNED content only (mirror-exact with the binder's build-time walk):
    the node's own declared currency, else the nearest declared ancestor WITHIN the pinned chain.
    ``None`` when nothing in the pinned chain declares — including a chain that dangles out of
    the pin undeclared (the pin cannot answer what it never saw). Cycle-bounded by a visited
    set."""
    current: str | None = str(node_id).lower()
    walked: set[str] = set()
    while current is not None and current not in walked and current in tree:
        ccy = declared.get(current)
        if ccy:
            return ccy
        walked.add(current)
        parent = tree[current]
        current = str(parent).lower() if parent else None
    return None


def _pinned_subtree_of(tree: dict[str, str | None], node_id: str) -> set[str]:
    """The node's subtree WITHIN the pinned tree (the node + every pinned descendant), computed
    from the captured parent map — bounded by the pin's own size, no live read."""
    children: dict[str, list[str]] = {}
    for child, parent in tree.items():
        if parent is not None:
            children.setdefault(parent, []).append(child)
    out: set[str] = set()
    stack = [str(node_id)]
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current)
        stack.extend(children.get(current, []))
    return out


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
    scope_node_id: str | None = None,
) -> ExposureRunResult:
    """Run a governed exposure aggregation. Build-in-request (default — ``portfolio_id`` +
    ``as_of_valid_at``: builds an ``EXPOSURE_INPUT`` snapshot with FX pinned) or consume-existing
    (``snapshot_id``). See the module docstring for the failure model + the AD-014 invariant.

    ``scope_node_id`` (STRUCT-3, DP-7 / REQ-PPM-008): the consume path's EXPLICIT node. A
    full-subtree (v2-predicate) snapshot REFUSES a node-less consume — the shipped path stamped
    NULL and failed the node-id clause silently; a LEGACY (v1) snapshot keeps its pre-STRUCT-3
    semantics so reproduction of old runs is untouched. The node is validated against the
    snapshot's PINNED subtree (never a live walk — AD-014/the scope fence), the run computes
    ONLY the node's sub-holdings, an empty pinned sub-subtree refuses (DP-10), and the validated
    node is stamped as the run's ``scope_portfolio_id`` (the node id carried on the run). On the
    build path the scope IS ``portfolio_id`` — ``scope_node_id`` there is refused as ambiguous."""
    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/exposure/audit) ---
    if not code_version:
        raise ExposureInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise ExposureInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise ExposureInputError("initiator is required (FW-RUN/TR-15)")

    # --- Bind the snapshot (cross-tenant/unknown/incomplete/FX-missing ⇒ pre-create refusal) ---
    node_scope: set[str] | None = None
    if snapshot_id is None and scope_node_id is not None:
        # The build path's scope IS portfolio_id (the subtree root) — a second node argument is
        # the same ambiguity the P3-C1 guard below refuses.
        raise ExposureInputError(
            "scope_node_id applies to the consume path only — the build path's node is "
            "portfolio_id"
        )
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
        # --- STRUCT-3 (DP-7): the consume node, validated against the PINNED subtree ---
        comps_pre = list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        pinned_tree, pinned_position_pfs, pinned_declared = _pinned_tree_and_position_portfolios(
            comps_pre
        )
        is_v3 = snapshot.binding_predicate_version == NODE_FX_BINDING_PREDICATE
        strict = is_v3 or snapshot.binding_predicate_version == SUBTREE_BINDING_PREDICATE
        if strict and scope_node_id is None:
            raise ExposureInputError(
                "a consume run on a full-subtree snapshot must name its node (scope_node_id) — "
                "REQ-PPM-008: the node id is carried on the run, never NULL"
            )
        if scope_node_id is not None and strict:
            # v2 only: validate against the pinned subtree and filter the compute to it. A
            # LEGACY (v1, holdings-only-pinned) snapshot skips BOTH (review folds F6/F7): its
            # pin set cannot answer membership (a grouping-node root is legitimately unpinned
            # there), and filtering would silently truncate a run that pre-STRUCT-3 semantics
            # computed in full — the exact divergence that would break reproduction of legacy
            # build-path runs. On a legacy snapshot the given node is stamped verbatim (the
            # adapter passes the ORIGINAL run's scope) and the compute stays whole-snapshot.
            node_key = str(scope_node_id).lower()
            if node_key not in pinned_tree:
                raise ExposureInputError(
                    f"scope_node_id {scope_node_id} is not a node of the snapshot's pinned "
                    "subtree — a run cannot be scoped to a node its snapshot never saw"
                )
            node_scope = _pinned_subtree_of(pinned_tree, node_key)
            if not (node_scope & pinned_position_pfs):
                # DP-10: a node whose pinned sub-subtree holds no positions REFUSES rather than
                # returning zero.
                raise ExposureInputError(
                    f"the pinned subtree of node {scope_node_id} holds no positions — an empty "
                    "subtree refuses rather than returning zero (REQ-PPM-008)"
                )
        # --- STRUCT-4 (DP-11): the consume run's reporting base. The pre-STRUCT-4 tail
        # (`base_currency or DEFAULT_BASE`) silently recomputed an undeclared book in USD — the
        # reproduction registry documents the hazard verbatim. Resolution is over PINNED content
        # only (AD-014 — the compute may not ask the live tree): the scoped node's declaration
        # chain, else the pinned top-of-tree's; nothing resolvable ⇒ REFUSE, never default.
        # The reproduction adapters pass the ORIGINAL run's stored base explicitly, so legacy
        # runs reproduce untouched. ---
        if scope_node_id is not None and strict:
            # The NODE's chain — only where the compute is actually node-filtered. On a legacy
            # v1 snapshot the compute stays whole-book (the F6/F7 folds above), so anchoring
            # the base to the named node would denominate the WHOLE book in one sleeve's
            # currency (review fold C10) — v1 falls through to the top-of-tree resolution.
            declared_base = _pinned_reporting_currency(
                pinned_tree, pinned_declared, str(scope_node_id)
            )
        else:
            # Review fold C7: EVERY pinned top must resolve, and to the SAME currency. A v1
            # pin can carry several dangling tops (position-bearing sleeves only); counting an
            # UNRESOLVABLE top as agreement would let one sleeve's declaration silently price
            # its sibling — refused, never guessed (the P3-C1 ambiguity rule).
            tops = [n for n, p in pinned_tree.items() if p is None or p not in pinned_tree]
            top_resolved = [
                _pinned_reporting_currency(pinned_tree, pinned_declared, t) for t in tops
            ]
            declared_base = (
                top_resolved[0]
                if top_resolved and None not in top_resolved and len(set(top_resolved)) == 1
                else None
            )
        if base_currency:
            if is_v3 and scope_node_id is not None and declared_base not in (None, base_currency):
                # v3 ONLY (the STRUCT-3 lesson — new strictness keys to the artifact's own
                # version marker): an explicit base contradicting the node's declaration is a
                # refused override, not a silent recompute in a foreign currency.
                raise ReportingCurrencyConflictError(
                    f"base_currency {base_currency!r} contradicts node {scope_node_id}'s "
                    f"declared reporting currency {declared_base!r} — a node-scoped read is "
                    "refused rather than silently overriding the declaration (REQ-PPM-010)"
                )
            base = base_currency
        elif declared_base is not None:
            base = declared_base
        else:
            raise UndeclaredReportingCurrencyError(
                "the snapshot's pinned declaration chain resolves no reporting currency — an "
                "undeclared scope REFUSES rather than defaulting (REQ-PPM-010/DP-11); pass "
                "base_currency explicitly"
            )
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
        inputs = _read_components(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant),
            # DP-12: only a v3 snapshot's rows STATE their triangulation pivot — v1/v2 rows
            # keep the pre-STRUCT-4 fx_legs bytes exactly (byte-compared reproduction field).
            stated_pivot=(
                DEFAULT_BASE
                if snapshot.binding_predicate_version == NODE_FX_BINDING_PREDICATE
                else None
            ),
        )
        if node_scope is not None:
            # STRUCT-3: a node-scoped consume run computes ONLY the node's sub-holdings — the
            # membership set was derived from the PINNED tree pre-create, never a live walk.
            inputs = _PinnedInputs(
                positions={k: v for k, v in inputs.positions.items() if k[0] in node_scope},
                marks=inputs.marks,
                rate_map=inputs.rate_map,
                asset_classes=inputs.asset_classes,
                terms=inputs.terms,
                stated_pivot=inputs.stated_pivot,
            )
        return _build_rows(
            inputs=inputs,
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
        # STRUCT-1: the gap NAMES join the persisted reason — DP-4 mints operator-actionable gap
        # classes (missing-face-value, missing-denomination-currency) and a reason that names
        # neither is not a legible refusal. The pre-P3-C2 bare-str(gate) prefix is preserved.
        format_reason=lambda gate, gaps: (f"{gate}: {'; '.join(gaps)}" if gaps else str(gate)),
        # API-1b (OD-API-1b-B): the ROOT is the build-path portfolio_id (the subtree this run
        # aggregates). The snapshot-consume path did NOT take a root → NULL (honest, OD-API-1b-D).
        # STRUCT-3: the consume path stamps its VALIDATED node (REQ-PPM-008 — the node id is
        # carried on the run); only a LEGACY node-less consume still stamps the honest NULL.
        scope_portfolio_id=(
            (str(scope_node_id) if scope_node_id is not None else None)
            if snapshot_id is not None
            else portfolio_id
        ),
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
            .order_by(
                ExposureAggregate.portfolio_id,
                ExposureAggregate.instrument_id,
                ExposureAggregate.exposure_type,
            )
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
    exposure_type: str | None = None,
) -> list[ExposureAggregate]:
    """API-1 entity/time read (Class A): ``exposure_aggregate`` rows across COMPLETED runs for a
    (portfolio, instrument). A run's rows SPAN the portfolio SUBTREE, so the ``portfolio_id`` filter
    row-filters to the queried book's own rows. Silent-empty on a foreign id; ``as_of=None`` =
    now. ``exposure_type`` (STRUCT-1) filters to ONE measure; an unknown measure REFUSES
    (:class:`ExposureInputError` — a vocabulary error is a caller defect, not an empty book)."""
    if exposure_type is not None and exposure_type not in EXPOSURE_TYPES:
        raise ExposureInputError(
            f"unknown exposure_type {exposure_type!r} — expected one of {sorted(EXPOSURE_TYPES)}"
        )
    return list_governed_results(
        session,
        ExposureAggregate,
        acting_tenant=acting_tenant,
        filters=(
            (ExposureAggregate.portfolio_id, portfolio_id),
            (ExposureAggregate.instrument_id, instrument_id),
            (ExposureAggregate.exposure_type, exposure_type),
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
    exposure_type: str | None = None,
) -> list[ExposureAggregate]:
    """API-1 latest-resolver (Class A): the newest COMPLETED exposure run's rows for the portfolio
    (the run may be rooted at an ancestor — rows returned are the portfolio's own; empty when
    none). ``exposure_type`` (STRUCT-1) filters to ONE measure of that run."""
    return latest_run_rows(
        list_exposure_by_entity(
            session,
            acting_tenant=acting_tenant,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            as_of=as_of,
            exposure_type=exposure_type,
        )
    )


class NothingToSumError(Exception):
    """A summed read over an EMPTY population (no COMPLETED run carries the measure). Distinct
    from the 422 caller-defect class (review fold: empty-scope refusals map 409, the
    EmptySnapshotError convention — an empty book is a state of the world, not a bad request)."""

    def __init__(self, exposure_type: str) -> None:
        super().__init__(
            f"no COMPLETED exposure run carries measure {exposure_type!r} for this portfolio — "
            "nothing to sum"
        )
        self.exposure_type = str(exposure_type)


@dataclass(frozen=True)
class ExposureSum:
    """A summed latest-exposure read (STRUCT-2, REQ-PPM-007): ONE run, ONE measure, with the
    provenance a consumer needs to cite it."""

    total: Decimal
    exposure_type: str
    base_currency: str
    calculation_run_id: str
    n_rows: int


def summed_latest_exposure(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    exposure_type: str | None,
    as_of=None,  # noqa: ANN001  (datetime | None)
) -> ExposureSum:
    """The ADDITIVE positive case of the aggregation contract (STRUCT-2): the newest COMPLETED
    run's ``exposure_amount`` total for ONE declared measure.

    Two refusals, both fail-closed BY CONSTRUCTION (the review's V-007-2 shape — mixture
    detection over returned rows passes vacuously on a single-measure book, so the measure is
    REQUIRED instead): (1) no ``exposure_type`` ⇒ refused — a sum across measures is a category
    error, never a conversion; (2) the contract lookup governs the sum — flip the operator and
    this read refuses (the result-obedience control)."""
    from irp_shared.aggregation.contracts import (
        NotAggregatableError,
        assert_aggregatable,
        require_additive_selection,
    )

    # The selector requirement comes FROM the grain declaration (review fold: the earlier form
    # required exposure_type by hand — "additive by hand, not by contract", the exact pattern
    # the plan forbids for STRUCT-3's rollup). Flip the declaration and the requirement moves.
    try:
        require_additive_selection("EXPOSURE_AGGREGATE", {"exposure_type": exposure_type})
    except NotAggregatableError:
        raise ExposureInputError(
            "a summed exposure read must fix every declared additive-selector dimension "
            "(exposure_type) — aggregating rows of different measure types is refused, never "
            "converted (REQ-PPM-007)"
        ) from None
    assert_aggregatable("EXPOSURE_AGGREGATE", "exposure_amount")
    rows = latest_exposure(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=portfolio_id,
        as_of=as_of,
        exposure_type=exposure_type,
    )
    if not rows:
        raise NothingToSumError(str(exposure_type))
    total = sum((r.exposure_amount for r in rows), Decimal(0))
    return ExposureSum(
        total=total,
        exposure_type=str(exposure_type),
        base_currency=rows[0].base_currency,
        calculation_run_id=rows[0].calculation_run_id,
        n_rows=len(rows),
    )


@dataclass(frozen=True)
class NodeRollup:
    """One node's composed totals for ONE measure (STRUCT-3, REQ-PPM-008 / DP-9): read-time
    composition over the run's LEAF rows — the leaf rows were quantized once at the run, so the
    composition is exact by construction; no parent row is ever persisted (parent-scoped RUNS
    stay the governed number)."""

    node_id: str
    exposure_type: str
    total: Decimal
    n_rows: int
    base_currency: str
    #: STRUCT-4 (REQ-PPM-010): the node's DECLARED reporting currency resolved over the PINNED
    #: declaration chain (None = nothing declared — honest, no translation attempted).
    reporting_currency: str | None = None
    #: The node total TRANSLATED into ``reporting_currency`` via the run's PINNED FX components
    #: (never a live rate — AD-014). None when undeclared or when the pinned set has no path.
    translated_total: Decimal | None = None
    translated_currency: str | None = None
    #: The effective composite multiplier used (12dp, HALF_UP) — Decimal(1) on the identity path.
    translation_fx_rate: Decimal | None = None
    #: The ordered published-rate legs of the translation (empty on identity).
    translation_legs: tuple = ()
    #: The triangulation pivot when the translation took two legs (DP-12 — stated, not inferred).
    translation_pivot: str | None = None
    #: A pre-PPM-010 snapshot lacking the node-currency leg surfaces the gap HONESTLY — never a
    #: retroactive refusal, never a fabricated 1.0 (the planning row's risk-first test).
    missing_fx: str | None = None


def rollup_exposure(
    session: Session, *, acting_tenant: str, run_id: str, node_id: str
) -> list[NodeRollup]:
    """Per-measure totals for ``node_id`` composed from a COMPLETED run's rows over the node's
    subtree AS THE RUN SAW IT (the pinned tree — a re-parent after the run cannot move a
    historical rollup). Consults the aggregation contract for every measure (REQ-PPM-007: the
    operator AND the grain selectors govern; a NOT_AGGREGATABLE flip refuses this read).
    Refusals: an unknown/foreign run; a run without a pinned tree (a legacy v1 snapshot cannot
    anchor a node rollup); a node outside the pinned subtree."""
    from irp_shared.aggregation.contracts import (
        assert_aggregatable,
        require_additive_selection,
    )

    run = resolve_run(session, run_id, acting_tenant=acting_tenant)
    if run.status != "COMPLETED":
        # Review fold: a FAILED run has nothing to compose — refusing is honest; a silent
        # empty list reads as "the node is worth zero".
        raise ExposureInputError(
            f"run {run_id} is {run.status} — a rollup composes a COMPLETED run's rows only"
        )
    if run.input_snapshot_id is None:
        raise ExposureInputError(f"run {run_id} carries no input snapshot — nothing to roll up")
    snapshot = resolve_snapshot(session, run.input_snapshot_id, acting_tenant=acting_tenant)
    if snapshot.binding_predicate_version not in (
        SUBTREE_BINDING_PREDICATE,
        NODE_FX_BINDING_PREDICATE,
    ):
        raise ExposureInputError(
            f"run {run_id} was bound to a pre-STRUCT-3 snapshot without a full-subtree pin — "
            "a node rollup needs the run's stored tree view"
        )
    comps = list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
    pinned_tree, _, pinned_declared = _pinned_tree_and_position_portfolios(comps)
    rate_map = _read_components(comps).rate_map
    node_key = str(node_id).lower()
    if node_key not in pinned_tree:
        raise ExposureInputError(
            f"node {node_id} is not in the run's pinned subtree — a rollup cannot be anchored "
            "at a node the run never saw"
        )
    member_ids = _pinned_subtree_of(pinned_tree, node_key)
    rows = list_exposure(session, run_id=run_id, acting_tenant=acting_tenant)
    out: list[NodeRollup] = []
    for measure in sorted({r.exposure_type for r in rows}):
        # The contract governs the composition: the operator must be ADDITIVE (flip it and this
        # read refuses — mutation-proven), and the selector check is the FORWARD guard — with
        # today's single selector it is satisfied per-measure by construction, but a future
        # selector dimension this read does not fix will refuse here rather than silently sum
        # across it (the review's vacuity note, kept deliberately).
        require_additive_selection("EXPOSURE_AGGREGATE", {"exposure_type": measure})
        assert_aggregatable("EXPOSURE_AGGREGATE", "exposure_amount")
        member_rows = [
            r
            for r in rows
            if r.exposure_type == measure and str(r.portfolio_id).lower() in member_ids
        ]
        if not member_rows:
            continue  # a measure with no rows UNDER THIS NODE is absent, never a zero
        bases = {r.base_currency for r in member_rows}
        if len(bases) != 1:
            raise ExposureInputError(
                f"the node's rows span base currencies {sorted(bases)} — a single total would "
                "mix currencies (REQ-PPM-007: refused, never converted)"
            )
        total = sum((r.exposure_amount for r in member_rows), Decimal(0))
        base = next(iter(bases))
        # --- STRUCT-4 (REQ-PPM-010): translate the node total into the node's DECLARED
        # reporting currency, from the run's PINNED FX components only (AD-014 — never a live
        # rate). Undeclared ⇒ no translation (honest None); a pre-PPM-010 snapshot lacking the
        # node-currency leg ⇒ ``missing_fx`` — surfaced, never refused retroactively, never a
        # fabricated 1.0. ---
        reporting = _pinned_reporting_currency(pinned_tree, pinned_declared, node_key)
        translated: Decimal | None = None
        translated_ccy: str | None = None
        fx_rate: Decimal | None = None
        legs: tuple = ()
        pivot: str | None = None
        missing_fx: str | None = None
        if reporting is not None:
            if reporting == base:
                # The same-currency no-op is EXACT — the total passes through untouched (the
                # regression-guard clause: no rate lookup, no re-rounding on the identity path).
                translated, translated_ccy, fx_rate = total, reporting, Decimal(1)
            else:
                composed = compose_effective_rate(
                    rate_map, from_currency=base, to_currency=reporting, base=DEFAULT_BASE
                )
                if composed is None:
                    missing_fx = f"missing-fx:{base}->{reporting}"
                else:
                    effective, fx_legs = composed
                    fx_rate = effective.quantize(_FX_QUANTUM, rounding=ROUND_HALF_UP)
                    translated = (total * fx_rate).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
                    translated_ccy = reporting
                    legs = tuple(fx_legs)
                    pivot = DEFAULT_BASE if len(fx_legs) == 2 else None
        out.append(
            NodeRollup(
                node_id=str(node_id),
                exposure_type=measure,
                total=total,
                n_rows=len(member_rows),
                base_currency=base,
                reporting_currency=reporting,
                translated_total=translated,
                translated_currency=translated_ccy,
                translation_fx_rate=fx_rate,
                translation_legs=legs,
                translation_pivot=pivot,
                missing_fx=missing_fx,
            )
        )
    if not out:
        # The DP-10 shape at read time (review BLOCKING F18): a node with NO rows of this run
        # under it must refuse — a zero-rollup response reads as "this node is worth nothing".
        raise ExposureInputError(
            f"no rows of run {run_id} lie under node {node_id} — an empty rollup refuses "
            "rather than reporting zero (REQ-PPM-008)"
        )
    return out


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
