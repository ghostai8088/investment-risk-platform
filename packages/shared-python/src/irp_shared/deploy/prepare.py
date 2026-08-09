"""Migrate + seed, as one re-runnable deployment step (DEP-1, Wave-15, OQ-W15P-3/4).

Why this exists at all. The shipped compose stack had **no migration step anywhere** and **no
container able to run one** — the backend image carries neither ``alembic`` nor ``migrations/`` —
so `docker compose up` produced a backend pointed at an empty database. Nothing caught it because
CI never ran the stack (planning fact F1). This module is the missing step, and it lives in
``irp_shared`` rather than in a shell script so it is importable, testable, and shipped by the same
package install the migrate image already performs.

**Both halves are idempotent, deliberately.** A deployment step that cannot be re-run after a
partial failure is a step that turns every hiccup into a manual recovery:

- ``alembic upgrade head`` is a no-op when already at head.
- ``seed_system_reference`` was made idempotent at DEP-1 (OQ-W15P-4) — per-code get-or-create,
  existing rows untouched. Before DEP-1 it declared itself single-use and had no non-test caller.

The seed runs under SYSTEM tenant context because the hybrid ``WITH CHECK`` requires it, and it
commits so the context (which is transaction-local and auto-clears at COMMIT) does not leak.
"""

from __future__ import annotations

import logging
import os
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.reference.bootstrap import count_seeded, seed_system_reference

log = logging.getLogger(__name__)

#: The deploy-time env var naming the platform operator's OIDC subject (ONBOARD-1a, ratified
#: OQ-ONB-2 sub-fork (a)). Absent = a LOUD no-op, never an error: most deployments are not
#: provisioning deployments, and an aborting prepare step would wedge `upgrade head` for all of
#: them — which is why this lives HERE and not in an alembic revision (the verifier pass's B5).
OPERATOR_SUBJECT_ENV = "IRP_PLATFORM_OPERATOR_SUBJECT"


def seed_platform_operator(session: Session, *, subject: str) -> str:
    """Idempotently seed the platform operator: one SYSTEM-tenant user + its role grant.

    Returns the operator's ``app_user.id``. Re-running with the same subject changes nothing
    (the `seed_system_reference` idempotency bar: a deploy must be re-runnable after a partial
    failure). The ROLE and its permission rows are migration `0067`'s delivery — this seeds only
    the identity, which is deployment-specific and therefore cannot live in a migration.
    """
    from irp_shared.entitlement.models import AppUser, UserRole
    from irp_shared.entitlement.platform_catalog import (
        PLATFORM_OPERATOR_ROLE,
        platform_role_id,
    )

    existing = session.execute(
        select(AppUser).where(
            AppUser.tenant_id == SYSTEM_TENANT_ID,
            AppUser.external_subject == subject,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    operator = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=SYSTEM_TENANT_ID,
        external_subject=subject,
        display_name="Platform Operator",
        is_active=True,
    )
    session.add(operator)
    session.flush()
    session.add(
        UserRole(
            id=str(uuid.uuid4()),
            tenant_id=SYSTEM_TENANT_ID,
            user_id=operator.id,
            role_id=platform_role_id(PLATFORM_OPERATOR_ROLE),
        )
    )
    session.flush()
    return operator.id


def prepare_database(
    database_url: str | None = None, *, alembic_ini: str = "alembic.ini"
) -> dict[str, int]:
    """Apply migrations, then seed the SYSTEM reference slice. Returns the post-seed counts.

    Raises rather than degrading: a deployment that cannot reach its database, or cannot migrate,
    must fail loudly at the prepare step. Starting the backend against an unmigrated database is
    the failure mode this whole step exists to prevent, and it is far quieter than a crash.
    """
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required to prepare the database — refusing to guess a target"
        )

    # Imported HERE, not at module scope, on purpose: `irp_shared` declares exactly one runtime
    # dependency (sqlalchemy), and a top-level alembic import would quietly make the core shared
    # package require it everywhere — for a path only a deploy container ever takes. Declared as
    # the `deploy` optional extra in pyproject instead.
    from alembic import command
    from alembic.config import Config

    log.info("applying migrations to head")
    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", url)
    # The stack-proof CI job is MUTATION-PROVEN against this exact line. At `0c0fdc3` this read
    # `command.upgrade(cfg, "base")` — leaving the database with no schema, re-creating the defect
    # class DEP-1 found. CI run 31023628263: the Stack-proof job FAILED with
    # `relation "currency" does not exist` while ALL SEVEN other jobs stayed green. The job is a
    # control, not an assertion that one exists (P9).
    command.upgrade(cfg, "head")

    log.info("seeding the SYSTEM reference slice (idempotent)")
    engine = make_engine(url)
    try:
        session = make_session_factory(engine)()
        try:
            set_tenant_context(session, SYSTEM_TENANT_ID)
            seed_system_reference(session, actor_id="system")
            session.commit()
            # Re-arm the context: it is transaction-local and auto-cleared by the COMMIT above, so
            # the count read would otherwise run with NO tenant and see nothing under RLS. This is
            # the documented MD-H1 annex-4 trap that has bitten a fold before.
            set_tenant_context(session, SYSTEM_TENANT_ID)
            counts = count_seeded(session)
            session.commit()
            log.info("seed complete: %s", counts)
            # ONBOARD-1a: the platform operator, seeded from the deploy env — never a migration
            # (an env-dependent migration is irreproducible, and an aborting one wedges every
            # non-provisioning deploy). Absent var = a LOUD no-op: the line below prints either
            # way, so a deploy log always says which case this was.
            subject = os.environ.get(OPERATOR_SUBJECT_ENV, "").strip()
            if subject:
                set_tenant_context(session, SYSTEM_TENANT_ID)
                operator_id = seed_platform_operator(session, subject=subject)
                session.commit()
                counts["platform_operator"] = 1
                log.info("platform operator seeded: subject=%s id=%s", subject, operator_id)
            else:
                log.info(
                    "platform operator NOT seeded (%s unset) — this deployment cannot create "
                    "tenants over HTTP until it is",
                    OPERATOR_SUBJECT_ENV,
                )
            return counts
        finally:
            session.close()
    finally:
        engine.dispose()


def main() -> None:  # pragma: no cover - the container entrypoint
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    counts = prepare_database()
    print(f"database prepared: {counts}")


if __name__ == "__main__":  # pragma: no cover
    main()
