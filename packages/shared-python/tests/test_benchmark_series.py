"""SQLite-local unit/behavior tests for P2-7 benchmark time series (ENT-052, captured INPUTS).

RLS + the no-append-only close-out live in ``test_benchmark_series_pg.py``; here we prove: the
``benchmark_level`` + ``benchmark_return`` FR single-row protocol (capture / supersede / correct /
reconstruct on both axes; date carried forward; current-head uniqueness; prior-content
immutability); the ``level_type`` / ``return_basis`` variant discriminators (coexisting series under
ONE benchmark); the binder finiteness (level: + positivity) guard + the ``> 0`` / ``> -1``
economic-sanity DQ gates; the RACE-SAFE (P3-C2 OD-E savepoint) DQ resolve-or-register; audit
(``MARKET.BENCHMARK_LEVEL_*``/``_RETURN_*``; per-op grain; no read audit); VENDOR_BENCHMARK ORIGIN
lineage REUSE; and the captured-input scope (NO calculation_run / model_version / computed returns).

Fixture realism (TD-1, 2026-07-09): index levels are O(10^2..10^4), daily returns are small
fractions; deliberately out-of-band values live ONLY in the guard/DQ-rejection tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.models import DataQualityRule
from irp_shared.dq.rules import RULE_TYPE_NOT_NULL
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.lineage.models import EDGE_KIND_ORIGIN, LineageEdge
from irp_shared.marketdata import (
    LEVEL_TYPE_PRICE_RETURN,
    LEVEL_TYPE_TOTAL_RETURN,
    RETURN_BASIS_PRICE,
    RETURN_BASIS_TOTAL,
    RETURN_TYPE_SIMPLE,
    BenchmarkActor,
    BenchmarkSeriesValueError,
    NoCurrentBenchmarkSeries,
    capture_benchmark,
    capture_benchmark_level,
    capture_benchmark_return,
    correct_benchmark_level,
    correct_benchmark_return,
    list_benchmark_levels,
    list_benchmark_returns,
    reconstruct_benchmark_level_as_of,
    reconstruct_benchmark_return_as_of,
    resolve_benchmark,
    supersede_benchmark_level,
    supersede_benchmark_return,
)
from irp_shared.marketdata import benchmark_series as bs_mod
from irp_shared.models import Base
from irp_shared.reference.models import Currency

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VA = datetime(2026, 6, 1, tzinfo=UTC)
VA2 = datetime(2026, 6, 15, tzinfo=UTC)
KNOWN = datetime(2030, 1, 1, tzinfo=UTC)
LD = date(2026, 5, 29)  # a real trading day (Friday)
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


def _ccy(db: Session, *codes: str) -> None:
    for code in codes or ("USD",):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _benchmark(db: Session, tenant: str, code: str = "SPX"):  # noqa: ANN202
    bm = capture_benchmark(
        db,
        benchmark_code=code,
        benchmark_source="SP_DJI",
        benchmark_currency="USD",
        acting_tenant=tenant,
        actor=ACTOR,
        index_family="S&P",
        valid_from=T0,
    )
    db.flush()
    return resolve_benchmark(db, bm.id, acting_tenant=tenant)


# ---------- benchmark_level (FR single-row) ----------


def test_capture_level(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    row = capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),  # a realistic S&P 500 index level
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    assert row.level_value == Decimal("4500.25") and row.level_type == LEVEL_TYPE_PRICE_RETURN
    assert row.record_version == 1 and row.benchmark_id == bm.id


def test_coexisting_level_types_under_one_benchmark(session: Session) -> None:
    """The level_type discriminator: PRICE_RETURN + TOTAL_RETURN coexist for the same
    (benchmark, level_date) — one definition carries its variants (OD-P2-7-C)."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_TOTAL_RETURN,
        level_value=Decimal("9800.50"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    session.flush()
    rows = list_benchmark_levels(session, acting_tenant=tenant, benchmark_id=bm.id)
    assert {r.level_type for r in rows} == {LEVEL_TYPE_PRICE_RETURN, LEVEL_TYPE_TOTAL_RETURN}
    assert len(rows) == 2


def test_level_supersede_correct_reconstruct(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    r1 = capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
        now=VA,
    )
    session.flush()
    # supersede (valid-time): a NEW valid version; level_date carried forward.
    r2 = supersede_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4512.75"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    session.flush()
    assert r2.record_version == 2 and r2.supersedes_id == r1.id and r2.level_date == LD
    # correct (system-time): as-known restatement; prior content NEVER mutated.
    r3 = correct_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4511.90"),
        restatement_reason="vendor restatement",
        acting_tenant=tenant,
        actor=ACTOR,
    )
    session.flush()
    assert r3.record_version == 3 and r3.restatement_reason == "vendor restatement"
    assert r2.level_value == Decimal("4512.75")  # prior content immutable
    # current head (both axes open) is r3.
    cur = reconstruct_benchmark_level_as_of(
        session,
        acting_tenant=tenant,
        benchmark_id=bm.id,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        valid_at=VA2,
        known_at=KNOWN,
    )
    assert cur is not None and cur.record_version == 3


