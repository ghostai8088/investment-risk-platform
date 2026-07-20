"""Run the CC-1 stage-8 demo (OD-CC-1-H) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_cc1_stage8`: seeds PE-MERIDIAN-X, captures
the 25M USD commitment by the flagship book, records the call/distribution stream — incl.
the mis-captured call REVERSED (the negation append) and recaptured — and the recallable
distribution. CAPTURE-ONLY: no model code, no validation record, no calculation run (the
campaign count pins stay 19/34/95 — asserted by the exercising suites). Requires the MG-1
campaign; refuse-not-skip on this stage's own footprint; commits ONCE.

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
        python scripts/run_demo_cc1.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the stage-8 target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import (
        DemoCc1AlreadySeededError,
        DemoCc1PrereqError,
        run_demo_cc1_stage8,
    )

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_cc1_stage8(session)
            session.commit()
        except (DemoCc1AlreadySeededError, DemoCc1PrereqError) as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("CC-1 stage-8 demo COMPLETE")
    print(f"  tenant:        {summary.tenant_id}")
    print(f"  fund:          {summary.fund_instrument_id} (PE-MERIDIAN-X)")
    print(f"  commitment:    {summary.commitment_id} (25,000,000.000000 USD)")
    print(
        f"  calls:         {summary.calls_recorded} captures + {summary.reversals_recorded} "
        f"reversal -> net called {summary.net_called} (the negation self-correction)"
    )
    print(
        f"  distributions: {summary.distributions_recorded} -> net {summary.net_distributed} "
        f"(one recallable, captured as data)"
    )
    print("  counts:        19 codes / 34 validation records / 95 runs — UNCHANGED (capture-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
