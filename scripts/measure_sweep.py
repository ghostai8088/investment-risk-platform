"""Measure a full 19-family reproduction sweep, end to end (REPRO-2, ratified OQ-REP2-4 / R5).

**Why this exists rather than an estimate.** A 19-family sweep re-executes every registered
binder SEQUENTIALLY inside the tick's phases-1-2 transaction, and that transaction holds the
per-tenant audit advisory lock until it commits. Nineteen re-executions is a real cost with a real
consequence: while the sweep runs, no other governed act in that tenant can take the lock. The
ratification accepted that cost AGAINST A MEASURED NUMBER and named the trigger for splitting the
sweep out of the single transaction. An accepted cost nobody measured is a guess with a signature
on it.

Usage (against the local validation container, after a demo campaign has seeded a book):

    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \\
        .venv/bin/python scripts/measure_sweep.py

It prints the wall time and the per-family disposition counts, and it exits non-zero if the sweep
could not run at all — a measurement of a sweep that did not happen is worse than no measurement.
"""

from __future__ import annotations

import os
import sys
import time


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    tenant = os.environ.get("IRP_MEASURE_TENANT")
    if not tenant:
        print("IRP_MEASURE_TENANT is required (the tenant whose book is swept)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.db.tenant import persistent_tenant_context
    from irp_shared.reproduction.registry import REPRODUCIBLE_FAMILIES
    from irp_shared.reproduction.service import run_reproduction_sweep

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        detach = persistent_tenant_context(session, tenant)
        try:
            started = time.monotonic()
            outcome = run_reproduction_sweep(
                session,
                acting_tenant=tenant,
                actor_id="measurement",
                code_version="measure",
                environment_id="measure",
            )
            session.commit()
            elapsed = time.monotonic() - started
        finally:
            detach()
    finally:
        session.close()
        engine.dispose()

    checked = len(outcome.checks)
    print(f"SWEEP_SECONDS={elapsed:.2f}")
    print(f"SWEEP_FAMILIES_REGISTERED={len(REPRODUCIBLE_FAMILIES)}")
    print(f"SWEEP_VERDICTS={checked}")
    print(f"SWEEP_UNRESOLVED={len(outcome.unresolved)}")
    print(f"SWEEP_STATUS={outcome.status}")
    for check in outcome.checks:
        print(f"  {check.family_key}: {check.verdict} ({check.rows_compared} rows)")
    # A sweep that judged NOTHING is not a fast sweep, it is an absent one — and reporting its
    # wall time as an acceptance number would be the vacuous-measurement shape.
    if checked == 0:
        print(
            "REFUSED: the sweep produced no verdicts, so this number measures an empty loop",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entrypoint
    raise SystemExit(main())
