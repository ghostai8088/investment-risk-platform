"""Run the DS-2 stage-6 demo (OD-DS-2-E) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_ds2_stage6`: seeds PE-HARBORVIEW-IX (16 quarterly
marks generated at a KNOWN true alpha of 0.4), runs the DECLARED baseline + the AR1_ESTIMATED
convention (alpha-hat + the band — estimation with honest uncertainty, deliberately NOT a
recovery claim) + the OKUNEV_WHITE_ITERATIVE whitening, and files the 2 INITIAL AWC dossiers.
NO TRIGGERED re-validation (no closable condition names the declared-alpha rider — recorded).
Requires the MG-1 campaign; refuse-not-skip on this stage's own footprint; commits ONCE.

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
        python scripts/run_demo_ds2.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the stage-6 target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import (
        DemoDs2AlreadySeededError,
        DemoDs2PrereqError,
        run_demo_ds2_stage6,
    )

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_ds2_stage6(session)
            session.commit()
        except (DemoDs2AlreadySeededError, DemoDs2PrereqError) as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("DS-2 stage-6 demo COMPLETE")
    print(f"  tenant:             {summary.tenant_id}")
    print(f"  estimated version:  {summary.estimated_version_id}")
    print(f"  okunev-white ver.:  {summary.okunev_white_version_id}")
    print(
        f"  the estimation:     alpha_true {summary.alpha_true} -> alpha_hat "
        f"{summary.alpha_hat} +/- {summary.alpha_stderr} (band; upward bias disclosed)"
    )
    print(
        f"  runs:               declared {summary.declared_run_id} / estimated "
        f"{summary.estimated_run_id} / okunev-white {summary.okunev_white_run_id}"
    )
    print(f"  filed:              {summary.initials_filed} INITIAL (NO TRIGGERED - recorded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
