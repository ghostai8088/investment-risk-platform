"""The P17 populated-database exercise for migration 0073 (STRUCT-4, DP-11) — a COMMITTED harness.

The 0073 BACKFILL is the migration's entire content: every UNDECLARED root gains an explicit
``'USD'`` declaration (the silent default those books computed under, now stated), a bumped
``record_version``, and one appended ENT-076 history row stamped ``source='0073_BACKFILL'``.
The full-PG battery migrates an EMPTY schema and cannot exercise it; this harness proves it over
real rows: downgrade to 0072, seed the pre-0073 shapes RAW (an undeclared root with an undeclared
child, and a DECLARED root — the negative control), upgrade to head, and assert exactly one root
changed.

Destructive by design — point it ONLY at a disposable validation database:

    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \\
        python scripts/migration_0073_p17_check.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.pool import NullPool


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (a DISPOSABLE validation database)", file=sys.stderr)
        return 2

    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0072_portfolio_hierarchy_version"],
        check=True,
    )

    from irp_shared.db.session import make_engine

    engine = make_engine(url, poolclass=NullPool)
    # RAW head inserts, deliberately: the binder refuses/normalizes since STRUCT-4, so only raw
    # SQL reproduces the pre-0073 world (undeclared heads). The migration owner bypasses RLS
    # here — exactly the migration's own execution posture.
    tenant = str(uuid.uuid4())
    bare_root, bare_child, declared_root = (str(uuid.uuid4()) for _ in range(3))
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO portfolio (id, tenant_id, code, name, node_type, "
                "parent_portfolio_id, status, base_currency_code, record_version, valid_from, "
                "created_at, updated_at) VALUES "
                "(:r, :t, :rc, 'p17 bare root', 'FUND', NULL, 'ACTIVE', NULL, 1, now(), now(), "
                "now()), "
                "(:c, :t, :cc, 'p17 bare child', 'STRATEGY', :r, 'ACTIVE', NULL, 1, now(), "
                "now(), now()), "
                "(:d, :t, :dc, 'p17 declared root', 'FUND', NULL, 'ACTIVE', 'EUR', 3, now(), "
                "now(), now())"
            ),
            {
                "r": bare_root,
                "c": bare_child,
                "d": declared_root,
                "t": tenant,
                "rc": f"P17C-R-{uuid.uuid4().hex[:6]}",
                "cc": f"P17C-C-{uuid.uuid4().hex[:6]}",
                "dc": f"P17C-D-{uuid.uuid4().hex[:6]}",
            },
        )

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    with engine.connect() as conn:
        root_row = conn.execute(
            text("SELECT base_currency_code, record_version FROM portfolio WHERE id = :i"),
            {"i": bare_root},
        ).one()
        child_row = conn.execute(
            text("SELECT base_currency_code, record_version FROM portfolio WHERE id = :i"),
            {"i": bare_child},
        ).one()
        declared_row = conn.execute(
            text("SELECT base_currency_code, record_version FROM portfolio WHERE id = :i"),
            {"i": declared_root},
        ).one()
        backfill_rows = conn.execute(
            text(
                "SELECT portfolio_id, base_currency_code, record_version FROM "
                "portfolio_hierarchy_version WHERE source = '0073_BACKFILL'"
            )
        ).fetchall()
    if root_row != ("USD", 2):
        raise RuntimeError(f"bare root not backfilled to ('USD', 2): {tuple(root_row)}")
    if child_row != (None, 1):
        raise RuntimeError(f"bare CHILD was touched — NULL there means INHERIT: {tuple(child_row)}")
    if declared_row != ("EUR", 3):
        raise RuntimeError(f"declared root was touched: {tuple(declared_row)}")
    ours = [r for r in backfill_rows if str(r[0]) == bare_root]
    if len(ours) != 1 or ours[0][1] != "USD" or ours[0][2] != 2:
        raise RuntimeError(f"expected ONE 0073_BACKFILL history row for the bare root: {ours}")
    if any(str(r[0]) in (bare_child, declared_root) for r in backfill_rows):
        raise RuntimeError("a 0073_BACKFILL row exists for a node the migration must not touch")
    print(f"P17 OK: one root declared, child+declared-root untouched, history appended ({ours})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
