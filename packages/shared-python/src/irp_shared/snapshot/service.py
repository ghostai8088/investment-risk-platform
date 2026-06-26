"""``build_snapshot`` governed binder + ``verify_snapshot`` (P2-1, ENT-049/050 — AD-014).

``build_snapshot`` composes the already-shipped, tenant-predicated reads into an immutable snapshot:
it resolves the bound scope (``resolve_portfolio`` — cross-tenant/unknown fails closed BEFORE any
write), enumerates the open positions of the subtree (``reconstruct_subtree_holdings_as_of``) and
their marks at a fixed ``valuation_date`` (``attach_marks_as_of``), re-resolves each input by id
under the acting tenant (the per-component pin + cross-tenant safety), pins the physical version +
the canonical ``captured_content`` + ``content_hash``, computes the header ``manifest_hash``, roots
a ``data_snapshot`` lineage edge per component, runs the caller-side completeness DQ gate (fail-
closed), and emits ``SNAPSHOT.CREATE`` — all in the caller's single transaction (CTRL-032 rollback).

It **computes no derived number** (no ``quantity x mark``, no exposure) and **creates/​wires no
``calculation_run``** — imports NO ``calc`` symbol (readiness §10, never becomes wiring).

``verify_snapshot`` re-resolves each component by id (the explicit-tenant-predicate resolvers, not a
bare ``session.get``) at the FROZEN cutoffs, re-serializes, and compares ``content_hash`` — the
authoritative reproducibility check. FR components are byte-stable under later supersede/correction;
an EV ``portfolio`` amend (``record_version`` bump) is reported as drift.

One-way imports: ``snapshot -> {portfolio, position, valuation, holdings, lineage, dq, audit, db}``;
nothing imports ``snapshot``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.db.mixins import utcnow
from irp_shared.dq.models import SEVERITY_ERROR, DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL
from irp_shared.dq.service import register_dq_rule, run_quality_check
from irp_shared.holdings import (
    HoldingWithMark,
    attach_marks_as_of,
    reconstruct_subtree_holdings_as_of,
)
from irp_shared.holdings.service import HoldingRow
from irp_shared.lineage.service import record_internal_lineage
from irp_shared.portfolio import PortfolioNotVisible, resolve_portfolio
from irp_shared.position import PositionNotVisible, resolve_position
from irp_shared.snapshot.events import SnapshotActor, record_snapshot_create
from irp_shared.snapshot.models import (
    COMPONENT_KIND_PORTFOLIO,
    COMPONENT_KIND_POSITION,
    COMPONENT_KIND_VALUATION,
    SNAPSHOT_PURPOSES,
    DatasetSnapshot,
    DatasetSnapshotComponent,
)
from irp_shared.snapshot.serialize import (
    content_hash,
    manifest_hash,
    portfolio_content,
    position_content,
    serialize_content,
    valuation_content,
)
from irp_shared.valuation import ValuationNotVisible, resolve_valuation

#: The v1 binding/selection rule (versioned via the header ``binding_predicate_version``).
DEFAULT_BINDING_PREDICATE = "v1:subtree-open-positions"

#: The per-tenant completeness DataQualityRule (resolve-or-register, the ``ensure_manual_source``
#: pattern). A NOT_NULL rule over a derived dataset — no new evaluator, Protocol untouched (§16).
_COMPLETENESS_RULE_CODE = "snapshot.completeness"


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
    ``drifted_components`` lists the component ids whose live value/version differs (or is gone)."""

    ok: bool
    component_count: int
    drifted_components: list[str] = field(default_factory=list)


