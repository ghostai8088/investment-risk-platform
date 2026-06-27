"""SQLite-local unit/behavior tests for P2-2 fx_rate (captured FX market data + convert).

RLS is a no-op on SQLite (FORCE-RLS isolation + the SYSTEM/foreign currency-visibility proofs live
in
``test_fx_rate_pg.py``); here we prove: the FR protocol (capture / supersede / correct / both-axes
``reconstruct_fx_rate_as_of`` / current-head uniqueness / prior-content immutability / rate_date
carried forward); the ``convert`` arithmetic (identity / direct / reciprocal / triangulation /
exact-
date / fail-closed, no silent 1.0); the governed DQ gate (strictly-positive RANGE + the new
evaluator
bounds + no-regression); ``MARKET.FX_*`` audit grain (+ no emit on convert); VENDOR-source ORIGIN
lineage per physical version + fail-closed rollback; the hybrid-aware ``resolve_currency``;
entitlement
parity; and the load-bearing scope fences (no calc/exposure/snapshot import; nothing imports
marketdata).
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
from irp_shared.dq.rules import RULE_TYPE_RANGE, DQEvaluation, evaluate_range
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, LineageEdge
from irp_shared.marketdata import (
    FxRate,
    FxRateActor,
    FxRateNotFound,
    FxRateValueError,
    capture_fx_rate,
    convert,
    correct_fx_rate,
    reconstruct_fx_rate_as_of,
    supersede_fx_rate,
)
from irp_shared.marketdata import service as fx_service
from irp_shared.models import Base
from irp_shared.reference.models import Currency
from irp_shared.reference.service import CurrencyNotVisible, resolve_currency

VA = datetime(2026, 6, 1, tzinfo=UTC)
KA = datetime(2030, 1, 1, tzinfo=UTC)  # fixed future known cutoff (>= wall-clock system_from)
RD = date(2026, 6, 1)
ACTOR = FxRateActor(actor_id="steward")


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


def _seed_currencies(db: Session, *codes: str, tenant: str | None = None) -> None:
    """Seed SYSTEM (global) currency vocab rows; optionally a tenant override row."""
    for code in codes or ("USD", "EUR", "JPY", "GBP"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=VA))
        if tenant is not None:
            db.add(Currency(tenant_id=tenant, code=code, name=f"{code} (own)", valid_from=VA))
    db.flush()


def _capture(db: Session, tenant: str, base: str, quote: str, rate: str, **kw):  # noqa: ANN202
    return capture_fx_rate(
        db,
        base_currency=base,
        quote_currency=quote,
        rate_date=RD,
        rate=Decimal(rate),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
        **kw,
    )


# ---------- FR protocol ----------


def test_capture_and_reconstruct_both_axes(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    row = _capture(session, t, "EUR", "USD", "1.08", rate_source="ECB")
    session.commit()
    got = reconstruct_fx_rate_as_of(
        session,
        acting_tenant=t,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=RD,
        valid_at=VA,
        known_at=KA,
    )
    assert got is not None and got.id == row.id and got.rate == Decimal("1.08")
    assert got.rate_source == "ECB" and got.record_version == 1
    # known_at BEFORE system_from -> not yet known -> None (system axis honored)
    assert (
        reconstruct_fx_rate_as_of(
            session,
            acting_tenant=t,
            base_currency="EUR",
            quote_currency="USD",
            rate_date=RD,
            valid_at=VA,
            known_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        is None
    )


def test_current_head_uniqueness(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    _capture(session, t, "EUR", "USD", "1.08")
    session.flush()
    with pytest.raises(
        IntegrityError
    ):  # a second open head for the same key violates the partial-unique
        _capture(session, t, "EUR", "USD", "1.09")
        session.flush()


def test_supersede_closes_valid_to_and_carries_forward(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    head = _capture(session, t, "EUR", "USD", "1.08", rate_source="ECB")
    session.commit()
    eff = datetime(2026, 6, 2, tzinfo=UTC)
    new = supersede_fx_rate(
        session,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=RD,
        rate_type="MID",
        acting_tenant=t,
        actor=ACTOR,
        effective_at=eff,
        rate=Decimal("1.10"),
    )
    session.commit()
    assert session.get(FxRate, head.id).valid_to == eff  # prior closed
    assert new.rate == Decimal("1.10") and new.rate_source == "ECB"  # carried forward
    assert new.rate_date == RD and new.record_version == 2  # rate_date carried verbatim


def test_correct_closes_system_to_content_immutable(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    head = _capture(session, t, "EUR", "USD", "1.08")
    session.commit()
    orig_rate = head.rate
    corrected = correct_fx_rate(
        session,
        head,
        restatement_reason="vendor fix",
        acting_tenant=t,
        actor=ACTOR,
        rate=Decimal("1.0801"),
    )
    session.commit()
    prior = session.get(FxRate, head.id)
    assert prior.system_to is not None and prior.rate == orig_rate  # prior content immutable
    assert corrected.rate == Decimal("1.0801") and corrected.restatement_reason == "vendor fix"
    assert corrected.rate_date == RD and corrected.supersedes_id == head.id


# ---------- convert ----------


def test_convert_identity_direct_reciprocal_triangulated(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    _capture(session, t, "EUR", "USD", "1.08")
    _capture(session, t, "USD", "JPY", "150")
    session.commit()
    # identity
    assert convert(
        session,
        amount=Decimal("5"),
        from_currency="USD",
        to_currency="USD",
        valid_at=VA,
        acting_tenant=t,
    ).converted_amount == Decimal("5")
    # direct
    assert convert(
        session,
        amount=Decimal("100"),
        from_currency="EUR",
        to_currency="USD",
        valid_at=VA,
        acting_tenant=t,
    ).converted_amount == Decimal("108.00")
    # reciprocal
    r = convert(
        session,
        amount=Decimal("108"),
        from_currency="USD",
        to_currency="EUR",
        valid_at=VA,
        acting_tenant=t,
    )
    assert r.converted_amount == Decimal("100") and "reciprocal" in r.rate_path[0]
    # triangulated EUR->JPY via USD base (1.08 * 150 = 162)
    tri = convert(
        session,
        amount=Decimal("1"),
        from_currency="EUR",
        to_currency="JPY",
        valid_at=VA,
        acting_tenant=t,
    )
    assert tri.converted_amount == Decimal("162") and len(tri.rate_path) == 2


def test_convert_missing_leg_fails_closed_no_silent_one(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    _capture(session, t, "EUR", "USD", "1.08")
    session.commit()
    with pytest.raises(FxRateNotFound):  # GBP has no rate -> fail closed (NOT a silent 1.0)
        convert(
            session,
            amount=Decimal("1"),
            from_currency="GBP",
            to_currency="USD",
            valid_at=VA,
            acting_tenant=t,
        )


def test_convert_exact_date_matching(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    _capture(session, t, "EUR", "USD", "1.08")  # rate_date = 2026-06-01
    session.commit()
    # a valid_at on a DIFFERENT calendar date -> rate_date mismatch -> fail closed (exact-date v1)
    with pytest.raises(FxRateNotFound):
        convert(
            session,
            amount=Decimal("1"),
            from_currency="EUR",
            to_currency="USD",
            valid_at=datetime(2026, 6, 2, tzinfo=UTC),
            acting_tenant=t,
        )


# ---------- DQ ----------


def test_dq_rejects_non_positive_rate(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    session.commit()  # persist the currency vocab so the per-iteration rollback can't discard it
    for bad in ("0", "-1.5"):
        with pytest.raises(DataQualityError):
            _capture(session, t, "EUR", "USD", bad)
        session.rollback()
    assert session.execute(select(func.count()).select_from(FxRate)).scalar_one() == 0


def test_value_checks_reject_bad_type_and_degenerate_pair(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    with pytest.raises(FxRateValueError):  # BID not in v1 vocab
        _capture(session, t, "EUR", "USD", "1.08", rate_type="BID")
    with pytest.raises(FxRateValueError):  # degenerate pair
        _capture(session, t, "USD", "USD", "1.0")


def test_range_evaluator_bounds() -> None:
    pos = {"column": "v", "min": 0, "min_inclusive": False}
    assert evaluate_range(pos, [{"v": Decimal("0.01")}]).passed is True
    assert evaluate_range(pos, [{"v": Decimal("0")}]).passed is False  # exclusive lower
    assert evaluate_range(pos, [{"v": None}]).passed is False  # null is an offender
    rng = {"column": "v", "min": 1, "max": 10}  # inclusive both
    assert evaluate_range(rng, [{"v": 1}, {"v": 10}]).passed is True
    assert evaluate_range(rng, [{"v": 11}]).passed is False
    assert isinstance(evaluate_range(pos, []), DQEvaluation)


def test_range_in_registry_does_not_regress_shipped_evaluators() -> None:
    from irp_shared.dq.rules import (
        REGISTRY,
        RULE_TYPE_ALLOWED_VALUES,
        RULE_TYPE_NOT_NULL,
        evaluate_allowed_values,
        evaluate_not_null,
    )

    assert set(REGISTRY) == {RULE_TYPE_NOT_NULL, RULE_TYPE_ALLOWED_VALUES, RULE_TYPE_RANGE}
    # shipped evaluators' OUTPUTS unchanged
    assert evaluate_not_null({"column": "c"}, [{"c": 1}, {"c": None}]).failed_count == 1
    assert evaluate_allowed_values({"column": "c", "allowed": ["A"]}, [{"c": "B"}]).passed is False


# ---------- audit + lineage ----------


def test_audit_grain_and_no_emit_on_convert(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    _capture(session, t, "EUR", "USD", "1.08")
    session.commit()

    def _count(ev: str) -> int:
        return session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == ev)
        ).scalar_one()

    assert _count("MARKET.FX_CREATE") == 1
    head = reconstruct_fx_rate_as_of(
        session,
        acting_tenant=t,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=RD,
        valid_at=VA,
        known_at=KA,
    )
    correct_fx_rate(
        session, head, restatement_reason="x", acting_tenant=t, actor=ACTOR, rate=Decimal("1.1")
    )
    session.commit()
    assert _count("MARKET.FX_CREATE") == 1 and _count("MARKET.FX_UPDATE") == 1
    assert _count("MARKET.FX_CORRECTION") == 1  # correct = UPDATE close-out + CORRECTION
    # convert emits NOTHING
    n_before = session.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    convert(
        session,
        amount=Decimal("1"),
        from_currency="EUR",
        to_currency="USD",
        valid_at=VA,
        acting_tenant=t,
    )
    assert session.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == n_before


def test_fail_closed_rollback_on_lineage_or_audit_failure(session: Session, monkeypatch) -> None:  # noqa: ANN001
    # CTRL-032: if record_lineage OR record_event raises mid-write, the whole governed unit rolls
    # back — no fx_rate row, no fx ORIGIN lineage edge, no MARKET.FX_CREATE event (the valuation
    # test_fail_closed_audit_rollback precedent; covers the lineage/audit-emit arm, distinct from
    # the DQ-gate arm proven by test_dq_rejects_non_positive_rate).
    import irp_shared.marketdata.events as ev

    orig_lin, orig_evt = ev.record_lineage, ev.record_event
    t = str(uuid.uuid4())
    _seed_currencies(session)
    session.commit()  # currencies persist across the per-arm rollbacks

    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("provenance rail down")

    for target in ("record_lineage", "record_event"):
        monkeypatch.setattr(ev, "record_lineage", orig_lin)
        monkeypatch.setattr(ev, "record_event", orig_evt)
        monkeypatch.setattr(ev, target, _boom)
        with pytest.raises(RuntimeError):
            _capture(session, t, "EUR", "USD", "1.08")
        session.rollback()
        assert session.execute(select(func.count()).select_from(FxRate)).scalar_one() == 0
        assert (
            session.execute(
                select(func.count())
                .select_from(LineageEdge)
                .where(LineageEdge.target_entity_type == "fx_rate")
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "MARKET.FX_CREATE")
            ).scalar_one()
            == 0
        )


def test_one_vendor_origin_edge_per_physical_version(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session)
    head = _capture(session, t, "EUR", "USD", "1.08")
    session.commit()
    new = supersede_fx_rate(
        session,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=RD,
        rate_type="MID",
        acting_tenant=t,
        actor=ACTOR,
        effective_at=datetime(2026, 6, 2, tzinfo=UTC),
        rate=Decimal("1.1"),
    )
    session.commit()
    edges = (
        session.execute(select(LineageEdge).where(LineageEdge.target_entity_type == "fx_rate"))
        .scalars()
        .all()
    )
    targets = {e.target_entity_id for e in edges}
    assert targets == {
        head.id,
        new.id,
    }  # one ORIGIN edge per physical version; close-out roots none
    assert all(e.edge_kind == EDGE_KIND_ORIGIN for e in edges)


# ---------- hybrid currency resolution ----------


def test_resolve_currency_hybrid(session: Session) -> None:
    t = str(uuid.uuid4())
    other = str(uuid.uuid4())
    session.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=VA))
    session.add(Currency(tenant_id=other, code="ZZZ", name="foreign", valid_from=VA))
    session.flush()
    assert resolve_currency(session, "USD", acting_tenant=t).code == "USD"  # SYSTEM resolves
    with pytest.raises(CurrencyNotVisible):  # a foreign tenant's currency is NOT visible
        resolve_currency(session, "ZZZ", acting_tenant=t)
    with pytest.raises(CurrencyNotVisible):  # unknown code
        resolve_currency(session, "XXX", acting_tenant=t)


def test_capture_rejects_unknown_currency(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currencies(session, "USD")  # EUR not seeded
    with pytest.raises(CurrencyNotVisible):
        _capture(session, t, "EUR", "USD", "1.08")


# ---------- entitlement parity ----------


def test_marketdata_permissions_grants_as_ratified() -> None:
    view = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.view" in codes}
    ingest = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.ingest" in codes}
    assert view == {"data_steward", "risk_analyst_1l", "risk_manager_2l", "platform_admin"}
    assert ingest == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in view and "auditor_3l" not in ingest


# ---------- scope fences ----------

_MD_SRC = pathlib.Path(fx_service.__file__).parent


def test_marketdata_imports_no_calc_exposure_snapshot_risk() -> None:
    forbidden = {"calc", "exposure", "snapshot"}
    risk_tokens = (
        "var",
        "expected_shortfall",
        "covariance",
        "volatility",
        "factor",
        "curve",
        "yield",
    )
    for path in _MD_SRC.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                assert not (forbidden & set(parts)), f"{path.name} imports {node.module}"
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert not (forbidden & set(a.name.split("."))), f"{path.name} imports {a.name}"
        text = path.read_text().lower()
        for tok in risk_tokens:
            assert f"import {tok}" not in text and f".{tok}(" not in text


def test_nothing_imports_marketdata() -> None:
    """``marketdata`` is a leaf, EXCEPT ``models.py`` (every model) and the P2-3 consumers of the
    PURE FX leg helpers: ``snapshot`` (pins FX legs at build) + ``exposure`` (composes the effective
    rate over captured legs). ``marketdata`` still imports neither — a one-way dependency."""
    root = pathlib.Path(fx_service.__file__).parents[1]
    for path in root.rglob("*.py"):
        if (
            "marketdata" in path.parts
            or "snapshot" in path.parts
            or "exposure" in path.parts
            or path.name == "models.py"
        ):
            continue
        text = path.read_text()
        assert "import irp_shared.marketdata" not in text, path
        assert "from irp_shared.marketdata" not in text, path


def test_convert_uses_only_published_rate_arithmetic() -> None:
    # convert MAY multiply (it is published-rate arithmetic) but imports no model/curve/risk symbol.
    tree = ast.parse((_MD_SRC / "convert.py").read_text())
    assert any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult) for n in ast.walk(tree))
    assert "reconstruct_fx_rate_as_of" in (_MD_SRC / "convert.py").read_text()


# ---------- migration head ----------


def test_fx_rate_table_registered_but_not_append_only() -> None:
    # The new fx_rate table IS present in the metadata aggregator (the cross-slice "new table
    # present"
    # assertion); and it is FR — NOT append-only (no APPEND_ONLY membership; close-out UPDATEs
    # allowed).
    from irp_shared.db.mixins import FullReproducibleMixin

    assert "fx_rate" in Base.metadata.tables
    assert issubclass(FxRate, FullReproducibleMixin)


def test_migration_0017_chain_position() -> None:
    # P2-3 advanced the head to 0018_exposure_aggregate; 0017_fx_rate keeps its chain position
    # (down_revision 0016) and is reachable in the revision walk (no longer the head).
    from alembic.script import ScriptDirectory

    root = pathlib.Path(fx_service.__file__)
    while not (root / "alembic.ini").exists():
        assert root != root.parent, "alembic.ini not found"
        root = root.parent
    script = ScriptDirectory(str(root / "migrations"))
    assert script.get_revision("0017_fx_rate").down_revision == "0016_dataset_snapshot"
    revs = {r.revision for r in script.walk_revisions()}
    assert "0017_fx_rate" in revs
