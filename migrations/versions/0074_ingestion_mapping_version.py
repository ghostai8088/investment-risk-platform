"""W19-S3a (REQ-INT-001): ENT-077 ``ingestion_mapping_version`` — the ratifiable source mapping.

INGEST-1's artifact (ratified 2026-08-12, OQ-ING-1..4): a mapping is versioned DATA interpreted by a
closed operation vocabulary, proposed by a model, ratified by a human, and executed deterministically
forever. Onboarding a client's file needs no software release, which is the whole economic argument.

**CREATE TABLE only — no data path, and this migration's proof says so honestly.** There are no
pre-existing rows to migrate, so a "P17 harness over a populated DB" would be vacuous here; the proof
that matters is a schema-reading PG test (``test_ingest_mapping_pg.py``): RLS enabled AND forced, the
symmetric authorship CHECK firing on both arms, the partial unique index genuinely partial, the FK
constraint names present un-truncated, and ``irp_ops`` holding no privilege. Migration ``0075``, which
ALTERs a table populated on every live deployment, is the one that gets the real committed harness.

PROPRIETARY, tenant-scoped, **symmetric** FORCE RLS (``USING`` == ``WITH CHECK``). NEVER hybrid — the
AD-013-R2 set is closed at seven. **No ``irp_prevent_mutation`` trigger and no APPEND_ONLY_TABLES
entry**: the ``status`` projection must transition PROPOSED -> RATIFIED -> SUPERSEDED, the
``ingestion_batch``/``calculation_run`` precedent. Content immutability is service-enforced.

No permission is minted here, so ``DELIVERS`` is empty BY MEASUREMENT rather than by omission: the
governed R-07 act at this slice mints one AUDIT code (``DATA.MAPPING``, whose taxonomy row is its
mint record), and audit codes are not delivered by migrations — only entitlement codes are.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID

revision: str = "0074_ingestion_mapping_version"
down_revision: str | None = "0073_declare_root_currency"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: Entitlement codes this migration delivers to running databases (P17). EMPTY by measurement: S3a
#: mints no permission — the ratifier code lands at S3b with the four-eyes lifecycle. Written out
#: rather than omitted so a reader can tell "none" from "forgotten".
DELIVERS: tuple[str, ...] = ()

#: The CHECK constraint SUFFIX only, on BOTH sides — ``env.py`` passes ``target_metadata`` so
#: ``op.create_table`` applies ``ck_%(table_name)s_%(constraint_name)s`` itself; the full name would
#: mint a doubled, 63-char-truncated name that DRIFTS from the ORM's, and ``alembic check`` does not
#: compare CHECK constraints so the drift gate is blind to it (the 0055/0057 lesson).
_CHECK_AUTHORSHIP = "authorship_evidence"

#: Every name this migration mints, asserted at import time (the P3-8/BT-1 63-char lesson, and the
#: classification_assignment.supersedes_id recurrence: PostgreSQL TRUNCATES silently, so an overflow
#: is a live drift rather than an error). Both FKs below carry EXPLICIT names because their
#: convention-generated forms are 68 chars.
_IDENTIFIERS = (
    "ingestion_mapping_version",
    "pk_ingestion_mapping_version",
    "fk_ingestion_mapping_version_data_source_id_data_source",
    "fk_ingestion_mapping_version_model_version",
    "fk_ingestion_mapping_version_supersedes",
    "uq_ingestion_mapping_version_label",
    "uq_ingestion_mapping_version_active",
    f"ck_ingestion_mapping_version_{_CHECK_AUTHORSHIP}",
    "ix_ingestion_mapping_version_tenant_id",
    "ix_ingestion_mapping_version_data_source_id",
    "ix_ingestion_mapping_version_proposer_model_version_id",
    "tenant_isolation_ingestion_mapping_version",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]

#: The authorship coherence constraint, SYMMETRIC in both directions — REQ-INT-001 clause (7)'s
#: teeth at the database. A MODEL_PROPOSED row must carry its model version and prompt identity; a
#: HAND_AUTHORED row must carry NEITHER, so stale or forged model attribution cannot sit on a row a
#: reviewer reads as operator-written.
_AUTHORSHIP_CHECK = (
    "(authorship = 'MODEL_PROPOSED' AND proposer_model_version_id IS NOT NULL "
    "AND proposal_prompt_hash IS NOT NULL) OR "
    "(authorship = 'HAND_AUTHORED' AND proposer_model_version_id IS NULL "
    "AND proposal_prompt_hash IS NULL)"
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "ingestion_mapping_version",
        sa.Column("id", GUID, nullable=False),
        sa.Column("tenant_id", GUID, nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source_id", GUID, nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("version_label", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("operations", sa.JSON(), nullable=False),
        sa.Column("operations_hash", sa.String(64), nullable=False),
        sa.Column("authorship", sa.String(20), nullable=False),
        sa.Column("proposer_model_version_id", GUID, nullable=True),
        sa.Column("proposal_prompt_hash", sa.String(64), nullable=True),
        sa.Column("proposal_prompt_ref", sa.String(255), nullable=True),
        sa.Column("proposal_response_ref", sa.String(255), nullable=True),
        sa.Column("proposed_by_actor_id", sa.String(255), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ratified_by_actor_id", sa.String(255), nullable=True),
        sa.Column("ratified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", GUID, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_mapping_version"),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_source.id"],
            name="fk_ingestion_mapping_version_data_source_id_data_source",
        ),
        sa.ForeignKeyConstraint(
            ["proposer_model_version_id"],
            ["model_version.id"],
            name="fk_ingestion_mapping_version_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["ingestion_mapping_version.id"],
            name="fk_ingestion_mapping_version_supersedes",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "source_type",
            "version_label",
            name="uq_ingestion_mapping_version_label",
        ),
        sa.CheckConstraint(_AUTHORSHIP_CHECK, name=_CHECK_AUTHORSHIP),
    )
    op.create_index(
        "ix_ingestion_mapping_version_tenant_id", "ingestion_mapping_version", ["tenant_id"]
    )
    op.create_index(
        "ix_ingestion_mapping_version_data_source_id",
        "ingestion_mapping_version",
        ["data_source_id"],
    )
    op.create_index(
        "ix_ingestion_mapping_version_proposer_model_version_id",
        "ingestion_mapping_version",
        ["proposer_model_version_id"],
    )
    # At most ONE ratified mapping per (tenant, source, source_type). The predicate is spelled on
    # BOTH dialects and IDENTICALLY: a postgresql_where-only index renders on SQLite as a PLAIN
    # unique index with the predicate silently DROPPED, which would make the unit tier reject a
    # legal second PROPOSED row while proving nothing about Postgres.
    op.create_index(
        "uq_ingestion_mapping_version_active",
        "ingestion_mapping_version",
        ["tenant_id", "data_source_id", "source_type"],
        unique=True,
        postgresql_where=sa.text("status = 'RATIFIED'"),
        sqlite_where=sa.text("status = 'RATIFIED'"),
    )

    if is_pg:
        op.execute("ALTER TABLE ingestion_mapping_version ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE ingestion_mapping_version FORCE ROW LEVEL SECURITY")
        # SYMMETRIC: the SYSTEM literal must NEVER appear here — this table is PROPRIETARY and the
        # hybrid set is closed at seven (a DB census asserts the SYSTEM-admitting set equals it).
        op.execute(
            "CREATE POLICY tenant_isolation_ingestion_mapping_version "
            "ON ingestion_mapping_version "
            "USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            "WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )
        # NO irp_prevent_mutation trigger, deliberately: status must transition. See the module
        # docstring — content immutability is service-enforced and mutation-proven instead.
        # NO grants: 0070's ALTER DEFAULT PRIVILEGES already covers irp_app for future tables, and
        # irp_ops must hold nothing here (a PG test asserts exactly that).


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS tenant_isolation_ingestion_mapping_version "
            "ON ingestion_mapping_version"
        )
    op.drop_index("uq_ingestion_mapping_version_active", "ingestion_mapping_version")
    op.drop_index(
        "ix_ingestion_mapping_version_proposer_model_version_id", "ingestion_mapping_version"
    )
    op.drop_index("ix_ingestion_mapping_version_data_source_id", "ingestion_mapping_version")
    op.drop_index("ix_ingestion_mapping_version_tenant_id", "ingestion_mapping_version")
    op.drop_table("ingestion_mapping_version")