def _ensure_completeness_rule(
    session: Session, *, tenant_id: str, actor: SnapshotActor
) -> DataQualityRule:
    """Resolve-or-register the per-tenant snapshot-completeness NOT_NULL rule (governed/audited)."""
    rule = session.execute(
        select(DataQualityRule).where(
            DataQualityRule.tenant_id == str(tenant_id),
            DataQualityRule.code == _COMPLETENESS_RULE_CODE,
        )
    ).scalar_one_or_none()
    if rule is not None:
        return rule
    return register_dq_rule(
        session,
        tenant_id=str(tenant_id),
        code=_COMPLETENESS_RULE_CODE,
        name="Snapshot bound-set completeness",
        rule_type=RULE_TYPE_NOT_NULL,
        actor_id=actor.actor_id,
        params={"column": "present"},
        target_entity_type="dataset_snapshot",
        severity=SEVERITY_ERROR,
        actor_type=actor.actor_type,
    )


def _run_completeness_gate(
    session: Session,
    *,
    acting_tenant: str,
    actor: SnapshotActor,
    header: DatasetSnapshot,
    holdings: list[HoldingRow],
    enriched: list[HoldingWithMark],
) -> None:
    """Fail-closed completeness: every non-zero-quantity bound position MUST have a same-as-of mark.

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
        h
        for h in holdings
        if h.quantity != 0 and (h.portfolio_id, h.instrument_id) not in have_mark
    ]
    dataset: list[dict[str, Any]] = [{"present": None} for _ in gap] if gap else [{"present": True}]
    rule = _ensure_completeness_rule(session, tenant_id=acting_tenant, actor=actor)
    run_quality_check(
        session,
        rule=rule,
        dataset=dataset,
        actor_id=actor.actor_id,
        target_entity_type="dataset_snapshot",
        target_entity_id=header.id,
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
) -> DatasetSnapshot:
    """Build one immutable ``dataset_snapshot`` over the bound portfolio subtree (governed). See the
    module docstring. ``as_of_known_at`` defaults to now and is FROZEN onto the header;
    ``as_of_valuation_date`` defaults to ``date(as_of_valid_at)``."""
    if purpose not in SNAPSHOT_PURPOSES:
        raise SnapshotPurposeError(purpose)
    known = as_of_known_at if as_of_known_at is not None else utcnow()
    val_date = as_of_valuation_date if as_of_valuation_date is not None else as_of_valid_at.date()

    # 1. Resolve the bound scope FIRST — a foreign/unknown portfolio raises PortfolioNotVisible
    #    (fail closed on SQLite AND PG) BEFORE any enumeration or write.
    resolve_portfolio(session, str(portfolio_id), acting_tenant=acting_tenant)

    # 2. Enumerate the open positions of the subtree + their marks at the fixed valuation_date
    #    (the shipped, tenant-bounded, cycle-safe, arithmetic-free composers).
    holdings = reconstruct_subtree_holdings_as_of(
        session,
        acting_tenant=acting_tenant,
        portfolio_id=str(portfolio_id),
        valid_at=as_of_valid_at,
        known_at=known,
    )
    enriched = attach_marks_as_of(
        session,
        acting_tenant=acting_tenant,
        holdings=holdings,
        valuation_date=val_date,
        valid_at=as_of_valid_at,
        known_at=known,
    )

    # 3. Re-resolve each input by id under the acting tenant (the per-component pin + cross-tenant
    #    safety) and capture its canonical content. component spec = (kind, target_type, row, hash).
    specs: list[tuple[str, str, Any, str, str]] = []
    seen_portfolios: set[str] = set()
    for e in enriched:
        h = e.holding
        pos = resolve_position(session, h.position_id, acting_tenant=acting_tenant)
        _append_spec(specs, COMPONENT_KIND_POSITION, "position", pos, position_content(pos))
        if h.portfolio_id not in seen_portfolios:
            seen_portfolios.add(h.portfolio_id)
            pf = resolve_portfolio(session, h.portfolio_id, acting_tenant=acting_tenant)
            _append_spec(specs, COMPONENT_KIND_PORTFOLIO, "portfolio", pf, portfolio_content(pf))
        if e.mark is not None:
            val = resolve_valuation(session, e.mark.valuation_id, acting_tenant=acting_tenant)
            _append_spec(specs, COMPONENT_KIND_VALUATION, "valuation", val, valuation_content(val))

    # 4. No empty / foreign-scope snapshot (fail closed before any write).
    if not specs:
        raise EmptySnapshotError(str(portfolio_id))

    # 5. Header (with the manifest hash over the component hashes + the cutoffs).
    m_hash = manifest_hash(
        tenant_id=acting_tenant,
        as_of_valid_at=as_of_valid_at,
        as_of_known_at=known,
        as_of_valuation_date=val_date,
        binding_predicate_version=binding_predicate_version,
        component_count=len(specs),
        component_hashes=[(kind, row.id, c_hash) for (kind, _t, row, _cc, c_hash) in specs],
    )
    header = DatasetSnapshot(
        tenant_id=str(acting_tenant),
        label=label,
        purpose=purpose,
        as_of_valid_at=as_of_valid_at,
        as_of_known_at=known,
        as_of_valuation_date=val_date,
        binding_predicate_version=binding_predicate_version,
        component_count=len(specs),
        manifest_hash=m_hash,
        created_by=actor.actor_id,
    )
    session.add(header)
    session.flush()

    # 6. Components (server-stamped tenant == header tenant) + one lineage edge each.
    for kind, ttype, row, captured, c_hash in specs:
        comp = DatasetSnapshotComponent(
            tenant_id=str(acting_tenant),
            snapshot_id=header.id,
            component_kind=kind,
            target_entity_type=ttype,
            target_entity_id=row.id,
            pinned_valid_from=getattr(row, "valid_from", None),
            pinned_system_from=getattr(row, "system_from", None),  # NULL for EV portfolio
            pinned_record_version=getattr(row, "record_version", None),
            captured_content=captured,
            content_hash=c_hash,
        )
        session.add(comp)
    session.flush()
    for _kind, ttype, row, _captured, _ch in specs:
        record_internal_lineage(
            session, snapshot_id=header.id, target_entity_type=ttype, target_entity_id=row.id
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


def _append_spec(
    specs: list[tuple[str, str, Any, str, str]],
    kind: str,
    target_type: str,
    row: Any,
    content: dict[str, Any],
) -> None:
    captured = serialize_content(content)
    specs.append((kind, target_type, row, captured, content_hash(captured)))


def resolve_snapshot(session: Session, snapshot_id: str, *, acting_tenant: str) -> DatasetSnapshot:
    """Resolve a ``dataset_snapshot`` header by id with an EXPLICIT tenant predicate (fail-closed on
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


def _reresolve_content(
    session: Session, comp: DatasetSnapshotComponent, *, acting_tenant: str
) -> dict[str, Any]:
    """Re-resolve a component's target by id (explicit-tenant-predicate resolver, never session.get)
    and return its current canonical content dict. Raises the resolver's ``*NotVisible`` if gone."""
    if comp.component_kind == COMPONENT_KIND_POSITION:
        return position_content(
            resolve_position(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    if comp.component_kind == COMPONENT_KIND_VALUATION:
        return valuation_content(
            resolve_valuation(session, comp.target_entity_id, acting_tenant=acting_tenant)
        )
    return portfolio_content(
        resolve_portfolio(session, comp.target_entity_id, acting_tenant=acting_tenant)
    )


def verify_snapshot(session: Session, *, snapshot_id: str, acting_tenant: str) -> VerifyResult:
    """Re-resolve each component under the acting tenant, re-serialize, and compare ``content_hash``
    (the authoritative reproducibility check). Drift = a changed value/version (or a gone target).
    Emits NO audit event (read/verify is no-emit, OD-023). Raises :class:`SnapshotNotFound` if the
    header is not visible."""
    resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
    comps = list_components(session, snapshot_id=snapshot_id, acting_tenant=acting_tenant)
    drifted: list[str] = []
    for comp in comps:
        try:
            live = _reresolve_content(session, comp, acting_tenant=acting_tenant)
        except (PositionNotVisible, ValuationNotVisible, PortfolioNotVisible):
            drifted.append(comp.id)
            continue
        if content_hash(serialize_content(live)) != comp.content_hash:
            drifted.append(comp.id)
    return VerifyResult(ok=not drifted, component_count=len(comps), drifted_components=drifted)
