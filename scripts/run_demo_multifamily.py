"""Run the MF-1 demo multi-family extension (OD-MF-1-B) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_multifamily_extension`: opens one session, executes
the ratified extension against the LIVING demo tenant (the MG-1 base campaign must have been
seeded first — run ``scripts/run_demo_campaign.py``), commits ONCE, and prints the end-state
summary. Idempotency is refuse-not-skip on the extension's own footprint — a demo tenant that
already holds the loadings model exits with an error telling the operator to reset both stages.

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
        python scripts/run_demo_multifamily.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the extension target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import (
        DemoMultifamilyAlreadySeededError,
        DemoMultifamilyPrereqError,
        run_demo_multifamily_extension,
    )

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_multifamily_extension(session)
            session.commit()
        except (DemoMultifamilyAlreadySeededError, DemoMultifamilyPrereqError) as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("MF-1 demo multi-family extension COMPLETE")
    print(f"  tenant:                {summary.tenant_id}")
    print(f"  sleeve portfolio:      {summary.portfolio_id}")
    print(f"  loadings version:      {summary.loadings_model_version_id}")
    print(f"  alpha=1 version:       {summary.alpha1_version_id}")
    print(f"  factors:               {', '.join(sorted(summary.factor_ids))}")
    print(f"  instruments:           {', '.join(sorted(summary.instrument_ids))}")
    print(f"  promoted loadings:     {summary.promoted_loadings}")
    print(f"  loadings run:          {summary.loadings_run_id}")
    print(f"  covariance run:        {summary.covariance_run_id}")
    for code, run_id in sorted(summary.flagship_run_ids.items()):
        print(f"  evidence {code}: {run_id}")
    print(f"  TRIGGERED filed:       {summary.triggered_validations_filed}")
    print(f"  INITIAL filed:         {summary.initial_validations_filed}")
    print(f"  EXCEPTION filed:       {summary.exceptions_filed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
