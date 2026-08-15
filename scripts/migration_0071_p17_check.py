"""The P17 populated-database exercise for migration 0071 (STRUCT-1) — a COMMITTED harness.

P18 clause 2: a harness whose output is cited as governed evidence lives in the repository. This
is the procedure executed at the STRUCT-1 gate (2026-08-15, quoted in the PR): downgrade to 0070,
seed a REAL exposure row through the governed services (never a bare INSERT), then upgrade to
0071 with the table populated — proving the key-widening ALTER runs over data, not only over the
empty schema the full-PG battery migrates.

Destructive by design (downgrade + seed) — point it ONLY at a disposable validation database:

    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \\
        python scripts/migration_0071_p17_check.py

Exits 0 with the widened constraint read back from pg_constraint; any failure raises.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.pool import NullPool


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (a DISPOSABLE validation database)", file=sys.stderr)
        return 2

    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "0070_app_role"], check=True)

    from irp_shared.db.session import make_engine, make_session_factory
    from irp_shared.db.tenant import persistent_tenant_context
    from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
    from irp_shared.exposure import ExposureActor, run_exposure
    from irp_shared.portfolio import PortfolioActor, create_portfolio
    from irp_shared.position import create_position
    from irp_shared.position.service import PositionActor
    from irp_shared.reference.instrument import create_instrument
    from irp_shared.reference.models import Currency
    from irp_shared.reference.service import ReferenceActor
    from irp_shared.valuation import create_valuation
    from irp_shared.valuation.service import ValuationActor

    engine = make_engine(url, poolclass=NullPool)
    db = make_session_factory(engine)()
    tenant = str(uuid.uuid4())
    persistent_tenant_context(db, tenant)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    if (
        db.query(Currency)
        .filter(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == "USD")
        .first()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=t0))
    db.flush()
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"P17-{uuid.uuid4().hex[:6]}",
        name="p17",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=f"P17-EQ-{uuid.uuid4().hex[:6]}",
        name="i",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal("100"),
        valid_from=t0,
    )
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=date(2026, 6, 1),
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal("12.50"),
        currency_code="USD",
        valid_from=t0,
    )
    db.flush()
    result = run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="s"),
        code_version="p17",
        environment_id="local",
        portfolio_id=pf,
        as_of_valid_at=datetime(2026, 6, 1, tzinfo=UTC),
        base_currency="USD",
    )
    if result.status != "COMPLETED":
        raise RuntimeError(f"seed run {result.status}: {result.failure_reason}")
    db.commit()
    print(f"seeded {len(result.rows)} governed exposure row(s) at 0070")

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    with engine.connect() as conn:
        constraint = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'uq_exposure_aggregate_run_grain'"
            )
        ).scalar_one()
        count = conn.execute(text("SELECT COUNT(*) FROM exposure_aggregate")).scalar_one()
    if "exposure_type" not in constraint:
        raise RuntimeError(f"constraint not widened: {constraint}")
    print(f"P17 OK: upgraded over {count} populated row(s); constraint = {constraint}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
