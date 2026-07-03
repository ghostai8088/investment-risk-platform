"""SQLite-local tests for the P1C-6 deterministic synthetic dataset (labeled, never-auto-run).

Proves: determinism (byte-identical re-run of the domain surface) + uuid5 ids + fixed injected
timestamps; the AST/source fence forbidding every wall-clock/random vector; SYNTH_* naming + no real
vendor/agency/exchange names + no real ISIN/CUSIP/SEDOL/LEI; FK integrity + tenant isolation; the
governed-path (audit + lineage + verify_chain); the never-auto-run + non-synthetic refusal guards;
the required edge-case scenarios (short / reversal-with-price / position+valuation correction /
multi valuation_date / stale-missing valuation); the no-compute fence; no-raw-SQL/no-BYPASSRLS; and
no migration / migration head unchanged.
"""

from __future__ import annotations

import ast
import pathlib
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.lineage.models import LineageEdge
from irp_shared.models import Base
from irp_shared.portfolio import Portfolio
from irp_shared.position import Position, reconstruct_position_as_of
from irp_shared.reference.models import Instrument
from irp_shared.synthetic import (
    SEED_EPOCH,
    SYNTHETIC_TENANT_ID,
    SyntheticSeedRefused,
    build_synthetic_dataset,
    synthetic_id,
)
from irp_shared.synthetic import builder as builder_mod
from irp_shared.synthetic import ids as ids_mod
from irp_shared.transaction.models import Transaction
from irp_shared.valuation import Valuation, reconstruct_valuation_as_of

_SYN_MODULES = (ids_mod, builder_mod)


@pytest.fixture(autouse=True)
def _allow_synthetic(monkeypatch) -> None:  # noqa: ANN001
    """Set the synthetic-seed env gate for EVERY test here (auto-restored after each test).

    The refusal tests that need it ABSENT override via ``monkeypatch.delenv`` in their own body
    (the same function-scoped ``monkeypatch`` instance, so the override wins and is cleaned up).
    This keeps the suite self-contained: no reliance on the operator's shell exporting the var,
    and no mutation of the process-global ``os.environ`` (the prior fixture's flaw)."""
    monkeypatch.setenv("IRP_ALLOW_SYNTHETIC_SEED", "1")


@pytest.fixture
def seeded() -> Session:
    """A fresh in-memory DB seeded with the synthetic dataset (gate via ``_allow_synthetic``)."""
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        build_synthetic_dataset(db, allow_synthetic_seed=True)
        db.commit()
        yield db
    finally:
        db.close()
        engine.dispose()


def _fresh_seeded():  # noqa: ANN202 - helper builds + returns (engine, db)
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    build_synthetic_dataset(db, allow_synthetic_seed=True)
    db.commit()
    return engine, db


def _surface(db: Session) -> list[tuple]:
    """The deterministic domain surface (id + key business fields + the injected temporal axes).
    Excludes wall-clock metadata (created_at/updated_at) which is not part of the deterministic
    surface."""
    rows: list[tuple] = []
    for inst in db.execute(select(Instrument).order_by(Instrument.code)).scalars():
        rows.append(("instrument", inst.id, inst.code, inst.asset_class, inst.valid_from))
    for pf in db.execute(select(Portfolio).order_by(Portfolio.code)).scalars():
        rows.append(
            ("portfolio", pf.id, pf.code, pf.node_type, pf.parent_portfolio_id, pf.valid_from)
        )
    for p in db.execute(select(Position).order_by(Position.id)).scalars():
        rows.append(
            ("position", p.id, str(p.quantity), p.valid_from, p.system_from, p.supersedes_id)
        )
    for v in db.execute(select(Valuation).order_by(Valuation.id)).scalars():
        rows.append(
            ("valuation", v.id, str(v.mark_value), v.valuation_date, v.valid_from, v.system_from)
        )
    for txn in db.execute(select(Transaction).order_by(Transaction.id)).scalars():
        rows.append(("transaction", txn.id, txn.txn_type, str(txn.quantity), txn.system_from))
    return rows


