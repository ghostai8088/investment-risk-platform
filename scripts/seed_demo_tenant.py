"""Seed the Northlight demo tenant (BOOK-1a) into ``DATABASE_URL``.

    IRP_ALLOW_DEMO_SEED=1 DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \\
        python scripts/seed_demo_tenant.py

A thin wrapper over ``python -m irp_shared.demo_tenant.cli`` (the module the deploy flag runs
inside the migrate image); the remit named this script, so it exists by that name.
"""

from __future__ import annotations

import sys

from irp_shared.demo_tenant.cli import main

if __name__ == "__main__":
    sys.exit(main())
