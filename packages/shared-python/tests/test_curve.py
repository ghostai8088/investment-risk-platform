"""SQLite-local unit/behavior tests for P2-5 curve + curve_point (captured yield/spread curves).

RLS is a no-op on SQLite (the FORCE-RLS isolation + the curve_point P0001-trigger append-only proof
live in ``test_curve_pg.py``); here we prove: FR header protocol (capture / supersede / correct /
both-axes ``reconstruct_curve_as_of`` / current-head uniqueness / prior-header immutability /
curve_date carried forward); ``curve_source`` in the key (multi-vendor coexistence); the
``curve_type`` ↔ ``reference_key`` invariant; the version-pinned ``curve_point`` nodes (ORM
append-only guard); the ``curve_type``/``value_type`` vocabs + tenor; ``interpolation_method``
inert; the value-type-conditional DQ gate (required-field + tenor + DF-positive + rates/spreads
[-1,1], fail-closed); ``MARKET.CURVE_*`` audit grain (one event per curve; no emit on read);
VENDOR_CURVE ORIGIN lineage per physical version + fail-closed rollback; entitlement parity; and the
load-bearing scope fences (captured-not-computed; no COMPONENT_KIND_CURVE; curve_point append-only,
curve NOT append-only).
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

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, LineageEdge
from irp_shared.marketdata import (
    CURVE_TYPES,
    CURVE_VALUE_TYPES,
    Curve,
    CurveActor,
    CurveNode,
    CurvePoint,
    CurveValueError,
    NoCurrentCurve,
    capture_curve,
    correct_curve,
    list_curve_points,
    reconstruct_curve_as_of,
    supersede_curve,
)
from irp_shared.marketdata import curve as curve_mod
from irp_shared.models import Base
from irp_shared.reference.models import Currency
from irp_shared.reference.service import CurrencyNotVisible

VA = datetime(2026, 6, 1, tzinfo=UTC)
KA = datetime(2030, 1, 1, tzinfo=UTC)
CD = date(2026, 6, 1)
ACTOR = CurveActor(actor_id="steward")


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


def _seed_currency(db: Session, *codes: str) -> None:
    for code in codes or ("USD", "EUR"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=VA))
    db.flush()


def _nodes() -> list[CurveNode]:
    return [
        CurveNode("3M", 90, "ZERO_RATE", Decimal("0.0425")),
        CurveNode("1Y", 365, "ZERO_RATE", Decimal("0.0440")),
        CurveNode("1Y", 365, "DISCOUNT_FACTOR", Decimal("0.9560")),
    ]


def _capture(db: Session, tenant: str, source: str = "BLOOMBERG", **kw):  # noqa: ANN202
    return capture_curve(
        db,
        curve_type=kw.pop("curve_type", "TREASURY"),
        currency_code="USD",
        curve_date=CD,
        curve_source=source,
        nodes=kw.pop("nodes", _nodes()),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
        **kw,
    )


# ---------- FR protocol (header) ----------


def test_capture_and_reconstruct_both_axes(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    head = _capture(session, t)
    session.commit()
    # the header point_count equals the count of persisted version-pinned nodes
    assert head.point_count == 3 == len(list_curve_points(session, head.id, acting_tenant=t))
    got = reconstruct_curve_as_of(
        session,
        acting_tenant=t,
        curve_type="TREASURY",
        currency_code="USD",
        curve_date=CD,
        curve_source="BLOOMBERG",
        valid_at=VA,
        known_at=KA,
    )
    assert got is not None and got.id == head.id and got.record_version == 1
    assert (
        reconstruct_curve_as_of(
            session,
            acting_tenant=t,
            curve_type="TREASURY",
            currency_code="USD",
            curve_date=CD,
            curve_source="BLOOMBERG",
            valid_at=VA,
            known_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        is None
    )


def test_current_head_uniqueness(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    _capture(session, t)
    session.flush()
    with pytest.raises(IntegrityError):
        _capture(session, t)
        session.flush()


def test_curve_source_in_key_multi_vendor(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    _capture(session, t, source="BLOOMBERG")
    _capture(session, t, source="REUTERS")
    session.commit()
    opens = {
        r.curve_source
        for r in session.execute(select(Curve).where(Curve.valid_to.is_(None))).scalars().all()
    }
    assert opens == {"BLOOMBERG", "REUTERS"}


def test_supersede_closes_valid_to_fresh_nodes_carries_date(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    head = _capture(session, t)
    session.commit()
    eff = datetime(2026, 6, 2, tzinfo=UTC)
    new = supersede_curve(
        session,
        curve_type="TREASURY",
        currency_code="USD",
        curve_date=CD,
        curve_source="BLOOMBERG",
        nodes=[CurveNode("3M", 90, "ZERO_RATE", Decimal("0.0500"))],
        acting_tenant=t,
        actor=ACTOR,
        effective_at=eff,
    )
    session.commit()
    assert session.get(Curve, head.id).valid_to == eff  # prior closed
    assert new.record_version == 2 and new.curve_date == CD and new.point_count == 1
    # prior version's nodes stay readable + immutable (version-pinned)
    assert len(list_curve_points(session, head.id, acting_tenant=t)) == 3
    assert len(list_curve_points(session, new.id, acting_tenant=t)) == 1


def test_correct_closes_system_to_content_immutable(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    head = _capture(session, t)
    session.commit()
    corrected = correct_curve(
        session,
        head,
        restatement_reason="vendor fix",
        nodes=[CurveNode("3M", 90, "ZERO_RATE", Decimal("0.0426"))],
        acting_tenant=t,
        actor=ACTOR,
    )
    session.commit()
    prior = session.get(Curve, head.id)
    assert prior.system_to is not None and prior.curve_type == "TREASURY"  # prior content immutable
    assert corrected.restatement_reason == "vendor fix" and corrected.supersedes_id == head.id
    assert corrected.curve_date == CD  # carried verbatim
    assert len(list_curve_points(session, head.id, acting_tenant=t)) == 3  # prior nodes untouched


# ---------- version-pinned append-only nodes ----------


def test_curve_point_is_append_only(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    head = _capture(session, t)
    session.commit()
    point = list_curve_points(session, head.id, acting_tenant=t)[0]
    with pytest.raises(AppendOnlyViolation):  # the ORM before_update guard
        point.point_value = Decimal("0.99")
        session.flush()
    session.rollback()
    with pytest.raises(AppendOnlyViolation):  # the ORM before_delete guard
        session.delete(list_curve_points(session, head.id, acting_tenant=t)[0])
        session.flush()


def test_tenor_days_normalization_dup_reject(session: Session) -> None:
    # "12M" and "1Y" normalize to tenor_days=365 → the (curve_id, value_type, tenor_days) UNIQUE
    # rejects the duplicate tenor within one curve version.
    t = str(uuid.uuid4())
    _seed_currency(session)
    with pytest.raises(IntegrityError):
        _capture(
            session,
            t,
            nodes=[
                CurveNode("12M", 365, "ZERO_RATE", Decimal("0.044")),
                CurveNode("1Y", 365, "ZERO_RATE", Decimal("0.045")),
            ],
        )
        session.flush()


# ---------- reference_key invariant + vocabs + tenor ----------


def test_reference_key_invariant(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    with pytest.raises(CurveValueError):  # rate curve + non-NONE reference_key
        _capture(session, t, reference_key="RATING:BBB")
    with pytest.raises(CurveValueError):  # CREDIT_SPREAD + NONE
        capture_curve(
            session,
            curve_type="CREDIT_SPREAD",
            currency_code="USD",
            curve_date=CD,
            curve_source="MARKIT",
            nodes=[CurveNode("1Y", 365, "SPREAD", Decimal("0.0015"))],
            acting_tenant=t,
            actor=ACTOR,
            reference_key="NONE",
        )
    # happy path: CREDIT_SPREAD + opaque label (realizes ENT-023 by value)
    cs = capture_curve(
        session,
        curve_type="CREDIT_SPREAD",
        currency_code="USD",
        curve_date=CD,
        curve_source="MARKIT",
        nodes=[CurveNode("1Y", 365, "SPREAD", Decimal("0.0015"))],
        acting_tenant=t,
        actor=ACTOR,
        reference_key="ISSUER:LEI123",
    )
    session.commit()
    assert cs.reference_key == "ISSUER:LEI123" and cs.curve_type == "CREDIT_SPREAD"


def test_curve_type_and_value_type_and_tenor_validation(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    with pytest.raises(CurveValueError):  # out-of-vocab curve_type
        _capture(session, t, curve_type="JUNK")
    with pytest.raises(CurveValueError):  # out-of-vocab value_type
        _capture(session, t, nodes=[CurveNode("1Y", 365, "VOLATILITY", Decimal("0.2"))])
    with pytest.raises(CurveValueError):  # tenor_days <= 0
        _capture(session, t, nodes=[CurveNode("0M", 0, "ZERO_RATE", Decimal("0.04"))])
    with pytest.raises(CurveValueError):  # bad tenor_label pattern
        _capture(session, t, nodes=[CurveNode("1X", 365, "ZERO_RATE", Decimal("0.04"))])
    with pytest.raises(CurveValueError):  # empty node set
        _capture(session, t, nodes=[])
    assert set(CURVE_TYPES) == {"TREASURY", "GOVT", "SWAP", "OIS", "CREDIT_SPREAD"}
    assert set(CURVE_VALUE_TYPES) == {"ZERO_RATE", "PAR_RATE", "DISCOUNT_FACTOR", "SPREAD"}


def test_interpolation_method_is_inert_label(session: Session) -> None:
    # interpolation_method is captured verbatim as metadata; no engine consumes it (a scope-fence
    # below asserts no interpolation symbol in the module).
    t = str(uuid.uuid4())
    _seed_currency(session)
    head = _capture(session, t, interpolation_method="CUBIC_SPLINE")
    session.commit()
    assert head.interpolation_method == "CUBIC_SPLINE"


# ---------- DQ (value-type-conditional) ----------


def test_dq_value_type_conditional(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    session.commit()

    def _cap(value_type: str, val: str):  # noqa: ANN202
        return _capture(
            session, t, nodes=[CurveNode("1Y", 365, value_type, Decimal(val))], curve_type="SWAP"
        )

    # DISCOUNT_FACTOR strictly positive
    with pytest.raises(DataQualityError):
        _cap("DISCOUNT_FACTOR", "0")
    session.rollback()
    _cap("DISCOUNT_FACTOR", "1.5")  # no upper bound for DF
    session.rollback()
    # rates/spreads in [-1, 1]; negatives ALLOWED
    _cap("ZERO_RATE", "-0.5")
    session.rollback()
    _cap("PAR_RATE", "-0.5")  # negative PAR_RATE accepted
    session.rollback()
    _cap("SPREAD", "-0.0010")
    session.rollback()
    with pytest.raises(DataQualityError):  # rate out of sanity band
        _cap("ZERO_RATE", "1.5")
    session.rollback()
    assert session.execute(select(func.count()).select_from(Curve)).scalar_one() == 0


def test_dq_required_field_fail_closed(session: Session) -> None:
    # A None required node value fails closed (no row) — the DB-level NOT NULL on point_value is the
    # required-field enforcement backstop (paired with the governed required-field DQ gate).
    t = str(uuid.uuid4())
    _seed_currency(session)
    session.commit()
    with pytest.raises(IntegrityError):
        _capture(session, t, nodes=[CurveNode("1Y", 365, "ZERO_RATE", None)])  # type: ignore[arg-type]
        session.flush()
    session.rollback()
    assert session.execute(select(func.count()).select_from(Curve)).scalar_one() == 0


def test_dq_evaluators_not_regressed() -> None:
    # The (params, dataset) Protocol is UNTOUCHED — the shipped evaluators behave unchanged.
    from irp_shared.dq.rules import REGISTRY, RULE_TYPE_RANGE, evaluate_range

    assert RULE_TYPE_RANGE in REGISTRY
    pos = {"column": "point_value", "min": 0, "min_inclusive": False}
    band = {"column": "point_value", "min": -1, "max": 1}
    assert (
        evaluate_range(pos, [{"point_value": Decimal("1.5")}]).passed is True
    )  # DF no upper bound
    assert evaluate_range(pos, [{"point_value": Decimal("0")}]).passed is False
    assert evaluate_range(band, [{"point_value": Decimal("-0.5")}]).passed is True  # negative ok
    assert evaluate_range(band, [{"point_value": Decimal("1.5")}]).passed is False


# ---------- audit + lineage ----------


def test_audit_grain_one_event_per_curve_no_read(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    # a 1-node curve and a 3-node curve each emit exactly ONE CURVE_CREATE (event-count independent
    # of point_count).
    _capture(session, t, source="A", nodes=[CurveNode("1Y", 365, "ZERO_RATE", Decimal("0.04"))])
    _capture(session, t, source="B", nodes=_nodes())
    session.commit()

    def _c(ev: str) -> int:
        return session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == ev)
        ).scalar_one()

    assert _c("MARKET.CURVE_CREATE") == 2  # one per curve, not per node (1+3 nodes)
    head = reconstruct_curve_as_of(
        session,
        acting_tenant=t,
        curve_type="TREASURY",
        currency_code="USD",
        curve_date=CD,
        curve_source="B",
        valid_at=VA,
        known_at=KA,
    )
    correct_curve(
        session,
        head,
        restatement_reason="x",
        nodes=[CurveNode("1Y", 365, "ZERO_RATE", Decimal("0.041"))],
        acting_tenant=t,
        actor=ACTOR,
    )
    session.commit()
    assert _c("MARKET.CURVE_UPDATE") == 1 and _c("MARKET.CURVE_CORRECTION") == 1
    n_before = session.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    reconstruct_curve_as_of(
        session,
        acting_tenant=t,
        curve_type="TREASURY",
        currency_code="USD",
        curve_date=CD,
        curve_source="B",
        valid_at=VA,
    )
    assert session.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == n_before


def test_one_vendor_origin_edge_per_version_header_targeted(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    head = _capture(session, t)
    session.commit()
    new = supersede_curve(
        session,
        curve_type="TREASURY",
        currency_code="USD",
        curve_date=CD,
        curve_source="BLOOMBERG",
        nodes=[CurveNode("1Y", 365, "ZERO_RATE", Decimal("0.05"))],
        acting_tenant=t,
        actor=ACTOR,
        effective_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    session.commit()
    edges = (
        session.execute(select(LineageEdge).where(LineageEdge.target_entity_type == "curve"))
        .scalars()
        .all()
    )
    assert {e.target_entity_id for e in edges} == {head.id, new.id}  # one per header version
    assert all(e.edge_kind == EDGE_KIND_ORIGIN for e in edges)
    # no lineage edge targets curve_point (the nodes are covered transitively via the header)
    assert (
        session.execute(
            select(func.count())
            .select_from(LineageEdge)
            .where(LineageEdge.target_entity_type == "curve_point")
        ).scalar_one()
        == 0
    )


def test_fail_closed_rollback_on_lineage_or_audit_failure(session: Session, monkeypatch) -> None:  # noqa: ANN001
    orig_lin, orig_evt = curve_mod.record_lineage, curve_mod.record_event
    t = str(uuid.uuid4())
    _seed_currency(session)
    session.commit()

    def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("provenance rail down")

    for target in ("record_lineage", "record_event"):
        monkeypatch.setattr(curve_mod, "record_lineage", orig_lin)
        monkeypatch.setattr(curve_mod, "record_event", orig_evt)
        monkeypatch.setattr(curve_mod, target, _boom)
        with pytest.raises(RuntimeError):
            _capture(session, t)
        session.rollback()
        assert session.execute(select(func.count()).select_from(Curve)).scalar_one() == 0
        assert session.execute(select(func.count()).select_from(CurvePoint)).scalar_one() == 0
        assert (
            session.execute(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "MARKET.CURVE_CREATE")
            ).scalar_one()
            == 0
        )


# ---------- currency ----------


def test_capture_rejects_unknown_currency(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session, "EUR")  # USD not seeded
    with pytest.raises(CurrencyNotVisible):
        _capture(session, t)


def test_supersede_with_no_open_head_raises(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    with pytest.raises(NoCurrentCurve):
        supersede_curve(
            session,
            curve_type="TREASURY",
            currency_code="USD",
            curve_date=CD,
            curve_source="NONE",
            nodes=[CurveNode("1Y", 365, "ZERO_RATE", Decimal("0.04"))],
            acting_tenant=t,
            actor=ACTOR,
            effective_at=VA,
        )


# ---------- entitlement parity ----------


def test_marketdata_permissions_grants_as_ratified() -> None:
    # curve REUSES marketdata.view/.ingest — NO new permission.
    view = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.view" in codes}
    ingest = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.ingest" in codes}
    assert view == {"data_steward", "risk_analyst_1l", "risk_manager_2l", "platform_admin"}
    assert ingest == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in view and "auditor_3l" not in ingest


# ---------- scope fences ----------

_MD_SRC = pathlib.Path(curve_mod.__file__).parent


def test_curve_fr_header_curve_point_append_only() -> None:
    from irp_shared.db.mixins import FullReproducibleMixin, ImmutableAppendOnlyMixin

    assert "curve" in Base.metadata.tables and "curve_point" in Base.metadata.tables
    assert issubclass(Curve, FullReproducibleMixin)  # header FR
    assert issubclass(CurvePoint, ImmutableAppendOnlyMixin)  # nodes IA append-only
    # the 0020 migration puts ONLY curve_point in APPEND_ONLY_TABLES; curve (FR) has no trigger.
    root = pathlib.Path(curve_mod.__file__)
    while not (root / "alembic.ini").exists():
        root = root.parent
    src = (root / "migrations" / "versions" / "0020_curves.py").read_text()
    for line in src.splitlines():
        if line.strip().startswith("APPEND_ONLY_TABLES ="):
            assert "curve_point" in line and '"curve",' not in line and "'curve'," not in line


def test_no_component_kind_curve_minted() -> None:
    import irp_shared.snapshot.models as snap_models

    assert not hasattr(snap_models, "COMPONENT_KIND_CURVE")
    assert "CURVE" not in snap_models.SNAPSHOT_COMPONENT_KINDS


def test_curve_module_no_construction_or_risk_symbols() -> None:
    # captured-not-computed: binder imports no calc/exposure/snapshot, has no multiplication, and
    # DEFINES/CALLS no construction/interpolation/risk func. We check CODE IDENTIFIERS (funcdef +
    # call names), NOT raw text — so docstring prose negations ("NO interpolation, bootstrapping
    # ...") and the inert ``interpolation_method`` attribute (a read, not a call) don't trip fence.
    forbidden_imports = {"calc", "exposure", "snapshot"}
    risk_verbs = (
        "interpolat",
        "bootstrap",
        "discount",
        "duration",
        "key_rate",
        "value_at_risk",
        "expected_shortfall",
        "covariance",
        "factor_model",
    )
    tree = ast.parse((_MD_SRC / "curve.py").read_text())
    called_or_defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not (forbidden_imports & set(node.module.split("."))), node.module
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not (forbidden_imports & set(a.name.split("."))), a.name
        assert not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)), "no ast.Mult"
        if isinstance(node, ast.FunctionDef):
            called_or_defined.add(node.name.lower())
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                called_or_defined.add(f.id.lower())
            elif isinstance(f, ast.Attribute):
                called_or_defined.add(f.attr.lower())
    blob = " ".join(called_or_defined)
    for verb in risk_verbs:
        assert verb not in blob, verb


def test_reference_key_is_plain_string_no_fk() -> None:
    # reference_key is an opaque String in v1 — NOT an FK (no resolver, no ForeignKey).
    col = Curve.__table__.columns["reference_key"]
    assert not col.foreign_keys
    assert "resolve_reference" not in (_MD_SRC / "curve.py").read_text()


# ---------- migration head ----------


def test_migration_head_is_0020_curves() -> None:
    from alembic.script import ScriptDirectory

    root = pathlib.Path(curve_mod.__file__)
    while not (root / "alembic.ini").exists():
        assert root != root.parent
        root = root.parent
    script = ScriptDirectory(str(root / "migrations"))
    assert script.get_current_head() == "0020_curves"
    assert script.get_revision("0020_curves").down_revision == "0019_price_point"