# --- 1 deterministic repeatability + 2 uuid5 ids + 3 fixed timestamps ---


def test_deterministic_repeatability() -> None:
    e1, db1 = _fresh_seeded()
    e2, db2 = _fresh_seeded()
    try:
        assert _surface(db1) == _surface(db2)  # byte-identical domain surface across fresh runs
    finally:
        db1.close()
        e1.dispose()
        db2.close()
        e2.dispose()


def test_uuid5_deterministic_ids(seeded: Session) -> None:
    # Every domain id equals its uuid5(namespace, key) — not a random uuid4.
    assert seeded.get(Position, synthetic_id("position:acct1:bond:v1")) is not None
    assert seeded.get(Instrument, synthetic_id("instrument:SYNTH-BOND-A")) is not None
    assert seeded.get(Portfolio, synthetic_id("portfolio:SYNTH-FUND")) is not None
    assert seeded.get(Valuation, synthetic_id("valuation:acct1:bond:vd1:v1")) is not None


def _naive(dt):  # noqa: ANN001, ANN202 - drop tzinfo (SQLite returns naive datetimes)
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def test_fixed_injected_timestamps(seeded: Session) -> None:
    # First instrument written stamps valid_from == SEED_EPOCH (clock tick 0); every system_from is
    # within the fixed seed window (proves the injected clock, not wall-clock ~2026-06). SQLite
    # returns naive datetimes, so compare tz-stripped.
    epoch = _naive(SEED_EPOCH)
    upper = epoch.replace(hour=1)  # all ticks are within seconds of SEED_EPOCH
    bond = seeded.get(Instrument, synthetic_id("instrument:SYNTH-BOND-A"))
    assert _naive(bond.valid_from) == epoch
    for p in seeded.execute(select(Position)).scalars():
        assert epoch <= _naive(p.system_from) < upper
    for v in seeded.execute(select(Valuation)).scalars():
        assert epoch <= _naive(v.system_from) < upper


# --- 4 + 16 + 17 AST/source fences (no wall-clock/random, no compute, no raw-SQL/BYPASSRLS) ---

_FORBIDDEN_CALL_NAMES = {"utcnow", "uuid4", "new_uuid", "uuid1"}
_FORBIDDEN_ATTRS = {"now", "utcnow", "uuid4", "uuid1"}
_FORBIDDEN_IMPORTS = {"random", "secrets"}


def _module_path(mod) -> pathlib.Path:  # noqa: ANN001
    return pathlib.Path(mod.__file__)


def test_no_wallclock_or_random_in_synthetic_modules() -> None:
    for mod in _SYN_MODULES:
        tree = ast.parse(_module_path(mod).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    assert f.id not in _FORBIDDEN_CALL_NAMES, f"{mod.__name__}: {f.id}()"
                if isinstance(f, ast.Attribute):
                    assert f.attr not in _FORBIDDEN_ATTRS, f"{mod.__name__}: .{f.attr}()"
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"now", "utcnow"}, f"{mod.__name__}: .{node.attr}"
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = [a.name.split(".")[0] for a in node.names]
                mod_root = (getattr(node, "module", "") or "").split(".")[0]
                for bad in _FORBIDDEN_IMPORTS:
                    assert bad not in names and bad != mod_root, f"{mod.__name__}: imports {bad}"


def test_no_compute_no_rawsql_no_bypassrls() -> None:
    # AST-based (inspects CODE, not the docstrings that DESCRIBE these fences). The seed composes
    # binders only: no arithmetic (no market value / exposure / quantity*mark), no raw SQL execution
    # (no `text(...)` / `.execute(...)`), no BYPASSRLS path (set_tenant_context only).
    for mod in _SYN_MODULES:
        tree = ast.parse(_module_path(mod).read_text())
        mults = [
            n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult)
        ]
        assert not mults, f"{mod.__name__}: multiplies (possible market-value/exposure compute)"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    assert f.id != "text", f"{mod.__name__}: raw-SQL text() call"
                if isinstance(f, ast.Attribute):
                    assert f.attr != "execute", f"{mod.__name__}: raw .execute() call"
            if isinstance(node, ast.Name):
                assert node.id not in {"irp_ops", "BYPASSRLS"}, f"{mod.__name__}: BYPASSRLS path"


