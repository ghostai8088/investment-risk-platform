"""SQLite-local unit/behavior tests for P2-6 benchmark + benchmark_constituent (captured benchmark/
index data).

RLS is a no-op on SQLite (the FORCE-RLS isolation lives in ``test_benchmark_pg.py``); here we prove:
the EV definition (create / in-place update / record_version / REFERENCE.* audit + identity
uniqueness); the FR membership set protocol (capture / supersede / correct / both-axes
``reconstruct_membership_as_of`` / current-head uniqueness / prior-row content-immutability /
effective_date carried forward / set atomicity); the instrument NOT-NULL FK + constituent-currency
resolution; the weight ``RANGE [0, 1]`` DQ gate (required-field + sanity, fail-closed) + empty-set
reject; the split audit grain (``REFERENCE.*`` definition, ``MARKET.BENCHMARK_CONSTITUENT_*``
for the membership — one event per set, no emit on read); VENDOR_BENCHMARK ORIGIN lineage
(benchmark-targeted, per version) + fail-closed rollback; entitlement parity; and the load-bearing
scope fences (captured-not-computed; no benchmark_level/return; neither table append-only).
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
from irp_shared.audit.service import verify_chain
from irp_shared.db.mixins import EffectiveDatedMixin, FullReproducibleMixin
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, LineageEdge
from irp_shared.marketdata import (
    Benchmark,
    BenchmarkActor,
    BenchmarkConstituent,
    BenchmarkNotVisible,
    BenchmarkValueError,
    ConstituentInput,
    NoCurrentMembership,
    capture_benchmark,
    capture_membership,
    correct_membership,
    reconstruct_membership_as_of,
    resolve_benchmark,
    supersede_membership,
    update_benchmark,
)
from irp_shared.marketdata import benchmark as benchmark_mod
from irp_shared.models import Base
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.reference.models import Currency, Instrument
from irp_shared.reference.service import CurrencyNotVisible

VF = datetime(2020, 1, 1, tzinfo=UTC)
ED = date(2026, 3, 31)
VA = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
VA2 = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
VA3 = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
KA = datetime(2030, 1, 1, tzinfo=UTC)
ACTOR = BenchmarkActor(actor_id="steward")


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
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=VF))
    db.flush()


def _seed_instruments(db: Session, tenant: str, n: int = 3) -> list[str]:
    ids: list[str] = []
    for i in range(n):
        inst = Instrument(
            tenant_id=tenant,
            code=f"INS{i}",
            name=f"Instrument {i}",
            asset_class="EQUITY",
            instrument_type="EQUITY",
            valid_from=VF,
            record_version=1,
        )
        db.add(inst)
        db.flush()
        ids.append(inst.id)
    return ids


def _capture_benchmark(db: Session, tenant: str, source: str = "SP_DJI", **kw) -> Benchmark:  # noqa: ANN003
    return capture_benchmark(
        db,
        benchmark_code=kw.pop("benchmark_code", "SPX"),
        benchmark_source=source,
        benchmark_currency="USD",
        acting_tenant=tenant,
        actor=ACTOR,
        index_family="S&P",
        **kw,
    )


def _cons(ids: list[str], weights: list[str]) -> list[ConstituentInput]:
    return [
        ConstituentInput(instrument_id=i, weight=Decimal(w))
        for i, w in zip(ids, weights, strict=False)
    ]


# ---------- EV definition (REFERENCE.* audit) ----------


def test_benchmark_create_and_update_in_place(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    bm = _capture_benchmark(session, t)
    session.commit()
    assert bm.record_version == 1 and bm.benchmark_name is None
    update_benchmark(session, bm, acting_tenant=t, actor=ACTOR, benchmark_name="S&P 500")
    session.commit()
    # EV in-place: same physical row, bumped version (one row, not two).
    assert bm.record_version == 2 and bm.benchmark_name == "S&P 500"
    assert session.execute(select(func.count()).select_from(Benchmark)).scalar_one() == 1


def test_benchmark_identity_uniqueness(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    _capture_benchmark(session, t, source="SP_DJI")
    session.commit()
    # same (tenant, code, source) violates the EV identity unique constraint.
    with pytest.raises(IntegrityError):
        _capture_benchmark(session, t, source="SP_DJI")
    session.rollback()
    # a different source coexists (multi-vendor).
    _capture_benchmark(session, t, source="BLOOMBERG")
    session.commit()
    assert session.execute(select(func.count()).select_from(Benchmark)).scalar_one() == 2


def test_benchmark_update_rejects_non_updatable_and_unknown_currency(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    bm = _capture_benchmark(session, t)
    session.commit()
    with pytest.raises(BenchmarkValueError):
        update_benchmark(session, bm, acting_tenant=t, actor=ACTOR, benchmark_code="NEW")
    session.rollback()
    with pytest.raises(CurrencyNotVisible):
        update_benchmark(session, bm, acting_tenant=t, actor=ACTOR, benchmark_currency="ZZZ")
    session.rollback()


def test_benchmark_unknown_currency_fails_closed(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session, "EUR")  # no USD
    with pytest.raises(CurrencyNotVisible):
        _capture_benchmark(session, t)
    session.rollback()
    assert session.execute(select(func.count()).select_from(Benchmark)).scalar_one() == 0


def test_resolve_benchmark_cross_tenant_fails_closed(session: Session) -> None:
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_currency(session)
    bm = _capture_benchmark(session, a)
    session.commit()
    assert resolve_benchmark(session, bm.id, acting_tenant=a).id == bm.id
    with pytest.raises(BenchmarkNotVisible):
        resolve_benchmark(session, bm.id, acting_tenant=b)


# ---------- FR membership set protocol ----------


def test_membership_capture_supersede_correct_reconstruct_both_axes(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 3)
    bm = _capture_benchmark(session, t)
    session.commit()

    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids[:2], ["0.6", "0.4"]),
        acting_tenant=t,
        actor=ACTOR,
        now=VA,
    )
    session.commit()
    # supersede (drop ids[1], add ids[2])
    supersede_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons([ids[0], ids[2]], ["0.5", "0.5"]),
        acting_tenant=t,
        actor=ACTOR,
        effective_at=VA2,
        now=VA2,
    )
    session.commit()
    # correct (restate weights, same valid period)
    correct_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons([ids[0], ids[2]], ["0.55", "0.45"]),
        restatement_reason="vendor restatement",
        acting_tenant=t,
        actor=ACTOR,
        now=VA3,
    )
    session.commit()

    # current view = the corrected set
    cur = reconstruct_membership_as_of(
        session, acting_tenant=t, benchmark_id=bm.id, effective_date=ED, valid_at=VA3
    )
    assert sorted(str(r.weight) for r in cur) == ["0.450000000000", "0.550000000000"]
    # as-of the ORIGINAL capture as-known-before-supersede = the first set
    orig = reconstruct_membership_as_of(
        session,
        acting_tenant=t,
        benchmark_id=bm.id,
        effective_date=ED,
        valid_at=VA,
        known_at=datetime(2026, 3, 31, 13, 0, tzinfo=UTC),
    )
    assert sorted(str(r.weight) for r in orig) == ["0.400000000000", "0.600000000000"]
    assert {r.instrument_id for r in orig} == {ids[0], ids[1]}  # the original members


def test_membership_effective_date_carried_forward_and_distinct_from_valid_from(
    session: Session,
) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 2)
    bm = _capture_benchmark(session, t)
    session.commit()
    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.5", "0.5"]),
        acting_tenant=t,
        actor=ACTOR,
        now=VA,
    )
    session.commit()
    supersede_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.6", "0.4"]),
        acting_tenant=t,
        actor=ACTOR,
        effective_at=VA2,
        now=VA2,
    )
    session.commit()
    rows = session.execute(select(BenchmarkConstituent)).scalars().all()
    # effective_date is the same logical key on every version; valid_from advances on supersede.
    # (SQLite returns naive datetimes for DateTime(timezone=True), so compare distinctness, not the
    # exact tz-aware values — the PG isolation is proven in test_benchmark_pg.py.)
    assert {r.effective_date for r in rows} == {ED}
    assert len(rows) == 4 and len({r.valid_from for r in rows}) == 2  # capture VA vs supersede VA2


def test_membership_content_immutable_on_correction(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 2)
    bm = _capture_benchmark(session, t)
    session.commit()
    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.6", "0.4"]),
        acting_tenant=t,
        actor=ACTOR,
        now=VA,
    )
    session.commit()
    prior = sorted(
        reconstruct_membership_as_of(
            session,
            acting_tenant=t,
            benchmark_id=bm.id,
            effective_date=ED,
            valid_at=VA,
            known_at=datetime(2026, 3, 31, 13, 0, tzinfo=UTC),
        ),
        key=lambda r: r.instrument_id,
    )
    snap = [(r.id, r.instrument_id, str(r.weight), r.effective_date) for r in prior]
    correct_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.7", "0.3"]),
        restatement_reason="restate",
        acting_tenant=t,
        actor=ACTOR,
        now=VA3,
    )
    session.commit()
    # the prior (now-closed) rows: instrument/weight/effective_date unchanged; only system_to set.
    for rid, inst, weight, eff in snap:
        row = session.get(BenchmarkConstituent, rid)
        assert row.instrument_id == inst and str(row.weight) == weight and row.effective_date == eff
        assert row.system_to is not None
    # reconstruct at the OLD known_at still returns the original weights.
    early = reconstruct_membership_as_of(
        session,
        acting_tenant=t,
        benchmark_id=bm.id,
        effective_date=ED,
        valid_at=VA,
        known_at=datetime(2026, 3, 31, 13, 0, tzinfo=UTC),
    )
    assert sorted(str(r.weight) for r in early) == ["0.400000000000", "0.600000000000"]


def test_membership_current_head_uniqueness(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 1)
    bm = _capture_benchmark(session, t)
    session.commit()
    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["1.0"]),
        acting_tenant=t,
        actor=ACTOR,
        now=VA,
    )
    session.commit()
    # a second open row for the SAME (benchmark, instrument, eff_date) violates the partial-uq.
    session.add(
        BenchmarkConstituent(
            tenant_id=t,
            benchmark_id=bm.id,
            instrument_id=ids[0],
            effective_date=ED,
            weight=Decimal("0.5"),
            valid_from=VA2,
            system_from=VA2,
            record_version=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_membership_supersede_correct_require_open_set(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 1)
    bm = _capture_benchmark(session, t)
    session.commit()
    with pytest.raises(NoCurrentMembership):
        supersede_membership(
            session,
            bm,
            effective_date=ED,
            constituents=_cons(ids, ["1.0"]),
            acting_tenant=t,
            actor=ACTOR,
            effective_at=VA2,
        )
    session.rollback()
    with pytest.raises(NoCurrentMembership):
        correct_membership(
            session,
            bm,
            effective_date=ED,
            constituents=_cons(ids, ["1.0"]),
            restatement_reason="x",
            acting_tenant=t,
            actor=ACTOR,
        )
    session.rollback()


# ---------- instrument FK + constituent currency ----------


def test_membership_unknown_instrument_fails_closed(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    bm = _capture_benchmark(session, t)
    session.commit()
    with pytest.raises(InstrumentNotVisible):
        capture_membership(
            session,
            bm,
            effective_date=ED,
            constituents=[ConstituentInput(str(uuid.uuid4()), Decimal("1.0"))],
            acting_tenant=t,
            actor=ACTOR,
        )
    session.rollback()
    assert session.execute(select(func.count()).select_from(BenchmarkConstituent)).scalar_one() == 0


def test_membership_cross_tenant_instrument_fails_closed(session: Session) -> None:
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_currency(session)
    other = _seed_instruments(session, b, 1)  # instrument owned by tenant b
    bm = _capture_benchmark(session, a)
    session.commit()
    with pytest.raises(InstrumentNotVisible):
        capture_membership(
            session,
            bm,
            effective_date=ED,
            constituents=[ConstituentInput(other[0], Decimal("1.0"))],
            acting_tenant=a,
            actor=ACTOR,
        )
    session.rollback()


def test_membership_constituent_currency_resolved(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session, "USD", "EUR")
    ids = _seed_instruments(session, t, 1)
    bm = _capture_benchmark(session, t)
    session.commit()
    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=[ConstituentInput(ids[0], Decimal("1.0"), constituent_currency="EUR")],
        acting_tenant=t,
        actor=ACTOR,
    )
    session.commit()
    with pytest.raises(CurrencyNotVisible):
        capture_membership(
            session,
            bm,
            effective_date=date(2026, 6, 30),
            constituents=[ConstituentInput(ids[0], Decimal("1.0"), constituent_currency="ZZZ")],
            acting_tenant=t,
            actor=ACTOR,
        )
    session.rollback()


# ---------- DQ gate (weight RANGE [0,1]; required-field; empty set) ----------


def test_weight_range_dq(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 1)
    bm = _capture_benchmark(session, t)
    session.commit()

    def _cap(weight: str, eff: date) -> None:
        capture_membership(
            session,
            bm,
            effective_date=eff,
            constituents=[ConstituentInput(ids[0], Decimal(weight))],
            acting_tenant=t,
            actor=ACTOR,
        )

    with pytest.raises(DataQualityError):  # weight < 0
        _cap("-0.01", date(2026, 1, 1))
    session.rollback()
    with pytest.raises(DataQualityError):  # weight > 1
        _cap("1.5", date(2026, 1, 2))
    session.rollback()
    _cap("0", date(2026, 1, 3))  # inclusive band: 0 and 1 accepted
    session.commit()
    _cap("1", date(2026, 1, 4))
    session.commit()
    assert session.execute(select(func.count()).select_from(BenchmarkConstituent)).scalar_one() == 2


def test_required_field_reject_and_dq_rollback(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 2)
    bm = _capture_benchmark(session, t)
    session.commit()
    # a None weight hits the DB NOT NULL at the set flush (before the DQ gate) — IntegrityError.
    with pytest.raises(IntegrityError):
        capture_membership(
            session,
            bm,
            effective_date=ED,
            constituents=[ConstituentInput(ids[0], None)],  # type: ignore[arg-type]
            acting_tenant=t,
            actor=ACTOR,
        )
    session.rollback()
    # a weight-band failure rolls back the WHOLE set (no rows, no edge, no event).
    with pytest.raises(DataQualityError):
        capture_membership(
            session,
            bm,
            effective_date=ED,
            constituents=_cons(ids, ["0.5", "2.0"]),
            acting_tenant=t,
            actor=ACTOR,
        )
    session.rollback()
    assert session.execute(select(func.count()).select_from(BenchmarkConstituent)).scalar_one() == 0
    assert (
        session.execute(
            select(func.count())
            .select_from(LineageEdge)
            .where(LineageEdge.target_entity_type == "benchmark")
        ).scalar_one()
        == 1  # only the definition-create edge survives
    )


def test_empty_membership_set_rejected(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    bm = _capture_benchmark(session, t)
    session.commit()
    with pytest.raises(BenchmarkValueError):  # before any write — the RANGE gate is non-vacuous
        capture_membership(
            session, bm, effective_date=ED, constituents=[], acting_tenant=t, actor=ACTOR
        )
    session.rollback()


# ---------- audit grain (split family; one event per set; no read) ----------


def test_audit_split_family_and_per_op_grain(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 3)
    bm = _capture_benchmark(session, t)
    session.commit()
    update_benchmark(session, bm, acting_tenant=t, actor=ACTOR, benchmark_name="S&P 500")
    session.commit()
    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids[:2], ["0.6", "0.4"]),
        acting_tenant=t,
        actor=ACTOR,
    )
    session.commit()
    supersede_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons([ids[0], ids[2]], ["0.5", "0.5"]),
        acting_tenant=t,
        actor=ACTOR,
        effective_at=VA2,
    )
    session.commit()
    correct_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons([ids[0], ids[2]], ["0.55", "0.45"]),
        restatement_reason="restate",
        acting_tenant=t,
        actor=ACTOR,
    )
    session.commit()

    def _c(ev: str) -> int:
        return session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == ev)
        ).scalar_one()

    # the EV definition uses REFERENCE.* (NOT MARKET.BENCHMARK_*); membership uses MARKET.*.
    assert _c("REFERENCE.CREATE") == 1 and _c("REFERENCE.UPDATE") == 1
    assert _c("MARKET.BENCHMARK_CONSTITUENT_CREATE") == 2  # capture + supersede-new
    assert _c("MARKET.BENCHMARK_CONSTITUENT_UPDATE") == 2  # supersede + correct close-outs
    assert _c("MARKET.BENCHMARK_CONSTITUENT_CORRECTION") == 1
    # the definition is NOT in the MARKET.* family.
    assert _c("MARKET.BENCHMARK_CREATE") == 0 and _c("MARKET.BENCHMARK_UPDATE") == 0
    assert verify_chain(session, t).ok


def test_one_event_per_set_independent_of_count_and_no_read(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 3)
    bm = _capture_benchmark(session, t)
    session.commit()
    # a 1-constituent set and a 3-constituent set each emit exactly ONE CONSTITUENT_CREATE.
    capture_membership(
        session,
        bm,
        effective_date=date(2026, 1, 1),
        constituents=_cons(ids[:1], ["1.0"]),
        acting_tenant=t,
        actor=ACTOR,
    )
    capture_membership(
        session,
        bm,
        effective_date=date(2026, 2, 1),
        constituents=_cons(ids, ["0.5", "0.3", "0.2"]),
        acting_tenant=t,
        actor=ACTOR,
    )
    session.commit()
    before = session.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    assert (
        session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.BENCHMARK_CONSTITUENT_CREATE")
        ).scalar_one()
        == 2  # one per set, NOT per constituent (1 + 3 constituents)
    )
    # reads emit NO event.
    reconstruct_membership_as_of(
        session, acting_tenant=t, benchmark_id=bm.id, effective_date=date(2026, 1, 1), valid_at=KA
    )
    resolve_benchmark(session, bm.id, acting_tenant=t)
    assert session.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == before


# ---------- lineage (VENDOR_BENCHMARK ORIGIN; benchmark-targeted) ----------


def test_vendor_benchmark_lineage_per_version(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 2)
    bm = _capture_benchmark(session, t)  # definition create -> 1 edge
    session.commit()
    update_benchmark(session, bm, acting_tenant=t, actor=ACTOR, benchmark_name="N")  # update -> 0
    session.commit()
    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.5", "0.5"]),
        acting_tenant=t,
        actor=ACTOR,
    )  # capture -> 1
    session.commit()
    supersede_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.6", "0.4"]),
        acting_tenant=t,
        actor=ACTOR,
        effective_at=VA2,
    )  # supersede -> 1 new (close-out roots 0)
    session.commit()
    correct_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.7", "0.3"]),
        restatement_reason="r",
        acting_tenant=t,
        actor=ACTOR,
    )  # correct -> 1 new (close-out roots 0)
    session.commit()

    edges = (
        session.execute(select(LineageEdge).where(LineageEdge.target_entity_type == "benchmark"))
        .scalars()
        .all()
    )
    assert len(edges) == 4  # def-create + capture + supersede-new + correct-new
    assert all(e.edge_kind == EDGE_KIND_ORIGIN for e in edges)
    assert all(e.target_entity_id == bm.id for e in edges)
    # ZERO edges target benchmark_constituent (covered transitively via benchmark_id).
    assert (
        session.execute(
            select(func.count())
            .select_from(LineageEdge)
            .where(LineageEdge.target_entity_type == "benchmark_constituent")
        ).scalar_one()
        == 0
    )


# ---------- entitlement parity ----------


def test_marketdata_permissions_grants_as_ratified() -> None:
    # benchmark REUSES marketdata.view/.ingest — NO new permission.
    view = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.view" in codes}
    ingest = {r for r, codes in ROLE_TEMPLATES.items() if "marketdata.ingest" in codes}
    assert view == {"data_steward", "risk_analyst_1l", "risk_manager_2l", "platform_admin"}
    assert ingest == {"data_steward", "platform_admin"}
    assert "auditor_3l" not in view and "auditor_3l" not in ingest


# ---------- temporal class + append-only registry ----------


def test_temporal_classes_neither_append_only() -> None:
    assert "benchmark" in Base.metadata.tables
    assert "benchmark_constituent" in Base.metadata.tables
    assert issubclass(Benchmark, EffectiveDatedMixin)  # EV definition
    assert issubclass(BenchmarkConstituent, FullReproducibleMixin)  # FR membership
    # the 0021 migration puts NEITHER table in APPEND_ONLY_TABLES (a difference from curve_point).
    root = pathlib.Path(benchmark_mod.__file__)
    while not (root / "alembic.ini").exists():
        root = root.parent
    mig = (root / "migrations" / "versions" / "0021_benchmark.py").read_text()
    assert "APPEND_ONLY_TABLES: tuple[str, ...] = ()" in mig
    assert "benchmark_constituent" not in mig.split("APPEND_ONLY_TABLES")[1].split("\n")[0]


def test_benchmark_constituent_fr_close_out_update_succeeds(session: Session) -> None:
    # FR (NOT append-only) — a current-head row's valid_to/system_to CAN be UPDATEd (the close-out);
    # there is no P0001 trigger / ORM guard (unlike curve_point).
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 1)
    bm = _capture_benchmark(session, t)
    session.commit()
    rows = capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["1.0"]),
        acting_tenant=t,
        actor=ACTOR,
    )
    session.commit()
    rows[0].valid_to = VA2  # close-out UPDATE succeeds (no append-only guard)
    session.flush()
    session.commit()
    assert session.get(BenchmarkConstituent, rows[0].id).valid_to == VA2


# ---------- scope fences (captured-not-computed) ----------


def test_benchmark_module_no_analytics_symbols() -> None:
    # captured-not-computed: the binder imports no calc/exposure/snapshot/convert, has no
    # multiplication/subtraction, and DEFINES/CALLS no analytics/risk func. CODE IDENTIFIERS
    # (funcdef + call names) are checked, NOT raw text (so docstring negations don't trip it).
    forbidden_imports = {"calc", "exposure", "snapshot", "convert"}
    risk_verbs = (
        "active_return",
        "active_risk",
        "tracking_error",
        "attribution",
        "performance",
        "covariance",
        "factor_model",
        "value_at_risk",
        "expected_shortfall",
        "scenario",
        "return_calc",
        "interpolat",
    )
    tree = ast.parse(pathlib.Path(benchmark_mod.__file__).read_text())
    called_or_defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not (forbidden_imports & set(node.module.split("."))), node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not (forbidden_imports & set(alias.name.split("."))), alias.name
        # No multiplication anywhere in the binder — capture computes nothing (no weight/return/
        # active-weight math). (Set difference `-` for attribute validation is legitimate and uses
        # ast.Sub on set operands, so only ast.Mult is fenced — the curve-precedent choice.)
        if isinstance(node, ast.BinOp):
            assert not isinstance(node.op, ast.Mult), "no ast.Mult (no weight/return math)"
        if isinstance(node, ast.FunctionDef):
            called_or_defined.add(node.name.lower())
        elif isinstance(node, ast.Call):
            func_node = node.func
            if isinstance(func_node, ast.Name):
                called_or_defined.add(func_node.id.lower())
            elif isinstance(func_node, ast.Attribute):
                called_or_defined.add(func_node.attr.lower())
    blob = " ".join(called_or_defined)
    for verb in risk_verbs:
        assert verb not in blob, verb


def test_benchmark_level_and_return_tables_realized() -> None:
    # P2-7 realized the levels/returns as the net-new ENT-052 (OD-P2-6-K discharged).
    assert "benchmark_level" in Base.metadata.tables
    assert "benchmark_return" in Base.metadata.tables


# ---------- review folds: TR-08 justification + DC-2-only after_value + no-op update ----------


def test_correction_justification_and_dc2_only_after_value(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 2)
    bm = _capture_benchmark(session, t)
    session.commit()
    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.6", "0.4"]),
        acting_tenant=t,
        actor=ACTOR,
        now=VA,
    )
    session.commit()
    correct_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.7", "0.3"]),
        restatement_reason="vendor fix",
        acting_tenant=t,
        actor=ACTOR,
        now=VA3,
    )
    session.commit()
    corr = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "MARKET.BENCHMARK_CONSTITUENT_CORRECTION")
    ).scalar_one()
    # TR-08: the restatement_reason lands on the canonical justification field.
    assert corr.justification == "vendor fix"
    # after_value carries ONLY DC-2 metadata — never the constituent payload (instrument_id/weight).
    assert set(corr.after_value) == {
        "benchmark_code",
        "benchmark_source",
        "benchmark_currency",
        "effective_date",
        "constituent_count",
    }
    blob = str(corr.after_value)
    assert "instrument_id" not in blob and "weight" not in blob and ids[0] not in blob


def test_dq_failure_rolls_back_supersede_whole_unit(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    ids = _seed_instruments(session, t, 2)
    bm = _capture_benchmark(session, t)
    session.commit()
    capture_membership(
        session,
        bm,
        effective_date=ED,
        constituents=_cons(ids, ["0.6", "0.4"]),
        acting_tenant=t,
        actor=ACTOR,
        now=VA,
    )
    session.commit()
    # a bad weight on SUPERSEDE fails closed -> the WHOLE unit rolls back: the close-out UPDATE is
    # undone (the prior set stays open), no new rows, no extra audit events persist.
    with pytest.raises(DataQualityError):
        supersede_membership(
            session,
            bm,
            effective_date=ED,
            constituents=_cons(ids, ["0.5", "2.0"]),
            acting_tenant=t,
            actor=ACTOR,
            effective_at=VA2,
        )
    session.rollback()
    open_rows = (
        session.execute(
            select(BenchmarkConstituent).where(
                BenchmarkConstituent.valid_to.is_(None), BenchmarkConstituent.system_to.is_(None)
            )
        )
        .scalars()
        .all()
    )
    assert len(open_rows) == 2 and {str(r.weight) for r in open_rows} == {
        "0.600000000000",
        "0.400000000000",
    }
    assert session.execute(select(func.count()).select_from(BenchmarkConstituent)).scalar_one() == 2
    # no UPDATE/CORRECTION event survived the rollback (only the original capture's CREATE).
    assert (
        session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.BENCHMARK_CONSTITUENT_UPDATE")
        ).scalar_one()
        == 0
    )


def test_noop_update_does_not_bump_or_emit(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    bm = _capture_benchmark(session, t)
    session.commit()
    update_benchmark(session, bm, acting_tenant=t, actor=ACTOR)  # no changes
    session.commit()
    assert bm.record_version == 1  # no version bump
    assert (
        session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "REFERENCE.UPDATE")
        ).scalar_one()
        == 0  # no no-op event
    )


def test_update_null_currency_rejected(session: Session) -> None:
    t = str(uuid.uuid4())
    _seed_currency(session)
    bm = _capture_benchmark(session, t)
    session.commit()
    with pytest.raises(BenchmarkValueError):  # NOT NULL — fail-closed 422, never an unmapped 500
        update_benchmark(session, bm, acting_tenant=t, actor=ACTOR, benchmark_currency=None)
    session.rollback()
