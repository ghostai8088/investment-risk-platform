"""SQLite-local unit/behavior tests for P2-4 price_point (captured price market data).

RLS is a no-op on SQLite (the FORCE-RLS isolation + symmetric-policy proofs live in
``test_price_point_pg.py``); here we prove: the FR protocol (capture / supersede / correct /
both-axes ``reconstruct_price_as_of`` / current-head uniqueness / prior-content immutability /
price_date carried forward); ``price_source`` in the key (multi-vendor coexistence); the
``price_type`` controlled vocab + RAW-only policy (no adjustment columns); the governed DQ gate
(required-field + strictly-positive RANGE, fail-closed); ``MARKET.PRICE_*`` audit grain (no emit on
read); VENDOR-source ORIGIN lineage per physical version + fail-closed rollback; the cross-tenant
instrument fail-closed + hybrid-aware currency resolution; entitlement parity; and the load-bearing
scope fences (captured-not-computed; no COMPONENT_KIND_PRICE; price_point NOT append-only).
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, LineageEdge
from irp_shared.marketdata import (
    PRICE_TYPES,
    NoCurrentPrice,
    PriceActor,
    PricePoint,
    PriceValueError,
    capture_price,
    correct_price,
    reconstruct_price_as_of,
    supersede_price,
)
from irp_shared.marketdata import price as price_mod
from irp_shared.models import Base
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.reference.models import Currency, Instrument
from irp_shared.reference.service import CurrencyNotVisible

VA = datetime(2026, 6, 1, tzinfo=UTC)
KA = datetime(2030, 1, 1, tzinfo=UTC)  # fixed future known cutoff (>= wall-clock system_from)
PD = date(2026, 6, 1)
ACTOR = PriceActor(actor_id="steward")


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


def _seed_currencies(db: Session, *codes: str) -> None:
    for code in codes or ("USD", "EUR", "JPY"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=VA))
    db.flush()


def _seed_instrument(db: Session, tenant: str, code: str = "AAPL") -> str:
    inst = Instrument(tenant_id=tenant, code=code, name=code, asset_class="EQUITY", valid_from=VA)
    db.add(inst)
    db.flush()
    return inst.id


def _capture(
    db: Session,
    tenant: str,
    instrument_id: str,
    price: str = "150.25",
    source: str = "BLOOMBERG",
    **kw,  # noqa: ANN003
):  # noqa: ANN202
    return capture_price(
        db,
        instrument_id=instrument_id,
        price_date=PD,
        price=Decimal(price),
        currency_code="USD",
        price_source=source,
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
        **kw,
    )


# ---------- FR protocol ----------


def test_capture_and_reconstruct_both_axes(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    row = _capture(session, t, iid, "150.25")
    session.commit()
    got = reconstruct_price_as_of(
        session,
        acting_tenant=t,
        instrument_id=iid,
        price_date=PD,
        price_type="CLOSE",
        currency_code="USD",
        price_source="BLOOMBERG",
        valid_at=VA,
        known_at=KA,
    )
    assert got is not None and got.id == row.id and got.price == Decimal("150.25")
    assert got.currency_code == "USD" and got.record_version == 1
    # known_at BEFORE system_from -> not yet known -> None (system axis honored)
    assert (
        reconstruct_price_as_of(
            session,
            acting_tenant=t,
            instrument_id=iid,
            price_date=PD,
            price_type="CLOSE",
            currency_code="USD",
            price_source="BLOOMBERG",
            valid_at=VA,
            known_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        is None
    )


def test_current_head_uniqueness(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    _capture(session, t, iid, "150.25")
    session.flush()
    with pytest.raises(
        IntegrityError
    ):  # a second open head for the SAME key violates partial-unique
        _capture(session, t, iid, "150.30")
        session.flush()


def test_price_source_in_key_permits_multi_vendor(session: Session) -> None:
    # price_source IS a key component (the deliberate departure from fx_rate's inert rate_source):
    # two vendors quoting the SAME instrument/date/type/currency coexist as two open heads.
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    _capture(session, t, iid, "150.25", source="BLOOMBERG")
    _capture(session, t, iid, "150.30", source="REUTERS")
    session.commit()
    open_sources = {
        r.price_source
        for r in session.execute(select(PricePoint).where(PricePoint.valid_to.is_(None)))
        .scalars()
        .all()
    }
    assert open_sources == {"BLOOMBERG", "REUTERS"}


def test_supersede_closes_valid_to_and_carries_forward(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    head = _capture(session, t, iid, "150.25")
    session.commit()
    eff = datetime(2026, 6, 2, tzinfo=UTC)
    new = supersede_price(
        session,
        instrument_id=iid,
        price_date=PD,
        price_type="CLOSE",
        currency_code="USD",
        price_source="BLOOMBERG",
        acting_tenant=t,
        actor=ACTOR,
        effective_at=eff,
        price=Decimal("151.00"),
    )
    session.commit()
    assert session.get(PricePoint, head.id).valid_to == eff  # prior closed
    assert new.price == Decimal("151.00") and new.price_source == "BLOOMBERG"  # key carried
    assert new.price_date == PD and new.record_version == 2  # price_date carried verbatim


def test_supersede_backdated_effective_at_refused(session: Session) -> None:
    # MD-H1 window-coherence: effective_at at/before the head's valid_from (VA) is refused (→ 422).
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    _capture(session, t, iid, "150.25")  # valid_from=VA
    session.commit()
    with pytest.raises(PriceValueError):
        supersede_price(
            session,
            instrument_id=iid,
            price_date=PD,
            price_type="CLOSE",
            currency_code="USD",
            price_source="BLOOMBERG",
            acting_tenant=t,
            actor=ACTOR,
            effective_at=VA,  # == valid_from → zero-width, refused (strictly-greater)
            price=Decimal("151.00"),
        )


def test_correct_closes_system_to_content_immutable(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    head = _capture(session, t, iid, "150.25")
    session.commit()
    orig_price = head.price
    corrected = correct_price(
        session,
        head,
        restatement_reason="vendor fix",
        acting_tenant=t,
        actor=ACTOR,
        price=Decimal("150.2600"),
    )
    session.commit()
    prior = session.get(PricePoint, head.id)
    assert prior.system_to is not None and prior.price == orig_price  # prior content immutable
    assert corrected.price == Decimal("150.2600") and corrected.restatement_reason == "vendor fix"
    assert corrected.price_date == PD and corrected.supersedes_id == head.id


# ---------- DQ ----------


def test_dq_rejects_non_positive_price(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    session.commit()  # persist vocab + instrument so the per-iteration rollback can't discard them
    for bad in ("0", "-1.5"):
        with pytest.raises(DataQualityError):
            _capture(session, t, iid, bad)
        session.rollback()
    assert session.execute(select(func.count()).select_from(PricePoint)).scalar_one() == 0


def test_value_checks_reject_bad_price_type(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    with pytest.raises(PriceValueError):  # BID not in v1 vocab (CLOSE/MID/NAV)
        _capture(session, t, iid, "150.25", price_type="BID")


def test_price_type_vocab_close_mid_nav(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    for i, ptype in enumerate(PRICE_TYPES):  # CLOSE / MID / NAV all accepted, distinct open heads
        capture_price(
            session,
            instrument_id=iid,
            price_date=PD,
            price=Decimal(f"{100 + i}"),
            currency_code="USD",
            price_source="BLOOMBERG",
            acting_tenant=t,
            actor=ACTOR,
            price_type=ptype,
            valid_from=VA,
        )
    session.commit()
    assert session.execute(select(func.count()).select_from(PricePoint)).scalar_one() == 3


# ---------- audit + lineage ----------


def test_audit_grain_and_no_emit_on_read(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    _capture(session, t, iid, "150.25")
    session.commit()

    def _count(ev: str) -> int:
        return session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == ev)
        ).scalar_one()

    assert _count("MARKET.PRICE_CREATE") == 1
    head = reconstruct_price_as_of(
        session,
        acting_tenant=t,
        instrument_id=iid,
        price_date=PD,
        price_type="CLOSE",
        currency_code="USD",
        price_source="BLOOMBERG",
        valid_at=VA,
        known_at=KA,
    )
    correct_price(
        session, head, restatement_reason="x", acting_tenant=t, actor=ACTOR, price=Decimal("150.30")
    )
    session.commit()
    assert _count("MARKET.PRICE_CREATE") == 1 and _count("MARKET.PRICE_UPDATE") == 1
    assert _count("MARKET.PRICE_CORRECTION") == 1  # correct = UPDATE close-out + CORRECTION
    # an as-of READ emits NOTHING
    n_before = session.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    reconstruct_price_as_of(
        session,
        acting_tenant=t,
        instrument_id=iid,
        price_date=PD,
        price_type="CLOSE",
        currency_code="USD",
        price_source="BLOOMBERG",
        valid_at=VA,
    )
    assert session.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == n_before


def test_fail_closed_rollback_on_lineage_or_audit_failure(session: Session, monkeypatch) -> None:  # noqa: ANN001
    # CTRL-032: if record_lineage OR record_event raises mid-write, the whole governed unit rolls
    # back — no price_point row, no ORIGIN lineage edge, no MARKET.PRICE_CREATE event.
    orig_lin, orig_evt = price_mod.record_lineage, price_mod.record_event
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    session.commit()  # currencies + instrument persist across the per-arm rollbacks

    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("provenance rail down")

    for target in ("record_lineage", "record_event"):
        monkeypatch.setattr(price_mod, "record_lineage", orig_lin)
        monkeypatch.setattr(price_mod, "record_event", orig_evt)
        monkeypatch.setattr(price_mod, target, _boom)
        with pytest.raises(RuntimeError):
            _capture(session, t, iid, "150.25")
        session.rollback()
        assert session.execute(select(func.count()).select_from(PricePoint)).scalar_one() == 0
        assert (
            session.execute(
                select(func.count())
                .select_from(LineageEdge)
                .where(LineageEdge.target_entity_type == "price_point")
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "MARKET.PRICE_CREATE")
            ).scalar_one()
            == 0
        )


def test_one_vendor_origin_edge_per_physical_version(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    head = _capture(session, t, iid, "150.25")
    session.commit()
    new = supersede_price(
        session,
        instrument_id=iid,
        price_date=PD,
        price_type="CLOSE",
        currency_code="USD",
        price_source="BLOOMBERG",
        acting_tenant=t,
        actor=ACTOR,
        effective_at=datetime(2026, 6, 2, tzinfo=UTC),
        price=Decimal("151.00"),
    )
    session.commit()
    edges = (
        session.execute(select(LineageEdge).where(LineageEdge.target_entity_type == "price_point"))
        .scalars()
        .all()
    )
    targets = {e.target_entity_id for e in edges}
    assert targets == {
        head.id,
        new.id,
    }  # one ORIGIN edge per physical version; close-out roots none
    assert all(e.edge_kind == EDGE_KIND_ORIGIN for e in edges)


# ---------- instrument / currency resolution ----------


def test_capture_rejects_cross_tenant_instrument(session: Session) -> None:
    t, other = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_currencies(session)
    foreign_iid = _seed_instrument(session, other)  # belongs to a DIFFERENT tenant
    with pytest.raises(InstrumentNotVisible):
        _capture(session, t, foreign_iid, "150.25")


def test_capture_rejects_unknown_currency(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session, "USD")
    iid = _seed_instrument(session, t)
    with pytest.raises(CurrencyNotVisible):
        capture_price(
            session,
            instrument_id=iid,
            price_date=PD,
            price=Decimal("1"),
            currency_code="ZZZ",  # not seeded
            price_source="BLOOMBERG",
            acting_tenant=t,
            actor=ACTOR,
            valid_from=VA,
        )


def test_supersede_with_no_open_head_raises(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    iid = _seed_instrument(session, t)
    with pytest.raises(NoCurrentPrice):
        supersede_price(
            session,
            instrument_id=iid,
            price_date=PD,
            price_type="CLOSE",
            currency_code="USD",
            price_source="NONE",
            acting_tenant=t,
            actor=ACTOR,
            effective_at=VA,
        )


# ---------- entitlement parity ----------


def test_marketdata_permissions_grants_as_ratified() -> None:
    # price REUSES marketdata.view/.ingest — NO new permission; the ratified grants are unchanged.
    view = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.view" in codes}
    ingest = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.ingest" in codes}
    assert view == {"data_steward", "risk_analyst_1l", "risk_manager_2l", "platform_admin"}
    assert ingest == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in view and "auditor_3l" not in ingest


# ---------- scope fences ----------

_MD_SRC = pathlib.Path(price_mod.__file__).parent


def test_price_point_is_fr_not_append_only() -> None:
    # price_point IS in the metadata aggregator and is FR — NOT append-only: migration 0019 declares
    # NO APPEND_ONLY_TABLES / irp_prevent_mutation trigger (only symmetric RLS), and no other
    # migration ever lists price_point as append-only (close-out UPDATEs allowed).
    import pathlib as _pl

    from irp_shared.db.mixins import FullReproducibleMixin

    assert "price_point" in Base.metadata.tables
    assert issubclass(PricePoint, FullReproducibleMixin)

    root = _pl.Path(price_mod.__file__)
    while not (root / "alembic.ini").exists():
        root = root.parent
    versions = root / "migrations" / "versions"
    src_0019 = (versions / "0019_price_point.py").read_text()
    assert "CREATE TRIGGER" not in src_0019  # an FR table has no append-only mutation trigger
    for mig in versions.glob("*.py"):
        for line in mig.read_text().splitlines():
            if line.strip().startswith("APPEND_ONLY_TABLES ="):  # the assignment statement only
                assert "price_point" not in line, f"{mig.name} lists price_point as append-only"


def test_price_point_raw_only_no_adjustment_columns() -> None:
    # RAW-only captured price (OD-P2-4-F): NO corporate-action adjustment column / adjusted price.
    cols = set(PricePoint.__table__.columns.keys())
    forbidden = {"adjustment_basis", "adjusted_price", "adjustment_factor", "unadjusted_price"}
    assert not (forbidden & cols), f"price_point leaks an adjustment column: {forbidden & cols}"


def test_price_source_and_key_columns_not_null() -> None:
    # The promoted key columns are DB-level NOT NULL (so the current-head key is not defeasible).
    cols = PricePoint.__table__.columns
    for key_col in ("price_type", "currency_code", "price_source", "instrument_id"):
        assert cols[key_col].nullable is False, f"{key_col} must be NOT NULL"
    idx = next(i for i in PricePoint.__table__.indexes if i.name == "uq_price_point_current")
    assert [c.name for c in idx.columns] == [
        "tenant_id",
        "instrument_id",
        "price_date",
        "price_type",
        "currency_code",
        "price_source",
    ]


def test_no_component_kind_price_minted() -> None:
    # Snapshot integration is readiness-only (OD-P2-4-J): NO COMPONENT_KIND_PRICE in P2-4.
    import irp_shared.snapshot.models as snap_models

    assert not hasattr(snap_models, "COMPONENT_KIND_PRICE")
    assert "PRICE" not in snap_models.SNAPSHOT_COMPONENT_KINDS


def test_price_module_imports_no_calc_exposure_snapshot_risk() -> None:
    forbidden = {"calc", "exposure", "snapshot"}
    risk_tokens = ("var", "expected_shortfall", "covariance", "factor", "curve", "yield", "return_")
    tree = ast.parse((_MD_SRC / "price.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not (forbidden & set(node.module.split("."))), f"price.py imports {node.module}"
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not (forbidden & set(a.name.split("."))), f"price.py imports {a.name}"
    text = (_MD_SRC / "price.py").read_text().lower()
    for tok in risk_tokens:
        assert f"import {tok}" not in text and f".{tok}(" not in text


# ---------- migration head ----------


def test_migration_0019_chain_position() -> None:
    # P2-5 advanced head to 0020_curves; 0019_price_point keeps its chain position (down_revision
    # 0018_exposure_aggregate) and stays reachable in the revision walk (no longer the head).
    import pathlib as _pl

    from alembic.script import ScriptDirectory

    root = _pl.Path(price_mod.__file__)
    while not (root / "alembic.ini").exists():
        assert root != root.parent, "alembic.ini not found"
        root = root.parent
    script = ScriptDirectory(str(root / "migrations"))
    assert script.get_current_head() == "0038_var_residual_variance"
    assert script.get_revision("0019_price_point").down_revision == "0018_exposure_aggregate"
    assert "0019_price_point" in {r.revision for r in script.walk_revisions()}
