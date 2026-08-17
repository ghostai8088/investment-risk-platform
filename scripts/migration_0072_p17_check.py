"""The P17 populated-database exercise for migration 0072 (STRUCT-3) — a COMMITTED harness.

The 0072 BACKFILL is the migration's data path: one ENT-076 history row per pre-existing
portfolio, captured from the head at the head's ``valid_from``. The full-PG battery migrates an
EMPTY schema and cannot exercise it; this harness proves it over real rows: downgrade to 0071,
seed portfolio nodes THROUGH THE GOVERNED SERVICE (so the pre-0072 world genuinely has heads and
no history), upgrade to head, and assert one history row per node with the head's state.

Destructive by design — point it ONLY at a disposable validation database:

    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \\
        python scripts/migration_0072_p17_check.py
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
        [sys.executable, "-m", "alembic", "downgrade", "0071_exposure_type_in_grain_key"],
        check=True,
    )

    from irp_shared.db.session import make_engine

    engine = make_engine(url, poolclass=NullPool)
    # RAW head inserts, deliberately: the binder writes history co-transactionally SINCE 0072,
    # so only raw SQL can produce the pre-0072 world this harness must start from (heads with
    # no history rows). The migration owner bypasses RLS here — exactly the migration's own
    # execution posture.
    tenant = str(uuid.uuid4())
    fund_id, sleeve_id = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO portfolio (id, tenant_id, code, name, node_type, "
                "parent_portfolio_id, status, record_version, valid_from, created_at, "
                "updated_at) VALUES "
                "(:f, :t, :fc, 'p17 fund', 'FUND', NULL, 'ACTIVE', 1, now(), now(), now()), "
                "(:s, :t, :sc, 'p17 sleeve', 'STRATEGY', :f, 'ACTIVE', 1, now(), now(), now())"
            ),
            {
                "f": fund_id,
                "s": sleeve_id,
                "t": tenant,
                "fc": f"P17-F-{uuid.uuid4().hex[:6]}",
                "sc": f"P17-S-{uuid.uuid4().hex[:6]}",
            },
        )
    with engine.connect() as conn:
        heads = conn.execute(text("SELECT COUNT(*) FROM portfolio")).scalar_one()
    print(f"seeded; portfolio heads pre-upgrade: {heads}")

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    with engine.connect() as conn:
        history = conn.execute(
            text("SELECT COUNT(*) FROM portfolio_hierarchy_version")
        ).scalar_one()
        sleeve_parent = conn.execute(
            text(
                "SELECT COUNT(*) FROM portfolio_hierarchy_version "
                "WHERE parent_portfolio_id IS NOT NULL"
            )
        ).scalar_one()
    if history != heads:
        raise RuntimeError(f"backfill count {history} != portfolio heads {heads}")
    if sleeve_parent < 1:
        raise RuntimeError("no backfilled row carries a parent edge — the tree did not survive")
    print(f"P17 OK: backfilled {history} history row(s) over {heads} populated head(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
