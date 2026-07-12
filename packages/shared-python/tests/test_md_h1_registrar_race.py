"""MD-H1 OD-D: the model/version first-registration race — savepoint resolve-or-register.

The race (a Wave-1..2 residual shared by all governed-family bootstraps): two concurrent FIRST
registrations of the same model both SELECT-miss then INSERT the same ``(tenant_id, code)`` (or
``(model_id, version_label)``); one hits the unique constraint. Pre-fix, that IntegrityError aborted
the whole co-transactional bootstrap (a 500). Post-fix, ``resolve_or_register_model`` /
``resolve_or_register_version`` wrap the INSERT in a SAVEPOINT and, on the collision, roll back ONLY
the failed INSERT and re-SELECT the peer's committed row — mirroring the ``dq/gates`` savepoint
pattern (see ``test_p3c2_dq_rule_race.py``).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.model import service as model_service
from irp_shared.model.models import Model, ModelVersion
from irp_shared.model.service import (
    register_model_version,
    resolve_or_register_model,
    resolve_or_register_version,
)
from irp_shared.models import Base

_TENANT = str(uuid.uuid4())
_CODE = "risk.test.model"


def _session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return make_session_factory(engine)()


def _resolve_model(db: Session):  # noqa: ANN202
    return resolve_or_register_model(
        db,
        tenant_id=_TENANT,
        code=_CODE,
        name="Test model",
        model_type="TEST",
        actor_id="a",
    )


def _resolve_version(db: Session, model: Model):  # noqa: ANN202
    return resolve_or_register_version(
        db,
        model=model,
        version_label="v1",
        register=lambda: register_model_version(
            db,
            model=model,
            version_label="v1",
            actor_id="a",
            code_version="c1",
            status="REGISTERED",
        ),
    )


def test_model_first_registration_then_resolves_idempotently() -> None:
    db = _session()
    first = _resolve_model(db)
    db.flush()
    again = _resolve_model(db)
    assert again.id == first.id
    n = len(db.execute(select(Model).where(Model.code == _CODE)).scalars().all())
    assert n == 1  # no duplicate inventory
    db.close()


def test_version_first_registration_then_resolves_idempotently() -> None:
    db = _session()
    model = _resolve_model(db)
    db.flush()
    first = _resolve_version(db, model)
    db.flush()
    again = _resolve_version(db, model)
    assert again.id == first.id
    n = len(
        db.execute(select(ModelVersion).where(ModelVersion.model_id == model.id)).scalars().all()
    )
    assert n == 1
    db.close()


def test_model_race_collision_recovers_via_savepoint(monkeypatch) -> None:  # noqa: ANN001
    """Force the initial SELECT to miss once against a committed peer model: the INSERT collides,
    the savepoint rolls it back, and the peer is resolved WITHOUT the IntegrityError escaping and
    WITHOUT a dangling MODEL.REGISTER audit from the loser."""
    db = _session()
    peer = _resolve_model(db)  # the run that won the race
    db.flush()
    audits_before = len(
        db.execute(select(AuditEvent).where(AuditEvent.event_type == "MODEL.REGISTER"))
        .scalars()
        .all()
    )
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
    resolved = _resolve_model(db)  # collide on INSERT → savepoint → re-SELECT (real) → peer
    monkeypatch.undo()

    assert resolved.id == peer.id  # recovered to the peer, no exception escaped
    n = len(db.execute(select(Model).where(Model.code == _CODE)).scalars().all())
    assert n == 1
    audits_after = len(
        db.execute(select(AuditEvent).where(AuditEvent.event_type == "MODEL.REGISTER"))
        .scalars()
        .all()
    )
    assert audits_after == audits_before  # the loser's INSERT (+ its audit) was unwound
    db.close()


def test_version_race_collision_recovers_via_savepoint(monkeypatch) -> None:  # noqa: ANN001
    """Same interleave on the (model_id, version_label) unique key: the loser re-SELECTs the peer
    version instead of raising."""
    db = _session()
    model = _resolve_model(db)
    db.flush()
    peer = _resolve_version(db, model)
    db.flush()
    real_execute = db.execute
    state = {"forced": False}

    class _Miss:
        def scalar_one_or_none(self):  # noqa: ANN202
            return None

    def fake_execute(statement, *args, **kwargs):  # noqa: ANN001, ANN202
        if not state["forced"]:
            state["forced"] = True
            return _Miss()
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", fake_execute)
    resolved = _resolve_version(db, model)
    monkeypatch.undo()

    assert resolved.id == peer.id
    n = len(
        db.execute(select(ModelVersion).where(ModelVersion.model_id == model.id)).scalars().all()
    )
    assert n == 1
    db.close()


def test_helpers_use_savepoint(monkeypatch) -> None:  # noqa: ANN001
    """Guard: both helpers must call begin_nested (the SAVEPOINT) on the INSERT path — a regression
    removing it would let the IntegrityError abort the whole governed bootstrap."""
    db = _session()
    called = {"nested": 0}
    real_begin_nested = db.begin_nested

    def spy():  # noqa: ANN202
        called["nested"] += 1
        return real_begin_nested()

    monkeypatch.setattr(db, "begin_nested", spy)
    model = _resolve_model(db)  # INSERT path → 1 savepoint
    db.flush()
    _resolve_version(db, model)  # INSERT path → 1 more
    assert called["nested"] >= 2, "both helpers must wrap the INSERT in a SAVEPOINT"
    db.close()


def test_service_imports_integrity_error() -> None:
    """The savepoint recovery keys on IntegrityError — assert the symbol is wired."""
    from sqlalchemy.exc import IntegrityError

    assert model_service.IntegrityError is IntegrityError


def test_real_bootstrap_race_recovers_end_to_end(monkeypatch) -> None:  # noqa: ANN001
    """Review fold (finder 4): drive a REAL family registrar (active-risk, code_version-only)
    through the forced collision — the loser must resolve the peer AND its unconditional identity
    checks must pass on the peer (same code_version), returning the peer version, not a 500."""
    from irp_shared.risk.bootstrap import register_active_risk_model

    db = _session()
    tenant = str(uuid.uuid4())
    peer = register_active_risk_model(
        db, tenant_id=tenant, actor_id="a", code_version="c1"
    )  # the racer that won
    db.flush()

    real_execute = db.execute
    state = {"missed": 0}

    class _Miss:
        def scalar_one_or_none(self):  # noqa: ANN202
            return None

    def fake_execute(statement, *args, **kwargs):  # noqa: ANN001, ANN202
        # Force ONLY the loser's FIRST resolve (the model head) to stale-miss, driving the model
        # leg into its INSERT against the winner's committed row; the recovery re-SELECT (and the
        # version leg) run for real. (The INSERT itself goes through flush, not Session.execute.)
        if state["missed"] < 1:
            state["missed"] += 1
            return _Miss()
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", fake_execute)
    resolved = register_active_risk_model(db, tenant_id=tenant, actor_id="b", code_version="c1")
    monkeypatch.undo()

    assert resolved.id == peer.id  # recovered to the peer through BOTH savepoint legs
    db.close()


def test_real_bootstrap_race_with_mismatched_peer_is_governed_conflict(monkeypatch) -> None:  # noqa: ANN001
    """The race-then-conflict path: the loser resolves a peer whose code_version DIFFERS — the
    unconditional identity check must raise the governed ModelVersionConflictError (422 class),
    never an IntegrityError 500."""
    from irp_shared.model.service import ModelVersionConflictError
    from irp_shared.risk.bootstrap import register_active_risk_model

    db = _session()
    tenant = str(uuid.uuid4())
    register_active_risk_model(db, tenant_id=tenant, actor_id="a", code_version="c1")
    db.flush()

    real_execute = db.execute
    state = {"missed": 0}

    class _Miss:
        def scalar_one_or_none(self):  # noqa: ANN202
            return None

    def fake_execute(statement, *args, **kwargs):  # noqa: ANN001, ANN202
        if state["missed"] < 1:  # ONLY the model-head resolve stale-misses (see the twin above)
            state["missed"] += 1
            return _Miss()
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", fake_execute)
    with pytest.raises(ModelVersionConflictError):
        register_active_risk_model(db, tenant_id=tenant, actor_id="b", code_version="c2")
    monkeypatch.undo()
    db.close()
