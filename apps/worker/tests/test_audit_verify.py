"""Tests for the audit-verification ops CLI (item 4; BR-12/18, CTRL-026)."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import text

from irp_shared.audit.models import AuditCheckpoint
from irp_shared.audit.service import record_event
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.models import Base
from irp_worker.audit_verify import main


def _seed(url: str, tenant: str, n: int) -> None:
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        for _ in range(n):
            record_event(
                db,
                event_type="TEST.EVENT",
                tenant_id=tenant,
                actor_type="user",
                actor_id="u",
                source_module="test",
                action="create",
            )
        db.commit()
    finally:
        db.close()
        engine.dispose()


def test_cli_reports_healthy_chain(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'audit.db'}"
    _seed(url, str(uuid.uuid4()), 3)
    assert main(["--database-url", url]) == 0


def test_cli_no_database_url_returns_2() -> None:
    assert main(["--database-url", ""]) == 2


def test_cli_checkpoint_writes_checkpoint(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'audit.db'}"
    _seed(url, str(uuid.uuid4()), 4)
    assert main(["--database-url", url, "--checkpoint"]) == 0

    engine = make_engine(url)
    db = make_session_factory(engine)()
    try:
        checkpoints = db.query(AuditCheckpoint).all()
        assert len(checkpoints) == 1
        assert checkpoints[0].sequence_no == 4
    finally:
        db.close()
        engine.dispose()


def test_cli_detects_tampering(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'audit.db'}"
    _seed(url, str(uuid.uuid4()), 3)

    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE audit_event SET after_value = :v WHERE sequence_no = 2"), {"v": '{"x": 1}'}
        )
    engine.dispose()

    assert main(["--database-url", url]) == 1
