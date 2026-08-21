"""W19-S3b (REQ-INT-001 clause 6): ENT-078 ``ingestion_mapping_ratification``.

Four-eyes that cannot be edited into existence. A ratification is a NEW ROW referencing the mapping
version it decides — the ``entitlement_request`` / ``breach_action`` shape — rather than a mutation
of ENT-077's own columns, because ENT-077 is status-mutable by design and its content guard is an
ORM listener that does not fire on any non-ORM write path.

**IA TRUE append-only**: this table IS in ``APPEND_ONLY_TABLES``, carries the
``irp_prevent_mutation`` trigger, and its ORM class carries the guard too — the 0072
belt-and-braces pattern. ENT-075 shipped with only the trigger and its first mutation attempt was
caught by PostgreSQL rather than by the code.

**This table OWNS the "at most one RATIFIED mapping per source" invariant** (DS3b-5,
owner-ratified). ``data_source_id`` / ``source_type`` are denormalized from the version for exactly
that reason: the current mapping for a source is read from THIS append-only surface — the latest
resolution row for that source — rather than from ENT-077's mutable ``status``, the column this
table exists to stop trusting. It is enforced structurally, NOT by a partial unique index; the
upgrade-side note records the two attempts the database refused and why.

**CREATE TABLE only, and this migration therefore gets NO P17 harness**, by the same reasoning the
repo already applied to ``0074``: there are no pre-existing rows, so a populated-DB proof would be
vacuous and claiming one would be paperwork rather than evidence. Its DDL is proven by a
schema-reading PG test. ``0077`` ALTERs a table populated since ``0014`` and gets the real harness.

**Revision id is ``0076_mapping_ratification``, not ``0076_ingestion_mapping_ratification``** — the
latter is 35 characters and alembic's ``alembic_version.version_num`` is ``varchar(32)``. That is
the ``0073`` trap, avoided by counting rather than by discovering it during an upgrade.

PROPRIETARY, tenant-scoped, symmetric FORCE RLS. NEVER hybrid — the AD-013-R2 set is closed at seven.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID

revision: str = "0076_mapping_ratification"
down_revision: str | None = "0075_bind_batch_to_mapping"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: Entitlement codes this migration delivers (P17). EMPTY by measurement: the three mapping codes
#: are delivered by ``0077``, which is the commit that mints them. Written out rather than omitted
#: so a reader can tell "none" from "forgotten".
DELIVERS: tuple[str, ...] = ()

#: The CHECK suffixes — SUFFIX ONLY on both sides (the 0055/0057 lesson).
_CK_OUTCOME = "outcome"
_CK_RESOLVER = "resolver_present"

#: Asserted at import time (the P3-8/BT-1 63-char lesson). Every name this migration mints.
_IDENTIFIERS = (
    "ingestion_mapping_ratification",
    "pk_ingestion_mapping_ratification",
    "fk_ingestion_mapping_ratification_version",
    "uq_ingestion_mapping_ratification_seq",
    f"ck_ingestion_mapping_ratification_{_CK_OUTCOME}",
    f"ck_ingestion_mapping_ratification_{_CK_RESOLVER}",
    "ix_ingestion_mapping_ratification_tenant_id",
    "ix_ingestion_mapping_ratification_mapping_version_id",
    "ix_ingestion_mapping_ratification_tenant_outcome",
    "tenant_isolation_ingestion_mapping_ratification",
    "trg_ingestion_mapping_ratification_no_mutation",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]
assert len(revision) <= 32, f"alembic_version.version_num is varchar(32); {revision} is {len(revision)}"

#: This table joins the append-only set. Declared here because APPEND_ONLY_TABLES is a per-migration
#: constant on this project, not a shared runtime one.
APPEND_ONLY_TABLES: tuple[str, ...] = ("ingestion_mapping_ratification",)
TENANT_SCOPED_TABLES: tuple[str, ...] = ("ingestion_mapping_ratification",)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "ingestion_mapping_ratification",
        sa.Column("id", GUID, nullable=False),
        sa.Column("tenant_id", GUID, nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("mapping_version_id", GUID, nullable=False),
        sa.Column("data_source_id", GUID, nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("resolved_by", sa.String(255), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_mapping_ratification"),
        sa.ForeignKeyConstraint(
            ["mapping_version_id"],
            ["ingestion_mapping_version.id"],
            name="fk_ingestion_mapping_ratification_version",
        ),
        sa.UniqueConstraint("tenant_id", "seq", name="uq_ingestion_mapping_ratification_seq"),
        sa.CheckConstraint(
            "outcome IN ('RATIFIED', 'WITHDRAWN', 'SUPERSEDED')", name=_CK_OUTCOME
        ),
        sa.CheckConstraint(
            "resolved_by IS NOT NULL AND length(resolved_by) > 0", name=_CK_RESOLVER
        ),
    )
    op.create_index(
        "ix_ingestion_mapping_ratification_tenant_id",
        "ingestion_mapping_ratification",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ingestion_mapping_ratification_mapping_version_id",
        "ingestion_mapping_ratification",
        ["mapping_version_id"],
    )
    op.create_index(
        "ix_ingestion_mapping_ratification_tenant_outcome",
        "ingestion_mapping_ratification",
        ["tenant_id", "outcome"],
    )
    # NOTE there is deliberately NO partial unique index for "one current ratified mapping per
    # source". Two attempts were made and the database refused both: on an append-only log nothing
    # ever leaves a predicate, so `WHERE outcome='RATIFIED'` cannot express "currently ratified".
    # The invariant is enforced structurally instead — the current mapping is the one named by the
    # LATEST resolution row, and `uq_..._seq` makes "latest" unique by construction. See the ORM
    # model's comment for the full reasoning; it is recorded there because that is where a reader
    # looking for the missing index will go.

    if is_pg:
        op.execute("ALTER TABLE ingestion_mapping_ratification ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE ingestion_mapping_ratification FORCE ROW LEVEL SECURITY")
        # SYMMETRIC. The SYSTEM literal must NEVER appear — this table is PROPRIETARY and the
        # hybrid set is closed at seven, DB-censused.
        op.execute(
            "CREATE POLICY tenant_isolation_ingestion_mapping_ratification "
            "ON ingestion_mapping_ratification "
            "USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            "WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )
        # The append-only trigger. Unlike ENT-077, this table has NO status to transition — a
        # decision is made once.
        op.execute(
            "CREATE TRIGGER trg_ingestion_mapping_ratification_no_mutation "
            "BEFORE UPDATE OR DELETE ON ingestion_mapping_ratification "
            "FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_ingestion_mapping_ratification_no_mutation "
            "ON ingestion_mapping_ratification"
        )
        op.execute(
            "DROP POLICY IF EXISTS tenant_isolation_ingestion_mapping_ratification "
            "ON ingestion_mapping_ratification"
        )
    # NOTE: no `uq_ingestion_mapping_ratification_active` drop. An earlier draft of `upgrade()`
    # created that partial unique index; the index was removed when the DB refused two legitimate
    # replacements (see the upgrade-side note) and the matching drop survived here for one commit —
    # a downgrade that references a name `upgrade()` never creates. It is unreachable from any
    # from-empty test, because those never downgrade. Found by reading the pair together.
    op.drop_index(
        "ix_ingestion_mapping_ratification_tenant_outcome", "ingestion_mapping_ratification"
    )
    op.drop_index(
        "ix_ingestion_mapping_ratification_mapping_version_id",
        "ingestion_mapping_ratification",
    )
    op.drop_index(
        "ix_ingestion_mapping_ratification_tenant_id", "ingestion_mapping_ratification"
    )
    op.drop_table("ingestion_mapping_ratification")