def test_level_as_known_correction_is_bitemporal(session: Session) -> None:
    """A clean system-axis proof: a correction with an EXPLICIT known-time; an as-known read BEFORE
    it returns the original captured level, AFTER it returns the corrected level (same valid
    period)."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=VA,
        now=VA,
    )
    session.flush()
    known_before = datetime(2026, 6, 10, tzinfo=UTC)
    correct_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4499.80"),
        restatement_reason="vendor restatement",
        acting_tenant=tenant,
        actor=ACTOR,
        now=datetime(2026, 6, 20, tzinfo=UTC),
    )
    session.flush()
    old = reconstruct_benchmark_level_as_of(
        session,
        acting_tenant=tenant,
        benchmark_id=bm.id,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        valid_at=VA,
        known_at=known_before,
    )
    new = reconstruct_benchmark_level_as_of(
        session,
        acting_tenant=tenant,
        benchmark_id=bm.id,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        valid_at=VA,
        known_at=KNOWN,
    )
    assert old is not None and old.level_value == Decimal("4500.25")  # pre-correction view
    assert new is not None and new.level_value == Decimal("4499.80")  # corrected view


def test_level_current_head_uniqueness(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    session.flush()
    # review fold E4: assert the SPECIFIC IntegrityError on the partial-unique current head (a broad
    # Exception would pass on any unrelated error before the DB flush).
    with pytest.raises(IntegrityError):
        capture_benchmark_level(
            session,
            bm,
            level_date=LD,
            level_type=LEVEL_TYPE_PRICE_RETURN,
            level_value=Decimal("4600.00"),
            acting_tenant=tenant,
            actor=ACTOR,
            valid_from=T0,
        )
        session.flush()


# ---------- benchmark_return (FR single-row) ----------


def test_capture_return_and_bases_coexist(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    capture_benchmark_return(
        session,
        bm,
        return_date=LD,
        return_basis=RETURN_BASIS_PRICE,
        return_value=Decimal("0.0123"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    capture_benchmark_return(
        session,
        bm,
        return_date=LD,
        return_basis=RETURN_BASIS_TOTAL,
        return_value=Decimal("0.0131"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    session.flush()
    rows = list_benchmark_returns(session, acting_tenant=tenant, benchmark_id=bm.id)
    assert {r.return_basis for r in rows} == {RETURN_BASIS_PRICE, RETURN_BASIS_TOTAL}
    assert all(r.return_type == RETURN_TYPE_SIMPLE for r in rows)


def test_return_supersede_correct_reconstruct(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    r1 = capture_benchmark_return(
        session,
        bm,
        return_date=LD,
        return_basis=RETURN_BASIS_TOTAL,
        return_value=Decimal("0.0131"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    session.flush()
    r2 = supersede_benchmark_return(
        session,
        bm,
        return_date=LD,
        return_basis=RETURN_BASIS_TOTAL,
        return_value=Decimal("0.0125"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    session.flush()
    assert r2.record_version == 2 and r2.supersedes_id == r1.id
    r3 = correct_benchmark_return(
        session,
        bm,
        return_date=LD,
        return_basis=RETURN_BASIS_TOTAL,
        return_value=Decimal("0.0128"),
        restatement_reason="vendor restatement",
        acting_tenant=tenant,
        actor=ACTOR,
    )
    session.flush()
    assert r3.record_version == 3 and r1.return_value == Decimal("0.0131")  # prior immutable
    cur = reconstruct_benchmark_return_as_of(
        session,
        acting_tenant=tenant,
        benchmark_id=bm.id,
        return_date=LD,
        return_basis=RETURN_BASIS_TOTAL,
        valid_at=VA2,
        known_at=KNOWN,
    )
    assert cur is not None and cur.record_version == 3


# ---------- audit + lineage ----------


def test_audit_events_and_origin_lineage(session: Session) -> None:
    """capture=1 CREATE + 1 ORIGIN; supersede=2 (UPDATE + CREATE) + 1 new ORIGIN; correct=2
    (UPDATE + CORRECTION) + 1 ORIGIN. Values NEVER appear in the audit payload."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    supersede_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4512.75"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA2,
    )
    correct_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4511.90"),
        restatement_reason="vendor restatement",
        acting_tenant=tenant,
        actor=ACTOR,
    )
    session.flush()
    evs = [
        e.event_type
        for e in session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type.like("MARKET.BENCHMARK_LEVEL_%"))
            .order_by(AuditEvent.sequence_no)
        ).scalars()
    ]
    assert evs == [
        "MARKET.BENCHMARK_LEVEL_CREATE",  # capture
        "MARKET.BENCHMARK_LEVEL_UPDATE",  # supersede close-out
        "MARKET.BENCHMARK_LEVEL_CREATE",  # supersede new version
        "MARKET.BENCHMARK_LEVEL_UPDATE",  # correct close-out
        "MARKET.BENCHMARK_LEVEL_CORRECTION",  # corrected version
    ]
    # DC-2 audit payload never carries the captured value, but DOES carry the logical key
    # (review fold E3: pins spec.key_attrs — dropping level_type/return_basis from the grain would
    # silently strip it from the audit metadata + the DQ presence-check, making PR vs TR/NET
    # corrections indistinguishable).
    create = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.BENCHMARK_LEVEL_CREATE")
            .order_by(AuditEvent.sequence_no)
        )
        .scalars()
        .first()
    )
    assert create is not None
    assert create.after_value["level_type"] == LEVEL_TYPE_PRICE_RETURN  # the logical key IS present
    assert "level_date" in create.after_value
    for e in session.execute(
        select(AuditEvent).where(AuditEvent.event_type.like("MARKET.BENCHMARK_LEVEL_%"))
    ).scalars():
        assert "level_value" not in (e.after_value or {})
    # ORIGIN edges: one per NEW physical version (capture + supersede-new + correction = 3).
    origins = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.edge_kind == EDGE_KIND_ORIGIN,
                LineageEdge.target_entity_type == "benchmark_level",
            )
        )
        .scalars()
        .all()
    )
    assert len(origins) == 3


