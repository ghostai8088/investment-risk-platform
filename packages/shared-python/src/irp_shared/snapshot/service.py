"""``build_snapshot`` governed binder + ``verify_snapshot`` (P2-1, ENT-049/050 — AD-014).

``build_snapshot`` composes the already-shipped, tenant-predicated reads into an immutable
snapshot:
it resolves the bound scope (``resolve_portfolio`` — cross-tenant/unknown fails closed BEFORE any
write), enumerates the open positions of the subtree (``reconstruct_subtree_holdings_as_of``) and
their marks at a fixed ``valuation_date`` (``attach_marks_as_of``), re-resolves each input by id
under the acting tenant (the per-component pin + cross-tenant safety), pins the physical version +
the canonical ``captured_content`` + ``content_hash``, computes the header ``manifest_hash``, roots
a ``data_snapshot`` lineage edge per component, runs the caller-side completeness DQ gate (fail-
closed), and emits ``SNAPSHOT.CREATE`` — all in the caller's single transaction (CTRL-032
rollback).

It **computes no derived number** (no ``quantity x mark``, no exposure) and **creates/​wires no
``calculation_run``** — imports NO ``calc`` symbol (readiness §10, never becomes wiring).

``verify_snapshot`` re-resolves each component by id (the explicit-tenant-predicate resolvers, not
a
bare ``session.get``) at the FROZEN cutoffs, re-serializes, and compares ``content_hash`` — the
authoritative reproducibility check. FR components are byte-stable under later
supersede/correction;
an EV ``portfolio`` amend (``record_version`` bump) is reported as drift.

One-way imports: ``snapshot -> {portfolio, position, valuation, holdings, marketdata, lineage, dq,
audit, db}`` (P2-3 adds ``marketdata`` for FX-leg pinning; P3-3 adds a **models-only,
function-local** ``exposure.models`` read for atom pinning — the ``exposure`` SERVICE is never
imported, it imports ``snapshot``, and hoisting the models import to module level is a circular
import). Imports NO ``calc`` symbol; creates/wires no ``calculation_run``. Only the aggregator +
the run consumers (``exposure``, ``risk``) import ``snapshot``.
"""

from __future__ import annotations

import json
from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.classification.service import (
    ClassificationNotVisible,
    canonical_tenant_id,
    resolve_ancestors,
    resolve_node,
    resolve_scheme,
)
from irp_shared.db.mixins import utcnow
from irp_shared.dq.gates import ensure_presence_rule, run_presence_gate
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.holdings import (
    HoldingWithMark,
    attach_marks_as_of,
    reconstruct_subtree_holdings_as_of,
)
from irp_shared.holdings.service import HoldingRow
from irp_shared.lineage.service import record_internal_lineage
from irp_shared.marketdata import (
    DEFAULT_BASE,
    BenchmarkNotVisible,
    CurveNotVisible,
    list_curve_points,
    reconstruct_curve_as_of,
    reconstruct_membership_as_of,
    resolve_benchmark,
    resolve_conversion_legs,
    resolve_curve,
)
from irp_shared.marketdata.benchmark_series import (
    list_benchmark_returns,
    reconstruct_benchmark_return_as_of,
)
from irp_shared.marketdata.factor import (
    FactorNotVisible,
    list_factor_returns,
    reconstruct_factor_return_as_of,
    resolve_factor,
)
from irp_shared.marketdata.models import REFERENCE_KEY_NONE, RETURN_TYPE_SIMPLE, FactorReturn
from irp_shared.marketdata.service import FxRateNotVisible, resolve_fx_rate
from irp_shared.portfolio import (
    Portfolio,
    PortfolioNotVisible,
    resolve_descendants,
    resolve_portfolio,
)
from irp_shared.position import PositionNotVisible, resolve_position
from irp_shared.reference.instrument import InstrumentNotVisible, resolve_instrument
from irp_shared.reference.instrument_terms import reconstruct_terms_as_of
from irp_shared.reference.service import CalendarNotVisible
from irp_shared.snapshot.events import SnapshotActor, record_snapshot_create
from irp_shared.snapshot.models import (
    COMPONENT_KIND_BENCHMARK,
    COMPONENT_KIND_BENCHMARK_RETURN,
    COMPONENT_KIND_CAPITAL_CALL,
    COMPONENT_KIND_CLASSIFICATION,
    COMPONENT_KIND_CLASSIFICATION_SCHEME,
    COMPONENT_KIND_COMMITMENT,
    COMPONENT_KIND_COVARIANCE,
    COMPONENT_KIND_CURVE,
    COMPONENT_KIND_DESMOOTHED_RETURN,
    COMPONENT_KIND_DISTRIBUTION,
    COMPONENT_KIND_EXPOSURE,
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FACTOR_EXPOSURE,
    COMPONENT_KIND_FACTOR_RETURN,
    COMPONENT_KIND_FX,
    COMPONENT_KIND_GOVERNED_VALUE,
    COMPONENT_KIND_HOLIDAY_CALENDAR,
    COMPONENT_KIND_INSTRUMENT,
    COMPONENT_KIND_INSTRUMENT_TERMS,
    COMPONENT_KIND_ISSUER_EDGE,
    COMPONENT_KIND_PORTFOLIO,
    COMPONENT_KIND_PORTFOLIO_RETURN,
    COMPONENT_KIND_POSITION,
    COMPONENT_KIND_PROXY_MAPPING,
    COMPONENT_KIND_PROXY_WEIGHT,
    COMPONENT_KIND_PURE_PRIVATE_RETURN,
    COMPONENT_KIND_SCENARIO,
    COMPONENT_KIND_TRANSACTION,
    COMPONENT_KIND_VALUATION,
    COMPONENT_KIND_VAR,
    PURPOSE_ACTIVE_RISK_INPUT,
    PURPOSE_BENCHMARK_RELATIVE_INPUT,
    PURPOSE_CONCENTRATION_INPUT,
    PURPOSE_COVARIANCE_INPUT,
    PURPOSE_DESMOOTHING_INPUT,
    PURPOSE_EXPOSURE_INPUT,
    PURPOSE_FACTOR_EXPOSURE_INPUT,
    PURPOSE_LIQUIDITY_INPUT,
    PURPOSE_PACING_INPUT,
    PURPOSE_PRIVATE_COVARIANCE_INPUT,
    PURPOSE_PRIVATE_FACTOR_RETURN_INPUT,
    PURPOSE_PROXY_WEIGHT_INPUT,
    PURPOSE_REPORT_INPUT,
    PURPOSE_RESIDUAL_SHRINKAGE_INPUT,
    PURPOSE_RETURN_INPUT,
    PURPOSE_ROLLING_RISK_INPUT,
    PURPOSE_SCENARIO_INPUT,
    PURPOSE_SENSITIVITY_INPUT,
    PURPOSE_SHARPE_INPUT,
    PURPOSE_VAR_BACKTEST_INPUT,
    PURPOSE_VAR_HS_INPUT,
    PURPOSE_VAR_INPUT,
    SNAPSHOT_PURPOSES,
    DatasetSnapshot,
    DatasetSnapshotComponent,
)
from irp_shared.snapshot.serialize import (
    _norm_guid,
    benchmark_membership_content,
    benchmark_return_series_content,
    capital_call_content,
    commitment_content,
    content_hash,
    covariance_content,
    curve_content,
    desmoothed_return_content,
    distribution_content,
    exposure_content,
    factor_content,
    factor_exposure_content,
    factor_return_series_content,
    fx_content,
    instrument_content,
    instrument_terms_content,
    manifest_hash,
    portfolio_content,
    portfolio_return_content,
    position_content,
    proxy_mapping_content,
    proxy_weight_estimate_content,
    pure_private_return_content,
    scenario_shock_content,
    serialize_content,
    transaction_content,
    valuation_content,
    var_result_content,
)
from irp_shared.valuation import ValuationNotVisible, resolve_valuation

#: The v1 binding/selection rule (versioned via the header ``binding_predicate_version``).
DEFAULT_BINDING_PREDICATE = "v1:subtree-open-positions"
#: STRUCT-3 (REQ-PPM-008): EXPOSURE_INPUT builds pin the FULL scope subtree — every node,
#: including position-less grouping nodes — so the run's stored tree view is reconstructable
#: from PORTFOLIO components alone and a consume run can validate its node against the pin. The
#: predicate string is the SELF-DESCRIBING marker the exposure consume path branches on: a
#: pre-STRUCT-3 snapshot (v1) keeps legacy semantics (reproduction of old runs untouched); a v2
#: snapshot REQUIRES an explicit consume node (DP-7).
SUBTREE_BINDING_PREDICATE = "v2:subtree-open-positions+full-node-pin"
#: STRUCT-4 (REQ-PPM-010, DP-11/DP-12): v3 EXPOSURE_INPUT builds ADDITIONALLY (a) redefine
#: FX-completeness against the set of RESOLVED node reporting currencies in scope (not just the
#: run base) — so a later node read in the node's own declared currency composes from pins alone —
#: and (b) mark rows whose triangulated ``fx_legs`` STATE their pivot. The predicate string is the
#: version marker the exposure paths branch on (the STRUCT-3 lesson: key new strictness to the
#: artifact's OWN marker, never to code age): v1/v2 snapshots keep their shipped semantics and
#: byte shapes exactly, so reproduction of old runs is untouched.
NODE_FX_BINDING_PREDICATE = "v3:subtree-open-positions+full-node-pin+node-fx"

#: The per-tenant completeness DataQualityRule (resolve-or-register, the ``ensure_manual_source``
#: pattern). A NOT_NULL rule over a derived dataset — no new evaluator, Protocol untouched (§16).
_COMPLETENESS_RULE_CODE = "snapshot.completeness"


def _ensure_snapshot_presence_rule(session: Session, *, acting_tenant: str, actor: SnapshotActor):
    # noqa: ANN202
    """The snapshot-completeness presence rule via the shared ``dq.gates`` helper (P3-4-R0 —
    rule code/name/target unchanged; evidence shape byte-identical to the pre-R0 copy)."""
    return ensure_presence_rule(
        session,
        tenant_id=str(acting_tenant),
        code=_COMPLETENESS_RULE_CODE,
        name="Snapshot bound-set completeness",
        target_entity_type="dataset_snapshot",
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
    )


class SnapshotPurposeError(Exception):
    """Raised when ``purpose`` is out of the controlled vocabulary (app-side allow-list; the row is
    immutable, so this must fail BEFORE any flush)."""

    def __init__(self, purpose: str) -> None:
        super().__init__(f"invalid snapshot purpose {purpose!r} (allowed: {SNAPSHOT_PURPOSES})")
        self.purpose = purpose


class EmptySnapshotError(Exception):
    """Raised when the bound scope yields zero components — fail closed (no empty snapshot)."""

    def __init__(self, portfolio_id: str) -> None:
        super().__init__(f"bound scope {portfolio_id} yields zero components — fail closed")
        self.portfolio_id = str(portfolio_id)


class SnapshotNotFound(Exception):
    """Raised when a ``dataset_snapshot`` id is not visible in the acting tenant scope (read/verify
    cross-tenant/unknown fails closed)."""

    def __init__(self, snapshot_id: str) -> None:
        super().__init__(f"dataset_snapshot {snapshot_id} is not visible in the current tenant")
        self.snapshot_id = str(snapshot_id)


@dataclass(frozen=True)
class VerifyResult:
    """The outcome of ``verify_snapshot``: ``ok`` iff every component re-resolves byte-identically.
    ``drifted_components`` lists the component ids whose live value/version differs (or is
    gone)."""

    ok: bool
    component_count: int
    drifted_components: list[str] = field(default_factory=list)


def _run_completeness_gate(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    header: DatasetSnapshot,
    holdings: list[HoldingRow],
    enriched: list[HoldingWithMark],
) -> None:
    """Fail-closed completeness: every non-zero-quantity bound position MUST have a same-as-of
    mark.

    The gap (expected - actual) is encoded as one ``{'present': None}`` row per missing key and run
    through the shipped ``run_quality_check`` NOT_NULL rule (the existing evaluator; Protocol
    UNTOUCHED). A non-empty gap fails ERROR-severity -> ``DataQualityError`` -> the whole unit
    (snapshot + components + lineage + the flagged result + audit) rolls back. An empty bound scope
    is rejected earlier (``EmptySnapshotError``).
    """
    have_mark = {
        (e.holding.portfolio_id, e.holding.instrument_id) for e in enriched if e.mark is not None
    }
    gap = [
        f"{h.portfolio_id}:{h.instrument_id}"
        for h in holdings
        if h.quantity != 0 and (h.portfolio_id, h.instrument_id) not in have_mark
    ]
    rule = _ensure_snapshot_presence_rule(session, acting_tenant=acting_tenant, actor=actor)
    run_presence_gate(
        session,
        rule=rule,
        gaps=gap,
        target_entity_type="dataset_snapshot",
        target_entity_id=header.id,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
    )


def build_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    purpose: str,
    portfolio_id: str,
    as_of_valid_at: datetime,
    label: str = "",
    as_of_known_at: datetime | None = None,
    as_of_valuation_date: date | None = None,
    binding_predicate_version: str = DEFAULT_BINDING_PREDICATE,
    base_currency: str | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``dataset_snapshot`` over the bound portfolio subtree (governed). See
    the
    module docstring. ``as_of_known_at`` defaults to now and is FROZEN onto the header;
    ``as_of_valuation_date`` defaults to ``date(as_of_valid_at)``.

    P2-3 (OD-P2-3-E): when ``base_currency`` is given (the ``EXPOSURE_INPUT`` case), the binder
    also
    pins, for each distinct mark currency != base, the convert-path ``fx_rate`` legs to that base
    as
    ``COMPONENT_KIND_FX`` components — so a later exposure run is reproducible from the snapshot
    alone
    (it reads the captured FX, never live market data). This is the FX-completeness gate:
    ``resolve_conversion_legs`` fails closed (:class:`~irp_shared.marketdata.FxRateNotFound`,
    before
    any write) if a leg is missing. When ``base_currency`` is ``None`` (the P2-1 behavior) no FX is
    pinned — backward-compatible. Still computes NO derived number (no ``qty x mark``)."""
    if purpose not in SNAPSHOT_PURPOSES:
        raise SnapshotPurposeError(purpose)
    known = as_of_known_at if as_of_known_at is not None else utcnow()
    val_date = as_of_valuation_date if as_of_valuation_date is not None else as_of_valid_at.date()

    # 1. Resolve the bound scope FIRST — a foreign/unknown portfolio raises PortfolioNotVisible
    #    (fail closed on SQLite AND PG) BEFORE any enumeration or write.
    resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)
    # STRUCT-3/STRUCT-4: EXPOSURE_INPUT snapshots carry the newest predicate (v3) unless the
    # caller pinned a version explicitly (the predicate string is load-bearing — see the
    # constants; explicit v2 keeps the STRUCT-3 semantics for the legacy-shape tests).
    if purpose == PURPOSE_EXPOSURE_INPUT and binding_predicate_version == DEFAULT_BINDING_PREDICATE:
        binding_predicate_version = NODE_FX_BINDING_PREDICATE

    # 2. Enumerate the open positions of the subtree + their marks at the fixed valuation_date
    #    (the shipped, tenant-bounded, cycle-safe, arithmetic-free composers).
    holdings = reconstruct_subtree_holdings_as_of(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=str(portfolio_id),
        valid_at=as_of_valid_at,
        known_at=known,
    )
    # DP-10 (STRUCT-3): an empty subtree REFUSES at submission — keyed to the HOLDINGS set, not
    # to the spec list (with grouping nodes pinned unconditionally the spec list is never empty
    # for a resolvable node, so the old `if not specs` guard could no longer fire).
    if not holdings:
        raise EmptySnapshotError(str(portfolio_id))
    enriched = attach_marks_as_of(
        session,
        acting_tenant=acting_tenant,
        holdings=holdings,
        valuation_date=val_date,
        valid_at=as_of_valid_at,
        known_at=known,
    )

    # 3. Re-resolve each input by id under the acting tenant (the per-component pin + cross-tenant
    # safety) and capture its canonical content. component spec = (kind, target_type, row, hash).
    specs: list[tuple[str, str, Any, str, str]] = []
    seen_portfolios: set[str] = set()
    seen_instruments: set[str] = set()
    mark_currencies: set[str] = set()
    denomination_currencies: set[str] = set()
    for e in enriched:
        h = e.holding
        pos = resolve_position(session, h.position_id, acting_tenant=acting_tenant)
        _append_spec(specs, COMPONENT_KIND_POSITION, "position", pos, position_content(pos))
        if h.portfolio_id not in seen_portfolios:
            seen_portfolios.add(h.portfolio_id)
            pf = resolve_portfolio(session, h.portfolio_id, acting_tenant=acting_tenant)
            _append_spec(specs, COMPONENT_KIND_PORTFOLIO, "portfolio", pf, portfolio_content(pf))
        # STRUCT-1 (REQ-PPM-006, DP-3): EXPOSURE_INPUT builds pin, per distinct instrument, the
        # instrument EV identity (asset_class — the DP-4 bond-gap rule reads it from the pin, never
        # live, AD-014) and the terms FR version as-of when one exists (face_value +
        # denomination_currency — the NOTIONAL inputs). No terms as-of ⇒ only the INSTRUMENT
        # component; the compute decides skip-vs-gap from the pinned asset_class.
        if purpose == PURPOSE_EXPOSURE_INPUT and h.instrument_id not in seen_instruments:
            seen_instruments.add(h.instrument_id)
            inst = resolve_instrument(session, h.instrument_id, acting_tenant=acting_tenant)
            _append_spec(
                specs, COMPONENT_KIND_INSTRUMENT, "instrument", inst, instrument_content(inst)
            )
            terms = reconstruct_terms_as_of(
                session,
                h.instrument_id,
                acting_tenant=acting_tenant,
                valid_at=as_of_valid_at,
                known_at=known,
            )
            if terms is not None:
                _append_spec(
                    specs,
                    COMPONENT_KIND_INSTRUMENT_TERMS,
                    "instrument_terms",
                    terms,
                    instrument_terms_content(terms),
                )
                # The NOTIONAL leg converts from the DENOMINATION currency (DP-4), which need not
                # be any mark's currency — its convert path must be pinned too or the compute
                # gaps on an FX the binder could have supplied. Gated on the face value existing
                # (review fold F-0): a terms row with a denomination but NO face value produces no
                # NOTIONAL (DP-4 SKIP), so demanding its FX path would turn the ratified skip into
                # a whole-run pre-create FxRateNotFound refusal for a leg the compute never uses.
                if terms.denomination_currency is not None and terms.face_value is not None:
                    denomination_currencies.add(terms.denomination_currency)
        if e.mark is not None:
            val = resolve_valuation(session, e.mark.valuation_id, acting_tenant=acting_tenant)
            _append_spec(specs, COMPONENT_KIND_VALUATION, "valuation", val, valuation_content(val))
            if val.currency_code is not None:
                mark_currencies.add(val.currency_code)

    # 3a-bis. STRUCT-3 (REQ-PPM-008): pin the FULL scope subtree — every node including
    #    position-less grouping nodes — so the run's stored tree view is reconstructable from
    #    PORTFOLIO components alone (edges no longer dangle) and re-parenting a MIDDLE node
    #    after the run cannot change what the run saw.
    node_reporting_currencies: set[str] = set()
    if purpose == PURPOSE_EXPOSURE_INPUT:
        root = resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)
        subtree = [root, *resolve_descendants(session, root, acting_tenant=acting_tenant)]
        for node in subtree:
            if str(node.id) in seen_portfolios:
                continue
            seen_portfolios.add(str(node.id))
            _append_spec(
                specs, COMPONENT_KIND_PORTFOLIO, "portfolio", node, portfolio_content(node)
            )
        # STRUCT-4 (DP-11, v3 only): the set of reporting currencies a NODE read of this
        # snapshot could resolve — each node's declaration walked WITHIN the pinned subtree
        # chain (own -> nearest declared ancestor up to the scope root), mirroring EXACTLY what
        # the consume side can resolve from pinned content. A currency resolvable above the
        # scope root is deliberately excluded: the pin cannot answer it, so pinning for it
        # would promise a read the snapshot cannot honor.
        if binding_predicate_version == NODE_FX_BINDING_PREDICATE:
            by_id = {str(n.id): n for n in subtree}
            for node in subtree:
                current: Portfolio | None = node
                walked: set[str] = set()
                while current is not None and str(current.id) not in walked:
                    if current.base_currency_code:
                        node_reporting_currencies.add(current.base_currency_code)
                        break
                    walked.add(str(current.id))
                    parent_id = current.parent_portfolio_id
                    current = by_id.get(str(parent_id)) if parent_id else None

    # 3b. P2-3: pin the FX legs (EXPOSURE_INPUT). For each distinct mark/denomination currency,
    #     pin the convert-path fx_rate rows to every conversion TARGET (triangulation pivot =
    #     DEFAULT_BASE). v1/v2: the single target is the run base (the shipped semantics,
    #     byte-identical). v3 (STRUCT-4, DP-11): the target set is REDEFINED as {run base} ∪ the
    #     resolved node reporting currencies in scope — including base -> node-currency legs, so
    #     a node total can be translated from pins alone. FX-completeness fails closed
    #     (FxRateNotFound) BEFORE any write if any required leg is missing as-of.
    if base_currency is not None:
        fx_targets = {base_currency}
        if binding_predicate_version == NODE_FX_BINDING_PREDICATE:
            fx_targets |= node_reporting_currencies
        seen_fx: set[str] = set()
        for ccy in sorted(mark_currencies | denomination_currencies | fx_targets):
            for target in sorted(fx_targets):
                if ccy == target:
                    continue
                for fx_row in resolve_conversion_legs(
                    session,
                    from_currency=ccy,
                    to_currency=target,
                    valid_at=as_of_valid_at,
                    acting_tenant=acting_tenant,
                    known_at=known,
                    base=DEFAULT_BASE,
                ):
                    if fx_row.id in seen_fx:
                        continue
                    seen_fx.add(fx_row.id)
                    _append_spec(specs, COMPONENT_KIND_FX, "fx_rate", fx_row, fx_content(fx_row))

    # 4. No empty / foreign-scope snapshot (fail closed before any write).
    if not specs:
        raise EmptySnapshotError(str(portfolio_id))

    # 5+6. Header + components + internal lineage (the shared P3-4-R0 persistence tail).
    header = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label=label,
        purpose=purpose,
        as_of_valid_at=as_of_valid_at,
        as_of_known_at=known,
        as_of_valuation_date=val_date,
        binding_predicate_version=binding_predicate_version,
    )

    # 7. Completeness gate (fail-closed; rollback on a gap) then the SNAPSHOT.CREATE event
    _run_completeness_gate(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        header=header,
        holdings=holdings,
        enriched=enriched,
    )
    record_snapshot_create(session, header=header, actor=actor)
    return header


def _persist_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    specs: list[tuple[str, str, Any, str, str]],
    label: str,
    purpose: str,
    as_of_valid_at: datetime,
    as_of_known_at: datetime,
    as_of_valuation_date: date,
    binding_predicate_version: str,
) -> DatasetSnapshot:
    """The shared snapshot persistence tail (P3-4-R0 — extracted from the three builders at the
    review-flagged tipping point): manifest hash over the specs + the immutable header + one
    component row per spec + one internal lineage edge per pinned target. The caller runs its own
    completeness gate(s) and ``record_snapshot_create`` AFTER this returns (ordering preserved
    byte-identically from the pre-R0 builders)."""
    # THE PURPOSE ALLOW-LIST, ENFORCED WHERE EVERY BUILD PATH PASSES (SR-1).
    #
    # Until SR-1 this check lived ONLY at the two generic entry points (`build_snapshot` and
    # `build_window_snapshot`), while the fifteen family builders passed their own constant straight
    # to this tail — so `SNAPSHOT_PURPOSES` was convention on the paths that actually mint governed
    # snapshots, and documentation everywhere it was described as "the ENFORCED allow-list". Raising
    # here makes it enforcement: this is the single line every build path crosses, and it still
    # fires
    # BEFORE any write (the header below is the first INSERT), so a bad purpose mints no immutable
    # governance garbage.
    #
    # The generic entry points keep their own check: it refuses before the subtree enumeration and
    # the portfolio resolution, which is cheaper and gives the caller a better-placed error.
    if purpose not in SNAPSHOT_PURPOSES:
        raise SnapshotPurposeError(purpose)
    m_hash = manifest_hash(
        tenant_id=acting_tenant,
        as_of_valid_at=as_of_valid_at,
        as_of_known_at=as_of_known_at,
        as_of_valuation_date=as_of_valuation_date,
        binding_predicate_version=binding_predicate_version,
        component_count=len(specs),
        component_hashes=[(kind, row.id, c_hash) for (kind, _t, row, _cc, c_hash) in specs],
    )
    header = DatasetSnapshot(
        tenant_id=str(acting_tenant),
        label=label,
        purpose=purpose,
        as_of_valid_at=as_of_valid_at,
        as_of_known_at=as_of_known_at,
        as_of_valuation_date=as_of_valuation_date,
        binding_predicate_version=binding_predicate_version,
        component_count=len(specs),
        manifest_hash=m_hash,
        created_by=actor.actor_id,
    )
    session.add(header)
    session.flush()
    for kind, ttype, row, captured, c_hash in specs:
        comp = DatasetSnapshotComponent(
            tenant_id=str(acting_tenant),
            snapshot_id=header.id,
            component_kind=kind,
            target_entity_type=ttype,
            target_entity_id=row.id,
            pinned_valid_from=getattr(row, "valid_from", None),
            pinned_system_from=getattr(row, "system_from", None),
            pinned_record_version=getattr(row, "record_version", None),
            captured_content=captured,
            content_hash=c_hash,
        )
        session.add(comp)
    session.flush()
    # One edge per unique pinned TARGET (P3-4: a factor appears under BOTH the FACTOR and the
    # FACTOR_RETURN kind — the input is still one row; prior builders never repeat a target, so
    # this is behavior-preserving for them).
    seen_targets: set[tuple[str, str]] = set()
    for _kind, ttype, row, _captured, _ch in specs:
        if (ttype, row.id) in seen_targets:
            continue
        seen_targets.add((ttype, row.id))
        record_internal_lineage(
            session, snapshot_id=header.id, target_entity_type=ttype, target_entity_id=row.id
        )
    return header


def _append_spec(
    specs: list[tuple[str, str, Any, str, str]],
    kind: str,
    target_type: str,
    row: Any,
    content: dict[str, Any],
) -> None:
    captured = serialize_content(content)
    specs.append((kind, target_type, row, captured, content_hash(captured)))


@dataclass(frozen=True)
class CurveSelector:
    """The full ``reconstruct_curve_as_of`` logical key for one curve to pin in a sensitivity-input
    snapshot (OD-P3-1-E). ``reference_key`` is ``"NONE"`` for a rate curve / the issuer-rating
    label
    for a ``CREDIT_SPREAD`` curve."""

    curve_type: str
    currency_code: str
    curve_date: date
    curve_source: str
    reference_key: str = REFERENCE_KEY_NONE


class CurveSnapshotError(Exception):
    """Raised when a requested curve selector does not resolve to a curve as-of (fail closed,
    BEFORE
    any write) — the curve-presence gate for a sensitivity-input snapshot. Maps to 409/404."""

    def __init__(self, selector: CurveSelector) -> None:
        super().__init__(f"no curve for selector {selector!r} as-of (fail closed)")
        self.selector = selector


def _run_curve_completeness_gate(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    header: DatasetSnapshot,
    empty_curve_ids: list[str],
) -> None:
    """Fail-closed completeness for a curve snapshot: every pinned curve MUST carry >=1 node. The
    gap
    (a curve with zero ``curve_point`` rows) is one ``{'present': None}`` row through the shipped
    ``run_quality_check`` NOT_NULL rule (Protocol UNTOUCHED) -> ``DataQualityError`` ->
    rollback."""
    rule = _ensure_snapshot_presence_rule(session, acting_tenant=acting_tenant, actor=actor)
    run_presence_gate(
        session,
        rule=rule,
        gaps=empty_curve_ids,
        target_entity_type="dataset_snapshot",
        target_entity_id=header.id,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
    )


def build_curve_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    curve_selectors: list[CurveSelector],
    as_of_valid_at: datetime,
    as_of_known_at: datetime | None = None,
    label: str = "",
    purpose: str = PURPOSE_SENSITIVITY_INPUT,
    binding_predicate_version: str = DEFAULT_BINDING_PREDICATE,
) -> DatasetSnapshot:
    """Build one immutable ``SENSITIVITY_INPUT`` snapshot pinning a set of ``curve`` versions
    (header + immutable node set) as ``COMPONENT_KIND_CURVE`` components — so an
    analytic-sensitivity
    run is reproducible from the snapshot alone (it reads the captured curve content, never a live
    curve read; OD-P3-1-E/F). Each selector is resolved at ``as_of_valid_at``/``as_of_known_at``
    via
    ``reconstruct_curve_as_of`` (cross-tenant/unknown fails closed). A selector with no curve as-of
    raises :class:`CurveSnapshotError` (curve-presence gate, before any write); a pinned curve with
    zero nodes fails the completeness gate. Curve-only — NO portfolio scope, computes NO number."""
    if purpose not in SNAPSHOT_PURPOSES:
        raise SnapshotPurposeError(purpose)
    known = as_of_known_at if as_of_known_at is not None else utcnow()
    val_date = as_of_valid_at.date()

    specs: list[tuple[str, str, Any, str, str]] = []
    empty_curve_ids: list[str] = []
    seen: set[str] = set()
    for sel in curve_selectors:
        header = reconstruct_curve_as_of(
            session,
            acting_tenant=acting_tenant,
            curve_type=sel.curve_type,
            currency_code=sel.currency_code,
            curve_date=sel.curve_date,
            curve_source=sel.curve_source,
            valid_at=as_of_valid_at,
            reference_key=sel.reference_key,
            known_at=known,
        )
        if header is None:
            raise CurveSnapshotError(sel)
        if header.id in seen:
            continue
        seen.add(header.id)
        nodes = list_curve_points(session, header.id, acting_tenant=acting_tenant)
        if not nodes:
            empty_curve_ids.append(header.id)
        _append_spec(specs, COMPONENT_KIND_CURVE, "curve", header, curve_content(header, nodes))

    if not specs:
        raise EmptySnapshotError("(no curve selectors)")

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label=label,
        purpose=purpose,
        as_of_valid_at=as_of_valid_at,
        as_of_known_at=known,
        as_of_valuation_date=val_date,
        binding_predicate_version=binding_predicate_version,
    )

    _run_curve_completeness_gate(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        header=header_row,
        empty_curve_ids=empty_curve_ids,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class FactorExposureSnapshotError(Exception):
    """Raised when a factor-exposure input snapshot cannot be built (an empty atom set for the
    exposure run, an empty factor list, or an unresolvable input) — fail closed, BEFORE any
    write. Maps to 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"factor-exposure snapshot input failed closed: {detail}")
        self.detail = detail


