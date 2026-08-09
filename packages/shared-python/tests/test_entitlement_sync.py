"""The catalog sync consults the revocation ledger — P17's second clause, made to FIRE.

Migration ``0064`` syncs the whole entitlement catalog into a database that already exists, which
is the only way a code minted after that database was created ever reaches it. As merged, that sync
also **restored template grants an administrator had deliberately revoked**: a revoked grant and a
never-delivered grant are the same database state, because the deterministic ``uuid5`` id is a
function of ``(role, code)`` alone. The Wave-16 close review refused to ratify the sync on those
terms — a governance action that a migration silently undoes is not a governance action.

``role_permission_revocation`` is the missing state and ``sync_catalog`` consults it. These tests
are the pin, and they are built so that neither half can pass for the wrong reason:

* the REFUSAL fires — a revoked grant is not restored, and the report names it;
* the discriminating POSITIVE control differs by exactly one row (the revocation) and proves the
  sync would otherwise have restored it. Without that control, "not restored" is equally
  consistent with a sync that did nothing at all — the shape LIM-2 recorded as a negative control
  proving little;
* the ledger's ABSENCE is reported, never inferred as "nothing was revoked".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, select
from sqlalchemy.pool import StaticPool

from irp_shared.db.base import Base
from irp_shared.db.session import make_engine
from irp_shared.entitlement.bootstrap import (
    ROLE_TEMPLATES,
    permission_id,
    role_id,
    role_permission_id,
)
from irp_shared.entitlement.sync import revoked_grant_ids, sync_catalog

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)

#: The grant the controls below revoke. A real, consequential one: the 3L auditor's read of
#: governed report artifacts — the kind of grant an administrator would remove on purpose, and the
#: kind whose silent restoration is a disclosure (the SCH-2 write-only-field lesson).
REVOKED_ROLE = "auditor_3l"
REVOKED_CODE = "report.view"


@pytest.fixture
def engine() -> Engine:
    eng = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _all_want_grant_ids() -> set[str]:
    return {
        role_permission_id(name, code) for name, codes in ROLE_TEMPLATES.items() for code in codes
    }


def _grant_ids(conn: sa.Connection) -> set[str]:
    return {
        str(r)
        for r in conn.execute(select(sa.column("id")).select_from(sa.table("role_permission")))
        .scalars()
        .all()
    }


def _record_revocation(conn: sa.Connection, role: str, code: str) -> None:
    """What an administrator does: remove the grant AND record why it is gone.

    Both halves, because either alone is a different scenario — deleting the grant without the
    record is the "never delivered" state the sync is supposed to repair.
    """
    conn.execute(
        sa.delete(sa.table("role_permission", sa.column("id"))).where(
            sa.column("id") == role_permission_id(role, code)
        )
    )
    conn.execute(
        sa.insert(
            sa.table(
                "role_permission_revocation",
                sa.column("id"),
                sa.column("role_id"),
                sa.column("permission_id"),
                sa.column("revoked_at"),
                sa.column("revoked_by"),
                sa.column("reason"),
                sa.column("created_at"),
                sa.column("updated_at"),
            )
        ),
        [
            {
                "id": str(uuid.uuid4()),
                "role_id": role_id(role),
                "permission_id": permission_id(code),
                "revoked_at": NOW,
                "revoked_by": "governance@example.com",
                "reason": "3L read withdrawn pending an independence review",
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
    )


def test_sync_seeds_an_empty_database_in_full() -> None:
    """The baseline the two controls below are measured against."""
    eng = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        report = sync_catalog(conn, now=NOW)
        assert _grant_ids(conn) == _all_want_grant_ids()
    assert report.grants_skipped_revoked == ()
    assert report.ledger_present is True
    assert report.grants_inserted == len(_all_want_grant_ids())
    eng.dispose()


def test_sync_does_not_restore_a_revoked_grant(engine: Engine) -> None:
    """THE REFUSAL. A deliberately revoked template grant survives a catalog sync."""
    with engine.begin() as conn:
        sync_catalog(conn, now=NOW)
        _record_revocation(conn, REVOKED_ROLE, REVOKED_CODE)
        assert role_permission_id(REVOKED_ROLE, REVOKED_CODE) not in _grant_ids(conn)

        report = sync_catalog(conn, now=NOW)

        assert role_permission_id(REVOKED_ROLE, REVOKED_CODE) not in _grant_ids(
            conn
        ), "the sync resurrected a grant an administrator deliberately revoked"
    assert report.grants_inserted == 0
    assert report.grants_skipped_revoked == ((REVOKED_ROLE, REVOKED_CODE),)
    assert any(
        "NOT restoring" in m and REVOKED_CODE in m for m in report.messages
    ), f"the skip must be LOGGED, not merely done: {report.messages}"


def test_sync_does_restore_the_same_grant_when_it_was_not_revoked(engine: Engine) -> None:
    """THE DISCRIMINATING CONTROL — differs from the refusal by exactly the revocation row.

    This is what makes the refusal above evidence. Delete the identical grant WITHOUT recording a
    revocation and the sync restores it, which is the whole point of ``0064``: a mint reaching a
    database that already exists. If this test ever fails, the refusal above proves nothing,
    because a sync that restores nothing would satisfy it too.
    """
    with engine.begin() as conn:
        sync_catalog(conn, now=NOW)
        conn.execute(
            sa.delete(sa.table("role_permission", sa.column("id"))).where(
                sa.column("id") == role_permission_id(REVOKED_ROLE, REVOKED_CODE)
            )
        )
        assert role_permission_id(REVOKED_ROLE, REVOKED_CODE) not in _grant_ids(conn)

        report = sync_catalog(conn, now=NOW)

        assert role_permission_id(REVOKED_ROLE, REVOKED_CODE) in _grant_ids(conn)
    assert report.grants_inserted == 1
    assert report.grants_skipped_revoked == ()


def test_a_revocation_scopes_to_its_own_pair(engine: Engine) -> None:
    """One revoked grant must not suppress the rest of the sync (the fail-wide shape D4 fixed).

    The alarm fold earlier in this same close found one unreadable row costing an entire phase; the
    same question belongs here, because the revocation set is consulted once for every grant.
    """
    other_role, other_code = "risk_manager_2l", "report.view"
    with engine.begin() as conn:
        sync_catalog(conn, now=NOW)
        _record_revocation(conn, REVOKED_ROLE, REVOKED_CODE)
        conn.execute(
            sa.delete(sa.table("role_permission", sa.column("id"))).where(
                sa.column("id") == role_permission_id(other_role, other_code)
            )
        )

        report = sync_catalog(conn, now=NOW)
        ids = _grant_ids(conn)

    assert (
        role_permission_id(other_role, other_code) in ids
    ), "a revocation on one role suppressed an unrelated role's grant of the same code"
    assert role_permission_id(REVOKED_ROLE, REVOKED_CODE) not in ids
    assert report.grants_inserted == 1
    assert report.grants_skipped_revoked == ((REVOKED_ROLE, REVOKED_CODE),)


def test_an_absent_ledger_is_reported_not_inferred_as_nothing_revoked(engine: Engine) -> None:
    """A database below ``0066`` has no ledger. The sync still runs; it says it could not consult.

    ``ledger_present=False`` is a different fact from "no revocations exist", and the distinction is
    the one P5 is about: assert by evidence, never by absence.
    """
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE role_permission_revocation"))
        ids, present = revoked_grant_ids(conn)
        assert (ids, present) == (set(), False)

        report = sync_catalog(conn, now=NOW)

        assert _grant_ids(conn) == _all_want_grant_ids()
    assert report.ledger_present is False
    assert any("COULD NOT be consulted" in m for m in report.messages), report.messages


def test_the_additive_behaviour_is_unchanged_where_no_revocation_is_recorded() -> None:
    """The justification for amending an APPLIED migration, checked rather than asserted.

    ``0064`` was edited after merge to route through ``sync_catalog``. The claim that made that
    acceptable is narrow and testable: where no revocation exists — every database below ``0066``,
    and every fresh one — the rows written are exactly the merged version's rows, i.e. the full
    want-set with nothing skipped. Both ledger states are run against identical fixtures and
    compared to each other, so the claim rests on execution rather than on reading the diff.
    """
    written: list[set[str]] = []
    for drop_ledger in (True, False):
        eng = make_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(eng)
        with eng.begin() as conn:
            if drop_ledger:
                conn.execute(sa.text("DROP TABLE role_permission_revocation"))
            report = sync_catalog(conn, now=NOW)
            written.append(_grant_ids(conn))
        assert report.grants_skipped_revoked == ()
        eng.dispose()

    assert written[0] == written[1] == _all_want_grant_ids()
