"""``python -m irp_shared.demo_tenant.cli`` — seed the Northlight tenant into ``DATABASE_URL``.

Runs as whatever role ``DATABASE_URL`` names. On a deployed stack that is the database SUPERUSER
through the migrate image (the prepare step's SYSTEM-seed shape), because the seed writes the
``tenant`` row and SYSTEM classification schemes that no application role may. It is armed by
``IRP_ALLOW_DEMO_SEED=1`` and refuses without it, on the report-identity proof's precedent: a
module that writes governed rows into whatever database it is pointed at must be pointed
deliberately.

Refuse-not-skip: an existing Northlight tenant exits 1 with ``REFUSED:`` and nothing written.
"""

from __future__ import annotations

import os
import sys
import time

import irp_shared.models  # noqa: F401 — every ORM model registered, so literal FKs resolve
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.demo_tenant.seed import DemoTenantAlreadySeededError, seed_demo_tenant

ARM = "IRP_ALLOW_DEMO_SEED"


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the seed target)", file=sys.stderr)
        return 2
    if os.environ.get(ARM) != "1":
        print(
            f"{ARM}=1 is required: this writes governed rows into whatever DATABASE_URL names",
            file=sys.stderr,
        )
        return 2
    engine = make_engine(url)
    session_factory = make_session_factory(engine)
    started = time.monotonic()
    with session_factory() as session:
        try:
            summary = seed_demo_tenant(session, log=lambda m: print(m, flush=True))
        except DemoTenantAlreadySeededError as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
        session.commit()
    elapsed = time.monotonic() - started
    print("Northlight tenant seeded:")
    print(f"  tenant:         {summary.tenant_id}")
    print(f"  funds:          {len(summary.fund_ids)} ({', '.join(sorted(summary.fund_ids))})")
    print(f"  accounts:       {len(summary.account_ids)}")
    print(f"  instruments:    {summary.instruments}")
    print(f"  boundaries:     {summary.boundaries} ({summary.month_ends} month-ends)")
    print(f"  marks:          {summary.marks}")
    print(f"  fx rates:       {summary.fx_rates}")
    print(f"  factor returns: {summary.factor_returns}")
    print(f"  loadings:       {summary.loadings}")
    print(f"  model versions: {len(summary.model_version_ids)}")
    total_runs = 0
    for family, n in sorted(summary.runs.items()):
        print(f"  runs.{family:<20s} {n}")
        total_runs = total_runs + n
    print(f"  runs total:     {total_runs}")
    print(f"  elapsed:        {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