# --- 5 no-real-name scan + 6 SYNTH_* naming ---

_REAL_NAME_DENYLIST = (
    "bloomberg",
    "refinitiv",
    "reuters",
    "markit",
    "moody",
    "s&p",
    "fitch",
    "ice data",
    "blackrock",
    "vanguard",
    "fidelity",
    "goldman",
    "jpmorgan",
    "barclays",
    "nyse",
    "new york stock exchange",
    "xnys",
    "nasdaq",
    "apple",
    "tesla",
    "microsoft",
)


def test_no_real_vendor_or_client_names(seeded: Session) -> None:
    # (a) the synthetic module source carries no real vendor/firm/exchange NAME ...
    for mod in _SYN_MODULES:
        low = _module_path(mod).read_text().lower()
        for bad in _REAL_NAME_DENYLIST:
            assert bad not in low, f"{mod.__name__}: real name {bad!r}"
    # (b) ... and neither does any seeded code / name / label.
    labels: list[str] = []
    for inst in seeded.execute(select(Instrument)).scalars():
        labels += [inst.code, inst.name]
    for pf in seeded.execute(select(Portfolio)).scalars():
        labels += [pf.code, pf.name]
    for v in seeded.execute(select(Valuation)).scalars():
        labels += [x for x in [v.mark_source, v.currency_code] if x]
    blob = " ".join(labels).lower()
    for bad in _REAL_NAME_DENYLIST:
        assert bad not in blob, f"seeded data carries real name {bad!r}"


def test_synth_naming_and_no_real_identifiers(seeded: Session) -> None:
    for inst in seeded.execute(select(Instrument)).scalars():
        assert inst.code.startswith("SYNTH-"), inst.code
    for pf in seeded.execute(select(Portfolio)).scalars():
        assert pf.code.startswith("SYNTH-"), pf.code
    # synthetic ISIN uses the reserved ZZ prefix + a structurally-invalid (non-12-char) body.
    from irp_shared.reference.models import IdentifierXref

    isins = [
        x.value
        for x in seeded.execute(
            select(IdentifierXref).where(IdentifierXref.scheme == "ISIN")
        ).scalars()
    ]
    assert isins and all(v.startswith("ZZ") for v in isins)


# --- 7 FK integrity + 8 tenant isolation ---


def test_fk_integrity_and_single_tenant(seeded: Session) -> None:
    pf_ids = {p.id for p in seeded.execute(select(Portfolio)).scalars()}
    inst_ids = {i.id for i in seeded.execute(select(Instrument)).scalars()}
    # every position/valuation/transaction references a seeded portfolio + instrument, same tenant
    for p in seeded.execute(select(Position)).scalars():
        assert p.portfolio_id in pf_ids and p.instrument_id in inst_ids
        assert p.tenant_id == SYNTHETIC_TENANT_ID
    for v in seeded.execute(select(Valuation)).scalars():
        assert v.portfolio_id in pf_ids and v.instrument_id in inst_ids
        assert v.tenant_id == SYNTHETIC_TENANT_ID
    for txn in seeded.execute(select(Transaction)).scalars():
        assert txn.portfolio_id in pf_ids and txn.instrument_id in inst_ids
        assert txn.tenant_id == SYNTHETIC_TENANT_ID
    # all portfolios/instruments are the synthetic tenant's
    for pf in seeded.execute(select(Portfolio)).scalars():
        assert pf.tenant_id == SYNTHETIC_TENANT_ID


# --- 9 governed-service path: audit + lineage + verify_chain ---


