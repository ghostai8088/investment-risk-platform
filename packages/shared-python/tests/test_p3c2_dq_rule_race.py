"""P3-C2 OD-E: the DQ-rule first-registration race — savepoint resolve-or-register.

The race (recorded as the P3-C1 residual): two concurrent FIRST governed runs of a tenant both
SELECT-miss then both INSERT the same ``(tenant_id, code)``; one hits
``uq_data_quality_rule_tenant_code``. Pre-fix, that IntegrityError aborted the whole
co-transactional run (a 500). Post-fix, ``ensure_presence_rule`` wraps the INSERT in a SAVEPOINT
and, on the collision, rolls back ONLY the failed INSERT and re-SELECTs the peer's committed rule.

The savepoint-catch branch is reachable ONLY when the initial SELECT misses AND the INSERT
collides — a genuine cross-transaction interleave. This test reproduces it deterministically in
one process by forcing the function's INITIAL select to miss exactly once (simulating a stale
snapshot) while a real conflicting rule already exists, so the INSERT raises a real
IntegrityError and the savepoint recovery runs for real.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq import gates as gates_mod
from irp_shared.dq.gates import ensure_presence_rule
from irp_shared.dq.models import DataQualityRule
from irp_shared.models import Base

_CODE = "risk.test.completeness"


def _session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return make_session_factory(engine)()


def _ensure(db: Session, tenant: str):  # noqa: ANN202
    return ensure_presence_rule(
        db,
        tenant_id=tenant,
        code=_CODE,
        name="test presence",
        target_entity_type="exposure_aggregate",
        actor_id="a",
    )


def test_first_registration_creates_then_resolves_idempotently() -> None:
    """Happy path: first call creates the rule; a second call SELECT-hits and returns the same
    rule (no second INSERT, no second audit)."""
    db = _session()
    tenant = str(uuid.uuid4())
    first = _ensure(db, tenant)
    db.flush()
    again = _ensure(db, tenant)
    assert again.id == first.id
    n_rules = len(
        db.execute(select(DataQualityRule).where(DataQualityRule.code == _CODE)).scalars().all()
    )
    assert n_rules == 1
    db.close()


def test_race_collision_recovers_via_savepoint_no_dangling_audit(monkeypatch) -> None:  # noqa: ANN001
    """Force the initial SELECT to miss once (a stale snapshot) against an existing rule: the
    INSERT collides, the savepoint rolls it back, and the peer rule is resolved WITHOUT the
    IntegrityError escaping and WITHOUT a dangling DATA.DQ_RULE_DEFINE audit row from the loser."""
    db = _session()
    tenant = str(uuid.uuid4())
    # A committed peer rule already exists (the run that won the race).
    peer = _ensure(db, tenant)
    db.flush()
    audits_before = len(
        db.execute(select(AuditEvent).where(AuditEvent.event_type == "DATA.DQ_RULE_DEFINE"))
        .scalars()
        .all()
    )

    # Force ONLY the next call's INITIAL select (inside ensure_presence_rule) to return a miss,
    # driving the code into the INSERT path against the existing (tenant, code) → real collision.
    real_execute = db.execute
    state = {"forced": False}

    class _Miss:
        def scalar_one_or_none(self):  # noqa: ANN202
            return None

    def fake_execute(statement, *args, **kwargs):  # noqa: ANN001, ANN202
        if not state["forced"]:
            state["forced"] = True
            return _Miss()  # the stale-snapshot SELECT-miss
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", fake_execute)
    resolved = _ensure(db, tenant)  # collides on INSERT → savepoint → re-SELECT (real) → peer
    monkeypatch.undo()

    assert resolved.id == peer.id  # recovered to the peer, no exception escaped
    # Still exactly one rule; NO dangling audit from the losing INSERT (savepoint unwound it).
    n_rules = len(
        db.execute(select(DataQualityRule).where(DataQualityRule.code == _CODE)).scalars().all()
    )
    assert n_rules == 1
    audits_after = len(
        db.execute(select(AuditEvent).where(AuditEvent.event_type == "DATA.DQ_RULE_DEFINE"))
        .scalars()
        .all()
    )
    assert audits_after == audits_before  # the loser emitted no audit
    db.close()


def test_module_uses_savepoint(monkeypatch) -> None:  # noqa: ANN001
    """Guard: ensure_presence_rule must call begin_nested (the SAVEPOINT) on the INSERT path —
    a regression removing it would let the IntegrityError abort the whole governed transaction."""
    db = _session()
    tenant = str(uuid.uuid4())
    called = {"nested": False}
    real_begin_nested = db.begin_nested

    def spy():  # noqa: ANN202
        called["nested"] = True
        return real_begin_nested()

    monkeypatch.setattr(db, "begin_nested", spy)
    _ensure(db, tenant)  # first registration takes the INSERT path
    assert called["nested"], "ensure_presence_rule must wrap the INSERT in a SAVEPOINT"
    db.close()


def test_gates_imports_integrity_error() -> None:
    """The savepoint recovery keys on IntegrityError — assert the symbol is wired (a rename
    would silently swallow the wrong exception or none)."""
    from sqlalchemy.exc import IntegrityError

    assert gates_mod.IntegrityError is IntegrityError