def _resolve_exposure_atom(session: Session, atom_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``exposure_aggregate`` atom by id with an EXPLICIT tenant predicate (models-only
    import — ``exposure.models`` imports no ``snapshot``/``calc`` symbol, so the one-way surface
    holds; the ``exposure`` SERVICE is deliberately NOT imported here, it imports ``snapshot``)."""
    from irp_shared.exposure.models import ExposureAggregate  # models-only (no cycle)

    row = session.execute(
        select(ExposureAggregate).where(
            ExposureAggregate.id == str(atom_id),
            ExposureAggregate.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise FactorExposureSnapshotError(f"exposure atom {atom_id} is not visible")
    return row


def _list_exposure_atoms(
    session: Session, run_id: str, *, acting_tenant: str, consuming_run_type: str
) -> list[Any]:
    """The ``exposure_aggregate`` atoms of a run FOR ONE CONSUMING FAMILY (tenant-scoped, stable
    order; models-only import).

    STRUCT-1 (REQ-PPM-006): the builder consults the family's consumed-measure declaration
    (``irp_shared.aggregation.contracts``) and pins ONLY atoms of that measure — with two measures
    per holding in one run, an unfiltered pin would double-count in every downstream sum. The
    declaration is the SINGLE filter authority: an undeclared family refuses here (fail-closed,
    ``UndeclaredConsumerError``), and the family's own pin parser refuses any foreign-measure atom
    that reaches it anyway (defense in depth)."""
    from irp_shared.aggregation.contracts import consumed_exposure_measure  # no cycle
    from irp_shared.exposure.models import ExposureAggregate  # models-only (no cycle)

    measure = consumed_exposure_measure(consuming_run_type)
    return list(
        session.execute(
            select(ExposureAggregate)
            .where(
                ExposureAggregate.calculation_run_id == str(run_id),
                ExposureAggregate.tenant_id == str(acting_tenant),
                ExposureAggregate.exposure_type == measure,
            )
            .order_by(ExposureAggregate.portfolio_id, ExposureAggregate.instrument_id)
        )
        .scalars()
        .all()
    )


#: The factor-exposure binding/selection rule (a truthful descriptor — NOT the P2-1
#: subtree-open-positions rule; the 2026-07 review finding).
FACTOR_EXPOSURE_BINDING_PREDICATE = "v1:exposure-run-atoms+factor-list"
#: The PA-2 proxy-model selection rule (OD-PA-2-C): atoms + factors + the CURRENT-HEAD proxy rows
#: of every pinned atom's instrument. The proxy binder REQUIRES this predicate.
FACTOR_EXPOSURE_PROXY_BINDING_PREDICATE = "v1:exposure-run-atoms+factor-list+proxy-rows"
#: FL-1 (OD-FL-1-D): the loadings-family selection rule — the SAME pinned content as the proxy
#: predicate (atoms + factors + the widened ENT-019 loading rows), but a DISTINCT predicate string
#: so the three families refuse each other's snapshots (the 3×3 symmetry). The loadings binder
#: REQUIRES this predicate; the allocation and proxy binders refuse it.
FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE = "v1:exposure-run-atoms+factor-list+loading-rows"


def build_factor_exposure_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_id: str,
    factor_ids: list[str],
    include_proxy_rows: bool = False,
    loadings_family: bool = False,
) -> DatasetSnapshot:
    """Build one immutable ``FACTOR_EXPOSURE_INPUT`` snapshot (P3-3, OD-P3-3-I) pinning:

    - one ``COMPONENT_KIND_EXPOSURE`` component per ``exposure_aggregate`` atom of the consumed
      exposure run — the FIRST **IA-row pin flavor** (``pinned_valid_from``/``record_version``
      NULL; ``pinned_system_from`` = the row's append time; drift impossible by construction), and
    - one ``COMPONENT_KIND_FACTOR`` component per selected ``factor`` EV definition (the
      ``PORTFOLIO`` EV-pin flavor; ``record_version`` the drift discriminator),

    so a factor-exposure run is reproducible from the snapshot alone (the compute reads this
    captured content — never a live exposure/factor read). Every input is re-resolved by id under
    the acting tenant (cross-tenant/unknown fails closed BEFORE any write). The run-status /
    factor-set partition validation is the RISK binder's pre-create gate — this builder pins,
    it does not adjudicate; it needs **no as-of** (the atoms are immutable; the header cutoffs are
    the pin time) and imports NO ``calc`` symbol. NO derived number is computed here. An empty
    atom set OR an empty ``factor_ids`` list fails closed BEFORE any write (a factor-less
    snapshot could only ever produce a refused run).

    **PA-2 (``include_proxy_rows=True`` — the proxy model's build path):** additionally pins
    one ``COMPONENT_KIND_PROXY_MAPPING`` per CURRENT-HEAD ``proxy_mapping`` row of every
    pinned atom's instrument (the per-row FR flavor; TR-09), and stamps the
    ``...+proxy-rows`` binding predicate — LOAD-BEARING: the run binder gates on it in BOTH
    directions (OD-PA-2-C), so never flip this flag independently of the bound model.

    **FL-1 (``loadings_family=True`` — the loadings model's build path):** pins the SAME
    ``COMPONENT_KIND_PROXY_MAPPING`` rows (the widened ENT-019 IS the loadings source — the pin
    serializer is untouched; ``private_instrument_id`` stays the key) but stamps the DISTINCT
    ``...+loading-rows`` predicate so the three families refuse each other's snapshots (the 3×3
    symmetry). Mutually exclusive with ``include_proxy_rows``."""
    now = utcnow()

    if include_proxy_rows and loadings_family:
        raise FactorExposureSnapshotError(
            "include_proxy_rows and loadings_family are mutually exclusive (one bound model per "
            "snapshot)"
        )
    if not factor_ids:
        raise FactorExposureSnapshotError("no factor ids to pin — an empty factor set is refused")
    atoms = _list_exposure_atoms(
        session, exposure_run_id, acting_tenant=acting_tenant, consuming_run_type="FACTOR_EXPOSURE"
    )
    if not atoms:
        raise FactorExposureSnapshotError(
            f"exposure run {exposure_run_id} has no visible atoms to pin"
        )

    specs: list[tuple[str, str, Any, str, str]] = []
    for atom in atoms:
        _append_spec(
            specs, COMPONENT_KIND_EXPOSURE, "exposure_aggregate", atom, exposure_content(atom)
        )
    seen_factors: set[str] = set()
    for fid in factor_ids:
        factor = resolve_factor(session, str(fid), acting_tenant=acting_tenant)
        if factor.id in seen_factors:
            continue
        seen_factors.add(factor.id)
        _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", factor, factor_content(factor))

    if include_proxy_rows or loadings_family:
        # PA-2 (OD-PA-2-C) / FL-1 (OD-FL-1-D): pin the CURRENT-HEAD proxy_mapping rows of every
        # pinned atom's instrument (the per-row FR flavor — a later weight supersede is invisible,
        # TR-09). For the PROXY family an instrument WITHOUT rows follows the indicator path and
        # zero rows overall degrades to allocation-v1; for the LOADINGS family an unloaded atom is
        # a fail-closed refusal at the binder's coverage gate (OD-FL-1-D), NOT decided here — this
        # builder pins, it does not adjudicate.
        # models-only (no cycle)
        from irp_shared.marketdata.models import (
            LOADING_FACTOR_FAMILIES,
            Factor,
            ProxyMapping,
        )

        # PPF-1 guard 1 (OD-PPF-1-B): family-scope the pinned proxy rows to the PUBLIC loading
        # families. A PPF-1 segment-membership row (a weight-1 MANUAL row onto a PRIVATE-family
        # factor) must NEVER be pinned into a public factor-exposure snapshot — unguarded it would
        # refuse every new PA-2/FL-1 run pre-create (the pinned PRIVATE factor is not in the
        # caller's factor_ids, and the family gate closes the "include it" escape). Every EXISTING
        # proxy/loading row's factor is already in LOADING_FACTOR_FAMILIES (the pre-PPF-1 capture
        # gate admitted nothing else), so this filter is byte-identical for all existing data and
        # excludes exactly the new PRIVATE rows.
        instrument_ids = sorted({str(a.instrument_id) for a in atoms})
        proxy_rows = (
            session.execute(
                select(ProxyMapping)
                .join(Factor, Factor.id == ProxyMapping.factor_id)
                .where(
                    ProxyMapping.tenant_id == str(acting_tenant),
                    ProxyMapping.private_instrument_id.in_(instrument_ids),
                    ProxyMapping.valid_to.is_(None),
                    ProxyMapping.system_to.is_(None),
                    Factor.factor_family.in_(LOADING_FACTOR_FAMILIES),
                )
                .order_by(ProxyMapping.private_instrument_id, ProxyMapping.factor_id)
            )
            .scalars()
            .all()
        )
        for row in proxy_rows:
            _append_spec(
                specs,
                COMPONENT_KIND_PROXY_MAPPING,
                "proxy_mapping",
                row,
                proxy_mapping_content(row),
            )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_FACTOR_EXPOSURE_INPUT,
        as_of_valid_at=now,
        as_of_known_at=now,
        as_of_valuation_date=now.date(),
        binding_predicate_version=(
            FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE
            if loadings_family
            else FACTOR_EXPOSURE_PROXY_BINDING_PREDICATE
            if include_proxy_rows
            else FACTOR_EXPOSURE_BINDING_PREDICATE
        ),
    )

    # No build-time DQ gate: the pinned atoms exist by construction (an empty set is refused
    # above) and the mapping-completeness gate is the RISK binder's fail-closed POST-create gate
    # (OD-P3-3-N) — a snapshot-level gap class does not exist for immutable-atom pins.
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class CovarianceSnapshotError(Exception):
    """Raised when a covariance-input snapshot cannot be built (fewer than two distinct factors,
    a window shorter than two observations, fewer than ``window_observations`` common return
    dates, or an unresolvable input) — fail closed, BEFORE any write. Maps to 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"covariance snapshot input failed closed: {detail}")
        self.detail = detail


def _resolve_factor_return_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``factor_return`` FR row by surrogate id with an EXPLICIT tenant predicate (the
    verify-path re-read; ``marketdata/factor.py`` stays UNTOUCHED — this is a snapshot-side
    resolver, the ``_resolve_exposure_atom`` precedent)."""
    row = session.execute(
        select(FactorReturn).where(
            FactorReturn.id == str(row_id),
            FactorReturn.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise CovarianceSnapshotError(f"factor return {row_id} is not visible")
    return row


def _factor_window_rows(
    session: Session,
    *,
    acting_tenant: str,
    factor_id: str,
    valid_at: datetime,
    known_at: datetime,
) -> dict[date, Any]:
    """The ``SIMPLE`` return VERSIONS of one factor true at ``valid_at`` as known at ``known_at``,
    keyed by ``return_date`` (dates > ``valid_at.date()`` excluded) — via the EXISTING reads only.
    The current-head list only ENUMERATES candidate dates (a superset of the dates known at any
    cut — a captured logical key always keeps exactly one open head); the pinned VERSION per date
    always comes from ``reconstruct_factor_return_as_of`` on BOTH axes, so the frozen header
    cutoffs reproduce the pinned content (the 2026-07 review fix: a current-heads default branch
    ignored the valid axis — a backdated ``valid_at`` under a later supersede, or a
    future-effective supersede, pinned a version NOT valid at the declared instant)."""
    head_dates = [
        r.return_date
        for r in list_factor_returns(
            session,
            acting_tenant=acting_tenant,
            factor_id=factor_id,
            return_type=RETURN_TYPE_SIMPLE,
        )
        if r.return_date <= valid_at.date()
    ]
    out: dict[date, Any] = {}
    for return_date in head_dates:
        row = reconstruct_factor_return_as_of(
            session,
            acting_tenant=acting_tenant,
            factor_id=factor_id,
            return_date=return_date,
            valid_at=valid_at,
            return_type=RETURN_TYPE_SIMPLE,
            known_at=known_at,
        )
        if row is not None:
            out[row.return_date] = row
    return out


#: The covariance binding/selection rule (OD-P3-4-I): the N most recent COMMON ``SIMPLE`` return
#: dates per selected factor, current/as-known-at the header cutoffs.
COVARIANCE_BINDING_PREDICATE = "v1:factor-return-window"


def build_covariance_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    factor_ids: list[str],
    window_observations: int,
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``COVARIANCE_INPUT`` snapshot (P3-4, OD-P3-4-I) pinning, per selected
    factor:

    - one ``COMPONENT_KIND_FACTOR`` component (the EV definition pin — the P3-3 flavor), and
    - one ``COMPONENT_KIND_FACTOR_RETURN`` component — the factor's aligned RETURN WINDOW: the
      ``window_observations`` most recent return dates COMMON to every selected factor (FR rows,
      the ``curve`` header+nodes shape; ``target_entity_type='factor'``, the series parent),

    so a covariance run is reproducible from the snapshot alone (the compute reads this captured
    content — never a live factor/return read; a later vendor supersede/correction of a window
    return is invisible to the pin, TR-09). Alignment is **fail-closed, no imputation/pairwise**
    (OD-P3-0-L): fewer than ``window_observations`` common dates raises
    :class:`CovarianceSnapshotError` BEFORE any write, as do a duplicate/sub-two factor list and
    a sub-two window. The declared-window/factor-frequency adjudication is the RISK binder's
    pre-create gate — this builder pins a well-formed window; it does not read the model
    registry. NO derived number is computed here."""
    now = utcnow()
    valid_at = as_of_valid_at if as_of_valid_at is not None else now
    known = as_of_known_at if as_of_known_at is not None else now  # FROZEN once (header == pin)

    if window_observations < 2:
        raise CovarianceSnapshotError(
            f"window_observations must be >= 2 (got {window_observations})"
        )
    # Lowercase-normalized dedup: PG resolves GUIDs case-insensitively, so case-variant spellings
    # of one id are the SAME factor (the 2026-07 review fix — a case-sensitive check let them
    # through to an IntegrityError inside _persist_snapshot on PG / a spurious 404 on SQLite).
    distinct_ids = list(dict.fromkeys(str(fid).lower() for fid in factor_ids))
    if len(distinct_ids) != len(factor_ids):
        raise CovarianceSnapshotError("duplicate factor ids — an ambiguous series set is refused")
    if len(distinct_ids) < 2:
        raise CovarianceSnapshotError(
            f"a covariance snapshot needs >= 2 distinct factors (got {len(distinct_ids)})"
        )

    factors = [resolve_factor(session, fid, acting_tenant=acting_tenant) for fid in distinct_ids]
    resolved_ids = [str(factor.id).lower() for factor in factors]
    if len(set(resolved_ids)) != len(resolved_ids):  # any residual aliasing — refuse pre-write
        raise CovarianceSnapshotError("duplicate factor ids — an ambiguous series set is refused")
    by_date = {
        factor.id: _factor_window_rows(
            session,
            acting_tenant=acting_tenant,
            factor_id=factor.id,
            valid_at=valid_at,
            known_at=known,
        )
        for factor in factors
    }

    # The N most recent COMMON dates (set intersection; fail-closed on a short overlap).
    common: set[date] = set.intersection(*(set(rows.keys()) for rows in by_date.values()))
    if len(common) < window_observations:
        raise CovarianceSnapshotError(
            f"only {len(common)} common return dates across {len(factors)} factors — "
            f"the declared window needs {window_observations} (no imputation, OD-P3-0-L)"
        )
    window_dates = sorted(common)[-window_observations:]

    specs: list[tuple[str, str, Any, str, str]] = []
    for factor in factors:
        window_rows = [by_date[factor.id][d] for d in window_dates]
        _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", factor, factor_content(factor))
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_RETURN,
            "factor",
            factor,
            factor_return_series_content(factor, window_rows),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_COVARIANCE_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=window_dates[-1],
        binding_predicate_version=COVARIANCE_BINDING_PREDICATE,
    )

    # No build-time DQ gate: the window is complete by construction (a short/misaligned window is
    # refused above, before any write) — the P3-3 no-snapshot-gap-class rationale.
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class VarSnapshotError(Exception):
    """Raised when a VaR-input snapshot cannot be built (an upstream run with no visible result
    rows, or an unresolvable pinned row) — fail closed, BEFORE any write. Maps to 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"VaR snapshot input failed closed: {detail}")
        self.detail = detail


class ActiveRiskSnapshotError(VarSnapshotError):
    """Raised when an ACTIVE_RISK_INPUT snapshot cannot be built (an upstream run with no visible
    rows, or a benchmark with no membership as-of) — fail closed, BEFORE any write. Subclasses
    :class:`VarSnapshotError` (shares the 409 + the row-resolver helpers) but carries an active-risk
    diagnostic so the wire detail names the right family (review). Maps to 409."""

    def __init__(self, detail: str) -> None:
        super(VarSnapshotError, self).__init__(
            f"active-risk snapshot input failed closed: {detail}"
        )
        self.detail = detail


def _resolve_factor_exposure_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``factor_exposure_result`` row by id with an EXPLICIT tenant predicate
    (models-only, FUNCTION-LOCAL import — hoisting would execute ``irp_shared.risk.__init__``,
    which imports the risk services, which import ``snapshot``: a circular import. The risk
    SERVICE is never imported here — the P3-3 ``_resolve_exposure_atom`` precedent)."""
    from irp_shared.risk.models import FactorExposureResult  # models-only (no cycle)

    row = session.execute(
        select(FactorExposureResult).where(
            FactorExposureResult.id == str(row_id),
            FactorExposureResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise VarSnapshotError(f"factor exposure row {row_id} is not visible")
    return row


def _resolve_covariance_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``covariance_result`` row by id with an EXPLICIT tenant predicate (models-only
    function-local import — see :func:`_resolve_factor_exposure_row`)."""
    from irp_shared.risk.models import CovarianceResult  # models-only (no cycle)

    row = session.execute(
        select(CovarianceResult).where(
            CovarianceResult.id == str(row_id),
            CovarianceResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise VarSnapshotError(f"covariance row {row_id} is not visible")
    return row


def _resolve_benchmark_constituent_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``benchmark_constituent`` FR row by surrogate id with an EXPLICIT tenant
    predicate (models-only function-local import — see :func:`_resolve_factor_exposure_row`; the
    marketdata SERVICE is never imported here)."""
    from irp_shared.marketdata.models import BenchmarkConstituent  # models-only (no cycle)

    row = session.execute(
        select(BenchmarkConstituent).where(
            BenchmarkConstituent.id == str(row_id),
            BenchmarkConstituent.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise VarSnapshotError(f"benchmark constituent {row_id} is not visible")
    return row


def _resolve_instrument_terms_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``instrument_terms`` FR row by surrogate id with an EXPLICIT tenant predicate
    (STRUCT-1; the ``_resolve_proxy_mapping_row`` precedent). Raises ``InstrumentNotVisible`` (the
    id in the message is the TERMS row's) — already in verify's drift except-tuple (CON-1)."""
    from irp_shared.reference.models import InstrumentTerms  # models-only (no cycle)

    row = session.execute(
        select(InstrumentTerms).where(
            InstrumentTerms.id == str(row_id),
            InstrumentTerms.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise InstrumentNotVisible(str(row_id))
    return row


def _resolve_proxy_mapping_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``proxy_mapping`` FR row by surrogate id with an EXPLICIT tenant predicate
    (models-only function-local import — the ``_resolve_benchmark_constituent_row`` precedent)."""
    from irp_shared.marketdata.models import ProxyMapping  # models-only (no cycle)

    row = session.execute(
        select(ProxyMapping).where(
            ProxyMapping.id == str(row_id),
            ProxyMapping.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise FactorExposureSnapshotError(f"proxy mapping {row_id} is not visible")
    return row


def _resolve_scenario_shock_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``scenario_shock`` FR row by surrogate id with an EXPLICIT tenant predicate
    (models-only function-local import — the ``_resolve_benchmark_constituent_row`` precedent; the
    risk SERVICE is never imported here). Used by ``_reresolve_content`` for SCENARIO components."""
    from irp_shared.risk.scenario_models import ScenarioShock  # models-only (no cycle)

    row = session.execute(
        select(ScenarioShock).where(
            ScenarioShock.id == str(row_id),
            ScenarioShock.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ScenarioSnapshotError(f"scenario shock {row_id} is not visible")
    return row


def _list_factor_exposure_rows(session: Session, run_id: str, *, acting_tenant: str) -> list[Any]:
    """The ``factor_exposure_result`` rows of a run (tenant-scoped, stable order; models-only
    function-local import — the reader twin of ``risk.factor_service.list_factor_exposures``,
    re-implemented here because importing the risk SERVICE is a circular import)."""
    from irp_shared.risk.models import FactorExposureResult  # models-only (no cycle)

    return list(
        session.execute(
            select(FactorExposureResult)
            .where(
                FactorExposureResult.calculation_run_id == str(run_id),
                FactorExposureResult.tenant_id == str(acting_tenant),
            )
            .order_by(
                FactorExposureResult.factor_id,
                FactorExposureResult.portfolio_id,
                FactorExposureResult.instrument_id,
            )
        )
        .scalars()
        .all()
    )


def _list_covariance_rows(session: Session, run_id: str, *, acting_tenant: str) -> list[Any]:
    """The ``covariance_result`` rows of a run (tenant-scoped, canonical-pair order; models-only
    function-local import — the reader twin of ``risk.covariance_service.list_covariances``)."""
    from irp_shared.risk.models import CovarianceResult  # models-only (no cycle)

    return list(
        session.execute(
            select(CovarianceResult)
            .where(
                CovarianceResult.calculation_run_id == str(run_id),
                CovarianceResult.tenant_id == str(acting_tenant),
            )
            .order_by(CovarianceResult.factor_id_1, CovarianceResult.factor_id_2)
        )
        .scalars()
        .all()
    )


#: The VaR binding/selection rule (OD-P3-5-I): every result row of the two consumed runs.
VAR_BINDING_PREDICATE = "v1:exposure-run-rows+covariance-run-rows"


def build_var_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_id: str,
    covariance_run_id: str,
) -> DatasetSnapshot:
    """Build one immutable ``VAR_INPUT`` snapshot (P3-5, OD-P3-5-I) pinning EVERY result row of
    the two consumed upstream governed runs:

    - one ``COMPONENT_KIND_FACTOR_EXPOSURE`` component per ``factor_exposure_result`` row, and
    - one ``COMPONENT_KIND_COVARIANCE`` component per ``covariance_result`` row

    (both the IA-row pin flavor — the source rows are TRUE append-only; drift impossible by
    construction), so a VaR run is reproducible from the snapshot alone (the compute reads this
    captured content — never a live result read; a later upstream RE-RUN produces new rows under
    a NEW run and cannot move a pinned VaR). **NO factor-definition pin** — both row types carry
    ``factor_id`` + ``factor_code`` (self-describing; OD-P3-5-I). An empty row set on either run
    fails closed BEFORE any write. The run-status / coverage / consistency adjudication is the
    RISK binder's pre-create gate — this builder pins, it does not adjudicate; it needs no as-of
    (the rows are immutable) and imports NO ``calc``/risk-service symbol."""
    now = utcnow()

    exposure_rows = _list_factor_exposure_rows(
        session, exposure_run_id, acting_tenant=acting_tenant
    )
    if not exposure_rows:
        raise VarSnapshotError(f"exposure run {exposure_run_id} has no visible result rows")
    covariance_rows = _list_covariance_rows(session, covariance_run_id, acting_tenant=acting_tenant)
    if not covariance_rows:
        raise VarSnapshotError(f"covariance run {covariance_run_id} has no visible result rows")

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in exposure_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_EXPOSURE,
            "factor_exposure_result",
            row,
            factor_exposure_content(row),
        )
    for row in covariance_rows:
        _append_spec(
            specs, COMPONENT_KIND_COVARIANCE, "covariance_result", row, covariance_content(row)
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_VAR_INPUT,
        as_of_valid_at=now,
        as_of_known_at=now,
        as_of_valuation_date=covariance_rows[0].window_end,
        binding_predicate_version=VAR_BINDING_PREDICATE,
    )

    # No build-time DQ gate: the pinned rows exist by construction (empty sets are refused
    # above) — the P3-3/P3-4 no-snapshot-gap-class rationale.
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


#: The active-risk binding/selection rule (OD-P3-7-E): the two runs' rows + the covariance factor
#: definitions + the declared benchmark membership set. "fexp-rows" = factor-EXPOSURE rows (NOT
#: "fx-rows" — "fx" means foreign-exchange everywhere else in this module: COMPONENT_KIND_FX).
#: Length-guarded (see the ``_BINDING_PREDICATES`` module-end assert) against varchar(50).
ACTIVE_RISK_BINDING_PREDICATE = "v1:fexp-rows+cov-rows+cov-factors+benchmark-set"


def build_active_risk_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_id: str,
    covariance_run_id: str,
    benchmark_id: str,
    benchmark_effective_date: date,
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``ACTIVE_RISK_INPUT`` snapshot (P3-7, OD-P3-7-E) pinning:

    - one ``COMPONENT_KIND_FACTOR_EXPOSURE`` per ``factor_exposure_result`` row (the portfolio side)
      + one ``COMPONENT_KIND_COVARIANCE`` per ``covariance_result`` row (Sigma) — both IA-row pins;
    - one ``COMPONENT_KIND_FACTOR`` per distinct factor of the covariance set (the EV definition —
      the ``currency_code -> factor`` map the benchmark side needs); and
    - one ``COMPONENT_KIND_BENCHMARK`` per constituent of the declared ``(benchmark_id,
      effective_date)`` membership resolved as-of the FROZEN instants (FR-version pins; a later
      vendor supersede/correction is invisible — TR-09),

    so an active-risk run is reproducible from the snapshot alone. An empty exposure/covariance row
    set OR an empty membership fails closed BEFORE any write. The run-status / coverage / currency
    adjudication is the RISK binder's pre-create gate — this builder pins a well-formed set; it does
    not read the model registry and imports NO ``calc``/risk-service symbol."""
    now = utcnow()
    valid_at = as_of_valid_at if as_of_valid_at is not None else now
    known = as_of_known_at if as_of_known_at is not None else now  # FROZEN once (header == pin)

    exposure_rows = _list_factor_exposure_rows(
        session, exposure_run_id, acting_tenant=acting_tenant
    )
    if not exposure_rows:
        raise ActiveRiskSnapshotError(f"exposure run {exposure_run_id} has no visible result rows")
    covariance_rows = _list_covariance_rows(session, covariance_run_id, acting_tenant=acting_tenant)
    if not covariance_rows:
        raise ActiveRiskSnapshotError(
            f"covariance run {covariance_run_id} has no visible result rows"
        )

    benchmark = resolve_benchmark(session, str(benchmark_id), acting_tenant=acting_tenant)
    constituents = reconstruct_membership_as_of(
        session,
        acting_tenant=acting_tenant,
        benchmark_id=benchmark.id,
        effective_date=benchmark_effective_date,
        valid_at=valid_at,
        known_at=known,
    )
    if not constituents:
        raise ActiveRiskSnapshotError(
            f"benchmark {benchmark_id} has no membership for {benchmark_effective_date} "
            f"as-of the declared instants"
        )

    # The distinct factor definitions of the covariance set (lowercase-normalized), in stable order.
    covariance_factor_ids = list(
        dict.fromkeys(
            str(fid).lower()
            for row in covariance_rows
            for fid in (row.factor_id_1, row.factor_id_2)
        )
    )

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in exposure_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_EXPOSURE,
            "factor_exposure_result",
            row,
            factor_exposure_content(row),
        )
    for row in covariance_rows:
        _append_spec(
            specs, COMPONENT_KIND_COVARIANCE, "covariance_result", row, covariance_content(row)
        )
    for fid in covariance_factor_ids:
        factor = resolve_factor(session, fid, acting_tenant=acting_tenant)
        _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", factor, factor_content(factor))
    for constituent in constituents:
        _append_spec(
            specs,
            COMPONENT_KIND_BENCHMARK,
            "benchmark_constituent",
            constituent,
            benchmark_membership_content(benchmark, constituent),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_ACTIVE_RISK_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=benchmark_effective_date,
        binding_predicate_version=ACTIVE_RISK_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class ReturnSnapshotError(Exception):
    """Raised when a portfolio-return input snapshot cannot be built (fewer than two exposure-run
    boundaries, a boundary run with no atoms, an unresolvable input, or a missing FX leg for a
    non-base external flow) — fail closed, BEFORE any write. Its OWN class (a perf number never
    borrows a risk-family error — the V8 lesson). Maps to 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"portfolio-return snapshot input failed closed: {detail}")
        self.detail = detail


def _resolve_transaction_row(session: Session, txn_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``transaction`` by id with an EXPLICIT tenant predicate (models-only import — the
    ``_resolve_exposure_atom`` precedent: ``transaction.models`` imports no ``snapshot`` symbol, so
    the one-way surface holds; the ``transaction`` SERVICE is deliberately NOT imported here)."""
    from irp_shared.transaction.models import Transaction  # models-only (no cycle / fence-safe)

    row = session.execute(
        select(Transaction).where(
            Transaction.id == str(txn_id),
            Transaction.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ReturnSnapshotError(f"transaction {txn_id} is not visible")
    return row


def _list_transactions_in_window(
    session: Session,
    portfolio_ids: Sequence[str],
    *,
    start_exclusive: date,
    end_inclusive: date,
    acting_tenant: str,
) -> list[Any]:
    """The ``transaction`` rows of the given portfolios whose ``trade_date`` is in the half-open
    window ``(start_exclusive, end_inclusive]`` (tenant-scoped, stable ``(trade_date, id)`` order;
    models-only import). The FULL captured set is returned — ``snapshot`` never imports the perf
    external-flow set, so the binder does the flow filtering (a flow ON the first boundary is
    already in BMV, hence the exclusive lower bound)."""
    from irp_shared.transaction.models import Transaction  # models-only (no cycle / fence-safe)

    if not portfolio_ids:
        return []
    return list(
        session.execute(
            select(Transaction)
            .where(
                Transaction.tenant_id == str(acting_tenant),
                Transaction.portfolio_id.in_([str(p) for p in portfolio_ids]),
                Transaction.trade_date > start_exclusive,
                Transaction.trade_date <= end_inclusive,
            )
            .order_by(Transaction.trade_date, Transaction.id)
        )
        .scalars()
        .all()
    )


#: The portfolio-return binding/selection rule (a truthful descriptor; PM-1, OD-PM-1-E).
RETURN_BINDING_PREDICATE = "v1:exposure-run-atoms+flow-txns+fx-legs"


def build_return_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_ids: Sequence[str],
    flow_txn_types: Sequence[str],
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``RETURN_INPUT`` snapshot (PM-1, OD-PM-1-E) pinning:

    - one ``COMPONENT_KIND_EXPOSURE`` per ``exposure_aggregate`` atom of EACH consumed run (the
      P3-3 IA-row pin flavor) — the ``N >= 2`` valuation boundaries whose ``as_of_valuation_date``s
      (read from each run's input snapshot) are the sub-period edges;
    - one ``COMPONENT_KIND_TRANSACTION`` per ``transaction`` whose ``trade_date`` falls in the
      half-open span ``(earliest_boundary, latest_boundary]`` for the boundary portfolios (the FULL
      in-window set — ``snapshot`` never imports the flow set; the binder filters to flows); and
    - one ``COMPONENT_KIND_FX`` per distinct FX leg needed to convert a non-base external FLOW's
      currency to the boundary base currency, resolved at the flow's ``trade_date`` (rate_date =
      ``valid_at.date()`` via end-of-day) as-known at the FROZEN header ``known_at`` (a later FX
      correction is invisible — TR-09),

    so a portfolio-return run is reproducible from the snapshot alone (the binder reads this
    captured content — never a live exposure/transaction/FX read). ``flow_txn_types`` is passed as
    DATA (a sequence of ``txn_type`` strings — NOT a ``perf`` import; the ``snapshot -> ...`` fence
    holds) so FX legs are pinned ONLY for genuine flows: a foreign-currency BUY does not force an FX
    leg, but a missing leg for a real non-base flow DOES fail closed (no imputation). Fewer than two
    runs, or a boundary run with no atoms, fails closed BEFORE any write
    (:class:`ReturnSnapshotError`, its OWN class). The run-status / scope / base-currency /
    boundary-ordering adjudication is the PERF binder's pre-create gate — this builder pins a
    well-formed set; it reads no model registry and imports NO ``calc``/``perf`` symbol."""
    now = utcnow()
    valid_at = as_of_valid_at if as_of_valid_at is not None else now
    known = as_of_known_at if as_of_known_at is not None else now  # FROZEN once (header == pin)

    run_ids = list(exposure_run_ids)
    if len(run_ids) < 2:
        raise ReturnSnapshotError(
            f"a portfolio-return snapshot needs >= 2 exposure-run boundaries (got {len(run_ids)})"
        )
    if len({str(rid).lower() for rid in run_ids}) != len(run_ids):
        # A repeated run id would pin its atoms twice -> a duplicate (kind, target) violating
        # uq_dataset_snapshot_component_snapshot_kind_target at the SECOND flush, AFTER the header
        # is written -> a raw IntegrityError, NOT the "fail closed BEFORE any write" contract (the
        # build_covariance_snapshot duplicate-id precedent). Refuse here.
        raise ReturnSnapshotError("duplicate exposure-run boundary ids — an ambiguous set refused")
    flow_types = {str(t) for t in flow_txn_types}

    # 1. Resolve each boundary run's atoms + its valuation date (from the run's input snapshot). The
    #    binder validates run status / single scope / single base / strict ordering pre-create.
    per_run_atoms: list[list[Any]] = []
    boundary_dates: list[date] = []
    base_currency: str | None = None
    for run_id in run_ids:
        atoms = _list_exposure_atoms(
            session, run_id, acting_tenant=acting_tenant, consuming_run_type="PORTFOLIO_RETURN"
        )
        if not atoms:
            raise ReturnSnapshotError(f"exposure run {run_id} has no visible atoms to pin")
        boundary = resolve_snapshot(
            session, atoms[0].input_snapshot_id, acting_tenant=acting_tenant
        )
        per_run_atoms.append(atoms)
        boundary_dates.append(boundary.as_of_valuation_date)
        if base_currency is None:
            base_currency = atoms[0].base_currency
    if base_currency is None:  # exposure atoms are NOT NULL base_currency; fail closed if ever not
        raise ReturnSnapshotError("boundary exposure runs carry no base currency to convert flows")

    # 2. The measured span + the boundary portfolio scope.
    start_exclusive = min(boundary_dates)
    end_inclusive = max(boundary_dates)
    portfolio_ids = list(
        dict.fromkeys(atom.portfolio_id for atoms in per_run_atoms for atom in atoms)
    )

    # 3. Pin every atom of every boundary run (EXPOSURE).
    specs: list[tuple[str, str, Any, str, str]] = []
    for atoms in per_run_atoms:
        for atom in atoms:
            _append_spec(
                specs, COMPONENT_KIND_EXPOSURE, "exposure_aggregate", atom, exposure_content(atom)
            )

    # 4. Pin every in-window transaction (TRANSACTION) — the FULL set; the binder filters to flows.
    transactions = _list_transactions_in_window(
        session,
        portfolio_ids,
        start_exclusive=start_exclusive,
        end_inclusive=end_inclusive,
        acting_tenant=acting_tenant,
    )
    for txn in transactions:
        _append_spec(
            specs, COMPONENT_KIND_TRANSACTION, "transaction", txn, transaction_content(txn)
        )

    # 5. Pin the FX legs for the non-base FLOW currencies at each flow's trade_date (FR-version
    #    pins; a missing leg for a genuine flow fails closed — no imputation). rate_date ==
    #    trade_date via valid_at = end-of-day(trade_date); known_at frozen at the header (TR-09).
    seen_fx: set[str] = set()
    for txn in transactions:
        if txn.txn_type not in flow_types:
            continue  # not an external flow — the binder ignores it, so no conversion is needed
        ccy = txn.currency_code
        if ccy is None or ccy == base_currency:
            continue  # a NULL currency on a flow is a binder refusal (never imputed); base = no leg
        flow_valid_at = datetime.combine(txn.trade_date, time.max, tzinfo=UTC)
        for fx_row in resolve_conversion_legs(
            session,
            from_currency=ccy,
            to_currency=base_currency,
            valid_at=flow_valid_at,
            acting_tenant=acting_tenant,
            known_at=known,
            base=DEFAULT_BASE,
        ):
            if fx_row.id in seen_fx:
                continue
            seen_fx.add(fx_row.id)
            _append_spec(specs, COMPONENT_KIND_FX, "fx_rate", fx_row, fx_content(fx_row))

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_RETURN_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=end_inclusive,
        binding_predicate_version=RETURN_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class BenchmarkRelativeSnapshotError(Exception):
    """Raised when an ex-post benchmark-relative input snapshot cannot be built (a return run with
    no visible result rows, an unresolvable input, or an empty benchmark window over the whole span)
    — fail closed, BEFORE any write. Its OWN class (a perf number never borrows a risk-family error
    — the V8 lesson). Maps to 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"benchmark-relative snapshot input failed closed: {detail}")
        self.detail = detail


def _resolve_portfolio_return_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``portfolio_return_result`` by id with an EXPLICIT tenant predicate (models-only
    import — the ``_resolve_exposure_atom`` precedent: ``perf.models`` imports no ``snapshot``
    symbol, so the one-way surface holds; the ``perf`` SERVICE is deliberately not imported)."""
    from irp_shared.perf.models import PortfolioReturnResult  # models-only (no cycle / fence-safe)

    row = session.execute(
        select(PortfolioReturnResult).where(
            PortfolioReturnResult.id == str(row_id),
            PortfolioReturnResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise BenchmarkRelativeSnapshotError(f"portfolio_return_result {row_id} is not visible")
    return row


def _list_portfolio_return_rows(session: Session, run_id: str, *, acting_tenant: str) -> list[Any]:
    """The ``portfolio_return_result`` rows of a return run (tenant-scoped, stable
    ``(metric_type, period_start)`` order; models-only import). ALL metrics are returned — the
    binder reads the DIETZ_PERIOD series + the TWR_LINKED row for the exact-linkage cross-check."""
    from irp_shared.perf.models import PortfolioReturnResult  # models-only (no cycle / fence-safe)

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


def _resolve_benchmark_return_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``benchmark_return`` FR version by surrogate id with an EXPLICIT tenant predicate
    (models-only import — for the verify re-resolution of a pinned window row)."""
    from irp_shared.marketdata.models import BenchmarkReturn  # models-only (no cycle)

    row = session.execute(
        select(BenchmarkReturn).where(
            BenchmarkReturn.id == str(row_id),
            BenchmarkReturn.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise BenchmarkRelativeSnapshotError(f"benchmark_return {row_id} is not visible")
    return row


def _benchmark_return_window(
    session: Session,
    *,
    benchmark_id: str,
    return_basis: str,
    start_exclusive: date,
    end_inclusive: date,
    valid_at: datetime,
    known_at: datetime,
    acting_tenant: str,
) -> list[Any]:
    """The ``SIMPLE`` ``benchmark_return`` VERSIONS of ``return_basis`` true at ``valid_at`` as
    known at ``known_at`` whose ``return_date`` is in the half-open span ``(start_exclusive,
    end_inclusive]`` — via the EXISTING reads only (the ``_factor_window_rows`` pattern). The
    current-head list only
    ENUMERATES candidate dates; the pinned VERSION per date always comes from
    ``reconstruct_benchmark_return_as_of`` on BOTH axes, so the frozen header cutoffs reproduce the
    pinned content (a later vendor supersede/correction is invisible — TR-09)."""
    head_dates = {
        r.return_date
        for r in list_benchmark_returns(
            session, acting_tenant=acting_tenant, benchmark_id=benchmark_id
        )
        if r.return_type == RETURN_TYPE_SIMPLE
        and r.return_basis == return_basis
        and start_exclusive < r.return_date <= end_inclusive
    }
    out: list[Any] = []
    for return_date in sorted(head_dates):
        row = reconstruct_benchmark_return_as_of(
            session,
            acting_tenant=acting_tenant,
            benchmark_id=benchmark_id,
            return_date=return_date,
            return_basis=return_basis,
            valid_at=valid_at,
            return_type=RETURN_TYPE_SIMPLE,
            known_at=known_at,
        )
        if row is not None:
            out.append(row)
    return out


#: The benchmark-relative binding/selection rule (a truthful descriptor; P3-8, OD-P3-8-G).
BENCHMARK_RELATIVE_BINDING_PREDICATE = "v1:return-run-rows+benchmark-window"


def build_benchmark_relative_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    portfolio_return_run_id: str,
    benchmark_id: str,
    return_basis: str,
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``BENCHMARK_RELATIVE_INPUT`` snapshot (P3-8, OD-P3-8-G) pinning:

    - one ``COMPONENT_KIND_PORTFOLIO_RETURN`` per ``portfolio_return_result`` row of the consumed
      return run (the P3-3 IA-row pin flavor — the DIETZ_PERIOD series + the TWR_LINKED row); and
    - one ``COMPONENT_KIND_BENCHMARK_RETURN`` series component pinning the in-span ``SIMPLE`` /
      ``return_basis`` benchmark_return rows (the FACTOR_RETURN header+rows flavor; ENT-052's FIRST
      governed consumer),

    so a benchmark-relative run is reproducible from the snapshot alone (the binder reads this
    captured content — never a live return/benchmark read; a later PM-1 re-run OR a benchmark vendor
    correction cannot move a historical result, TR-09). The span is ``(min period_start, max
    period_end]`` over the pinned return rows. A return run with NO visible rows OR an EMPTY
    benchmark span fails closed BEFORE any write (:class:`BenchmarkRelativeSnapshotError`). The
    currency / basis-uniformity / linkage adjudication is the PERF binder's pre-create gate — this
    builder pins a well-formed set; it reads no model registry and imports NO ``calc``/``perf``
    SERVICE symbol (the return rows are a models-only read)."""
    now = utcnow()
    valid_at = as_of_valid_at if as_of_valid_at is not None else now
    known = as_of_known_at if as_of_known_at is not None else now  # FROZEN once (header == pin)

    return_rows = _list_portfolio_return_rows(
        session, portfolio_return_run_id, acting_tenant=acting_tenant
    )
    if not return_rows:
        raise BenchmarkRelativeSnapshotError(
            f"portfolio-return run {portfolio_return_run_id} has no visible result rows to pin"
        )
    span_start = min(r.period_start for r in return_rows)
    span_end = max(r.period_end for r in return_rows)

    benchmark = resolve_benchmark(session, str(benchmark_id), acting_tenant=acting_tenant)
    window = _benchmark_return_window(
        session,
        benchmark_id=benchmark.id,
        return_basis=return_basis,
        start_exclusive=span_start,
        end_inclusive=span_end,
        valid_at=valid_at,
        known_at=known,
        acting_tenant=acting_tenant,
    )
    if not window:
        raise BenchmarkRelativeSnapshotError(
            f"benchmark {benchmark_id} has no {return_basis} returns in "
            f"({span_start}, {span_end}] as-of the declared instants"
        )

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in return_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_PORTFOLIO_RETURN,
            "portfolio_return_result",
            row,
            portfolio_return_content(row),
        )
    _append_spec(
        specs,
        COMPONENT_KIND_BENCHMARK_RETURN,
        "benchmark",
        benchmark,
        benchmark_return_series_content(benchmark, window),
    )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_BENCHMARK_RELATIVE_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=span_end,
        binding_predicate_version=BENCHMARK_RELATIVE_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class VarBacktestSnapshotError(Exception):
    """Raised when a VaR-backtesting input snapshot cannot be built (a return/VaR run with no
    visible result rows, or an unresolvable input) — fail closed, BEFORE any write. Its OWN class
    (the V8 lesson). Maps to 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"var-backtest snapshot input failed closed: {detail}")
        self.detail = detail


def _resolve_var_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``var_result`` by id with an EXPLICIT tenant predicate (models-only import —
    the ``_resolve_portfolio_return_row`` precedent; the ``risk`` SERVICE is not imported)."""
    from irp_shared.risk.models import VarResult  # models-only (no cycle / fence-safe)

    row = session.execute(
        select(VarResult).where(
            VarResult.id == str(row_id),
            VarResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise VarBacktestSnapshotError(f"var_result {row_id} is not visible")
    return row


def _list_var_rows(session: Session, run_id: str, *, acting_tenant: str) -> list[Any]:
    """The ``var_result`` rows of a VAR run (tenant-scoped, stable ``window_end`` order;
    models-only import)."""
    from irp_shared.risk.models import VarResult  # models-only (no cycle / fence-safe)

    return list(
        session.execute(
            select(VarResult)
            .where(
                VarResult.calculation_run_id == str(run_id),
                VarResult.tenant_id == str(acting_tenant),
            )
            .order_by(VarResult.window_end, VarResult.id)
        )
        .scalars()
        .all()
    )


#: The var-backtest binding/selection rule (a truthful descriptor; BT-1, OD-BT-1-J).
VAR_BACKTEST_BINDING_PREDICATE = "v1:return-run-rows+var-run-rows"


def build_var_backtest_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    portfolio_return_run_id: str,
    var_run_ids: list[str],
) -> DatasetSnapshot:
    """Build one immutable ``VAR_BACKTEST_INPUT`` snapshot (BT-1, OD-BT-1-J) pinning:

    - one ``COMPONENT_KIND_PORTFOLIO_RETURN`` per ``portfolio_return_result`` row of the consumed
      return run (REUSED from P3-8 — the realized-P&L side); and
    - one ``COMPONENT_KIND_VAR`` per ``var_result`` row of EACH listed VAR run (the P3-3 IA-row
      pin flavor — the forecast side),

    so a backtest is reproducible from the snapshot alone (the binder reads this captured content —
    never a live result read; a later re-run of either side cannot move a historical backtest,
    TR-09). A run with NO visible rows — either side — or a DUPLICATE ``var_run_ids`` entry fails
    closed BEFORE any write (:class:`VarBacktestSnapshotError`). The alignment / uniformity /
    identity adjudication is the RISK binder's pre-create gate — this builder pins a well-formed
    set; it imports NO ``calc``/``perf``/``risk`` SERVICE symbol (both sides are models-only
    reads)."""
    now = utcnow()
    # Both sides are IA rows (no valid/known axis to reconstruct): the header instants are stamped
    # now/now — the build_var_snapshot precedent. Caller-supplied cutoffs would be a backdatable
    # knowledge-time claim binding NOTHING (review fold).
    valid_at = known = now

    if not var_run_ids:
        # The build_factor_exposure_snapshot precedent: a VAR-less "backtest input" could only ever
        # produce a refused run — refuse BEFORE any write, never mint immutable governance garbage
        # (review fold).
        raise VarBacktestSnapshotError("var_run_ids is empty — nothing to backtest")
    if len(var_run_ids) != len({str(r).lower() for r in var_run_ids}):
        raise VarBacktestSnapshotError("duplicate var_run_ids — each VAR run pins once")

    return_rows = _list_portfolio_return_rows(
        session, portfolio_return_run_id, acting_tenant=acting_tenant
    )
    if not return_rows:
        raise VarBacktestSnapshotError(
            f"portfolio-return run {portfolio_return_run_id} has no visible result rows to pin"
        )
    var_rows: list[Any] = []
    for run_id in var_run_ids:
        rows = _list_var_rows(session, str(run_id), acting_tenant=acting_tenant)
        if not rows:
            raise VarBacktestSnapshotError(f"VAR run {run_id} has no visible result rows to pin")
        var_rows.extend(rows)

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in return_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_PORTFOLIO_RETURN,
            "portfolio_return_result",
            row,
            portfolio_return_content(row),
        )
    for row in var_rows:
        _append_spec(specs, COMPONENT_KIND_VAR, "var_result", row, var_result_content(row))

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_VAR_BACKTEST_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=max(r.period_end for r in return_rows),
        binding_predicate_version=VAR_BACKTEST_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class RollingRiskSnapshotError(Exception):
    """A rolling-risk input snapshot cannot be built (a return run with no visible rows) — raised
    BEFORE any write; never mints immutable governance garbage."""


def holiday_calendar_content(calendar: Any, holiday_dates: list[Any]) -> dict[str, Any]:
    """The HOLIDAY_CALENDAR pin content (CAL-1b, OQ-CAL-1-6-A) — NARROW by design (the ISSUER_EDGE
    field-exclusion precedent): the calendar IDENTITY (code/mic), its DECLARED coverage horizon,
    and the SORTED member dates. ``name``/``is_active``/``record_version`` are deliberately
    EXCLUDED so a cosmetic head amend does not redden every historical v2 pin; a date ADD or a
    coverage advance — the changes that alter what a v2 run would compute — honestly does."""
    return {
        "code": calendar.code,
        "mic": calendar.mic,
        "holidays_complete_through": (
            calendar.holidays_complete_through.isoformat()
            if calendar.holidays_complete_through is not None
            else None
        ),
        "holiday_dates": sorted(
            d.isoformat() if hasattr(d, "isoformat") else str(d) for d in holiday_dates
        ),
    }


def _holiday_calendar_spec(
    session: Session,
    specs: list[tuple[str, str, Any, str, str]],
    *,
    holiday_calendar_code: str,
    acting_tenant: str,
    error: type[Exception],
) -> None:
    """Resolve the declared calendar own-OR-SYSTEM and append its HOLIDAY_CALENDAR pin (CAL-1b).
    Refusals surface as the builder's own error class (a 409 build failure, pre-write)."""
    from irp_shared.reference.models import CalendarHoliday
    from irp_shared.reference.service import CalendarNotVisible, resolve_calendar

    try:
        calendar = resolve_calendar(session, holiday_calendar_code, acting_tenant=acting_tenant)
    except CalendarNotVisible as exc:
        raise error(str(exc)) from exc
    dates = list(
        session.execute(
            select(CalendarHoliday.holiday_date).where(CalendarHoliday.calendar_id == calendar.id)
        ).scalars()
    )
    _append_spec(
        specs,
        COMPONENT_KIND_HOLIDAY_CALENDAR,
        "calendar",
        calendar,
        holiday_calendar_content(calendar, dates),
    )


#: The rolling-risk binding/selection rule (RM-1, OD-RM-1-E): every row of ONE return run.
ROLLING_RISK_BINDING_PREDICATE = "v1:portfolio-return-run-rows"


def build_rolling_risk_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    portfolio_return_run_id: str,
    holiday_calendar_code: str | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``ROLLING_RISK_INPUT`` snapshot (RM-1, OD-RM-1-E) pinning one
    ``COMPONENT_KIND_PORTFOLIO_RETURN`` per ``portfolio_return_result`` row of the consumed run.

    **No new pin-key surface, and therefore no historical pin drift.** The existing
    ``portfolio_return_content`` serializer already carries ``metric_type``, ``period_start``,
    ``period_end``, ``return_value`` and ``n_periods`` — which is everything the month partition,
    the relink, the volatility, the rolling return AND the compounded-index drawdown need. The
    verifier confirmed this sufficiency; reusing the serializer verbatim is what keeps every
    previously-written PROXY/RETURN pin byte-stable (the 0038/0040 false-drift landmine class).

    Both sides are IA rows with no valid/known axis to reconstruct, so the header instants are
    stamped now/now — BT-1's precedent. A caller-supplied cutoff would be a backdatable
    knowledge-time claim binding nothing.
    """
    now = utcnow()
    valid_at = known = now

    return_rows = _list_portfolio_return_rows(
        session, portfolio_return_run_id, acting_tenant=acting_tenant
    )
    if not return_rows:
        raise RollingRiskSnapshotError(
            f"portfolio-return run {portfolio_return_run_id} has no visible result rows to pin"
        )

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in return_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_PORTFOLIO_RETURN,
            "portfolio_return_result",
            row,
            portfolio_return_content(row),
        )
    if holiday_calendar_code is not None:  # CAL-1b: the v2 pin; v1 callers stay byte-identical
        _holiday_calendar_spec(
            session,
            specs,
            holiday_calendar_code=holiday_calendar_code,
            acting_tenant=acting_tenant,
            error=RollingRiskSnapshotError,
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_ROLLING_RISK_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=max(r.period_end for r in return_rows),
        binding_predicate_version=ROLLING_RISK_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class SharpeSnapshotError(Exception):
    """A Sharpe-ratio input snapshot cannot be built (a return run with no visible rows, or a
    risk-free series with no rows in the span) — raised BEFORE any write; never mints immutable
    governance garbage. Its OWN class (the V8 lesson). Maps to 409."""


#: The Sharpe binding/selection rule (SR-1, OD-SR-1-E): every row of ONE return run PLUS the in-span
#: risk-free benchmark return window. 48 chars — the varchar(50) ceiling genuinely bites here, which
#: is why the module-end ``_BINDING_PREDICATES`` assert exists.
SHARPE_BINDING_PREDICATE = "v1:portfolio-return-run-rows+rf-benchmark-window"


def build_sharpe_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    portfolio_return_run_id: str,
    risk_free_benchmark_id: str,
    rf_return_basis: str,
    holiday_calendar_code: str | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``SHARPE_INPUT`` snapshot (SR-1, OD-SR-1-E) pinning:

    - one ``COMPONENT_KIND_PORTFOLIO_RETURN`` per ``portfolio_return_result`` row of the consumed
      PM-1 run (the RM-1/P3-8 flavor, existing serializer, no new pin-key surface); and
    - one ``COMPONENT_KIND_BENCHMARK_RETURN`` series component pinning the in-span ``SIMPLE`` /
      ``rf_return_basis`` rows of the RISK-FREE benchmark head.

    **The risk-free series is an ordinary benchmark** (OQ-SR-1-2 = A): ENT-052 carries vendor-
    published fraction returns at the shared 12dp scale with no frequency column, so a monthly cash
    series is capturable today with zero vocabulary change — and ENT-052's twice-ratified constraint
    (*"captured vendor-published values ONLY — NEVER computed from levels"*) is honored on its face
    because SR-1 captures published RETURNS. A yield curve (ENT-021) would need a registered
    yield→period-return model plus one curve header and selector per month-end; recorded, costed,
    and
    not taken in v1.

    **The pinned window spans exactly the MEASURED MONTHS, whole.** The binder joins by MONTH KEY,
    so the window must be expressed in months too: from the FIRST DAY of the first measured month to
    the LAST DAY of the last measured month. Both edges are load-bearing and both were wrong in the
    first implementation, in opposite directions — a review found each by execution:

    - **The lower edge must NOT reach into ``d_0``'s month.** ``d_0`` is the close of the month
      BEFORE the first measured month, and the alignment criterion guarantees its month is never a
      measured month (condition 4 forbids another boundary there; condition 3 forces every interior
      month to contribute). Pinning from ``d_0``'s month therefore captured ONLY rows the binder is
      guaranteed to refuse as unconsumed pins — so an ordinary continuous vendor cash series, which
      of course also publishes that month, produced a permanently unrunnable snapshot. Immutable, so
      unrepairable.
    - **The upper edge must be the last day of the last measured MONTH, not ``span_end``.** A book
      may close on the last BUSINESS day (GIPS 2.A.23.b) while its vendor dates on the calendar
      month end; truncating at ``span_end`` then dropped the final month's risk-free row and the
      binder refused for a missing month. A pure calendar accident, firing in roughly five months
      of twelve — and exactly the pair the month-key join exists to accept.

    **The vendor's ``return_date`` must fall INSIDE the month its return is for.** That is a
    declared capture convention, not an inference: a series dated on the first of the FOLLOWING
    month joins one month late under a ``(year, month)`` key, and nothing in the data can
    distinguish that from a correctly-dated series — the row counts match exactly. Such a series
    must be re-dated at capture. Recorded as a limitation rather than silently accommodated.

    The binder still refuses any pinned row whose month is not a measured month. Under this window
    that refusal is structurally unreachable through the build path and is therefore honest
    defense-in-depth against a hand-built snapshot — an unconsumed pin is a lie in the provenance.

    Fails closed BEFORE any write on an empty return run or an empty risk-free window. Both sides
    are
    IA/FR rows the header cutoffs reproduce; instants are stamped now/now (BT-1's precedent — a
    caller-supplied cutoff would be a backdatable knowledge-time claim binding nothing).
    """
    now = utcnow()
    valid_at = known = now

    return_rows = _list_portfolio_return_rows(
        session, portfolio_return_run_id, acting_tenant=acting_tenant
    )
    if not return_rows:
        raise SharpeSnapshotError(
            f"portfolio-return run {portfolio_return_run_id} has no visible result rows to pin"
        )
    span_end = max(r.period_end for r in return_rows)
    # The MEASURED months, read off the sub-period ENDS (the month a return is realized into). The
    # smallest period_end lies in the FIRST measured month; the largest in the last. `period_start`
    # is deliberately NOT used: the smallest of those is d_0, whose month is never measured.
    first_measured_end = min(r.period_end for r in return_rows)
    month_floor = date(first_measured_end.year, first_measured_end.month, 1)
    month_ceiling = date(
        span_end.year,
        span_end.month,
        monthrange(span_end.year, span_end.month)[1],
    )

    benchmark = resolve_benchmark(session, str(risk_free_benchmark_id), acting_tenant=acting_tenant)
    window = _benchmark_return_window(
        session,
        benchmark_id=benchmark.id,
        return_basis=rf_return_basis,
        # Half-open on the lower side, so step back one day to include month_floor itself.
        start_exclusive=month_floor - timedelta(days=1),
        end_inclusive=month_ceiling,
        valid_at=valid_at,
        known_at=known,
        acting_tenant=acting_tenant,
    )
    if not window:
        raise SharpeSnapshotError(
            f"risk-free benchmark {risk_free_benchmark_id} has no {rf_return_basis} returns in "
            f"[{month_floor}, {month_ceiling}] as-of the declared instants"
        )

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in return_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_PORTFOLIO_RETURN,
            "portfolio_return_result",
            row,
            portfolio_return_content(row),
        )
    _append_spec(
        specs,
        COMPONENT_KIND_BENCHMARK_RETURN,
        "benchmark",
        benchmark,
        benchmark_return_series_content(benchmark, window),
    )
    if holiday_calendar_code is not None:  # CAL-1b: the v2 pin; v1 callers stay byte-identical
        _holiday_calendar_spec(
            session,
            specs,
            holiday_calendar_code=holiday_calendar_code,
            acting_tenant=acting_tenant,
            error=SharpeSnapshotError,
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_SHARPE_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=span_end,
        binding_predicate_version=SHARPE_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class ScenarioSnapshotError(Exception):
    """A scenario-input snapshot cannot be built (empty exposure run / empty shock set) — raised
    BEFORE any write; never mints immutable governance garbage."""


#: The scenario binding/selection rule (OD-P3-6-F): every exposure row + every open shock.
SCENARIO_BINDING_PREDICATE = "v1:fexp-run-rows+scenario-shocks"


def build_scenario_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    factor_exposure_run_id: str,
    scenario_definition_id: str,
) -> DatasetSnapshot:
    """Build one immutable ``SCENARIO_INPUT`` snapshot (P3-6, OD-P3-6-F) pinning:

    - one ``COMPONENT_KIND_FACTOR_EXPOSURE`` per ``factor_exposure_result`` row of the consumed
      run (REUSED — the exposures the scenario shocks); and
    - one ``COMPONENT_KIND_SCENARIO`` per OPEN ``scenario_shock`` of the definition (the
      ``benchmark_constituent`` per-row FR flavor — each carries the definition identity),

    so a scenario run is reproducible from the snapshot alone (the binder reads this captured
    content — never a live result/shock read; a later shock supersede cannot move a historical run,
    TR-09). An exposure run with NO visible rows, or a definition with NO open shocks, fails closed
    BEFORE any write (:class:`ScenarioSnapshotError`). The exposed↔shock adjudication is the RISK
    binder's pre-create gate — this builder pins a well-formed set; it imports NO ``calc``/``risk``
    SERVICE symbol (both sides are models-only reads)."""
    # The binder reads (no cycle): reuse the SAME open-shock query the /scenarios/{id}/shocks
    # endpoint serves, so the pinned set can never diverge from the live list a caller sees.
    from irp_shared.risk.scenario import list_scenario_shocks, resolve_scenario_definition

    now = utcnow()
    valid_at = known = now  # both sides pinned as-known-now (the build_var precedent).

    exposure_rows = _list_factor_exposure_rows(
        session, factor_exposure_run_id, acting_tenant=acting_tenant
    )
    if not exposure_rows:
        raise ScenarioSnapshotError(
            f"factor-exposure run {factor_exposure_run_id} has no visible result rows to pin"
        )
    definition = resolve_scenario_definition(
        session, scenario_definition_id, acting_tenant=acting_tenant
    )
    shocks = list_scenario_shocks(
        session, scenario_definition_id=str(definition.id), acting_tenant=acting_tenant
    )
    if not shocks:
        raise ScenarioSnapshotError(
            f"scenario {scenario_definition_id} has no open shocks — nothing to apply"
        )

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in exposure_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_EXPOSURE,
            "factor_exposure_result",
            row,
            factor_exposure_content(row),
        )
    for shock in shocks:
        _append_spec(
            specs,
            COMPONENT_KIND_SCENARIO,
            "scenario_shock",  # the pinned ROW is a shock (its id is target_entity_id), NOT the
            shock,  # definition — the benchmark_constituent per-row FR precedent; keeps the
            scenario_shock_content(definition, shock),  # provenance type/id consistent + lets
        )  # _reresolve_content re-read the row by its true type (verify_snapshot integrity)

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_SCENARIO_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=now.date(),
        binding_predicate_version=SCENARIO_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class DesmoothingSnapshotError(Exception):
    """A desmoothing-input snapshot cannot be built (an inverted window; fewer than two visible
    marks — nothing to desmooth; an unresolvable portfolio/instrument) — raised BEFORE any write;
    never mints immutable governance garbage. Maps to 409."""


#: The desmoothing binding/selection rule (OD-PA-1-G): every current-head mark in the window.
DESMOOTHING_BINDING_PREDICATE = "v1:valuation-mark-window"


def build_desmoothing_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    portfolio_id: str,
    instrument_id: str,
    window_start: date,
    window_end: date,
) -> DatasetSnapshot:
    """Build one immutable ``DESMOOTHING_INPUT`` snapshot (PA-1, OD-PA-1-G) pinning one
    ``COMPONENT_KIND_VALUATION`` per CURRENT-HEAD ``valuation`` mark of the (portfolio, instrument)
    pair with ``valuation_date`` in ``[window_start, window_end]`` (REUSED kind — the
    exposure-snapshot flavor), so a desmoothing run is reproducible from the snapshot alone (a
    later mark correction cannot move a historical run, TR-09; AD-014 pinned-content-only reads).

    Fails closed BEFORE any write on: an inverted window; a hidden/cross-tenant portfolio or
    instrument; FEWER THAN TWO visible marks (no return series exists — structurally nothing to
    desmooth; the >=4-mark STATISTICAL gate is the binder's pre-create adjudication, OD-PA-1-H).
    Imports NO ``calc``/``perf`` SERVICE symbol (models-only reads)."""
    from irp_shared.reference.guards import assert_instrument_in_tenant  # no service cycle
    from irp_shared.valuation.models import Valuation  # models-only (no cycle)

    if window_start > window_end:
        raise DesmoothingSnapshotError(
            f"window_start {window_start} is after window_end {window_end} — refused"
        )
    resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)
    assert_instrument_in_tenant(
        session, str(instrument_id), acting_tenant=acting_tenant, error=DesmoothingSnapshotError
    )

    marks = list(
        session.execute(
            select(Valuation)
            .where(
                Valuation.tenant_id == str(acting_tenant),
                Valuation.portfolio_id == str(portfolio_id),
                Valuation.instrument_id == str(instrument_id),
                Valuation.valuation_date >= window_start,
                Valuation.valuation_date <= window_end,
                Valuation.valid_to.is_(None),
                Valuation.system_to.is_(None),
            )
            .order_by(Valuation.valuation_date)
        )
        .scalars()
        .all()
    )
    if len(marks) < 2:
        raise DesmoothingSnapshotError(
            f"only {len(marks)} visible mark(s) in [{window_start}, {window_end}] — a return "
            f"series needs at least two; nothing to desmooth"
        )

    now = utcnow()
    valid_at = known = now  # both sides pinned as-known-now (the build_var precedent).
    specs: list[tuple[str, str, Any, str, str]] = []
    for row in marks:
        _append_spec(specs, COMPONENT_KIND_VALUATION, "valuation", row, valuation_content(row))

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_DESMOOTHING_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=window_end,
        binding_predicate_version=DESMOOTHING_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class PacingSnapshotError(Exception):
    """A PACING_INPUT snapshot cannot be built (no CURRENT commitment for the (portfolio,
    instrument) pair; a hidden/cross-tenant portfolio or instrument) — raised BEFORE any write;
    never mints immutable governance garbage. Maps to 409/404."""


#: The pacing binding rule (OD-CC-2-D): ONE (portfolio, instrument) commitment current head + ALL
#: its capital_call/distribution event rows + the latest current-head valuation mark (if any).
PACING_BINDING_PREDICATE = "v1:commitment-head+all-events+latest-mark"


def _resolve_commitment_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``commitment`` FR row by id with an EXPLICIT tenant predicate (models-only
    import — the ``private_capital`` SERVICE is deliberately not imported; the pin re-resolves the
    exact version row, byte-stable under a later supersede/correct — TR-09)."""
    from irp_shared.private_capital.models import Commitment  # models-only (no cycle / fence-safe)

    row = session.execute(
        select(Commitment).where(
            Commitment.id == str(row_id), Commitment.tenant_id == str(acting_tenant)
        )
    ).scalar_one_or_none()
    if row is None:
        raise PacingSnapshotError(f"commitment {row_id} is not visible")
    return row


def _resolve_capital_call_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    from irp_shared.private_capital.models import CapitalCall  # models-only (no cycle)

    row = session.execute(
        select(CapitalCall).where(
            CapitalCall.id == str(row_id), CapitalCall.tenant_id == str(acting_tenant)
        )
    ).scalar_one_or_none()
    if row is None:
        raise PacingSnapshotError(f"capital_call {row_id} is not visible")
    return row


def _resolve_distribution_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    from irp_shared.private_capital.models import Distribution  # models-only (no cycle)

    row = session.execute(
        select(Distribution).where(
            Distribution.id == str(row_id), Distribution.tenant_id == str(acting_tenant)
        )
    ).scalar_one_or_none()
    if row is None:
        raise PacingSnapshotError(f"distribution {row_id} is not visible")
    return row


def build_pacing_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    portfolio_id: str,
    instrument_id: str,
) -> DatasetSnapshot:
    """Build one immutable ``PACING_INPUT`` snapshot (CC-2, OD-CC-2-D) for ONE (portfolio,
    instrument) pair, pinning: the CURRENT-HEAD ``commitment`` (COMMITMENT, the FR pin flavor); ALL
    ``capital_call`` + ``distribution`` event rows for the pair (CAPITAL_CALL/DISTRIBUTION, the IA
    true-append-only flavor — reversals INCLUDED, the Σ self-corrects); and the LATEST current-head
    ``valuation`` mark for the PAIR (max ``valuation_date``, both-axes-open — the NAV anchor) if one
    exists. Stamps ``as_of_valuation_date`` = the latest mark's date, else the snapshot build date
    — the DETERMINISTIC age anchor the pacing binder projects from (a wall-clock age would break
    pin-reproducibility). So a pacing run reproduces from the snapshot alone (a later
    supersede/correct/new-event cannot move a historical run, TR-09; AD-014 pinned-content-only
    reads). Fails closed BEFORE any write on a hidden pair or NO current commitment. Imports NO
    ``pacing`` SERVICE symbol (models-only reads of ``private_capital``/``valuation``)."""
    from irp_shared.private_capital.models import (  # models-only (no cycle / fence-safe)
        CapitalCall,
        Commitment,
        Distribution,
    )
    from irp_shared.reference.guards import assert_instrument_in_tenant
    from irp_shared.valuation.models import Valuation

    resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)
    assert_instrument_in_tenant(
        session, str(instrument_id), acting_tenant=acting_tenant, error=PacingSnapshotError
    )

    commitment = session.execute(
        select(Commitment).where(
            Commitment.tenant_id == str(acting_tenant),
            Commitment.portfolio_id == str(portfolio_id),
            Commitment.instrument_id == str(instrument_id),
            Commitment.valid_to.is_(None),
            Commitment.system_to.is_(None),
        )
    ).scalar_one_or_none()
    if commitment is None:
        raise PacingSnapshotError(
            f"no current commitment for portfolio {portfolio_id} to instrument {instrument_id} "
            f"— capture one first"
        )

    calls = list(
        session.execute(
            select(CapitalCall)
            .where(
                CapitalCall.tenant_id == str(acting_tenant),
                CapitalCall.portfolio_id == str(portfolio_id),
                CapitalCall.instrument_id == str(instrument_id),
            )
            .order_by(CapitalCall.event_date, CapitalCall.system_from)
        )
        .scalars()
        .all()
    )
    dists = list(
        session.execute(
            select(Distribution)
            .where(
                Distribution.tenant_id == str(acting_tenant),
                Distribution.portfolio_id == str(portfolio_id),
                Distribution.instrument_id == str(instrument_id),
            )
            .order_by(Distribution.event_date, Distribution.system_from)
        )
        .scalars()
        .all()
    )
    mark = session.execute(
        select(Valuation)
        .where(
            Valuation.tenant_id == str(acting_tenant),
            Valuation.portfolio_id == str(portfolio_id),
            Valuation.instrument_id == str(instrument_id),
            Valuation.valid_to.is_(None),
            Valuation.system_to.is_(None),
        )
        .order_by(Valuation.valuation_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    now = utcnow()
    valid_at = known = now
    as_of_valuation = mark.valuation_date if mark is not None else now.date()
    specs: list[tuple[str, str, Any, str, str]] = []
    _append_spec(
        specs, COMPONENT_KIND_COMMITMENT, "commitment", commitment, commitment_content(commitment)
    )
    for call in calls:
        _append_spec(
            specs, COMPONENT_KIND_CAPITAL_CALL, "capital_call", call, capital_call_content(call)
        )
    for dist in dists:
        _append_spec(
            specs, COMPONENT_KIND_DISTRIBUTION, "distribution", dist, distribution_content(dist)
        )
    if mark is not None:
        _append_spec(specs, COMPONENT_KIND_VALUATION, "valuation", mark, valuation_content(mark))

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_PACING_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=as_of_valuation,
        binding_predicate_version=PACING_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class ProxyWeightSnapshotError(Exception):
    """A PROXY_WEIGHT_INPUT snapshot cannot be built (an empty desmoothed run, no candidate factor,
    a candidate factor with no returns in the appraisal span) — raised BEFORE any write; never
    mints immutable governance garbage. Maps to 409."""


#: The proxy-weight binding rule (OD-PA-3-B): the consumed DESMOOTHED_RETURN run's per-period rows +
#: each candidate factor's SIMPLE-return window over the appraisal span.
PROXY_WEIGHT_BINDING_PREDICATE = "v1:desmoothed-period-rows+factor-return-span"


def _resolve_desmoothed_return_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``desmoothed_return_result`` by id with an EXPLICIT tenant predicate (models-only
    import — the ``perf`` SERVICE is deliberately not imported; used by ``_reresolve_content``)."""
    from irp_shared.perf.models import DesmoothedReturnResult  # models-only (no cycle / fence-safe)

    row = session.execute(
        select(DesmoothedReturnResult).where(
            DesmoothedReturnResult.id == str(row_id),
            DesmoothedReturnResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ProxyWeightSnapshotError(f"desmoothed_return_result {row_id} is not visible")
    return row


def _list_desmoothed_period_rows(session: Session, run_id: str, *, acting_tenant: str) -> list[Any]:
    """The per-period ``DESMOOTHED_PERIOD`` rows of a desmoothed-return run (tenant-scoped, ordered
    by ``period_start``; models-only import). The SUMMARY row is NOT pinned — only the per-period
    desmoothed series is the regression target."""
    from irp_shared.perf.models import (  # models-only (no cycle / fence-safe)
        METRIC_TYPE_DESMOOTHED_PERIOD,
        DesmoothedReturnResult,
    )

    return list(
        session.execute(
            select(DesmoothedReturnResult)
            .where(
                DesmoothedReturnResult.calculation_run_id == str(run_id),
                DesmoothedReturnResult.tenant_id == str(acting_tenant),
                DesmoothedReturnResult.metric_type == METRIC_TYPE_DESMOOTHED_PERIOD,
            )
            .order_by(DesmoothedReturnResult.period_start)
        )
        .scalars()
        .all()
    )


def build_proxy_weight_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    desmoothed_run_id: str,
    factor_ids: list[str],
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``PROXY_WEIGHT_INPUT`` snapshot (PA-3, OD-PA-3-B) pinning:

    - one ``COMPONENT_KIND_DESMOOTHED_RETURN`` per ``DESMOOTHED_PERIOD`` row of the consumed
      desmoothed run (the regression TARGET series — the source run's immutable output); and
    - per candidate factor: one ``COMPONENT_KIND_FACTOR`` (the EV definition pin) + one
      ``COMPONENT_KIND_FACTOR_RETURN`` — the factor's SIMPLE-return rows over the appraisal SPAN
      ``(min period_start, max period_end]`` (the covariance window flavor),

    so a proxy-weight estimation is reproducible from the snapshot alone (the binder reads this
    captured content — never a live read; a later mark/return supersede cannot move a historical
    estimate, TR-09). Fails closed BEFORE any write on an empty desmoothed run, a duplicate/empty
    candidate set, or a candidate factor with NO return in the span
    (:class:`ProxyWeightSnapshotError`).
    Per-period factor COVERAGE (does every appraisal period have a return to compound?) is the RISK
    binder's pre-create gate — this builder pins a well-formed superset. Models-only reads; NO
    ``perf``/``risk`` SERVICE symbol is imported."""
    now = utcnow()
    valid_at = as_of_valid_at if as_of_valid_at is not None else now
    known = as_of_known_at if as_of_known_at is not None else now  # FROZEN once (header == pin)

    period_rows = _list_desmoothed_period_rows(
        session, str(desmoothed_run_id), acting_tenant=acting_tenant
    )
    if not period_rows:
        raise ProxyWeightSnapshotError(
            f"desmoothed run {desmoothed_run_id} has no per-period result rows to pin"
        )
    distinct_ids = list(dict.fromkeys(str(fid).lower() for fid in factor_ids))
    if len(distinct_ids) != len(factor_ids):
        raise ProxyWeightSnapshotError(
            "duplicate factor ids — an ambiguous candidate set is refused"
        )
    if not distinct_ids:
        raise ProxyWeightSnapshotError("at least one candidate factor is required")

    span_start = min(r.period_start for r in period_rows)
    span_end = max(r.period_end for r in period_rows)

    factors = [resolve_factor(session, fid, acting_tenant=acting_tenant) for fid in distinct_ids]
    resolved_ids = [str(f.id).lower() for f in factors]
    if len(set(resolved_ids)) != len(resolved_ids):  # any residual aliasing — refuse pre-write
        raise ProxyWeightSnapshotError(
            "duplicate factor ids — an ambiguous candidate set is refused"
        )

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in period_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_DESMOOTHED_RETURN,
            "desmoothed_return_result",
            row,
            desmoothed_return_content(row),
        )
    for factor in factors:
        window = _factor_window_rows(
            session,
            acting_tenant=acting_tenant,
            factor_id=factor.id,
            valid_at=valid_at,
            known_at=known,
        )
        span_rows = [window[d] for d in sorted(window) if span_start < d <= span_end]
        if not span_rows:
            raise ProxyWeightSnapshotError(
                f"candidate factor {factor.id} has no returns in the appraisal span "
                f"({span_start}..{span_end}) — refused"
            )
        _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", factor, factor_content(factor))
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_RETURN,
            "factor",
            factor,
            factor_return_series_content(factor, span_rows),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_PROXY_WEIGHT_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=span_end,
        binding_predicate_version=PROXY_WEIGHT_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


#: The pure-private-factor binding rule (OD-PPF-1-C): per member — the consumed DESMOOTHED_RETURN
#: run's per-period rows + the member's current-head REGRESSION public proxy blend + the membership
#: row (onto the PRIVATE segment) — plus each public factor's return window over the whole span.
PRIVATE_FACTOR_RETURN_BINDING_PREDICATE = "v1:member-desmoothed+regression-blend+factor-span"


class PrivateFactorReturnSnapshotError(Exception):
    """Raised when a pure-private-factor-return-input snapshot cannot be built (a non-PRIVATE
    segment factor, an empty/duplicate member set, a member desmoothed run with no per-period rows,
    a member that is NOT a current-head member of the segment, a member with no current-head
    REGRESSION public blend — the P3-7 named-gap rule — or a blend factor with no return in the
    span) — raised BEFORE any write; never mints immutable governance garbage. Maps to 409."""


def build_private_factor_return_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    segment_factor_id: str,
    member_desmoothed_run_ids: list[str],
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``PRIVATE_FACTOR_RETURN_INPUT`` snapshot (PPF-1, OD-PPF-1-C) pinning, so
    a pooled pure-private factor return is reproducible from the snapshot ALONE (the binder reads
    this captured content — never a live read; a later mark/return/weight supersede cannot move a
    historical pooled return, TR-09):

    - one ``COMPONENT_KIND_FACTOR`` for the PRIVATE segment factor (its EV definition), and
    - per member (one consumed DESMOOTHED_RETURN run): its ``DESMOOTHED_PERIOD`` rows
      (``COMPONENT_KIND_DESMOOTHED_RETURN`` — the pure-private numerator series); the member's
      current-head ``MANUAL`` membership row onto the segment + its current-head ``REGRESSION``
      public proxy blend (both ``COMPONENT_KIND_PROXY_MAPPING``); and
    - per distinct blend factor: one ``COMPONENT_KIND_FACTOR`` + one
      ``COMPONENT_KIND_FACTOR_RETURN`` over the whole appraisal span (the proxy-weight flavor).

    Fails closed BEFORE any write (:class:`PrivateFactorReturnSnapshotError`): a non-PRIVATE
    segment, empty/duplicate members, an empty desmoothed run, a member with NO current-head
    membership row on the segment, a member with NO current-head REGRESSION blend (the P3-7
    named-gap rule — a blend-less member cannot have its proxy-implied return subtracted), or a
    blend factor with no return in the span. The min-members floor + identical-interval pooling
    are the RISK binder's pre-create gates — this builder pins a well-formed superset. Models-only
    reads; imports NO ``risk``-SERVICE symbol (the ``build_var_total_snapshot`` precedent)."""
    from irp_shared.marketdata.models import (
        FACTOR_FAMILY_PRIVATE,
        MAPPING_METHOD_MANUAL,
        MAPPING_METHOD_REGRESSION,
        ProxyMapping,
    )

    now = utcnow()
    valid_at = as_of_valid_at if as_of_valid_at is not None else now
    known = as_of_known_at if as_of_known_at is not None else now  # FROZEN once (header == pin)

    segment = resolve_factor(session, str(segment_factor_id), acting_tenant=acting_tenant)
    if segment.factor_family != FACTOR_FAMILY_PRIVATE:
        raise PrivateFactorReturnSnapshotError(
            f"segment factor {segment_factor_id} is family {segment.factor_family!r}, not "
            f"{FACTOR_FAMILY_PRIVATE!r} — refused"
        )
    distinct_runs = list(dict.fromkeys(str(r).lower() for r in member_desmoothed_run_ids))
    if len(distinct_runs) != len(member_desmoothed_run_ids):
        raise PrivateFactorReturnSnapshotError(
            "duplicate member desmoothed run(s) — an ambiguous member set is refused"
        )
    if not distinct_runs:
        raise PrivateFactorReturnSnapshotError("at least one member desmoothed run is required")

    specs: list[tuple[str, str, Any, str, str]] = []
    _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", segment, factor_content(segment))

    # Per member: pin the desmoothed series + the membership row + the REGRESSION public blend;
    # accumulate the distinct public blend factors + the global appraisal span.
    blend_factor_ids: set[str] = set()
    span_starts: list[date] = []
    span_ends: list[date] = []
    for run_id in distinct_runs:
        period_rows = _list_desmoothed_period_rows(session, run_id, acting_tenant=acting_tenant)
        if not period_rows:
            raise PrivateFactorReturnSnapshotError(
                f"member desmoothed run {run_id} has no per-period result rows to pin"
            )
        instrument_ids = {str(r.instrument_id).lower() for r in period_rows}
        if len(instrument_ids) != 1:
            raise PrivateFactorReturnSnapshotError(
                f"member desmoothed run {run_id} spans multiple instruments — refused"
            )
        instrument_id = next(iter(instrument_ids))
        span_starts.append(min(r.period_start for r in period_rows))
        span_ends.append(max(r.period_end for r in period_rows))

        # Pin the member's DESMOOTHED_PERIOD rows (the pure-private numerator series).
        for row in period_rows:
            _append_spec(
                specs,
                COMPONENT_KIND_DESMOOTHED_RETURN,
                "desmoothed_return_result",
                row,
                desmoothed_return_content(row),
            )

        # The membership row: a current-head MANUAL proxy_mapping onto the PRIVATE segment factor.
        membership = session.execute(
            select(ProxyMapping).where(
                ProxyMapping.tenant_id == str(acting_tenant),
                ProxyMapping.private_instrument_id == instrument_id,
                ProxyMapping.factor_id == str(segment.id),
                ProxyMapping.mapping_method == MAPPING_METHOD_MANUAL,
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
        ).scalar_one_or_none()
        if membership is None:
            raise PrivateFactorReturnSnapshotError(
                f"instrument {instrument_id} (member run {run_id}) is not a current-head member of "
                f"segment {segment.id} — no open MANUAL membership row; refused"
            )
        _append_spec(
            specs,
            COMPONENT_KIND_PROXY_MAPPING,
            "proxy_mapping",
            membership,
            proxy_mapping_content(membership),
        )

        # The member's current-head REGRESSION public blend (the var-total method filter).
        blend_rows = (
            session.execute(
                select(ProxyMapping)
                .where(
                    ProxyMapping.tenant_id == str(acting_tenant),
                    ProxyMapping.private_instrument_id == instrument_id,
                    ProxyMapping.mapping_method == MAPPING_METHOD_REGRESSION,
                    ProxyMapping.valid_to.is_(None),
                    ProxyMapping.system_to.is_(None),
                )
                .order_by(ProxyMapping.factor_id)
            )
            .scalars()
            .all()
        )
        if not blend_rows:
            raise PrivateFactorReturnSnapshotError(
                f"instrument {instrument_id} (member run {run_id}) has NO current-head REGRESSION "
                f"proxy blend — the proxy-implied return cannot be subtracted (named gap); refused"
            )
        for row in blend_rows:
            blend_factor_ids.add(str(row.factor_id).lower())
            _append_spec(
                specs,
                COMPONENT_KIND_PROXY_MAPPING,
                "proxy_mapping",
                row,
                proxy_mapping_content(row),
            )

    # The distinct public blend factors + their return windows over the whole appraisal span.
    span_start = min(span_starts)
    span_end = max(span_ends)
    for fid in sorted(blend_factor_ids):
        factor = resolve_factor(session, fid, acting_tenant=acting_tenant)
        window = _factor_window_rows(
            session,
            acting_tenant=acting_tenant,
            factor_id=factor.id,
            valid_at=valid_at,
            known_at=known,
        )
        span_rows = [window[d] for d in sorted(window) if span_start < d <= span_end]
        if not span_rows:
            raise PrivateFactorReturnSnapshotError(
                f"blend factor {factor.id} has no returns in the appraisal span "
                f"({span_start}..{span_end}] — refused"
            )
        _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", factor, factor_content(factor))
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_RETURN,
            "factor",
            factor,
            factor_return_series_content(factor, span_rows),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_PRIVATE_FACTOR_RETURN_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=span_end,
        binding_predicate_version=PRIVATE_FACTOR_RETURN_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


#: PPF-2 (OD-PPF-2-A): the private-covariance binding/selection rule — per PRIVATE segment, the
#: PURE_PRIVATE_PERIOD series of its LATEST pure-private factor run, aligned to the common appraisal
#: grid. Length-guarded (see the ``_BINDING_PREDICATES`` module-end assert) against varchar(50).
PRIVATE_COVARIANCE_BINDING_PREDICATE = "v1:pure-private-appraisal-series"


class PrivateCovarianceSnapshotError(Exception):
    """Raised when a private-covariance-input snapshot cannot be built (fewer than two distinct
    pure-private runs, a run with no per-period series, a run whose segment is non-PRIVATE or shared
    with another run, or fewer than ``window_observations`` common appraisal periods across the
    segments) — fail closed, BEFORE any write. Maps to 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"private covariance snapshot input failed closed: {detail}")
        self.detail = detail


def _list_pure_private_period_rows(
    session: Session, run_id: str, *, acting_tenant: str
) -> list[Any]:
    """The per-period ``PURE_PRIVATE_PERIOD`` rows of a pure-private factor run (tenant-scoped,
    ordered by ``period_start``; models-only import — no ``calc`` symbol, the snapshot fence). The
    SUMMARY row is NOT pinned — only the per-period series is the covariance input. The run id is
    passed explicitly (the caller resolves the segment's latest run — the ``proxy_weight``/PPF-1
    run-bound-input precedent)."""
    from irp_shared.risk.models import (  # models-only (no cycle / fence-safe)
        METRIC_TYPE_PURE_PRIVATE_PERIOD,
        PrivateFactorReturnResult,
    )

    return list(
        session.execute(
            select(PrivateFactorReturnResult)
            .where(
                PrivateFactorReturnResult.calculation_run_id == str(run_id),
                PrivateFactorReturnResult.tenant_id == str(acting_tenant),
                PrivateFactorReturnResult.metric_type == METRIC_TYPE_PURE_PRIVATE_PERIOD,
            )
            .order_by(PrivateFactorReturnResult.period_start)
        )
        .scalars()
        .all()
    )


def _resolve_pure_private_return_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``private_factor_return_result`` by id with an EXPLICIT tenant predicate
    (models-only import — the ``risk`` SERVICE is deliberately not imported; used by
    ``_reresolve_content`` for the ``verify_snapshot`` integrity re-read)."""
    from irp_shared.risk.models import PrivateFactorReturnResult  # models-only (no cycle)

    row = session.execute(
        select(PrivateFactorReturnResult).where(
            PrivateFactorReturnResult.id == str(row_id),
            PrivateFactorReturnResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise PrivateCovarianceSnapshotError(
            f"private_factor_return_result {row_id} is not visible"
        )
    return row


def build_private_covariance_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    pure_private_run_ids: list[str],
    window_observations: int,
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``PRIVATE_COVARIANCE_INPUT`` snapshot (PPF-2, OD-PPF-2-A) pinning, per
    consumed pure-private factor run (one PRIVATE segment each):

    - one ``COMPONENT_KIND_FACTOR`` component (the segment EV definition pin), and
    - one ``COMPONENT_KIND_PURE_PRIVATE_RETURN`` per common appraisal period — the segment's
      aligned pure-private return over the ``window_observations`` most recent
      ``(period_start, period_end]`` intervals COMMON to every selected segment (governed PPF-1
      ``PURE_PRIVATE_PERIOD`` rows; ``target_entity_type='private_factor_return_result'``),

    so an Ω_pp run is reproducible from the snapshot alone (the compute reads this captured
    content — never a live pure-private/factor read; a later PPF-1 re-run is invisible to the pin,
    TR-09). Each run is a run-bound input passed explicitly (the RISK binder resolves each segment's
    latest run — the ``proxy_weight``/``build_var_snapshot`` run-id precedent). Alignment is
    **fail-closed, no imputation/pairwise** (the OD-P3-0-L rule carried to appraisal periods): fewer
    than ``window_observations`` common intervals raises :class:`PrivateCovarianceSnapshotError`
    BEFORE any write, as do a duplicate/sub-two run list, a sub-two window, a run whose segment is
    non-PRIVATE or shared with another run, and a run with no pure-private series. The declared
    window is the RISK binder's pre-create gate — this builder pins a well-formed grid; it does not
    read the model registry. Models-only reads; imports NO ``risk``-SERVICE / ``calc`` symbol (the
    ``build_covariance_snapshot`` precedent). NO derived number is computed here."""
    from irp_shared.marketdata.models import FACTOR_FAMILY_PRIVATE

    now = utcnow()
    valid_at = as_of_valid_at if as_of_valid_at is not None else now
    known = as_of_known_at if as_of_known_at is not None else now  # FROZEN once (header == pin)

    if window_observations < 2:
        raise PrivateCovarianceSnapshotError(
            f"window_observations must be >= 2 (got {window_observations})"
        )
    distinct_runs = list(dict.fromkeys(str(rid).lower() for rid in pure_private_run_ids))
    if len(distinct_runs) != len(pure_private_run_ids):
        raise PrivateCovarianceSnapshotError(
            "duplicate pure-private run ids — an ambiguous series set is refused"
        )
    if len(distinct_runs) < 2:
        raise PrivateCovarianceSnapshotError(
            f"a private covariance snapshot needs >= 2 distinct pure-private runs "
            f"(got {len(distinct_runs)})"
        )

    # Per run: its PURE_PRIVATE_PERIOD series; derive + PRIVATE-check the single segment it holds.
    segment_by_run: dict[str, Any] = {}
    by_interval: dict[str, dict[tuple[date, date], Any]] = {}
    seen_segments: set[str] = set()
    for run_id in distinct_runs:
        period_rows = _list_pure_private_period_rows(session, run_id, acting_tenant=acting_tenant)
        if not period_rows:
            raise PrivateCovarianceSnapshotError(
                f"pure-private run {run_id} has no per-period result rows to pin"
            )
        seg_ids = {str(r.segment_factor_id).lower() for r in period_rows}
        if len(seg_ids) != 1:  # PPF-1 writes one segment per run — a mixed run is malformed
            raise PrivateCovarianceSnapshotError(
                f"pure-private run {run_id} spans multiple segments — refused"
            )
        seg_id = next(iter(seg_ids))
        if seg_id in seen_segments:  # two runs for one segment collapses the matrix shape
            raise PrivateCovarianceSnapshotError(
                f"segment {seg_id} appears in more than one pure-private run — refused"
            )
        seen_segments.add(seg_id)
        segment = resolve_factor(session, seg_id, acting_tenant=acting_tenant)
        if segment.factor_family != FACTOR_FAMILY_PRIVATE:
            raise PrivateCovarianceSnapshotError(
                f"segment factor {segment.id} is family {segment.factor_family!r}, not "
                f"{FACTOR_FAMILY_PRIVATE!r} — refused"
            )
        segment_by_run[run_id] = segment
        by_interval[run_id] = {(row.period_start, row.period_end): row for row in period_rows}

    # The N most recent COMMON intervals (set intersection; fail-closed on a short overlap).
    common: set[tuple[date, date]] = set.intersection(
        *(set(rows.keys()) for rows in by_interval.values())
    )
    if len(common) < window_observations:
        raise PrivateCovarianceSnapshotError(
            f"only {len(common)} common appraisal periods across {len(distinct_runs)} segments — "
            f"the declared window needs {window_observations} (no imputation, OD-P3-0-L)"
        )
    # ordered by (period_start, period_end); take the N most-recent common intervals
    window_intervals = sorted(common)[-window_observations:]

    # Pin in canonical segment order (lowercase-GUID), so the manifest is run-order-independent.
    specs: list[tuple[str, str, Any, str, str]] = []
    for run_id in sorted(distinct_runs, key=lambda r: str(segment_by_run[r].id).lower()):
        seg = segment_by_run[run_id]
        _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", seg, factor_content(seg))
        for interval in window_intervals:
            row = by_interval[run_id][interval]
            _append_spec(
                specs,
                COMPONENT_KIND_PURE_PRIVATE_RETURN,
                "private_factor_return_result",
                row,
                pure_private_return_content(row),
            )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_PRIVATE_COVARIANCE_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=window_intervals[-1][1],  # the latest common period_end
        binding_predicate_version=PRIVATE_COVARIANCE_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


#: RS-1 (OD-RS-1-B): the residual-shrinkage binding/selection rule — a cohort of promoted proxy-
#: weight estimate runs' ESTIMATION_SUMMARY rows (each residual_stdev + its residual df). Length-
#: guarded (see the ``_BINDING_PREDICATES`` module-end assert) against varchar(50).
RESIDUAL_SHRINKAGE_BINDING_PREDICATE = "v1:cohort-residual-variances+dof"


class ResidualShrinkageSnapshotError(Exception):
    """Raised when a residual-shrinkage-input snapshot cannot be built (a cohort member run is
    missing/non-COMPLETED — no visible ESTIMATION_SUMMARY — or a run is cited twice) — raised BEFORE
    any write; never mints immutable governance garbage. Maps to 409 (the
    ``ProxyWeightSnapshotError`` precedent)."""


def build_residual_shrinkage_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    cohort_estimate_run_ids: list[str],
) -> DatasetSnapshot:
    """Build one immutable ``RESIDUAL_SHRINKAGE_INPUT`` snapshot (RS-1, OD-RS-1-B) pinning, per
    cohort member, the ONE ``ESTIMATION_SUMMARY`` row of a promoted proxy-weight estimate run
    (``COMPONENT_KIND_PROXY_WEIGHT`` — the SAME ``proxy_weight_estimate_content`` flavor total-VaR
    already pins, which carries ``residual_stdev`` + ``n_observations`` + ``n_regressors`` +
    ``instrument_id``), so the empirical-Bayes fit is reproducible from the snapshot ALONE (the
    binder recomputes every w_i from this captured content — never a live estimate read; a later
    re-estimate cannot move a historical shrinkage, TR-09).

    Fails closed BEFORE any write (``ResidualShrinkageSnapshotError``) on an empty/duplicate cohort
    or a member run with no visible ``ESTIMATION_SUMMARY`` (missing / non-COMPLETED). The
    comparable-risk-group precondition and the N >= 3 identifiability floor are the RISK binder's
    pre-create gate — this builder pins a well-formed cohort of whatever size it is handed.
    Models-only reads;
    imports NO ``risk``-SERVICE symbol (the ``build_var_total_snapshot`` precedent)."""
    from irp_shared.risk.models import METRIC_TYPE_ESTIMATION_SUMMARY, ProxyWeightEstimateResult

    now = utcnow()
    distinct = list(dict.fromkeys(str(r).lower() for r in cohort_estimate_run_ids))
    if len(distinct) != len(cohort_estimate_run_ids):
        raise ResidualShrinkageSnapshotError(
            "duplicate cohort estimate run(s) — an ambiguous cohort is refused"
        )
    if not distinct:
        raise ResidualShrinkageSnapshotError("at least one cohort estimate run is required")

    specs: list[tuple[str, str, Any, str, str]] = []
    member_as_ofs: list[date] = []
    for run_id in distinct:
        summary = session.execute(
            select(ProxyWeightEstimateResult).where(
                ProxyWeightEstimateResult.tenant_id == str(acting_tenant),
                ProxyWeightEstimateResult.calculation_run_id == run_id,
                ProxyWeightEstimateResult.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY,
            )
        ).scalar_one_or_none()
        if summary is None:
            raise ResidualShrinkageSnapshotError(
                f"cohort estimate run {run_id} has no visible ESTIMATION_SUMMARY row "
                f"(missing/non-COMPLETED cited run) — refused"
            )
        # The shrinkage is as-of its STALEST input (HG-1 honesty: the shrunk estimate is only as
        # fresh as the oldest cohort member's regression span end — never falsely "fresh as now").
        # A member without a resolvable span end fails CLOSED (the HG-1 unmeasurable-shapes
        # doctrine — an unmeasurable member must never default the pin to age-0); a member that is
        # ITSELF a shrinkage output is refused (no shrink-of-shrunk chains — the pool is a
        # cross-section of RAW/EWMA regression estimates, adversarial-review fold).
        member_input = session.get(DatasetSnapshot, str(summary.input_snapshot_id))
        if member_input is None or member_input.as_of_valuation_date is None:
            raise ResidualShrinkageSnapshotError(
                f"cohort estimate run {run_id} cites input snapshot "
                f"{summary.input_snapshot_id} with no resolvable regression span end — the "
                f"shrinkage pin's as-of would be unmeasurable; refused"
            )
        if member_input.purpose == PURPOSE_RESIDUAL_SHRINKAGE_INPUT:
            raise ResidualShrinkageSnapshotError(
                f"cohort estimate run {run_id} is itself a residual-shrinkage output — "
                f"shrink-of-shrunk chains are refused (pool RAW/EWMA estimates only)"
            )
        member_as_ofs.append(member_input.as_of_valuation_date)
        _append_spec(
            specs,
            COMPONENT_KIND_PROXY_WEIGHT,
            "proxy_weight_estimate_result",
            summary,
            proxy_weight_estimate_content(summary),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_RESIDUAL_SHRINKAGE_INPUT,
        as_of_valid_at=now,
        as_of_known_at=now,
        as_of_valuation_date=min(member_as_ofs),  # every member measurable (refused above)
        binding_predicate_version=RESIDUAL_SHRINKAGE_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class VarTotalSnapshotError(VarSnapshotError):
    """Raised when a total-parametric-VaR-input snapshot cannot be built (a proxied instrument's
    OPEN REGRESSION mapping(s) cite a missing/non-COMPLETED/ambiguous/wrong-instrument estimation
    run) — fail closed, BEFORE any write. Subclasses :class:`VarSnapshotError` (shares the 409 +
    the row-resolver helpers) but carries a total-VaR diagnostic so the wire detail names the right
    family (the ``ActiveRiskSnapshotError`` precedent). Maps to 409."""

    def __init__(self, detail: str) -> None:
        super(VarSnapshotError, self).__init__(f"total-VaR snapshot input failed closed: {detail}")
        self.detail = detail


#: The total-VaR binding/selection rule (PA-4, OD-PA-4-C): everything ``VAR_BINDING_PREDICATE``
#: pins PLUS the proxied instruments' open REGRESSION mappings + their cited ESTIMATION_SUMMARY —
#: LOAD-BEARING (the binder gates on it in BOTH directions, the OD-PA-2-C precedent). Length-
#: guarded (see the ``_BINDING_PREDICATES`` module-end assert) against varchar(50).
VAR_TOTAL_BINDING_PREDICATE = "v1:exposure-run-rows+covariance-run-rows+proxy-wt"


def _resolve_proxy_weight_estimate_row(session: Session, row_id: str, *, acting_tenant: str) -> Any:
    """Resolve one ``proxy_weight_estimate_result`` row by id with an EXPLICIT tenant predicate
    (models-only, function-local import — the ``_resolve_factor_exposure_row`` precedent)."""
    from irp_shared.risk.models import ProxyWeightEstimateResult  # models-only (no cycle)

    row = session.execute(
        select(ProxyWeightEstimateResult).where(
            ProxyWeightEstimateResult.id == str(row_id),
            ProxyWeightEstimateResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise VarTotalSnapshotError(f"proxy weight estimate {row_id} is not visible")
    return row


def build_var_total_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_id: str,
    covariance_run_id: str,
) -> DatasetSnapshot:
    """Build one immutable ``VAR_INPUT`` snapshot (PA-4, OD-PA-4-C) pinning EVERYTHING
    ``build_var_snapshot`` pins PLUS, per distinct instrument of the pinned exposure rows carrying
    an OPEN REGRESSION-method ``proxy_mapping``:

    - one ``COMPONENT_KIND_PROXY_MAPPING`` per open REGRESSION row (REUSED PA-2 content — the
      per-row FR flavor; a later weight supersede/correction is invisible to the pin, TR-09), and
    - one ``COMPONENT_KIND_PROXY_WEIGHT`` — the row(s)' cited run's ``ESTIMATION_SUMMARY`` (the
      residual_stdev + the row's own ``instrument_id``, the ``var_result`` IA-row pin flavor),

    so a total-VaR run is reproducible from the snapshot alone (the compute reads this captured
    content — never a live proxy/estimate read). Stamps ``VAR_TOTAL_BINDING_PREDICATE`` — the
    total binder refuses a plain-predicate snapshot AND the plain binder refuses THIS predicate
    (the OD-PA-2-C symmetric-refusal precedent), so the idiosyncratic leg can never be silently
    dropped or silently smuggled in.

    Fails closed BEFORE any write when a proxied instrument's open REGRESSION mapping(s) cite
    MISSING/non-COMPLETED (no visible ``ESTIMATION_SUMMARY``)/AMBIGUOUS (span >1 distinct cited
    run)/WRONG-INSTRUMENT (the cited run's summary names a different instrument) estimation
    evidence (:class:`VarTotalSnapshotError`). Non-proxied and MANUAL-method instruments are
    simply not pinned here (the OD-PA-4 zero-idiosyncratic-risk default; no snapshot-level gap
    class for them — the P3-3/P3-4 no-gap-class rationale). Models-only, function-local reads;
    imports NO ``calc``/risk-SERVICE symbol (the P3-3 precedent)."""
    from irp_shared.marketdata.models import MAPPING_METHOD_REGRESSION, ProxyMapping
    from irp_shared.risk.models import METRIC_TYPE_ESTIMATION_SUMMARY, ProxyWeightEstimateResult

    now = utcnow()

    exposure_rows = _list_factor_exposure_rows(
        session, exposure_run_id, acting_tenant=acting_tenant
    )
    if not exposure_rows:
        raise VarSnapshotError(f"exposure run {exposure_run_id} has no visible result rows")
    covariance_rows = _list_covariance_rows(session, covariance_run_id, acting_tenant=acting_tenant)
    if not covariance_rows:
        raise VarSnapshotError(f"covariance run {covariance_run_id} has no visible result rows")

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in exposure_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_EXPOSURE,
            "factor_exposure_result",
            row,
            factor_exposure_content(row),
        )
    for row in covariance_rows:
        _append_spec(
            specs, COMPONENT_KIND_COVARIANCE, "covariance_result", row, covariance_content(row)
        )

    # PA-4 (OD-PA-4-C): per distinct pinned-exposure instrument with >=1 OPEN REGRESSION mapping,
    # cite + pin its ONE estimation run's ESTIMATION_SUMMARY (the PA-2 whole-book proxy-row query
    # precedent, method-filtered — MANUAL rows carry no estimation evidence and are not pinned).
    instrument_ids = sorted({str(r.instrument_id) for r in exposure_rows})
    regression_rows = (
        session.execute(
            select(ProxyMapping)
            .where(
                ProxyMapping.tenant_id == str(acting_tenant),
                ProxyMapping.private_instrument_id.in_(instrument_ids),
                ProxyMapping.mapping_method == MAPPING_METHOD_REGRESSION,
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
            .order_by(ProxyMapping.private_instrument_id, ProxyMapping.factor_id)
        )
        .scalars()
        .all()
    )
    by_instrument: dict[str, list[Any]] = {}
    for row in regression_rows:
        by_instrument.setdefault(str(row.private_instrument_id).lower(), []).append(row)

    for instrument_id, mapping_rows in sorted(by_instrument.items()):
        cited_run_ids = {
            str(r.source_calculation_run_id).lower()
            for r in mapping_rows
            if r.source_calculation_run_id is not None
        }
        if len(cited_run_ids) != 1:
            raise VarTotalSnapshotError(
                f"instrument {instrument_id} has {len(cited_run_ids)} distinct/absent cited "
                f"estimation runs across its open REGRESSION mapping(s) — an ambiguous or "
                f"missing citation is refused"
            )
        run_id = next(iter(cited_run_ids))
        summary = session.execute(
            select(ProxyWeightEstimateResult).where(
                ProxyWeightEstimateResult.tenant_id == str(acting_tenant),
                ProxyWeightEstimateResult.calculation_run_id == run_id,
                ProxyWeightEstimateResult.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY,
            )
        ).scalar_one_or_none()
        if summary is None:
            raise VarTotalSnapshotError(
                f"instrument {instrument_id}'s cited estimation run {run_id} has no visible "
                f"ESTIMATION_SUMMARY row (missing/non-COMPLETED cited run) — refused"
            )
        if str(summary.instrument_id).lower() != instrument_id:
            raise VarTotalSnapshotError(
                f"instrument {instrument_id}'s cited estimation run {run_id} names a DIFFERENT "
                f"instrument ({summary.instrument_id}) — refused"
            )
        for row in mapping_rows:
            _append_spec(
                specs,
                COMPONENT_KIND_PROXY_MAPPING,
                "proxy_mapping",
                row,
                proxy_mapping_content(row),
            )
        _append_spec(
            specs,
            COMPONENT_KIND_PROXY_WEIGHT,
            "proxy_weight_estimate_result",
            summary,
            proxy_weight_estimate_content(summary),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_VAR_INPUT,
        as_of_valid_at=now,
        as_of_known_at=now,
        as_of_valuation_date=covariance_rows[0].window_end,
        binding_predicate_version=VAR_TOTAL_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


#: PPF-3 (OD-PPF-3-F): the unified binding/selection rule. A SHORT fresh string — NEVER a
#: ``VAR_TOTAL`` suffix (``binding_predicate_version`` is ``String(50)``; VAR_TOTAL is already 49).
VAR_UNIFIED_BINDING_PREDICATE = "v1:unified-pins+private-cov+memberships"


class VarUnifiedSnapshotError(VarSnapshotError):
    """Raised when a unified-VaR input snapshot cannot be built (an empty/non-APPRAISAL private
    covariance run, no MANUAL pure-private membership among the exposure instruments, or a held
    segment absent from the pinned Ω_pp run) — fail closed, BEFORE any write. Maps to 409."""


def build_var_unified_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_id: str,
    covariance_run_id: str,
    private_covariance_run_id: str,
) -> DatasetSnapshot:
    """Build one immutable ``VAR_INPUT`` snapshot (PPF-3, OD-PPF-3-A/F) for the UNIFIED number.
    Pins everything ``build_var_total_snapshot`` pins EXCEPT the REGRESSION residual leg is
    REPARTITIONED — and ADDS the pure-private block:

    - one ``COMPONENT_KIND_FACTOR_EXPOSURE`` per public exposure row + one
      ``COMPONENT_KIND_COVARIANCE`` per public (DAILY) covariance row (the factor leg);
    - one ``COMPONENT_KIND_COVARIANCE`` per PPF-2 Ω_pp (APPRAISAL) row (the pure-private block —
      distinguished from the public Σ by ``frequency`` at parse) + one
      ``COMPONENT_KIND_PROXY_MAPPING`` per current-head MANUAL membership (instrument -> segment);
    - per REGRESSION-proxied instrument that is NOT a held pure-private segment member (the
      REPARTITION, OD-3-G), its open REGRESSION ``proxy_mapping`` rows + the cited
      ``ESTIMATION_SUMMARY`` (the residual leg over the non-private-segment members ONLY — a
      private-segment member's variance is the Ω_pp block, so its residual is neither pinned nor
      summed, avoiding the double-count).

    Stamps ``VAR_UNIFIED_BINDING_PREDICATE`` (the per-family EXACT-predicate refusal, OD-3-F): a
    unified snapshot is consumable ONLY by the unified binder — the plain/total binders refuse it,
    so the private block can never be silently dropped. Fails closed BEFORE any write
    (:class:`VarUnifiedSnapshotError` / :class:`VarTotalSnapshotError`) on an empty/non-APPRAISAL
    private covariance run, no MANUAL membership, a held segment uncovered by Ω_pp, or an ambiguous
    REGRESSION citation. Models-only, function-local reads; imports NO ``calc``/risk-SERVICE."""
    from irp_shared.marketdata.models import (
        FREQUENCY_APPRAISAL,
        MAPPING_METHOD_MANUAL,
        MAPPING_METHOD_REGRESSION,
        ProxyMapping,
    )
    from irp_shared.risk.models import METRIC_TYPE_ESTIMATION_SUMMARY, ProxyWeightEstimateResult

    now = utcnow()

    exposure_rows = _list_factor_exposure_rows(
        session, exposure_run_id, acting_tenant=acting_tenant
    )
    if not exposure_rows:
        raise VarSnapshotError(f"exposure run {exposure_run_id} has no visible result rows")
    covariance_rows = _list_covariance_rows(session, covariance_run_id, acting_tenant=acting_tenant)
    if not covariance_rows:
        raise VarSnapshotError(f"covariance run {covariance_run_id} has no visible result rows")
    private_cov_rows = _list_covariance_rows(
        session, private_covariance_run_id, acting_tenant=acting_tenant
    )
    if not private_cov_rows:
        raise VarUnifiedSnapshotError(
            f"private covariance run {private_covariance_run_id} has no visible result rows"
        )
    if any(r.frequency != FREQUENCY_APPRAISAL for r in private_cov_rows):
        raise VarUnifiedSnapshotError(
            f"private covariance run {private_covariance_run_id} is not APPRAISAL-frequency "
            f"(not an Omega_pp run) — refused"
        )

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in exposure_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_EXPOSURE,
            "factor_exposure_result",
            row,
            factor_exposure_content(row),
        )
    for row in covariance_rows:
        _append_spec(
            specs, COMPONENT_KIND_COVARIANCE, "covariance_result", row, covariance_content(row)
        )
    for row in private_cov_rows:  # the Ω_pp block (APPRAISAL — parsed by frequency)
        _append_spec(
            specs, COMPONENT_KIND_COVARIANCE, "covariance_result", row, covariance_content(row)
        )

    instrument_ids = sorted({str(r.instrument_id) for r in exposure_rows})

    # The MANUAL pure-private memberships (instrument -> segment) — these form p and drive the
    # repartition. A unified run needs >= 1 private fund; the Ω_pp run must span every held segment.
    manual_rows = (
        session.execute(
            select(ProxyMapping)
            .where(
                ProxyMapping.tenant_id == str(acting_tenant),
                ProxyMapping.private_instrument_id.in_(instrument_ids),
                ProxyMapping.mapping_method == MAPPING_METHOD_MANUAL,
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
            .order_by(ProxyMapping.private_instrument_id, ProxyMapping.factor_id)
        )
        .scalars()
        .all()
    )
    if not manual_rows:
        raise VarUnifiedSnapshotError(
            "no MANUAL pure-private segment membership among the exposure instruments — a unified "
            "run needs at least one private fund (else use the total-VaR family)"
        )
    held_segments = {str(r.factor_id).lower() for r in manual_rows}
    omega_diagonal = {
        str(r.factor_id_1).lower()
        for r in private_cov_rows
        if str(r.factor_id_1).lower() == str(r.factor_id_2).lower()
    }
    uncovered = held_segments - omega_diagonal
    if uncovered:
        raise VarUnifiedSnapshotError(
            f"held pure-private segments {sorted(uncovered)} are absent from the pinned Omega_pp "
            f"run {private_covariance_run_id} — the private covariance must span every held segment"
        )
    private_member_instruments = {str(r.private_instrument_id).lower() for r in manual_rows}
    for row in manual_rows:
        _append_spec(
            specs, COMPONENT_KIND_PROXY_MAPPING, "proxy_mapping", row, proxy_mapping_content(row)
        )

    # The REPARTITIONED residual leg (OD-3-G): pin the REGRESSION proxy + cited estimate ONLY for
    # proxied instruments that are NOT held pure-private members (their variance is the Ω_pp block).
    regression_rows = (
        session.execute(
            select(ProxyMapping)
            .where(
                ProxyMapping.tenant_id == str(acting_tenant),
                ProxyMapping.private_instrument_id.in_(instrument_ids),
                ProxyMapping.mapping_method == MAPPING_METHOD_REGRESSION,
                ProxyMapping.valid_to.is_(None),
                ProxyMapping.system_to.is_(None),
            )
            .order_by(ProxyMapping.private_instrument_id, ProxyMapping.factor_id)
        )
        .scalars()
        .all()
    )
    by_instrument: dict[str, list[Any]] = {}
    for row in regression_rows:
        iid = str(row.private_instrument_id).lower()
        if iid in private_member_instruments:
            continue  # repartitioned to the Ω_pp block — its residual is NOT a leg-3 term
        by_instrument.setdefault(iid, []).append(row)

    for instrument_id, mapping_rows in sorted(by_instrument.items()):
        cited_run_ids = {
            str(r.source_calculation_run_id).lower()
            for r in mapping_rows
            if r.source_calculation_run_id is not None
        }
        if len(cited_run_ids) != 1:
            raise VarTotalSnapshotError(
                f"instrument {instrument_id} has {len(cited_run_ids)} distinct/absent cited "
                f"estimation runs across its open REGRESSION mapping(s) — refused"
            )
        run_id = next(iter(cited_run_ids))
        summary = session.execute(
            select(ProxyWeightEstimateResult).where(
                ProxyWeightEstimateResult.tenant_id == str(acting_tenant),
                ProxyWeightEstimateResult.calculation_run_id == run_id,
                ProxyWeightEstimateResult.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY,
            )
        ).scalar_one_or_none()
        if summary is None:
            raise VarTotalSnapshotError(
                f"instrument {instrument_id}'s cited estimation run {run_id} has no visible "
                f"ESTIMATION_SUMMARY row — refused"
            )
        if str(summary.instrument_id).lower() != instrument_id:
            raise VarTotalSnapshotError(
                f"instrument {instrument_id}'s cited estimation run {run_id} names a DIFFERENT "
                f"instrument ({summary.instrument_id}) — refused"
            )
        for row in mapping_rows:
            _append_spec(
                specs,
                COMPONENT_KIND_PROXY_MAPPING,
                "proxy_mapping",
                row,
                proxy_mapping_content(row),
            )
        _append_spec(
            specs,
            COMPONENT_KIND_PROXY_WEIGHT,
            "proxy_weight_estimate_result",
            summary,
            proxy_weight_estimate_content(summary),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_VAR_INPUT,
        as_of_valid_at=now,
        as_of_known_at=now,
        as_of_valuation_date=covariance_rows[0].window_end,
        binding_predicate_version=VAR_UNIFIED_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


def resolve_snapshot(session: Session, snapshot_id: str, *, acting_tenant: str) -> DatasetSnapshot:
    """Resolve a ``dataset_snapshot`` header by id with an EXPLICIT tenant predicate (fail-closed
    on
    SQLite + PG). Raises :class:`SnapshotNotFound` on a hidden/unknown id."""
    header = session.execute(
        select(DatasetSnapshot).where(
            DatasetSnapshot.id == str(snapshot_id),
            DatasetSnapshot.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if header is None:
        raise SnapshotNotFound(str(snapshot_id))
    return header


def list_snapshots(
    session: Session,
    *,
    acting_tenant: str,
    purpose: str | None = None,
    as_of_valuation_date: date | None = None,
) -> list[DatasetSnapshot]:
    """API-1 F2 listing: ``dataset_snapshot`` headers under the acting tenant, optionally filtered
    by ``purpose`` and/or ``as_of_valuation_date`` (silent-empty on no match). Newest-first
    (``system_from`` DESC, id DESC). RLS-scoped; NO components (use :func:`list_components` or the
    by-id read for the heavy body). There is no portfolio/scope column on the snapshot header (the
    API-1b run-scope gap), so no portfolio filter is offered."""
    stmt = select(DatasetSnapshot).where(DatasetSnapshot.tenant_id == str(acting_tenant))
    if purpose is not None:
        stmt = stmt.where(DatasetSnapshot.purpose == str(purpose))
    if as_of_valuation_date is not None:
        stmt = stmt.where(DatasetSnapshot.as_of_valuation_date == as_of_valuation_date)
    stmt = stmt.order_by(DatasetSnapshot.system_from.desc(), DatasetSnapshot.id.desc())
    return list(session.execute(stmt).scalars().all())


def list_components(
    session: Session, *, snapshot_id: str, acting_tenant: str
) -> list[DatasetSnapshotComponent]:
    """The pinned components of a snapshot (tenant-scoped), ordered for stable display."""
    return list(
        session.execute(
            select(DatasetSnapshotComponent)
            .where(
                DatasetSnapshotComponent.snapshot_id == str(snapshot_id),
                DatasetSnapshotComponent.tenant_id == str(acting_tenant),
            )
            .order_by(
                DatasetSnapshotComponent.component_kind,
                DatasetSnapshotComponent.target_entity_id,
            )
        )
        .scalars()
        .all()
    )


class MalformedPinError(Exception):
    """RD-3 OD-A: the pinned ``captured_content`` on a series/composite component could not be
    parsed as a JSON object, or is missing a key ``_reresolve_content`` needs (truncated/tampered/
    non-object). Raised ONLY by ``_parsed_pin`` below — scoped to the four branches that actually
    parse ``captured_content`` (BENCHMARK_RETURN/FACTOR_RETURN/BENCHMARK/SCENARIO), not the whole
    ``_reresolve_content`` dispatch, so a live-data serialization bug in one of the other 14
    branches still raises loudly instead of being silently reported as drift (finder review)."""


def _parsed_pin(comp: DatasetSnapshotComponent, *keys: str) -> tuple[Any, ...]:
    """Parse ``comp.captured_content`` as a JSON object and pluck ``keys`` off it, refusing a
    non-parseable/non-object/missing-key pin as :class:`MalformedPinError` — content that cannot
    even be parsed has definitionally failed reproduction (OD-A rationale), never a raw 500."""
    try:
        pinned = json.loads(comp.captured_content)
        return tuple(pinned[key] for key in keys)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MalformedPinError(
            f"component {comp.id} captured_content is not a well-formed pin ({type(exc).__name__})"
        ) from exc


def _pinned_row_ids(comp: DatasetSnapshotComponent, rows: Any) -> list[str]:
    """Pluck each pinned row's ``id`` out of a ``pinned["rows"]`` value, refusing a non-iterable or
    element-missing-``id`` shape as :class:`MalformedPinError` (the same OD-A refusal class as
    ``_parsed_pin``, split out because this operates on an already-extracted value, not the raw
    JSON object)."""
    try:
        return [str(r["id"]) for r in rows]
    except (KeyError, TypeError) as exc:
        raise MalformedPinError(
            f"component {comp.id} captured_content 'rows' is not well-formed ({type(exc).__name__})"
        ) from exc


def _reresolve_content(
    session: Session,
    comp: DatasetSnapshotComponent,
    *,
    acting_tenant: str,
    benchmark_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-resolve a component's target by id (explicit-tenant-predicate resolver, never
    session.get)
    and return its current canonical content dict. Raises the resolver's ``*NotVisible`` if
    gone. ``benchmark_cache`` (when supplied) memoizes the single benchmark header across a
    snapshot's many BENCHMARK constituent components — one point-SELECT instead of N (review)."""
    if comp.component_kind == COMPONENT_KIND_POSITION:
        return position_content(
            resolve_position(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_VALUATION:
        return valuation_content(
            resolve_valuation(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_FX:
        return fx_content(
            resolve_fx_rate(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_CURVE:
        header = resolve_curve(session, comp.target_entity_id, acting_tenant=acting_tenant)
        nodes = list_curve_points(session, header.id, acting_tenant=acting_tenant)
        return curve_content(header, nodes)
    if comp.component_kind == COMPONENT_KIND_EXPOSURE:
        return exposure_content(
            _resolve_exposure_atom(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_INSTRUMENT:
        # STRUCT-1: the instrument EV identity pin (asset_class for the DP-4 rule). An EV amend
        # moves record_version/content — real drift the discriminator must see (TR-09).
        return instrument_content(
            resolve_instrument(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_INSTRUMENT_TERMS:
        # STRUCT-1: the terms FR version pin — byte-stable under a later supersede/correct (the
        # pinned version's immutable content, TR-09); a gone/cross-tenant row reports as drift.
        return instrument_terms_content(
            _resolve_instrument_terms_row(
                session, comp.target_entity_id, acting_tenant=acting_tenant
            )
        )
    if comp.component_kind == COMPONENT_KIND_TRANSACTION:
        return transaction_content(
            _resolve_transaction_row(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_PORTFOLIO_RETURN:
        return portfolio_return_content(
            _resolve_portfolio_return_row(
                session, comp.target_entity_id, acting_tenant=acting_tenant
            )
        )
    if comp.component_kind == COMPONENT_KIND_DESMOOTHED_RETURN:
        return desmoothed_return_content(
            _resolve_desmoothed_return_row(
                session, comp.target_entity_id, acting_tenant=acting_tenant
            )
        )
    if comp.component_kind == COMPONENT_KIND_PURE_PRIVATE_RETURN:
        return pure_private_return_content(
            _resolve_pure_private_return_row(
                session, comp.target_entity_id, acting_tenant=acting_tenant
            )
        )
    if comp.component_kind == COMPONENT_KIND_ISSUER_EDGE:
        # The narrow edge pin: drift iff the ISSUER EDGE moves (OQ-CON-1-7). Explicit-tenant
        # resolver; every other instrument field is excluded by the serializer.
        return issuer_edge_content(
            resolve_instrument(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_CLASSIFICATION:
        # THE PLATFORM'S FIRST RE-DERIVE-FLAVORED BRANCH (OQ-CON-1-9, deliberate deviation from
        # the by-id idiom): the assignment's physical row is re-read by id (FR — its fields are
        # immutable; a supersede is a NEW row), but the closure is re-resolved CODE-FIRST via
        # resolve_node's tenant precedence + a fresh ancestor walk — so a LEAF override, a level
        # or parent move, or an ancestor code change REDDENS the pin, while a name/description
        # rename cannot (both are excluded from the content).
        assignment = _resolve_assignment_row(
            session, comp.target_entity_id, acting_tenant=acting_tenant
        )
        node = resolve_node(
            session,
            scheme_id=str(assignment.scheme_id),
            code=assignment.node_code,
            acting_tenant=acting_tenant,
        )
        chain = resolve_ancestors(session, node=node, acting_tenant=acting_tenant)
        return classification_assignment_closure_content(assignment, [*chain, node])
    if comp.component_kind == COMPONENT_KIND_GOVERNED_VALUE:
        # RPT-1 (ENT-072): RE-DERIVE the family's values LIVE from the pinned source run, so a
        # report component honestly REDDENS if its family's rows ever move.
        #
        # It is tempting to return the pinned content unchanged here and call the component
        # "immutable by construction" — the source rows ARE IA append-only. That was refused: it is
        # exactly the vacuous verification this census exists to prevent (a kind with no real
        # branch makes ``verify_snapshot`` report ``ok`` over anything). Re-deriving means the
        # check has something to actually compare, and it also catches the case immutability does
        # NOT cover — the run becoming invisible to this tenant.
        from irp_shared.report.families import family_for
        from irp_shared.report.service import governed_value_content

        pinned = json.loads(comp.captured_content)
        family = family_for(str(pinned["family"]))
        run_id = str(pinned["source_run_id"])
        values = family.read_values(session, run_id, acting_tenant)
        # Provenance is re-resolved LIVE too, not copied from the pin. Copying it would make the
        # verification blind to the failure that matters most here: a model version re-pointed at a
        # different methodology document after the report was generated. The re-derived value is
        # compared against the pin by the caller, so a moved citation REDDENS.
        prov = family.read_provenance(session, run_id, acting_tenant)
        return governed_value_content(
            family_key=family.key,
            section_title=family.section_title,
            model_code=prov.model_code,
            methodology_ref=prov.methodology_ref,
            model_version_id=prov.model_version_id,
            run_id=run_id,
            source_snapshot_id=str(pinned["source_snapshot_id"]),
            # The knowledge time is a property of the PINNED source snapshot, which is IA
            # append-only — so carrying it forward from the pin is not a shortcut, it is the
            # only definition. Re-reading it live would just re-read the same immutable row.
            source_known_at=str(pinned["source_known_at"]),
            values=values,
        )
    if comp.component_kind == COMPONENT_KIND_HOLIDAY_CALENDAR:
        # CAL-1b, RE-DERIVE flavored (the CLASSIFICATION precedent): re-read the calendar HEAD by
        # the pinned target id under hybrid own-OR-SYSTEM visibility, then RE-DERIVE the member
        # date set LIVE — an ADD-ONLY refresh that inserts a date (or advances the declared
        # coverage) after the pin honestly REDDENS this component, which is exactly the drift
        # visibility OQ-CAL-1-6-A buys; a head rename/is_active flip cannot (excluded from the
        # narrow content).
        from irp_shared.reference.models import Calendar as _Calendar
        from irp_shared.reference.models import CalendarHoliday as _CalendarHoliday

        cal_row = session.execute(
            select(_Calendar).where(
                _Calendar.id == comp.target_entity_id,
                or_(
                    _Calendar.tenant_id == str(acting_tenant),
                    _Calendar.tenant_id == SYSTEM_TENANT_ID,
                ),
            )
        ).scalar_one_or_none()
        if cal_row is None:
            raise CalendarNotVisible(str(comp.target_entity_id))
        live_dates = list(
            session.execute(
                select(_CalendarHoliday.holiday_date).where(
                    _CalendarHoliday.calendar_id == cal_row.id
                )
            ).scalars()
        )
        return holiday_calendar_content(cal_row, live_dates)
    if comp.component_kind == COMPONENT_KIND_CLASSIFICATION_SCHEME:
        # Hybrid two-tenant resolver (SYSTEM rows are the normal case — the v5-pass resolver-
        # pattern correction).
        return classification_scheme_content(
            resolve_scheme(session, scheme_id=comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_VAR:
        return var_result_content(
            _resolve_var_row(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_BENCHMARK_RETURN:
        # Re-read the benchmark header (by the pinned target id) + each pinned FR row by surrogate
        # id (tenant-predicated). A superseded/corrected row is byte-stable (its immutable content
        # is what was pinned — close-out markers excluded, TR-09); a gone row reports as drift.
        benchmark = resolve_benchmark(session, comp.target_entity_id, acting_tenant=acting_tenant)
        (pinned_rows,) = _parsed_pin(comp, "rows")
        rows = [
            _resolve_benchmark_return_row(session, rid, acting_tenant=acting_tenant)
            for rid in _pinned_row_ids(comp, pinned_rows)
        ]
        return benchmark_return_series_content(benchmark, rows)
    if comp.component_kind == COMPONENT_KIND_FACTOR:
        return factor_content(
            resolve_factor(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_FACTOR_EXPOSURE:
        return factor_exposure_content(
            _resolve_factor_exposure_row(
                session, comp.target_entity_id, acting_tenant=acting_tenant
            )
        )
    if comp.component_kind == COMPONENT_KIND_COVARIANCE:
        return covariance_content(
            _resolve_covariance_row(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_FACTOR_RETURN:
        # Re-read the series parent + each pinned FR row by surrogate id (tenant-predicated). A
        # gone/cross-tenant row reports as drift; a superseded/corrected row is byte-stable (its
        # immutable content is what was pinned — the close-out markers are excluded, TR-09).
        factor = resolve_factor(session, comp.target_entity_id, acting_tenant=acting_tenant)
        (pinned_rows,) = _parsed_pin(comp, "rows")
        rows = [
            _resolve_factor_return_row(session, rid, acting_tenant=acting_tenant)
            for rid in _pinned_row_ids(comp, pinned_rows)
        ]
        return factor_return_series_content(factor, rows)
    if comp.component_kind == COMPONENT_KIND_BENCHMARK:
        # Re-read the benchmark header (from the pinned id) + the constituent FR row by surrogate
        # id (tenant-predicated). A gone/cross-tenant row reports as drift; a superseded/corrected
        # row is byte-stable (its immutable content is what was pinned — TR-09).
        (pinned_bid,) = _parsed_pin(comp, "benchmark_id")
        bid = str(pinned_bid)
        if benchmark_cache is not None and bid in benchmark_cache:
            benchmark = benchmark_cache[bid]  # one header per snapshot — resolved once
        else:
            benchmark = resolve_benchmark(session, bid, acting_tenant=acting_tenant)
            if benchmark_cache is not None:
                benchmark_cache[bid] = benchmark
        constituent = _resolve_benchmark_constituent_row(
            session, comp.target_entity_id, acting_tenant=acting_tenant
        )
        return benchmark_membership_content(benchmark, constituent)
    if comp.component_kind == COMPONENT_KIND_PROXY_MAPPING:
        # Re-read the proxy_mapping FR row by surrogate id (tenant-predicated). A superseded/
        # corrected row is byte-stable (its immutable content is what was pinned — TR-09).
        return proxy_mapping_content(
            _resolve_proxy_mapping_row(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_COMMITMENT:
        # Re-read the commitment FR version by surrogate id (tenant-predicated) — byte-stable under
        # a later supersede/correct (the pinned version's immutable content, TR-09); a gone/
        # cross-tenant row reports as drift.
        return commitment_content(
            _resolve_commitment_row(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_CAPITAL_CALL:
        # Re-read the capital_call IA row by id (tenant-predicated) — true append-only, byte-
        # identical on re-verify unless tampered (the transaction/var_result precedent).
        return capital_call_content(
            _resolve_capital_call_row(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_DISTRIBUTION:
        return distribution_content(
            _resolve_distribution_row(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_PROXY_WEIGHT:
        # Re-read the proxy_weight_estimate_result IA row by id (tenant-predicated) — true
        # append-only, so re-verification is byte-identical unless tampered (the ``var_result``
        # VAR-component precedent).
        return proxy_weight_estimate_content(
            _resolve_proxy_weight_estimate_row(
                session, comp.target_entity_id, acting_tenant=acting_tenant
            )
        )
    if comp.component_kind == COMPONENT_KIND_SCENARIO:
        # Re-read the scenario DEFINITION (from the pinned id) + the shock FR row by surrogate id
        # (tenant-predicated). A gone/cross-tenant row reports as drift; a superseded/corrected row
        # is byte-stable (its immutable content is what was pinned — TR-09). Without this branch a
        # SCENARIO_INPUT snapshot would fall through to portfolio_content and ALWAYS report drift.
        from irp_shared.risk.scenario import resolve_scenario_definition  # binder read (no cycle)

        (pinned_def_id,) = _parsed_pin(comp, "scenario_definition_id")
        definition = resolve_scenario_definition(
            session, str(pinned_def_id), acting_tenant=acting_tenant
        )
        shock = _resolve_scenario_shock_row(
            session, comp.target_entity_id, acting_tenant=acting_tenant
        )
        return scenario_shock_content(definition, shock)
    return portfolio_content(
        resolve_portfolio(session, comp.target_entity_id, acting_tenant=acting_tenant)
    )


def verify_snapshot(session: Session, *, snapshot_id: str, acting_tenant: str) -> VerifyResult:
    """Re-resolve each component under the acting tenant, re-serialize, and compare
    ``content_hash``
    (the authoritative reproducibility check). Drift = a changed value/version (or a gone target).
    Emits NO audit event (read/verify is no-emit, OD-023). Raises :class:`SnapshotNotFound` if the
    header is not visible."""
    resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
    comps = list_components(session, snapshot_id=snapshot_id, acting_tenant=acting_tenant)
    drifted: list[str] = []
    benchmark_cache: dict[str, Any] = {}  # the single benchmark header, resolved once per snapshot
    for comp in comps:
        try:
            live = _reresolve_content(
                session, comp, acting_tenant=acting_tenant, benchmark_cache=benchmark_cache
            )
        except (
            PositionNotVisible,
            ValuationNotVisible,
            PortfolioNotVisible,
            FxRateNotVisible,
            CurveNotVisible,
            FactorNotVisible,
            FactorExposureSnapshotError,
            CovarianceSnapshotError,
            PrivateCovarianceSnapshotError,
            VarSnapshotError,
            ReturnSnapshotError,
            BenchmarkRelativeSnapshotError,
            VarBacktestSnapshotError,
            BenchmarkNotVisible,
            ScenarioSnapshotError,
            ProxyWeightSnapshotError,
            PacingSnapshotError,
            # CON-1's three shapes: a gone instrument/assignment/scheme (or an unresolvable
            # code-first closure) is definitionally failed reproduction — drift, not a 500.
            InstrumentNotVisible,
            ClassificationNotVisible,
            ConcentrationSnapshotError,
            # CAL-1b: a gone/cross-tenant calendar head behind a HOLIDAY_CALENDAR pin is failed
            # reproduction — drift, not a 500 (the CON-1 three-shapes precedent).
            CalendarNotVisible,
            # RD-3 OD-A: the BENCHMARK_RETURN/FACTOR_RETURN/BENCHMARK/SCENARIO branches parse
            # ``captured_content`` via ``_parsed_pin``/``_pinned_row_ids``, which raise ONLY this
            # class on a truncated/tampered/non-object/missing-key pin — never a bare
            # KeyError/TypeError/ValueError/ArithmeticError, which would ALSO catch a live-data
            # serialization bug in one of the other 14 branches and mis-report it as drift (a
            # finder-review correction: the except-tuple must stay scoped to "the pin didn't
            # parse", not widen to "anything went wrong while re-resolving"). verify's contract is
            # "does the pinned content still reproduce?"; content that can't even be parsed has
            # definitionally failed reproduction, so it reports as drift, not a raw 500 (the P3-C3
            # binder malformed-pin idiom, applied here to the read/verify path).
            MalformedPinError,
        ):
            drifted.append(comp.id)
            continue
        if content_hash(serialize_content(live)) != comp.content_hash:
            drifted.append(comp.id)
    return VerifyResult(ok=not drifted, component_count=len(comps), drifted_components=drifted)


#: VAR-HS-1 truthful binding predicate (OD-VHS-F).
VAR_HS_BINDING_PREDICATE = "v1:exposure-run-rows+aligned-factor-return-windows"


def build_var_hs_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_id: str,
    window_observations: int,
    as_of_valid_at: datetime | None = None,
    as_of_known_at: datetime | None = None,
) -> DatasetSnapshot:
    """Build one immutable ``VAR_HS_INPUT`` snapshot (VAR-HS-1, OD-VHS-F) pinning:

    - one ``COMPONENT_KIND_FACTOR_EXPOSURE`` component per ``factor_exposure_result`` row of the
      consumed exposure run (the IA-row pin flavor — ``build_var_snapshot``'s exposure leg), and
    - one ``COMPONENT_KIND_FACTOR_RETURN`` component per DISTINCT factor of that run — the
      factor's aligned RETURN WINDOW (``build_covariance_snapshot``'s bitemporal per-date pin:
      the ``window_observations`` most recent dates COMMON to every factor; fail-closed, no
      imputation, OD-P3-0-L),

    so a historical-simulation run is reproducible from the snapshot alone (the compute reads
    this captured content — never a live read; later supersedes/re-runs cannot move a pinned
    number, TR-09). The factor SET is the exposure run's own factor set — an uncovered factor is
    impossible by construction on this path (hand-minted snapshots are still adjudicated by the
    binder). Declared-window/model adjudication is the RISK binder's pre-create gate — this
    builder pins; it does not read the model registry."""
    now = utcnow()
    valid_at = as_of_valid_at if as_of_valid_at is not None else now
    known = as_of_known_at if as_of_known_at is not None else now  # FROZEN once (header == pin)

    if window_observations < 2:
        raise VarSnapshotError(f"window_observations must be >= 2 (got {window_observations})")

    exposure_rows = _list_factor_exposure_rows(
        session, exposure_run_id, acting_tenant=acting_tenant
    )
    if not exposure_rows:
        raise VarSnapshotError(f"exposure run {exposure_run_id} has no visible result rows")

    factor_ids = list(dict.fromkeys(str(row.factor_id).lower() for row in exposure_rows))
    factors = [resolve_factor(session, fid, acting_tenant=acting_tenant) for fid in factor_ids]
    by_date = {
        factor.id: _factor_window_rows(
            session,
            acting_tenant=acting_tenant,
            factor_id=factor.id,
            valid_at=valid_at,
            known_at=known,
        )
        for factor in factors
    }
    common: set[date] = set.intersection(*(set(rows.keys()) for rows in by_date.values()))
    if len(common) < window_observations:
        raise VarSnapshotError(
            f"only {len(common)} common return dates across {len(factors)} factors — "
            f"the declared window needs {window_observations} (no imputation, OD-P3-0-L)"
        )
    window_dates = sorted(common)[-window_observations:]

    specs: list[tuple[str, str, Any, str, str]] = []
    for row in exposure_rows:
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_EXPOSURE,
            "factor_exposure_result",
            row,
            factor_exposure_content(row),
        )
    for factor in factors:
        window_rows = [by_date[factor.id][d] for d in window_dates]
        _append_spec(
            specs,
            COMPONENT_KIND_FACTOR_RETURN,
            "factor",
            factor,
            factor_return_series_content(factor, window_rows),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_VAR_HS_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=window_dates[-1],
        binding_predicate_version=VAR_HS_BINDING_PREDICATE,
    )

    # No build-time DQ gate: pinned content is complete by construction (empty/short/misaligned
    # inputs are refused above, before any write) — the P3-3/P3-4 rationale.
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class ConcentrationSnapshotError(Exception):
    """A concentration-input snapshot cannot be built — raised BEFORE any write (the PRE-BUILD
    refusals of OQ-CON-1-1/10/24/26: NULL-scope upstream run, mixed scheme versions of one family,
    mixed basis within a dimension, empty atom set); never mints immutable governance garbage."""


#: CON-1 (OQ-CON-1-6…10): atoms + issuer edges + assignments/closures + scheme rows. ≤ 50 chars.
CONCENTRATION_BINDING_PREDICATE = "v1:exposure-atoms+issuer-edges+classification"
#: LQ-1: the liquidity run's predicate. NO issuer edge — liquidity does not aggregate by issuer, so
#: pinning one would be an unconsumed component, and an unconsumed pin is the shape that verifies
#: VACUOUSLY (nothing re-resolves it, so nothing can report drift on it).
LIQUIDITY_BINDING_PREDICATE = "v1:exposure-atoms+liquidity-tier-assignments"
#: RPT-1: the report pins one GOVERNED_VALUE component per family, each carrying that family's
#: values AND provenance. 30 chars — well inside the String(50) ceiling enforced at import below.
REPORT_BINDING_PREDICATE = "v1:governed-values-by-family"


def issuer_edge_content(instrument: Any) -> dict[str, Any]:
    """The NARROW instrument→issuer edge pin (OQ-CON-1-7): ``{id, tenant_id, issuer_id}`` ONLY.

    ``record_version`` and every other ``_UPDATABLE`` field are deliberately EXCLUDED — the pin
    drifts iff the ISSUER EDGE moves, and is inert to renames/currency fixes/``is_active`` flips
    (the ``var_result_content`` field-exclusion precedent). Two mandatory controls ride the tests:
    the pin DOES drift on an issuer move, and does NOT drift on each excluded field."""
    # _norm_guid on BOTH sides of the join key, matching exposure_content. The atoms are
    # normalized, so a raw str() here would leave an uppercase-stored id unmatched and the
    # instrument would silently read UNCLASSIFIABLE rather than failing loudly (review).
    return {
        "id": _norm_guid(instrument.id),
        "tenant_id": _norm_guid(instrument.tenant_id),
        "issuer_id": (
            _norm_guid(instrument.issuer_id) if instrument.issuer_id is not None else None
        ),
    }


def classification_assignment_closure_content(assignment: Any, chain: list[Any]) -> dict[str, Any]:
    """One assignment row (incl. ``basis`` — OQ-CON-1-26) PLUS its resolved ancestor closure.

    The closure hashes ``code``/``parent_node_id``/``level`` and EXCLUDES ``name``/``description``
    (REF-1's carry #3: a cosmetic rename cannot redden a historical run)."""
    return {
        "id": _norm_guid(assignment.id),
        "tenant_id": _norm_guid(assignment.tenant_id),
        "entity_type": assignment.entity_type,
        # NORMALIZED: this is the (dimension_kind, instrument_id) join key the binder probes with
        # the atoms' already-normalized instrument_id.
        "entity_id": _norm_guid(assignment.entity_id),
        "scheme_id": _norm_guid(assignment.scheme_id),
        "dimension_kind": assignment.dimension_kind,
        "node_code": assignment.node_code,
        "basis": assignment.basis,
        "closure": [
            {
                "code": node.code,
                "parent_node_id": (
                    _norm_guid(node.parent_node_id) if node.parent_node_id is not None else None
                ),
                "level": node.level,
            }
            for node in chain
        ],
    }


def classification_scheme_content(scheme: Any) -> dict[str, Any]:
    """The scheme-row pin (OQ-CON-1-24 ii): WHICH taxonomy version produced the number — pinned as
    re-verifiable evidence, NOT as the mixed-version discriminator (that reads live heads)."""
    return {
        "id": _norm_guid(scheme.id),
        "scheme_family": scheme.scheme_family,
        "version_label": scheme.version_label,
    }


def build_concentration_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_id: str,
    scheme_by_dimension: dict[str, str],
) -> DatasetSnapshot:
    """Build one immutable ``CONCENTRATION_INPUT`` snapshot (CON-1) pinning FOUR shapes:

    - one ``COMPONENT_KIND_EXPOSURE`` per atom of the EXPLICITLY SELECTED exposure run (REUSED —
      the IA-row pin; "latest COMPLETED" is never a selection here, Part 6b item 5);
    - one ``COMPONENT_KIND_ISSUER_EDGE`` per DISTINCT instrument carrying exposure (the narrow
      ``{id, tenant_id, issuer_id}`` pin — a NULL edge pins honestly as NULL, the residual fact);
    - one ``COMPONENT_KIND_CLASSIFICATION`` per current-head assignment of a pinned INSTRUMENT
      under a REQUESTED scheme (assignment + ancestor closure, code-first semantics) — REF-1's
      assignment grain is the INSTRUMENT, not the issuer (review: the docstring said "issuer"); and
    - one ``COMPONENT_KIND_CLASSIFICATION_SCHEME`` per requested scheme row.

    **PRE-BUILD refusals (computable from current heads — no snapshot, no run):** a requested
    scheme id that resolves to a different ``dimension_kind`` than requested; MIXED BASIS within
    one dimension's pinned assignments (OQ-CON-1-26); a second LIVE scheme of the SAME
    ``(dimension_kind, scheme_family)`` carried by the pinned instruments (OQ-CON-1-24 i — mixed
    VERSIONS refuse; a different family simply is not consumed); an empty atom set. The NULL-scope
    upstream-run refusal lives in the BINDER (it needs the run head, read there). Classification
    is AS-OF-BUILD (OQ-CON-1-11): current heads, declared as a model assumption."""
    now = utcnow()
    valid_at = known = now

    atoms = _list_exposure_atoms(
        session, exposure_run_id, acting_tenant=acting_tenant, consuming_run_type="CONCENTRATION"
    )
    if not atoms:
        raise ConcentrationSnapshotError(
            f"exposure run {exposure_run_id} has no visible atoms to pin"
        )

    specs: list[tuple[str, str, Any, str, str]] = []
    for atom in atoms:
        _append_spec(
            specs, COMPONENT_KIND_EXPOSURE, "exposure_aggregate", atom, exposure_content(atom)
        )

    # The DISTINCT instruments carrying exposure — each edge pinned narrow, NULL edges included
    # (an issuer-less instrument is the UNCLASSIFIABLE residual, a fact the snapshot must carry).
    instrument_ids = sorted({str(a.instrument_id) for a in atoms})
    instruments = [
        resolve_instrument(session, iid, acting_tenant=acting_tenant) for iid in instrument_ids
    ]
    for inst in instruments:
        _append_spec(
            specs, COMPONENT_KIND_ISSUER_EDGE, "instrument", inst, issuer_edge_content(inst)
        )

    # The requested schemes, resolved (hybrid two-tenant read) and pinned.
    schemes: dict[str, Any] = {}
    for dimension_kind, scheme_id in sorted(scheme_by_dimension.items()):
        scheme = resolve_scheme(session, scheme_id=scheme_id, acting_tenant=acting_tenant)
        if scheme.dimension_kind != dimension_kind:
            raise ConcentrationSnapshotError(
                f"scheme {scheme_id} is a {scheme.dimension_kind} scheme; requested for "
                f"{dimension_kind}"
            )
        schemes[dimension_kind] = scheme
        _append_spec(
            specs,
            COMPONENT_KIND_CLASSIFICATION_SCHEME,
            "classification_scheme",
            scheme,
            classification_scheme_content(scheme),
        )

    # Current-head assignments for the pinned INSTRUMENTS under each requested scheme (REF-1's
    # assignment grain is the instrument — ``ASSIGNMENT_ENTITY_TYPES == ('instrument',)``), with
    # the ancestor closure resolved CODE-FIRST (tenant precedence) — plus the PRE-BUILD coherence
    # refusals over the pinned set.
    for dimension_kind, scheme in sorted(schemes.items()):
        # OQ-CON-1-24 (i) — the MIXED-VERSION refusal, computed over the LIVE book, NOT the pinned
        # set. The ratified wording said "among the pinned assignments"; the review proved that
        # discriminator structurally unfireable, because the pinned set is filtered to the
        # REQUESTED ``scheme_id`` and so can never hold a second version to discriminate against
        # (the pinned scheme rows were inert, and three docstrings + one API 409 advertised a
        # refusal no code path could produce). The check therefore reads the tenant's LIVE
        # current-head assignments for these instruments WITHOUT the scheme filter — a deliberate
        # STRENGTHENING of the ratified wording, recorded as such in the decision record.
        live_scheme_ids = _list_current_assignment_scheme_ids(
            session,
            entity_ids=instrument_ids,
            dimension_kind=dimension_kind,
            acting_tenant=acting_tenant,
        )
        same_family = sorted(
            sid
            for sid in live_scheme_ids
            if resolve_scheme(session, scheme_id=sid, acting_tenant=acting_tenant).scheme_family
            == scheme.scheme_family
        )
        if len(same_family) > 1:
            raise ConcentrationSnapshotError(
                f"mixed live scheme VERSIONS of family {scheme.scheme_family!r} within "
                f"{dimension_kind}: {same_family} — aggregating one version while the other's "
                f"assignments read UNCLASSIFIED understates concentration, so this refuses "
                f"fail-closed (OQ-CON-1-24 i); retire one version before running. A DIFFERENT "
                f"family co-existing stays legal and is simply not consumed (clause iii)."
            )
        rows = _list_current_assignments(
            session,
            entity_ids=instrument_ids,
            scheme_id=str(scheme.id),
            dimension_kind=dimension_kind,
            acting_tenant=acting_tenant,
        )
        bases = sorted({r.basis for r in rows})
        if len(bases) > 1:
            raise ConcentrationSnapshotError(
                f"mixed basis within {dimension_kind}: {bases} — mixed-basis aggregation is "
                f"refused fail-closed (OQ-CON-1-26); capture a single basis per dimension"
            )
        for row in rows:
            node = resolve_node(
                session,
                scheme_id=str(row.scheme_id),
                code=row.node_code,
                acting_tenant=acting_tenant,
            )
            chain = resolve_ancestors(session, node=node, acting_tenant=acting_tenant)
            _append_spec(
                specs,
                COMPONENT_KIND_CLASSIFICATION,
                "classification_assignment",
                row,
                classification_assignment_closure_content(row, [*chain, node]),
            )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_CONCENTRATION_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=valid_at.date(),
        binding_predicate_version=CONCENTRATION_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


class LiquiditySnapshotError(Exception):
    """A liquidity snapshot cannot be built from the current heads (LQ-1, PRE-BUILD)."""


def build_liquidity_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    exposure_run_id: str,
    scheme_id: str,
) -> DatasetSnapshot:
    """Build one immutable ``LIQUIDITY_INPUT`` snapshot (LQ-1) pinning THREE shapes:

    - one ``COMPONENT_KIND_EXPOSURE`` per atom of the EXPLICITLY SELECTED exposure run;
    - one ``COMPONENT_KIND_CLASSIFICATION`` per current-head ``LIQUIDITY_TIER`` assignment of a
      pinned instrument, with its ancestor closure (the kind is REUSED unchanged — LQ-1 mints no
      new component kind, only its own PURPOSE and predicate);
    - the referenced ``classification_scheme`` row.

    No issuer edge is pinned: liquidity does not aggregate by issuer, and an unconsumed pin
    verifies VACUOUSLY because nothing re-resolves it.

    **The untiered instrument is pinned by ABSENCE, deliberately.** A pinned instrument with no
    current-head tier simply has no CLASSIFICATION component, and the kernel reads that as
    UNCLASSIFIED. The alternative — a sentinel component asserting "no tier" — would make the
    snapshot claim something the book never said.

    **PRE-BUILD refusals (computable from current heads — no snapshot, no run):**

    1. *Wrong dimension.* A ``scheme_id`` resolving to a dimension other than ``LIQUIDITY_TIER``.
    2. *Mixed live scheme VERSIONS* of the same family (inherited from OQ-CON-1-24 i). Computed
       over the tenant's LIVE current-head assignments WITHOUT the scheme filter — NOT over the
       pinned set. CON-1's ratified wording said "among the pinned assignments" and its review
       proved that discriminator structurally UNFIREABLE, because the pinned set is already
       filtered to the requested scheme and so can never hold a second version to discriminate
       against. Repeating the ratified wording here would have re-shipped a refusal no code path
       could produce, which is why this reads the live book.
    3. *Mixed basis* within the dimension (inherited from OQ-CON-1-26).
    4. *An empty atom set.*

    Tier resolution is AS-OF-BUILD (ratified OQ-LQ-1-9), declared as a model assumption; the
    staleness bound that accompanies it is enforced in the BINDER, which is where the run's own
    clock lives.
    """
    from irp_shared.classification.models import DIMENSION_KIND_LIQUIDITY_TIER

    now = utcnow()
    valid_at = known = now

    atoms = _list_exposure_atoms(
        session, exposure_run_id, acting_tenant=acting_tenant, consuming_run_type="LIQUIDITY"
    )
    if not atoms:
        raise LiquiditySnapshotError(f"exposure run {exposure_run_id} has no visible atoms to pin")

    specs: list[tuple[str, str, Any, str, str]] = []
    for atom in atoms:
        _append_spec(
            specs, COMPONENT_KIND_EXPOSURE, "exposure_aggregate", atom, exposure_content(atom)
        )

    instrument_ids = sorted({str(a.instrument_id) for a in atoms})

    scheme = resolve_scheme(session, scheme_id=scheme_id, acting_tenant=acting_tenant)
    if scheme.dimension_kind != DIMENSION_KIND_LIQUIDITY_TIER:
        raise LiquiditySnapshotError(
            f"scheme {scheme_id} serves dimension {scheme.dimension_kind!r}, not "
            f"{DIMENSION_KIND_LIQUIDITY_TIER!r} — refusing to pin a ladder that is not a ladder"
        )
    _append_spec(
        specs,
        COMPONENT_KIND_CLASSIFICATION_SCHEME,
        "classification_scheme",
        scheme,
        classification_scheme_content(scheme),
    )

    # Refusal 2 — over the LIVE book, not the pinned set (see the docstring).
    live_scheme_ids = _list_current_assignment_scheme_ids(
        session,
        entity_ids=instrument_ids,
        dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
        acting_tenant=acting_tenant,
    )
    same_family = sorted(
        sid
        for sid in live_scheme_ids
        if resolve_scheme(session, scheme_id=sid, acting_tenant=acting_tenant).scheme_family
        == scheme.scheme_family
    )
    if len(same_family) > 1:
        raise LiquiditySnapshotError(
            f"mixed live scheme VERSIONS of family {scheme.scheme_family!r} within "
            f"{DIMENSION_KIND_LIQUIDITY_TIER}: {same_family} — tiering one version while the "
            f"other's assignments read UNCLASSIFIED understates coverage and can silently move "
            f"the illiquid share, so this refuses fail-closed; retire one version before running"
        )

    rows = _list_current_assignments(
        session,
        entity_ids=instrument_ids,
        scheme_id=str(scheme.id),
        dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
        acting_tenant=acting_tenant,
    )
    bases = sorted({r.basis for r in rows})
    if len(bases) > 1:
        raise LiquiditySnapshotError(
            f"mixed basis within {DIMENSION_KIND_LIQUIDITY_TIER}: {bases} — mixed-basis "
            f"aggregation is refused fail-closed; capture a single basis per dimension"
        )
    for row in rows:
        node = resolve_node(
            session,
            scheme_id=str(row.scheme_id),
            code=row.node_code,
            acting_tenant=acting_tenant,
        )
        chain = resolve_ancestors(session, node=node, acting_tenant=acting_tenant)
        _append_spec(
            specs,
            COMPONENT_KIND_CLASSIFICATION,
            "classification_assignment",
            row,
            classification_assignment_closure_content(row, [*chain, node]),
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_LIQUIDITY_INPUT,
        as_of_valid_at=valid_at,
        as_of_known_at=known,
        as_of_valuation_date=valid_at.date(),
        binding_predicate_version=LIQUIDITY_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


def build_report_input_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    portfolio_id: str,
    family_runs: dict[str, str],
    as_of_valuation_date: date,
) -> DatasetSnapshot:
    """Build one immutable ``REPORT_INPUT`` snapshot (RPT-1) pinning the family VALUES a report
    renders — one ``COMPONENT_KIND_GOVERNED_VALUE`` per bound family.

    The refusals live in ``report.service.build_report_snapshot`` and run BEFORE anything is
    persisted: an unknown family, a run that is missing / not COMPLETED / of the wrong run_type /
    another tenant's, a run computed for a DIFFERENT portfolio than the report names (the RPT-2
    review's attribution fence — hence the REQUIRED ``portfolio_id`` here), and — the load-bearing
    one — a family whose run yields ZERO values. A report section rendering "no data" is
    indistinguishable from one whose family silently returned nothing, and a board-facing artifact
    must not be able to show the second while meaning the first.

    The component's ``target_entity_id`` is the SOURCE RUN, not the report: that is what
    ``_reresolve_content`` re-derives from, and pointing it at the report would make verification
    circular.
    """
    from irp_shared.report.service import build_report_snapshot

    pinned = build_report_snapshot(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=portfolio_id,
        as_of_date=as_of_valuation_date,
        family_runs=family_runs,
    )
    now = datetime.now(UTC)
    specs: list[tuple[str, str, Any, str, str]] = []
    for _family_key, content in pinned:
        captured = serialize_content(content)
        specs.append(
            (
                COMPONENT_KIND_GOVERNED_VALUE,
                "calculation_run",
                _RunTarget(str(content["source_run_id"])),
                captured,
                content_hash(captured),
            )
        )

    header_row = _persist_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=actor,
        specs=specs,
        label="",
        purpose=PURPOSE_REPORT_INPUT,
        as_of_valid_at=now,
        as_of_known_at=now,
        as_of_valuation_date=as_of_valuation_date,
        binding_predicate_version=REPORT_BINDING_PREDICATE,
    )
    record_snapshot_create(session, header=header_row, actor=actor)
    return header_row


@dataclass(frozen=True)
class _RunTarget:
    """The minimal shape ``_persist_snapshot`` needs from a pinned target: its id.

    A thin adapter rather than passing the ``CalculationRun`` itself — the run has already been
    resolved and validated by ``build_report_snapshot``, and re-passing the ORM object would invite
    a second, unvalidated read at the persistence tail.
    """

    id: str


def _resolve_assignment_row(session: Session, assignment_id: str, *, acting_tenant: str) -> Any:
    """The pinned assignment's PHYSICAL row by surrogate id, own-tenant only (proprietary
    symmetric). FR: the row's fields are immutable (a supersede is a NEW row), so this re-read is
    byte-stable — the drift door is the code-first closure, not this row."""
    from irp_shared.classification.models import ClassificationAssignment

    row = session.execute(
        select(ClassificationAssignment).where(
            ClassificationAssignment.id == str(assignment_id),
            ClassificationAssignment.tenant_id == canonical_tenant_id(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ClassificationNotVisible(
            f"classification_assignment {assignment_id} is not visible to {acting_tenant}"
        )
    return row


def _list_current_assignment_scheme_ids(
    session: Session,
    *,
    entity_ids: list[str],
    dimension_kind: str,
    acting_tenant: str,
) -> list[str]:
    """The DISTINCT live scheme ids these instruments carry in one dimension — NO scheme filter.

    This is OQ-CON-1-24 (i)'s discriminator input. It deliberately does NOT read the pinned set:
    the pinned set is filtered to the requested scheme, so a second version can never appear in it
    (the review's BLOCKING). Own-tenant only — assignments are proprietary, never hybrid."""
    from irp_shared.classification.models import ClassificationAssignment

    if not entity_ids:
        return []
    rows = session.execute(
        select(ClassificationAssignment.scheme_id)
        .where(
            ClassificationAssignment.tenant_id == canonical_tenant_id(acting_tenant),
            ClassificationAssignment.entity_type == "instrument",
            ClassificationAssignment.entity_id.in_(entity_ids),
            ClassificationAssignment.dimension_kind == dimension_kind,
            ClassificationAssignment.valid_to.is_(None),
            ClassificationAssignment.system_to.is_(None),
        )
        .distinct()
    ).scalars()
    return sorted({str(r) for r in rows})


def _list_current_assignments(
    session: Session,
    *,
    entity_ids: list[str],
    scheme_id: str,
    dimension_kind: str,
    acting_tenant: str,
) -> list[Any]:
    """Current-head INSTRUMENT assignments under ONE requested scheme+dimension, own-tenant only
    (assignments are PROPRIETARY symmetric — never hybrid; the REF-1 grain is the instrument)."""
    from irp_shared.classification.models import ClassificationAssignment

    if not entity_ids:
        return []
    return list(
        session.execute(
            select(ClassificationAssignment)
            .where(
                ClassificationAssignment.tenant_id == canonical_tenant_id(acting_tenant),
                ClassificationAssignment.entity_type == "instrument",
                ClassificationAssignment.entity_id.in_(entity_ids),
                ClassificationAssignment.scheme_id == str(scheme_id),
                ClassificationAssignment.dimension_kind == dimension_kind,
                ClassificationAssignment.valid_to.is_(None),
                ClassificationAssignment.system_to.is_(None),
            )
            .order_by(ClassificationAssignment.entity_id)
        ).scalars()
    )


#: Every binding predicate is stamped verbatim into ``dataset_snapshot.binding_predicate_version``
#: (``String(50)``); SQLite ignores the length, so an over-long constant would surface only as an
#: opaque PG ``StringDataRightTruncation`` on the build path (review). Enforce the ceiling at import
#: time so the failure is a loud, unit-tier import error at the site of the offending constant.
_BINDING_PREDICATES = (
    LIQUIDITY_BINDING_PREDICATE,
    REPORT_BINDING_PREDICATE,
    DEFAULT_BINDING_PREDICATE,
    SUBTREE_BINDING_PREDICATE,
    NODE_FX_BINDING_PREDICATE,
    FACTOR_EXPOSURE_BINDING_PREDICATE,
    FACTOR_EXPOSURE_PROXY_BINDING_PREDICATE,
    FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE,
    PROXY_WEIGHT_BINDING_PREDICATE,
    COVARIANCE_BINDING_PREDICATE,
    VAR_BINDING_PREDICATE,
    ACTIVE_RISK_BINDING_PREDICATE,
    VAR_HS_BINDING_PREDICATE,
    RETURN_BINDING_PREDICATE,
    BENCHMARK_RELATIVE_BINDING_PREDICATE,
    VAR_BACKTEST_BINDING_PREDICATE,
    SCENARIO_BINDING_PREDICATE,
    DESMOOTHING_BINDING_PREDICATE,
    VAR_TOTAL_BINDING_PREDICATE,
    RESIDUAL_SHRINKAGE_BINDING_PREDICATE,
    PRIVATE_FACTOR_RETURN_BINDING_PREDICATE,
    PRIVATE_COVARIANCE_BINDING_PREDICATE,
    VAR_UNIFIED_BINDING_PREDICATE,
    # SR-1 folded in the two entries this guard had been missing since CC-2 and RM-1. A conformance
    # guard that does not enumerate every member is not a guard — PACING (41 chars) and ROLLING_RISK
    # (28) both fit, so nothing was broken, but the varchar(50) ceiling was unchecked for two
    # shipped
    # predicates and would have stayed unchecked for the next one.
    PACING_BINDING_PREDICATE,
    ROLLING_RISK_BINDING_PREDICATE,
    SHARPE_BINDING_PREDICATE,
    CONCENTRATION_BINDING_PREDICATE,
)
assert all(len(p) <= 50 for p in _BINDING_PREDICATES), (
    "a *_BINDING_PREDICATE exceeds dataset_snapshot.binding_predicate_version varchar(50): "
    + repr([p for p in _BINDING_PREDICATES if len(p) > 50])
)