def test_governed_path_audit_lineage_and_chain(seeded: Session) -> None:
    pos_id = synthetic_id("position:acct1:bond:v1")
    n_events = seeded.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == pos_id)
    ).scalar_one()
    assert n_events >= 1  # POSITION.CREATE emitted
    n_edges = seeded.execute(
        select(func.count()).select_from(LineageEdge).where(LineageEdge.target_entity_id == pos_id)
    ).scalar_one()
    assert n_edges >= 1  # MANUAL-source ORIGIN edge rooted
    assert (
        verify_chain(seeded, SYNTHETIC_TENANT_ID).ok is True
    )  # the per-tenant audit chain verifies


def test_synthetic_seed_produces_no_governed_derived_number(seeded: Session) -> None:
    # OD-P2-L: the synthetic seed is CAPTURE-ONLY — it produces ZERO calculation_run and ZERO
    # exposure_aggregate rows (governed derived numbers come ONLY from the AD-014/FW-RUN gate, never
    # from a seed). The no-compute AST fence (no Mult) is the static guard; this is the runtime
    # proof.
    from irp_shared.calc.models import CalculationRun
    from irp_shared.exposure import ExposureAggregate

    assert seeded.execute(select(func.count()).select_from(CalculationRun)).scalar_one() == 0
    assert seeded.execute(select(func.count()).select_from(ExposureAggregate)).scalar_one() == 0


# --- 10 never-auto-run guard + 11 non-synthetic refusal ---


def test_never_auto_run_not_wired_anywhere() -> None:
    root = pathlib.Path(builder_mod.__file__).resolve().parents[5]
    scan_dirs = [root / "migrations", root / "apps"]
    for d in scan_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text()
            assert "build_synthetic_dataset" not in text, f"{py} wires the synthetic seed"
            assert "irp_shared.synthetic" not in text, f"{py} imports the synthetic package"


def test_refuses_without_explicit_confirmation() -> None:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        with pytest.raises(SyntheticSeedRefused):
            build_synthetic_dataset(db, allow_synthetic_seed=False)  # no confirm
    finally:
        db.close()
        engine.dispose()


