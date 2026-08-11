"""DEPLOY-1 (pre-Wave-18, ratified 2026-08-11): the application role the deployment never had.

**The finding.** The platform's first hard invariant is "no BYPASSRLS application path". It holds
in the test tier and nowhere else. Measured on a real container at HEAD `1544fa9`:

* the deployed services connect as ``${POSTGRES_USER}`` (``docker-compose.yml:27/44/72``), which
  ``.env.example`` sets to ``irp``, and which the ``postgres:16`` image creates as a SUPERUSER —
  ``SELECT rolname, rolsuper, rolbypassrls`` returns ``irp | t | t``;
* ``irp_app`` — the ``NOSUPERUSER NOBYPASSRLS`` role that **61 test files** prove RLS against — is
  created ONLY inside those test files. ``grep -rn irp_app infra/ docker-compose.yml .env.example
  migrations/ scripts/`` returns nothing;
* the consequence, executed: two tenants seeded, no ``app.tenant_id`` GUC armed. As ``irp``:
  **2 rows visible**. As ``irp_app``: **0**. 84 tables carry FORCE RLS and it works perfectly, for
  a role the deployment never uses.

So every deployed proof CI runs — onboarding, reproduction, report identity — demonstrated its
behaviour with tenant isolation switched off, and the isolation tests were true of a role that
existed only while the tests were running.

**What this migration does, and deliberately does not.** It creates the role and grants it the
privileges an application needs — no more. It does NOT set a password: ``irp_app`` is created
``NOLOGIN`` here, because a password in a migration is a secret in source (BR-10). The deploy step
(`irp_shared.deploy.prepare`) sets the password from the environment and grants LOGIN, which is the
same split ``seed_platform_operator`` already uses for the operator identity: the migration
delivers the STRUCTURE, the deployment supplies the CREDENTIAL.

**Default privileges are the load-bearing half.** Granting on today's tables would leave every
table a future migration creates unreadable by the app, and the failure would surface as a
production 500 rather than a red test. ``ALTER DEFAULT PRIVILEGES`` is scoped to the role running
the migration (``FOR ROLE current_user`` implicitly), which is the same role every future migration
will run as, so new tables are covered by construction rather than by remembering.

The ``irp_ops`` precedent (migration `0003`) is followed exactly, including the idempotent
``DO $$ ... IF NOT EXISTS`` guard — a deploy must be re-runnable after a partial failure.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0070_app_role"
down_revision: str | None = "0069_legacy_tenant_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Fixed identifier, never user input — interpolation is safe (the `0003` precedent).
APP_ROLE = "irp_app"

#: No new permission code is minted here; P17's DELIVERS gate has nothing to read.
DELIVERS: tuple[str, ...] = ()


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # NOLOGIN on purpose: the credential is the deployment's to supply, not this file's to carry.
    # NOSUPERUSER NOBYPASSRLS are the two properties this entire migration exists to guarantee, and
    # they are asserted directly by `test_app_role_pg.py` rather than assumed from this text.
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') "
        f"THEN CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"
    )
    # Re-asserted even when the role already existed: the test tier creates `irp_app` with LOGIN and
    # a fixed password, and a database that has run the suite must not end up with an app role whose
    # properties came from a test fixture.
    op.execute(f"ALTER ROLE {APP_ROLE} NOSUPERUSER NOBYPASSRLS")

    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
    )
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    # Everything a LATER migration creates. Without this the app is broken by the next slice that
    # adds a table, and it would fail in production rather than in CI.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )


def downgrade() -> None:
    """Revoke and drop — but only what this revision granted.

    The role is dropped last and only after its privileges are revoked, because PostgreSQL refuses
    to drop a role that still owns or is granted anything. The DEFAULT PRIVILEGES entries must be
    revoked explicitly: dropping a role with default-privilege ACLs still referencing it fails with
    "cannot be dropped because some objects depend on it", which is the kind of thing a downgrade
    smoke finds and a reading does not — this project learned that on migration 0069 one day ago.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
