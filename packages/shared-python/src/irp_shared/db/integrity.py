"""Integrity-error discrimination (MD-H1 review fold — three finders converged on this).

The MD-H1 IntegrityError→409 mapping must catch ONLY the duplicate-open-head unique-constraint
collision it was minted for. An indiscriminate catch would mislabel every OTHER integrity failure
inside a governed capture unit — an FK violation, a NOT NULL regression, an RLS ``WITH CHECK``
rejection — as 409 "already exists", steering clients into duplicate-handling for what is actually
a data-integrity bug and hiding the 5xx from monitoring. ``is_unique_violation`` inspects the
driver-level cause so non-duplicate integrity failures can be RE-RAISED (fail-loud 500, the
pre-MD-H1 behavior for that class).

Backend detection: PostgreSQL/psycopg exposes SQLSTATE 23505 (``unique_violation``); SQLite (the
unit suite) exposes the ``UNIQUE constraint failed`` message. Anything unrecognized is treated as
NOT a unique violation (fail-loud).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

_PG_UNIQUE_VIOLATION = "23505"

T = TypeVar("T")


def is_unique_violation(exc: IntegrityError) -> bool:
    """True iff the wrapped driver error is a unique-constraint violation (the duplicate class)."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate is not None:
        return sqlstate == _PG_UNIQUE_VIOLATION
    return "UNIQUE constraint failed" in str(orig)  # the sqlite3 message shape


def resolve_or_insert(
    session: Session, *, resolve: Callable[[], T | None], insert: Callable[[], T]
) -> T:
    """The generic race-safe resolve-or-register (the ``dq/gates``/MD-H1 savepoint pattern, once).

    Two concurrent FIRST callers both ``resolve()``-miss then both ``insert()`` the same key — one
    hits the unique constraint. The insert runs inside a SAVEPOINT (``begin_nested``) so the loser's
    ``IntegrityError`` rolls back ONLY that insert (never the caller's whole governed unit, which an
    unwrapped error would abort into a 500 on PostgreSQL); the loser then re-resolves the peer's
    committed row (READ COMMITTED). A NON-unique integrity failure, or a unique collision whose peer
    cannot be re-resolved, re-raises loudly — this never swallows a real data-integrity bug.
    """
    row = resolve()
    if row is not None:
        return row
    try:
        with session.begin_nested():  # SAVEPOINT around the racy insert
            return insert()
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        peer = resolve()
        if peer is None:  # not the first-registration collision we handle — re-raise loudly
            raise
        return peer
