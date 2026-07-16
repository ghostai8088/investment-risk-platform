"""Run the MG-1 demo validation campaign (OD-MG-1-G) against ``DATABASE_URL``.

Thin CLI over :func:`irp_shared.demo.run_demo_campaign`: opens one session, executes the ratified
campaign against the reserved DEMO tenant, commits, and prints the end-state summary. Idempotency
is refuse-not-skip — a demo tenant that already holds model rows exits with an error telling the
operator to reset (the campaign files append-only validation records and never partially re-runs).

Usage:
    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp python scripts/run_demo_campaign.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (the campaign target database)", file=sys.stderr)
        return 2

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.demo import DemoCampaignAlreadySeededError, run_demo_campaign

    engine = make_engine(url)
    session = make_session_factory(engine)()
    try:
        try:
            summary = run_demo_campaign(session)
            session.commit()
        except DemoCampaignAlreadySeededError as exc:
            session.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
        engine.dispose()

    print("MG-1 demo campaign COMPLETE")
    print(f"  tenant:               {summary.tenant_id}")
    print(f"  validator (2L):       {summary.validator_user_id}")
    print(f"  registrar (1L):       {summary.registrar_user_id}")
    print(f"  portfolio:            {summary.portfolio_id}")
    print(f"  models registered:    {summary.models_registered}")
    print(f"  tiers assigned:       {summary.tiers_assigned}")
    print(f"  INITIAL validations:  {summary.initial_validations_filed}")
    print(f"  EXCEPTION records:    {summary.exceptions_filed}")
    print(f"  backtest pairs (N):   {summary.backtest_pairs}")
    print(f"  plain VaR runs:       {len(summary.var_run_ids)}")
    print(f"  HS VaR runs:          {len(summary.hs_run_ids)}")
    print(f"  total VaR runs:       {len(summary.total_run_ids)}")
    print(f"  BT-1 run:             {summary.bt1_run_id}")
    print(f"  BT-2 run:             {summary.bt2_run_id}")
    print(f"  ES / ES-total runs:   {summary.es_run_id} / {summary.es_total_run_id}")
    print(f"  return run:           {summary.portfolio_return_run_id}")
    print(f"  desmooth -> estimate: {summary.desmoothed_run_id} -> {summary.estimate_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
