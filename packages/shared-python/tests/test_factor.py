"""SQLite-local unit/behavior tests for P3-2 factor-return inputs (ENT-025, captured INPUTS).

RLS + the no-append-only close-out live in ``test_factor_pg.py``; here we prove: the ``factor`` EV
definition (capture/update/record_version); the ``factor_return`` FR single-row protocol
(capture/supersede/correct/reconstruct on both axes; return_date carried forward; current-head
uniqueness; prior-content immutability); the binder finiteness guard (NaN/±Inf rejected pre-write) +
the ``> -1`` economic-sanity DQ gate; audit (``REFERENCE.*`` for the definition +
``MARKET.FACTOR_RETURN_*`` for the series; per-op grain; no read audit); VENDOR_FACTOR ORIGIN
lineage; entitlement parity (``marketdata.*`` reuse); the captured-input scope fences (NO
calculation_run /
model_version / computed returns / price-derived); and the migration head.
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, DataSource, LineageEdge
from irp_shared.marketdata import (
    Factor,
    FactorActor,
    FactorNotVisible,
    FactorReturn,
    FactorValueError,
    NoCurrentFactorReturn,
    capture_factor,
    capture_factor_return,
    correct_factor_return,
    list_factor_returns,
    list_factors,
    reconstruct_factor_return_as_of,
    resolve_factor,
    supersede_factor_return,
    update_factor,
)
from irp_shared.marketdata import factor as factor_mod
from irp_shared.models import Base
from irp_shared.reference.models import Currency

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VA = datetime(2026, 6, 1, tzinfo=UTC)
VA2 = datetime(2026, 6, 15, tzinfo=UTC)
KNOWN = datetime(2030, 1, 1, tzinfo=UTC)
RD = date(2026, 5, 29)
ACTOR = FactorActor(actor_id="steward")


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
    for code in codes:
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _factor(db: Session, tenant: str, *, code: str = "MOMENTUM", family: str = "STYLE") -> Factor:
    f = capture_factor(
        db,
        factor_code=code,
        factor_source="MSCI_BARRA",
        factor_family=family,
        currency_code="USD",
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    db.flush()
    return f


# ---------- factor definition (EV) ----------


def test_capture_factor_ev(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    assert f.factor_code == "MOMENTUM" and f.factor_family == "STYLE" and f.frequency == "DAILY"
    assert f.record_version == 1


def test_update_factor_bumps_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    update_factor(session, f, acting_tenant=tenant, actor=ACTOR, description="Barra momentum")
    assert f.record_version == 2 and f.description == "Barra momentum"


def test_update_factor_noop_no_version_bump(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    update_factor(session, f, acting_tenant=tenant, actor=ACTOR)  # no changes
    assert f.record_version == 1


def test_factor_bad_family_rejected(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    with pytest.raises(FactorValueError):
        capture_factor(
            session,
            factor_code="X",
            factor_source="V",
            factor_family="NOT_A_FAMILY",
            acting_tenant=tenant,
            actor=ACTOR,
        )


def test_factor_code_source_uniqueness(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    _factor(session, tenant)
    with pytest.raises(Exception):  # noqa: B017 - IntegrityError on the EV identity unique
        _factor(session, tenant)
        session.flush()


def test_resolve_factor_cross_tenant_fails_closed(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, other)
    with pytest.raises(FactorNotVisible):
        resolve_factor(session, f.id, acting_tenant=tenant)


# ---------- factor_return (FR single-row) ----------


def test_capture_return(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    r = capture_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.0123"),
        acting_tenant=tenant,
        actor=ACTOR,
    )
    assert r.return_value == Decimal("0.0123") and r.return_type == "SIMPLE"
    assert r.record_version == 1 and r.factor_id == f.id


def test_supersede_and_correct_and_reconstruct(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    r1 = capture_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.0123"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,  # explicit early valid_from so the VA2 supersede is window-coherent
    )
    session.flush()
    # supersede (valid-time): a NEW valid version; return_date carried forward.
    r2 = supersede_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.0130"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    session.flush()
    assert r2.record_version == 2 and r2.supersedes_id == r1.id and r2.return_date == RD
    # correct (system-time): as-known restatement; prior content NEVER mutated.
    r3 = correct_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.0125"),
        restatement_reason="vendor restatement",
        acting_tenant=tenant,
        actor=ACTOR,
    )
    session.flush()
    assert r3.record_version == 3 and r3.restatement_reason == "vendor restatement"
    assert r2.return_value == Decimal("0.0130")  # prior content immutable

    # reconstruct: current head (both axes open) is r3.
    cur = reconstruct_factor_return_as_of(
        session, acting_tenant=tenant, factor_id=f.id, return_date=RD, valid_at=VA2, known_at=KNOWN
    )
    assert cur is not None and cur.record_version == 3


def test_current_head_uniqueness(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    capture_factor_return(
        session, f, return_date=RD, return_value=Decimal("0.01"), acting_tenant=tenant, actor=ACTOR
    )
    session.flush()
    # a second capture for the SAME (factor, return_date, return_type) violates current-head unique.
    with pytest.raises(Exception):  # noqa: B017
        capture_factor_return(
            session,
            f,
            return_date=RD,
            return_value=Decimal("0.02"),
            acting_tenant=tenant,
            actor=ACTOR,
        )
        session.flush()


def test_list_binders_current_head_and_tenant_scope(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    _factor(session, tenant, code="VALUE")
    _factor(session, other, code="MOMENTUM")  # another tenant — must NOT leak
    capture_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.01"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,  # explicit early valid_from so the VA2 supersede is window-coherent
    )
    session.flush()
    # supersede -> the OLD return version is closed; the list returns only the current head.
    supersede_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.02"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    session.flush()
    factors = list_factors(session, acting_tenant=tenant)
    assert {x.factor_code for x in factors} == {"MOMENTUM", "VALUE"}  # tenant-scoped, no leak
    returns = list_factor_returns(session, acting_tenant=tenant, factor_id=f.id)
    assert len(returns) == 1 and returns[0].return_value == Decimal("0.02")  # current head only


def test_supersede_without_current_fails(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    with pytest.raises(NoCurrentFactorReturn):
        supersede_factor_return(
            session,
            f,
            return_date=RD,
            return_value=Decimal("0.01"),
            acting_tenant=tenant,
            actor=ACTOR,
            effective_at=VA2,
        )


def test_supersede_backdated_effective_at_refused(session: Session) -> None:
    # MD-H1 window-coherence: effective_at at/before the head's valid_from (VA) is refused (→ 422).
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    capture_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.01"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
    )
    session.flush()
    with pytest.raises(FactorValueError):
        supersede_factor_return(
            session,
            f,
            return_date=RD,
            return_value=Decimal("0.02"),
            acting_tenant=tenant,
            actor=ACTOR,
            effective_at=VA,  # == valid_from → zero-width, refused (strictly-greater)
        )


def test_reproducible_by_capture_under_correction(session: Session) -> None:
    # A correction after an as-of-known read does not change the earlier as-known view.
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    r1 = capture_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.0123"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
        now=VA,
    )
    session.flush()
    known_before = datetime(2026, 6, 10, tzinfo=UTC)
    correct_factor_return(
        session,
        f,
        return_date=RD,
        # a realistic restated return, distinct from the original 0.0123
        return_value=Decimal("0.0456"),
        restatement_reason="restate",
        acting_tenant=tenant,
        actor=ACTOR,
        now=datetime(2026, 6, 20, tzinfo=UTC),
    )
    session.flush()
    # as-known-at a time BEFORE the correction -> the original value.
    as_known = reconstruct_factor_return_as_of(
        session,
        acting_tenant=tenant,
        factor_id=f.id,
        return_date=RD,
        valid_at=VA,
        known_at=known_before,
    )
    assert as_known is not None and as_known.return_value == Decimal("0.0123") == r1.return_value


# ---------- DQ ----------


def test_finiteness_guard_rejects_naninf(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    for bad in (Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN")):
        with pytest.raises(FactorValueError):
            capture_factor_return(
                session, f, return_date=RD, return_value=bad, acting_tenant=tenant, actor=ACTOR
            )
    # zero factor_return rows written (all rejected pre-write).
    assert _count_returns(session, tenant) == 0


def test_dq_rejects_return_below_minus_one(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    with pytest.raises(DataQualityError):
        capture_factor_return(
            session,
            f,
            return_date=RD,
            return_value=Decimal("-1.5"),
            acting_tenant=tenant,
            actor=ACTOR,
        )
    session.rollback()
    assert _count_returns(session, tenant) == 0


def test_bad_return_type_rejected(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    with pytest.raises(FactorValueError):
        capture_factor_return(
            session,
            f,
            return_date=RD,
            return_value=Decimal("0.01"),
            return_type="LOG",  # reserved, not minted
            acting_tenant=tenant,
            actor=ACTOR,
        )


# ---------- audit ----------


def test_audit_reference_and_market_events(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    capture_factor_return(
        session, f, return_date=RD, return_value=Decimal("0.01"), acting_tenant=tenant, actor=ACTOR
    )
    session.flush()
    types = [e.event_type for e in session.execute(select(AuditEvent)).scalars()]
    assert types.count("REFERENCE.CREATE") == 1  # the factor definition
    assert types.count("MARKET.FACTOR_RETURN_CREATE") == 1  # the captured return
    # NO RISK.* / no calculation_run audit for a captured input.
    assert not any(t.startswith("RISK.") for t in types)
    assert not any(t.startswith("CALC.") for t in types)


def test_supersede_correct_audit_grain(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    capture_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.01"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,  # explicit early valid_from so the VA2 supersede is window-coherent
    )
    supersede_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.02"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    correct_factor_return(
        session,
        f,
        return_date=RD,
        return_value=Decimal("0.03"),
        restatement_reason="r",
        acting_tenant=tenant,
        actor=ACTOR,
    )
    session.flush()
    types = [e.event_type for e in session.execute(select(AuditEvent)).scalars()]
    assert types.count("MARKET.FACTOR_RETURN_CREATE") == 2  # capture + supersede-insert
    assert types.count("MARKET.FACTOR_RETURN_UPDATE") == 2  # supersede close + correct close
    assert types.count("MARKET.FACTOR_RETURN_CORRECTION") == 1


# ---------- lineage ----------


def test_vendor_factor_origin_lineage(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    f = _factor(session, tenant)
    capture_factor_return(
        session, f, return_date=RD, return_value=Decimal("0.01"), acting_tenant=tenant, actor=ACTOR
    )
    session.flush()
    src = session.execute(
        select(DataSource).where(DataSource.code == "VENDOR_FACTOR", DataSource.tenant_id == tenant)
    ).scalar_one()
    origin = [
        e
        for e in session.execute(select(LineageEdge)).scalars()
        if e.edge_kind == EDGE_KIND_ORIGIN and e.source_id == src.id
    ]
    # one ORIGIN edge for the factor definition + one for the captured return version.
    kinds = {e.target_entity_type for e in origin}
    assert kinds == {"factor", "factor_return"}


# ---------- entitlement parity (marketdata.* reuse) ----------


def test_factor_reuses_marketdata_entitlements() -> None:
    # No new factor.* permission — captured factor data reuses marketdata.view/.ingest.
    all_codes = {c for codes in ROLE_TEMPLATES.values() for c in codes}
    assert not any(c.startswith("factor.") for c in all_codes), "no factor.* permission minted"
    view = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.view" in codes}
    ingest = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.ingest" in codes}
    assert {"risk_analyst_1l", "risk_manager_2l", "data_steward", "platform_admin"} <= view
    assert ingest == {"data_steward", "platform_admin"}  # maker/admin only
    assert "auditor_3l" not in view  # captured proprietary-input SoD


# ---------- scope fences (load-bearing) ----------

_FACTOR_SRC = pathlib.Path(factor_mod.__file__).read_text(encoding="utf-8")


def test_scope_fence_no_risk_or_compute_imports() -> None:
    tree = ast.parse(_FACTOR_SRC)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    forbidden = ("calc", "snapshot", "exposure", "risk", "factor_exposure", "covariance")
    for mod in imported:
        parts = set(mod.split("."))
        assert not (parts & set(forbidden)), f"forbidden import {mod}"


def test_scope_fence_no_return_arithmetic_or_analytics_idents() -> None:
    tree = ast.parse(_FACTOR_SRC)
    # A captured input performs NO return arithmetic (no Mult/Div on returns) and references no
    # analytics/compute identifier.
    assert not any(isinstance(n, ast.Mult | ast.Div) for n in ast.walk(tree)), "no arithmetic"
    idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    forbidden = {
        "calculation_run",
        "model_version",
        "factor_exposure",
        "covariance",
        "value_at_risk",
        "expected_shortfall",
        "compute_return",
        "price_point",
        "reconstruct_price_as_of",
    }
    assert not (idents & forbidden), idents & forbidden


# ---------- migration head ----------


def test_migration_head_is_factor_return() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0045_pacing_projection"  # CC-2
    assert script.get_revision("0023_factor_return").down_revision == "0022_sensitivity"


# ---------- helpers ----------


def _count_returns(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count()).select_from(FactorReturn).where(FactorReturn.tenant_id == tenant)
    ).scalar_one()
