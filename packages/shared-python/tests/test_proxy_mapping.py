"""SQLite-local unit/behavior tests for PA-0 proxy_mapping inputs (ENT-019, captured INPUTS).

The FIRST private-asset foundation (the differentiation-thesis destination). RLS + the
no-append-only close-out live in ``test_proxy_mapping_pg.py``; here we prove: the FR single-row
protocol (capture/supersede/correct/reconstruct on both axes; current-head uniqueness;
prior-content immutability); the MULTI-factor blend with NO sum-to-1 enforcement (a partial proxy);
the binder finiteness guard (NaN/±Inf) + mapping_method vocab + the required-field DQ gate; BOTH
cross-tenant-FK refusals (foreign instrument, foreign factor); audit (``MARKET.PROXY_MAPPING_*``;
per-op grain; no read audit); the MANUAL_PROXY ORIGIN lineage; entitlement parity
(``marketdata.*`` reuse — NO new codes); the captured-input scope fences (NO calculation_run /
model_version / snapshot / computed weight); and the migration head.

Fixture realism (TD-1): proxy weights are plausible factor loadings (0..1 fractions summing to a
partial proxy); the labeled boundary tests carry the deliberately out-of-band values.
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource, LineageEdge
from irp_shared.marketdata import (
    FactorActor,
    ProxyMapping,
    ProxyMappingActor,
    ProxyMappingNotVisible,
    ProxyMappingValueError,
    capture_factor,
    capture_proxy_mapping,
    correct_proxy_mapping,
    list_proxy_mappings,
    reconstruct_proxy_mapping_as_of,
    resolve_proxy_mapping,
    supersede_proxy_mapping,
)
from irp_shared.marketdata import proxy_mapping as pm_mod
from irp_shared.marketdata.proxy_mapping import NoCurrentProxyMapping
from irp_shared.models import Base
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VA = datetime(2026, 6, 1, tzinfo=UTC)
VA2 = datetime(2026, 6, 15, tzinfo=UTC)
KNOWN = datetime(2030, 1, 1, tzinfo=UTC)
ACTOR = ProxyMappingActor(actor_id="steward")


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _ccy(db: Session, *codes: str) -> None:
    for code in codes or ("USD",):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _instrument(db: Session, tenant: str, *, code: str = "PE-FUND-1") -> str:
    """A PRIVATE-asset instrument (ordinary instrument under a private asset_class convention)."""
    return create_instrument(
        db,
        tenant_id=tenant,
        code=f"{code}-{uuid.uuid4().hex[:6]}",
        name="Buyout Fund I",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id


def _factor(db: Session, tenant: str, *, code: str = "FX_USD") -> str:
    f = capture_factor(
        db,
        factor_code=f"{code}-{uuid.uuid4().hex[:6]}",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code="USD",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    db.flush()
    return f


def _book(db: Session, tenant: str) -> tuple[str, str, str]:
    """One private instrument + two public factors. Returns (instrument, factor_eq, factor_cr)."""
    _ccy(db, "USD")
    return _instrument(db, tenant), _factor(db, tenant, code="EQ"), _factor(db, tenant, code="CR")


# --------------------------------------------------------------------------- capture + blend


def test_capture_and_multi_factor_blend_no_sum_to_one(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, f_cr = _book(session, tenant)
    m1 = capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_cr,
        weight=Decimal("0.2"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    assert m1.mapping_method == "MANUAL" and m1.record_version == 1
    blend = list_proxy_mappings(session, private_instrument_id=inst, acting_tenant=tenant)
    assert len(blend) == 2
    total = sum(m.weight for m in blend)
    assert total == Decimal("0.900000000000")  # a PARTIAL proxy — NOT forced to sum to 1
    assert isinstance(blend[0], ProxyMapping)


def test_capture_resolves_by_id(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    m = capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.5"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    assert resolve_proxy_mapping(session, m.id, acting_tenant=tenant).weight == Decimal("0.5")
    with pytest.raises(ProxyMappingNotVisible):
        resolve_proxy_mapping(session, str(uuid.uuid4()), acting_tenant=tenant)


# --------------------------------------------------------------------------- FR bitemporal protocol


def test_supersede_correct_reconstruct(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    # Effective-dated supersede (valid time): a proxy REVISION.
    new = supersede_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.75"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    session.flush()
    assert new.record_version == 2 and new.weight == Decimal("0.75") and new.supersedes_id
    head = list_proxy_mappings(session, private_instrument_id=inst, acting_tenant=tenant)[0]
    assert head.weight == Decimal("0.750000000000")

    # As-known correction (system time): SAME valid window + a restatement_reason.
    corrected = correct_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.8"),
        restatement_reason="revised peer-group analysis",
        acting_tenant=tenant,
        actor=ACTOR,
    )
    session.flush()
    assert corrected.restatement_reason == "revised peer-group analysis"
    assert corrected.valid_from == new.valid_from  # correction preserves the valid window

    # Both-axes reconstruct: the ORIGINAL 0.7 is still visible AS-OF the early valid instant.
    old = reconstruct_proxy_mapping_as_of(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        valid_at=datetime(2026, 6, 5, tzinfo=UTC),
        known_at=KNOWN,
        acting_tenant=tenant,
    )
    assert old is not None and old.weight == Decimal("0.700000000000")


def test_current_head_uniqueness(session: Session) -> None:
    """Exactly ONE open version per (instrument, factor) on both axes — a second open capture for
    the same key trips the partial-unique index at flush."""
    from sqlalchemy.exc import IntegrityError

    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    with pytest.raises(IntegrityError):
        capture_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=f_eq,
            weight=Decimal("0.9"),
            acting_tenant=tenant,
            actor=ACTOR,
            valid_from=VA,
        )
        session.flush()
    session.rollback()


def test_prior_content_immutable_across_supersede(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    first = capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    first_id = first.id
    supersede_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.75"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    session.flush()
    prior = session.get(ProxyMapping, first_id)
    assert prior.weight == Decimal("0.700000000000")  # CONTENT never mutated
    assert prior.valid_to == VA2  # only the temporal axis closed


def test_supersede_backdated_effective_at_refused(session: Session) -> None:
    # MD-H1 window-coherence: effective_at at/before the head's valid_from (VA) is refused (→ 422).
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    with pytest.raises(ProxyMappingValueError):
        supersede_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=f_eq,
            weight=Decimal("0.75"),
            acting_tenant=tenant,
            actor=ACTOR,
            effective_at=VA,  # == valid_from → zero-width, refused (strictly-greater)
        )


def test_supersede_without_current_fails(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    with pytest.raises(NoCurrentProxyMapping):
        supersede_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=f_eq,
            weight=Decimal("0.5"),
            acting_tenant=tenant,
            actor=ACTOR,
            effective_at=VA2,
        )


def test_tenant_scope_isolation(session: Session) -> None:
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    inst1, f1, _ = _book(session, t1)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst1,
        factor_id=f1,
        weight=Decimal("0.5"),
        acting_tenant=t1,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    # SQLite has no RLS; the explicit tenant predicate on list still scopes.
    assert list_proxy_mappings(session, private_instrument_id=inst1, acting_tenant=t2) == []


# --------------------------------------------------------------------------- refusals


def test_finiteness_guard_rejects_naninf(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(ProxyMappingValueError):
            capture_proxy_mapping(
                session,
                private_instrument_id=inst,
                factor_id=f_eq,
                weight=bad,
                acting_tenant=tenant,
                actor=ACTOR,
                valid_from=VA,
            )


def test_unadmitted_factor_family_refused(session: Session) -> None:
    """The family gate stays fail-closed: a proxy onto an UNADMITTED family is refused at capture.
    FL-1 widened PA-0's CURRENCY-only gate to the LOADING_FACTOR_FAMILIES allow-list (STYLE is now
    admitted), so the refusal probe MOVES to ``OTHER`` — the catch-all that stays refused (the
    ES-1 probe-move pattern; unknown/OTHER never admitted)."""
    tenant = str(uuid.uuid4())
    inst, _, _ = _book(session, tenant)
    style = capture_factor(
        session,
        factor_code=f"MOMENTUM-{uuid.uuid4().hex[:6]}",
        factor_source="VENDOR_F",
        factor_family="OTHER",  # the catch-all — still refused after the FL-1 widening
        currency_code="USD",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    session.flush()
    with pytest.raises(ProxyMappingValueError):
        capture_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=style,
            weight=Decimal("0.5"),
            acting_tenant=tenant,
            actor=ACTOR,
            valid_from=VA,
        )
    assert list_proxy_mappings(session, private_instrument_id=inst, acting_tenant=tenant) == []


def test_bad_mapping_method_rejected(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    with pytest.raises(ProxyMappingValueError):
        capture_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=f_eq,
            weight=Decimal("0.5"),
            mapping_method="REGRESSION",  # reserved, not v1
            acting_tenant=tenant,
            actor=ACTOR,
            valid_from=VA,
        )


def test_foreign_instrument_and_factor_refused(session: Session) -> None:
    """BOTH FK targets are re-resolved tenant-filtered pre-write — a foreign/absent instrument or
    factor is refused (the P3-5 cross-tenant-FK guard), never a durable cross-tenant row."""
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    # RD-3 OD-B: _resolve_instrument_id now delegates to the shared reference/guards.py predicate;
    # the message normalizes to the guard's own wording ("instrument …", not "private instrument
    # …").
    with pytest.raises(ProxyMappingValueError, match=r"^instrument .* is not visible"):
        capture_proxy_mapping(
            session,
            private_instrument_id=str(uuid.uuid4()),  # foreign/absent instrument
            factor_id=f_eq,
            weight=Decimal("0.5"),
            acting_tenant=tenant,
            actor=ACTOR,
            valid_from=VA,
        )
    with pytest.raises(ProxyMappingValueError):
        capture_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=str(uuid.uuid4()),  # foreign/absent factor
            weight=Decimal("0.5"),
            acting_tenant=tenant,
            actor=ACTOR,
            valid_from=VA,
        )
    # Neither refusal left a durable row.
    assert list_proxy_mappings(session, private_instrument_id=inst, acting_tenant=tenant) == []


def test_correction_requires_reason(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    with pytest.raises(ProxyMappingValueError):
        correct_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=f_eq,
            weight=Decimal("0.8"),
            restatement_reason="",  # required
            acting_tenant=tenant,
            actor=ACTOR,
        )


# --------------------------------------------------------------------------- audit + lineage


def test_audit_market_events_and_grain(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    supersede_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.75"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    correct_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.8"),
        restatement_reason="revision",
        acting_tenant=tenant,
        actor=ACTOR,
    )
    session.flush()
    pm_events = [
        e.event_type
        for e in session.execute(select(AuditEvent)).scalars()
        if e.event_type.startswith("MARKET.PROXY_MAPPING")
    ]
    # capture=1 CREATE; supersede=2 (UPDATE close-out + CREATE); correct=2 (UPDATE + CORRECTION).
    assert pm_events.count("MARKET.PROXY_MAPPING_CREATE") == 2
    assert pm_events.count("MARKET.PROXY_MAPPING_UPDATE") == 2
    assert pm_events.count("MARKET.PROXY_MAPPING_CORRECTION") == 1
    # The CORRECTION event carries action="correct" (the sibling FR convention — review fold).
    correction = next(
        e
        for e in session.execute(select(AuditEvent)).scalars()
        if e.event_type == "MARKET.PROXY_MAPPING_CORRECTION"
    )
    assert correction.action == "correct"


def test_no_audit_on_read(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    before = session.execute(select(func.count()).select_from(AuditEvent)).scalar()
    list_proxy_mappings(session, private_instrument_id=inst, acting_tenant=tenant)
    reconstruct_proxy_mapping_as_of(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        valid_at=VA,
        known_at=KNOWN,
        acting_tenant=tenant,
    )
    after = session.execute(select(func.count()).select_from(AuditEvent)).scalar()
    assert before == after  # reads emit NO audit


def test_manual_proxy_origin_lineage(session: Session) -> None:
    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    m = capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    source_ids = {
        s.id
        for s in session.execute(
            select(DataSource).where(DataSource.code == "MANUAL_PROXY")
        ).scalars()
    }
    assert source_ids  # the MANUAL_PROXY source was minted
    edges = [
        e
        for e in session.execute(select(LineageEdge)).scalars()
        if e.target_entity_id == m.id and e.edge_kind == EDGE_KIND_ORIGIN
    ]
    assert len(edges) == 1 and edges[0].source_id in source_ids


# --------------------------------------------------------------------------- governance fences


def test_reuses_marketdata_entitlements() -> None:
    """PA-0 mints NO `proxy.*`/`proxy_mapping.*` permission — the ingest/read verbs are the reused
    `marketdata.ingest`/`marketdata.view` (OD-PA-0-E)."""
    from irp_shared.entitlement.bootstrap import PERMISSIONS

    codes = {c for c, _desc in PERMISSIONS}
    assert not any("proxy" in c for c in codes)
    # The steward holds both marketdata verbs (the factor/benchmark precedent).
    steward = set(ROLE_TEMPLATES["data_steward"])
    assert {"marketdata.view", "marketdata.ingest"} <= steward


def test_scope_fence_no_calc_or_model_imports() -> None:
    """proxy_mapping is a captured INPUT — it imports NO calc / model / snapshot symbol (NO
    calculation_run, NO model_version, NO snapshot pin; the factor_return fence)."""
    tree = ast.parse(pathlib.Path(pm_mod.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            assert "calc" not in parts, node.module
            assert "model" not in parts, node.module
            assert "snapshot" not in parts, node.module


def test_migration_head_is_proxy_mapping() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0051_breach_action"  # MG-2
    assert script.get_revision("0034_proxy_mapping").down_revision == "0033_var_backtest"


def test_required_field_dq_gate_runs(session: Session) -> None:
    """The DQ gate (required-field NOT_NULL) runs co-transactionally on capture — a DATA.VALIDATE
    result is recorded (the 'inputs present' governance leg; NO economic RANGE, OD-PA-0-D)."""
    from irp_shared.dq.models import DataQualityResult

    tenant = str(uuid.uuid4())
    inst, f_eq, _ = _book(session, tenant)
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=f_eq,
        weight=Decimal("0.7"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    results = list(session.execute(select(DataQualityResult)).scalars())
    assert any(r.passed for r in results)  # the NOT_NULL gate passed for a well-formed capture