# ---------- binder guards + DQ gates ----------


def test_finiteness_and_positivity_guards(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    for bad in (Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN")):
        with pytest.raises(BenchmarkSeriesValueError):
            capture_benchmark_level(
                session,
                bm,
                level_date=LD,
                level_type=LEVEL_TYPE_PRICE_RETURN,
                level_value=bad,
                acting_tenant=tenant,
                actor=ACTOR,
            )
    # A non-positive index level is impossible — rejected pre-write.
    with pytest.raises(BenchmarkSeriesValueError):
        capture_benchmark_level(
            session,
            bm,
            level_date=LD,
            level_type=LEVEL_TYPE_PRICE_RETURN,
            level_value=Decimal("0"),
            acting_tenant=tenant,
            actor=ACTOR,
        )
    # A non-finite return is rejected too.
    with pytest.raises(BenchmarkSeriesValueError):
        capture_benchmark_return(
            session,
            bm,
            return_date=LD,
            return_basis=RETURN_BASIS_PRICE,
            return_value=Decimal("Infinity"),
            acting_tenant=tenant,
            actor=ACTOR,
        )
    assert _count(session, "benchmark_level") == 0 and _count(session, "benchmark_return") == 0


def test_vocab_guards(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    with pytest.raises(BenchmarkSeriesValueError):
        capture_benchmark_level(
            session,
            bm,
            level_date=LD,
            level_type="BOGUS",
            level_value=Decimal("4500.25"),
            acting_tenant=tenant,
            actor=ACTOR,
        )
    with pytest.raises(BenchmarkSeriesValueError):
        capture_benchmark_return(
            session,
            bm,
            return_date=LD,
            return_basis="BOGUS",
            return_value=Decimal("0.01"),
            acting_tenant=tenant,
            actor=ACTOR,
        )
    with pytest.raises(BenchmarkSeriesValueError):
        capture_benchmark_return(
            session,
            bm,
            return_date=LD,
            return_basis=RETURN_BASIS_PRICE,
            return_type="LOG",
            return_value=Decimal("0.01"),
            acting_tenant=tenant,
            actor=ACTOR,
        )


def test_dq_band_rejects_return_below_minus_one(session: Session) -> None:
    """A boundary/adversarial fixture: a simple return cannot be below -100% -> the DQ RANGE
    (> -1) fails -> DataQualityError -> whole-unit rollback."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    with pytest.raises(DataQualityError):
        capture_benchmark_return(
            session,
            bm,
            return_date=LD,
            return_basis=RETURN_BASIS_PRICE,
            return_value=Decimal("-2"),
            acting_tenant=tenant,
            actor=ACTOR,  # below -100%
        )
    session.rollback()
    assert _count(session, "benchmark_return") == 0
    # EXACT BOUNDARY (review fold E1): the band is strict ``> -1`` (min_inclusive=False), so a
    # -100% return (exactly -1) is REJECTED — a min_inclusive True regression would let it through.
    with pytest.raises(DataQualityError):
        capture_benchmark_return(
            session,
            bm,
            return_date=LD,
            return_basis=RETURN_BASIS_PRICE,
            return_value=Decimal("-1"),
            acting_tenant=tenant,
            actor=ACTOR,
        )
    session.rollback()
    # ...but a just-inside value (a -99% crash — plausible tail) is ACCEPTED.
    row = capture_benchmark_return(
        session,
        bm,
        return_date=LD,
        return_basis=RETURN_BASIS_PRICE,
        return_value=Decimal("-0.99"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    assert row.return_value == Decimal("-0.99")


def test_no_current_head_refusals(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    with pytest.raises(NoCurrentBenchmarkSeries):
        supersede_benchmark_level(
            session,
            bm,
            level_date=LD,
            level_type=LEVEL_TYPE_PRICE_RETURN,
            level_value=Decimal("4500.25"),
            acting_tenant=tenant,
            actor=ACTOR,
            effective_at=VA2,
        )
    with pytest.raises(NoCurrentBenchmarkSeries):
        correct_benchmark_return(
            session,
            bm,
            return_date=LD,
            return_basis=RETURN_BASIS_PRICE,
            return_value=Decimal("0.01"),
            restatement_reason="x",
            acting_tenant=tenant,
            actor=ACTOR,
        )


def test_cross_tenant_list_is_empty(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    session.flush()
    # a different tenant sees nothing (the explicit tenant predicate; RLS is proven on PG).
    assert list_benchmark_levels(session, acting_tenant=other, benchmark_id=bm.id) == []


# ---------- DQ resolve-or-register is race-safe (P3-C2 OD-E) ----------


def test_dq_rule_registered_once_and_idempotent(session: Session) -> None:
    """Two captures (different keys) of one tenant register the presence/value rules ONCE each
    (resolve-or-register), not per-row."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    capture_benchmark_level(
        session,
        bm,
        level_date=date(2026, 5, 28),
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4488.10"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    session.flush()
    codes = [
        r.code
        for r in session.execute(
            select(DataQualityRule).where(DataQualityRule.code.like("benchmark_level.%"))
        ).scalars()
    ]
    assert sorted(codes) == ["benchmark_level.required_fields", "benchmark_level.value_sanity"]


def test_dq_ensure_rule_uses_savepoint(session: Session, monkeypatch) -> None:  # noqa: ANN001
    """Guard: the resolve-or-register wraps its INSERT in a SAVEPOINT (begin_nested) — a regression
    removing it would let a first-registration IntegrityError abort the whole governed write (the
    P3-C2 OD-E lesson)."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    bm = _benchmark(session, tenant)
    called = {"nested": False}
    real = session.begin_nested

    def spy():  # noqa: ANN202
        called["nested"] = True
        return real()

    monkeypatch.setattr(session, "begin_nested", spy)
    capture_benchmark_level(
        session,
        bm,
        level_date=LD,
        level_type=LEVEL_TYPE_PRICE_RETURN,
        level_value=Decimal("4500.25"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    assert called["nested"], "the DQ resolve-or-register must wrap the INSERT in a SAVEPOINT"


def test_dq_race_collision_recovers_via_savepoint_no_dangling_audit(
    session: Session, monkeypatch
) -> None:  # noqa: ANN001
    """Behavioral proof of the RACE-RECOVERY branch (review fold C1/E6 — the spy test only proved
    begin_nested is CALLED; this forces the actual collision). A committed peer rule already exists;
    force ``_ensure_rule``'s INITIAL select to miss once (a stale snapshot) → the INSERT collides on
    ``uq_data_quality_rule_tenant_code`` → the savepoint rolls it back → the loser re-SELECTs the
    peer WITHOUT the IntegrityError escaping and WITHOUT a dangling DATA.DQ_RULE_DEFINE audit."""
    tenant = str(uuid.uuid4())
    _ccy(session, "USD")
    code = "benchmark_level.required_fields"

    def _call():  # noqa: ANN202
        return bs_mod._ensure_rule(
            session,
            tenant_id=tenant,
            actor=ACTOR,
            entity_type="benchmark_level",
            code=code,
            name="Benchmark level required fields present",
            rule_type=RULE_TYPE_NOT_NULL,
            params={"column": "present"},
        )

    peer = _call()  # the committed peer rule (the run that won the race)
    session.flush()
    audits_before = len(
        session.execute(select(AuditEvent).where(AuditEvent.event_type == "DATA.DQ_RULE_DEFINE"))
        .scalars()
        .all()
    )

    real_execute = session.execute
    state = {"forced": False}

    class _Miss:
        def scalar_one_or_none(self):  # noqa: ANN202
            return None

    def fake_execute(statement, *args, **kwargs):  # noqa: ANN001, ANN202
        if not state["forced"]:
            state["forced"] = True
            return _Miss()  # the stale-snapshot SELECT-miss
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(session, "execute", fake_execute)
    resolved = _call()  # collides on INSERT → savepoint → re-SELECT (real) → peer
    monkeypatch.undo()

    assert resolved.id == peer.id  # recovered to the peer; no exception escaped
    n_rules = len(
        session.execute(select(DataQualityRule).where(DataQualityRule.code == code)).scalars().all()
    )
    assert n_rules == 1  # the loser's INSERT was unwound
    audits_after = len(
        session.execute(select(AuditEvent).where(AuditEvent.event_type == "DATA.DQ_RULE_DEFINE"))
        .scalars()
        .all()
    )
    assert audits_after == audits_before  # NO dangling audit from the losing branch


def test_series_spec_bands_and_grain_pinned() -> None:
    """Fence (review fold E3/E5): pin each spec's logical-key grain + DQ band so a silent drift —
    dropping ``return_basis`` from the return grain, or flipping a band's inclusivity/column — fails
    here even where the binder positivity guard shadows the level DQ gate at runtime."""
    assert bs_mod._LEVEL_SPEC.key_attrs == ("level_date", "level_type")
    assert bs_mod._RETURN_SPEC.key_attrs == ("return_date", "return_type", "return_basis")
    assert bs_mod._LEVEL_SPEC.value_rule_params == {
        "column": "level_value",
        "min": 0,
        "min_inclusive": False,
    }
    assert bs_mod._RETURN_SPEC.value_rule_params == {
        "column": "return_value",
        "min": -1,
        "min_inclusive": False,
    }


def _count(db: Session, table: str) -> int:
    from sqlalchemy import text

    return db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_migration_head_is_benchmark_series() -> None:
    import pathlib

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0032_benchmark_relative"
    assert script.get_revision("0029_benchmark_series").down_revision == "0028_var_historical"
