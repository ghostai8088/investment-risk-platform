"""W19-S3a (REQ-INT-001 clause 2, the batch half): bind ``ingestion_batch`` to its mapping version.

The one hook the INGEST-1 decision record named as the gap: *"``ingestion_batch`` — shipped; binds
``data_source_id``. **GAP:** binds no mapping version."* This migration closes it, and adds the
``lookup_as_of`` instant that makes clause (9)'s third input readable back rather than assumed.

**NULLABLE, and the reason is a data-path decision rather than a style choice.** ``ingestion_batch``
carries pre-existing rows on every live deployment, and a generic non-positions upload legitimately
has no mapping — the anti-corruption layer stages files this spine never interprets. A NOT NULL
column here would be undeliverable to a running database (the 0064 class P17 exists for), and
back-filling a sentinel mapping version would invent a governance record that never happened. So the
column is nullable with an honest docstring (the 0046 precedent) and the LOAD PATH requires it, not
the schema: ``load_batch`` stamps it, and a position can only be written through ``load_batch``.

Pre-0075 batches are unresolvable to a mapping version, permanently and by construction. That is
recorded here rather than papered over: they were staged before the spine existed.

**This is the migration with the real data path, so this is the one with the committed P17 harness**
(``scripts/migration_0075_p17_check.py``) — run over populated ``ingestion_batch`` rows, with a
negative control (a pre-existing batch the migration must leave untouched and NULL).

Explicit FK name: the convention-generated
``fk_ingestion_batch_mapping_version_id_ingestion_mapping_version`` is exactly 63 characters — at
PostgreSQL's limit rather than over it, which is not a margin. Named explicitly so a future column
rename cannot push it over silently.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID

revision: str = "0075_bind_batch_to_mapping"
down_revision: str | None = "0074_ingestion_mapping_version"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: Entitlement codes delivered here (P17). EMPTY by measurement — S3a mints no permission.
DELIVERS: tuple[str, ...] = ()

#: Asserted at import time (the P3-8/BT-1 63-char lesson).
_IDENTIFIERS = (
    "fk_ingestion_batch_mapping_version",
    "ix_ingestion_batch_mapping_version_id",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.add_column(
        "ingestion_batch",
        sa.Column("mapping_version_id", GUID, nullable=True),
    )
    op.add_column(
        "ingestion_batch",
        sa.Column("lookup_as_of", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_ingestion_batch_mapping_version_id", "ingestion_batch", ["mapping_version_id"]
    )
    op.create_foreign_key(
        "fk_ingestion_batch_mapping_version",
        "ingestion_batch",
        "ingestion_mapping_version",
        ["mapping_version_id"],
        ["id"],
    )
    # No backfill: see the module docstring. Pre-0075 batches stay NULL, honestly.
    rows = op.get_bind().execute(sa.text("SELECT count(*) FROM ingestion_batch")).scalar_one()
    print(  # noqa: T201 - migration console output
        f"0075: ingestion_batch now binds a mapping version; {rows} pre-existing batch row(s) "
        f"left NULL (staged before the mapping spine existed)"
    )


def downgrade() -> None:
    with op.batch_alter_table("ingestion_batch") as batch:
        batch.drop_constraint("fk_ingestion_batch_mapping_version", type_="foreignkey")
    op.drop_index("ix_ingestion_batch_mapping_version_id", "ingestion_batch")
    op.drop_column("ingestion_batch", "lookup_as_of")
    op.drop_column("ingestion_batch", "mapping_version_id")
