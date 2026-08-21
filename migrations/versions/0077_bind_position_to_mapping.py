"""W19-S3b (REQ-INT-001 clause 2, the position half): bind canonical holdings to their mapping.

The clause: *"every loaded position row binds the ratifying mapping version by hard FK — never a
free-text field"*. S3a delivered the batch half and left this one, because `position` has been
populated on every live deployment since `0014` and the column's SEMANTICS needed deciding first.

**NULLABLE, necessarily.** A hand-captured holding has no mapping version, and there are real rows
predating the spine. Nullable-plus-an-honest-docstring is the `0046` precedent; the LOAD PATH
requires the value, not the schema.

**The trap this column exists inside, recorded because it would have shipped silently.** The FR
binders build each new version from `{**carried, **new_fields}` where `carried` is exactly
`POSITION_FIELDS`. So:

- OUTSIDE `POSITION_FIELDS`, the column is dropped to NULL on every supersede and every correction
  — and `load_batch` issues BOTH verbs. A provenance FK would be populated on first capture and
  NULL on every subsequent load of the same holding: it would vanish exactly when the second file
  arrived.
- INSIDE `POSITION_FIELDS`, it carries forward blindly, so a hand-typed manual supersede of a
  file-loaded holding would inherit a mapping version that never produced it — the false-provenance
  class, which is worse than no attribution because a reader cannot tell it from a real one.

Neither default is right. The column is therefore NOT in `POSITION_FIELDS` and the three binders
take it as an EXPLICIT keyword: the interpreter passes the version that produced the row it is
writing; a manual call passes nothing and gets NULL.

**It is NOT added to `position_content`** — the snapshot hash. Measured, not reasoned: every
POSITION component in a seeded database currently re-serializes to its stored hash, and adding the
key with a NULL value breaks all of them, across a third of the snapshots. The affected surface is
`verify_snapshot` / `GET /snapshots/{id}/verify` — *not* the CTRL-018 sweep, which S3a's records
named and which does not read snapshot content hashes at all. That correction is recorded in the
S3b remit's Part 0.

**This migration ALTERs a populated table, so it gets the real P17 harness**
(`scripts/migration_0077_p17_check.py`) with both negative controls — unlike `0076`, which CREATEs
a table and for which a populated-DB proof would be vacuous.

Explicit FK name `fk_position_mapping_version`: naming the column `ingestion_mapping_version_id`
instead would generate a 66-char name and PostgreSQL truncates at 63 SILENTLY.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID

revision: str = "0077_bind_position_to_mapping"
down_revision: str | None = "0076_mapping_ratification"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: Entitlement codes this migration delivers to running databases (P17). NON-EMPTY: this is the
#: commit that mints the mapping governance codes, and appending to `bootstrap.PERMISSIONS` alone
#: is a mint for FUTURE deployments only — a database already running never sees it, and every
#: from-empty test passes over the gap.
DELIVERS: tuple[str, ...] = (
    "ingest.mapping.propose",
    "ingest.mapping.ratify",
    "ingest.mapping.view",
)

#: Asserted at import time (the P3-8/BT-1 63-char lesson).
_IDENTIFIERS = (
    "fk_position_mapping_version",
    "ix_position_mapping_version_id",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]
assert len(revision) <= 32, (
    f"alembic_version.version_num is varchar(32); {revision} is {len(revision)}"
)

#: A FIXED timestamp, not `func.now()`. `sync_catalog` binds this as a parameter, and a SQL
#: function object cannot be adapted to one — found by executing the migration, which is the only
#: way this class ever gets found. It is also the right choice on its own terms: a migration that
#: stamps wall-clock time produces a different database on every run.
SYNC_TS = datetime(2026, 8, 21, 12, 0, 0, tzinfo=UTC)


def upgrade() -> None:
    op.add_column("position", sa.Column("mapping_version_id", GUID, nullable=True))
    op.create_index("ix_position_mapping_version_id", "position", ["mapping_version_id"])
    op.create_foreign_key(
        "fk_position_mapping_version",
        "position",
        "ingestion_mapping_version",
        ["mapping_version_id"],
        ["id"],
    )
    # No backfill, and the silence is deliberate: rows captured before the spine existed have no
    # mapping version, and inventing one would be a false provenance record. They stay NULL.
    rows = op.get_bind().execute(sa.text('SELECT count(*) FROM "position"')).scalar_one()
    print(  # noqa: T201 - migration console output
        f"0077: position now binds a mapping version; {rows} pre-existing row(s) left NULL "
        f"(captured before the mapping spine existed)"
    )

    # The three mapping governance codes, delivered to THIS database. Appending to the catalog
    # constant is not a mint (P17): `0002` seeds from the live constants so every from-empty
    # database gets them with no migration at all, which is exactly why the undelivered case is
    # invisible to the unit tier.
    from irp_shared.entitlement.sync import sync_catalog

    report = sync_catalog(op.get_bind(), now=SYNC_TS)
    print(  # noqa: T201 - migration console output
        f"0077: +{report.permissions_inserted} permissions, +{report.grants_inserted} grants"
        + (
            f"; {len(report.grants_skipped_revoked)} revoked grant(s) NOT resurrected"
            if report.grants_skipped_revoked
            else ""
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("position") as batch:
        batch.drop_constraint("fk_position_mapping_version", type_="foreignkey")
    op.drop_index("ix_position_mapping_version_id", "position")
    op.drop_column("position", "mapping_version_id")
    # The permission rows are NOT removed. A downgrade that revoked a granted permission would be a
    # governance act disguised as a schema rollback, and `sync_catalog` is additive-only by design
    # for the mirror-image reason (it must not resurrect a deliberately revoked grant).