def test_refuses_without_env_gate(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("IRP_ALLOW_SYNTHETIC_SEED", raising=False)
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        with pytest.raises(SyntheticSeedRefused):
            build_synthetic_dataset(db, allow_synthetic_seed=True)  # confirm but no env gate
    finally:
        db.close()
        engine.dispose()


def test_refuses_non_synthetic_tenant(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("IRP_ALLOW_SYNTHETIC_SEED", "1")
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        with pytest.raises(SyntheticSeedRefused):
            build_synthetic_dataset(
                db, allow_synthetic_seed=True, tenant_id="not-the-synthetic-tenant"
            )
    finally:
        db.close()
        engine.dispose()


# --- 12-15 required edge-case scenarios ---


def test_reversal_with_non_null_price(seeded: Session) -> None:
    rev = seeded.get(Transaction, synthetic_id("txn:reverse:acct1:bond"))
    assert rev is not None and rev.txn_type == "REVERSAL"
    assert rev.reverses_transaction_id == synthetic_id("txn:buy:acct1:bond")
    assert rev.price is not None and rev.price > 0  # reversal carries the original's non-null price
    assert rev.quantity < 0  # negated


def test_position_correction_scenario(seeded: Session) -> None:
    # acct2/bond corrected from 500 → 550 (as-known): both axes reconstruct coherently.
    pf = synthetic_id("portfolio:SYNTH-ACCT-2")
    inst = synthetic_id("instrument:SYNTH-BOND-A")
    current = reconstruct_position_as_of(
        seeded,
        acting_tenant=SYNTHETIC_TENANT_ID,
        portfolio_id=pf,
        instrument_id=inst,
        valid_at=SEED_EPOCH.replace(hour=1),
    )
    assert current is not None and current.quantity.normalize() == 550  # latest known value
    assert current.restatement_reason is not None


def test_valuation_correction_and_multi_date(seeded: Session) -> None:
    pf = synthetic_id("portfolio:SYNTH-ACCT-1")
    inst = synthetic_id("instrument:SYNTH-BOND-A")
    vd1 = SEED_EPOCH.date()
    cur = reconstruct_valuation_as_of(
        seeded,
        acting_tenant=SYNTHETIC_TENANT_ID,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=vd1,
        valid_at=SEED_EPOCH.replace(hour=1),
    )
    assert cur is not None and cur.mark_value.normalize() == Decimal("101.75")  # corrected mark
    # a SECOND valuation_date exists (multi-date)
    dates = {
        v.valuation_date
        for v in seeded.execute(select(Valuation).where(Valuation.portfolio_id == pf)).scalars()
    }
    assert len(dates) >= 2


def test_stale_missing_valuation_scenario(seeded: Session) -> None:
    # acct1/equity has a position but NO valuation for any date → reconstruct returns None.
    pf = synthetic_id("portfolio:SYNTH-ACCT-1")
    eq = synthetic_id("instrument:SYNTH-EQ-B")
    assert (
        reconstruct_position_as_of(
            seeded,
            acting_tenant=SYNTHETIC_TENANT_ID,
            portfolio_id=pf,
            instrument_id=eq,
            valid_at=SEED_EPOCH.replace(hour=1),
        )
        is not None
    )
    missing = reconstruct_valuation_as_of(
        seeded,
        acting_tenant=SYNTHETIC_TENANT_ID,
        portfolio_id=pf,
        instrument_id=eq,
        valuation_date=SEED_EPOCH.date(),
        valid_at=SEED_EPOCH.replace(hour=1),
    )
    assert missing is None  # stale/missing valuation


# --- 18 no migration / no new entity ---


def test_prod_call_site_unchanged_when_seam_omitted() -> None:
    # A production call site passes NO seam args → the binder behaves exactly as before: a random
    # (non-synthetic, non-uuid5) id and a wall-clock system_from (NOT the SEED_EPOCH fixed clock).
    from irp_shared.portfolio import PortfolioActor, create_portfolio

    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        tenant = "11111111-1111-1111-1111-111111111111"
        pf = create_portfolio(
            db,
            tenant_id=tenant,
            code="PROD-PF",
            name="prod",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="prod-user"),
        )
        db.commit()
        # id is NOT a synthetic uuid5 and is NOT the SYNTH namespace value for this code
        assert pf.id != synthetic_id("portfolio:PROD-PF")
        # valid_from is the wall-clock default, NOT the injected SEED_EPOCH
        assert _naive(pf.valid_from) != _naive(SEED_EPOCH)
    finally:
        db.close()
        engine.dispose()


def test_no_migration_and_no_entity() -> None:
    pkg = pathlib.Path(builder_mod.__file__).parent
    assert not (pkg / "models.py").exists(), "synthetic must not define a persisted entity"
    root = pkg.resolve().parents[4]
    versions = root / "migrations" / "versions"
    for py in versions.glob("*.py"):
        assert "synthetic" not in py.read_text().lower(), f"{py} references synthetic"
    # P2-1..P2-6 own 0016..0021; P3-1 owns 0022_sensitivity; P3-2 owns 0023_factor_return; the
    # synthetic slice still adds no migration, so the next slot (0024+) must remain empty here.
    assert not list(versions.glob("0024*")), "no 0024 migration may be added by the synthetic slice"


# --- import-direction: synthetic -> {portfolio, position, valuation, transaction, reference, db} -


def test_import_direction() -> None:
    pkg = pathlib.Path(builder_mod.__file__).parent
    allowed = {"portfolio", "position", "valuation", "transaction", "reference", "db", "synthetic"}
    forbidden_roots = {"irp_backend", "irp_shared.models"}
    for py in pkg.glob("*.py"):
        for line in py.read_text().splitlines():
            line = line.strip()
            if not (line.startswith("from ") or line.startswith("import ")):
                continue
            for bad in forbidden_roots:
                assert bad not in line, f"{py.name} imports forbidden {bad}: {line}"
            if "irp_shared." in line:
                seg = line.split("irp_shared.")[1].split()[0].split(".")[0].rstrip(",")
                assert seg in allowed, f"{py.name} imports irp_shared.{seg}: {line}"
