"""The P17 populated-database exercise for migration 0075 (W19-S3a) — a COMMITTED harness.

``0075`` ALTERs ``ingestion_batch``, a table populated on every live deployment since P1A-4. The
full-PG battery migrates an EMPTY schema and therefore cannot exercise the data path at all — a
green battery over an empty database says nothing about a migration's behaviour over rows (CI
caught ``0069`` exactly that way). This harness proves it over real rows.

**What it proves, positively:** a batch that existed BEFORE the mapping spine survives the upgrade
with every one of its own columns unchanged and ``mapping_version_id`` / ``lookup_as_of`` NULL —
the honest state, because it really was staged before a mapping version could exist. Then the new
FK is proven live by writing a real mapping version and binding the pre-existing batch to it.

**The negative controls, and there are two:**

1. A SECOND pre-existing batch that nothing binds — it must still read NULL after the first is
   bound, so "the column is populated" cannot be an artefact of the migration back-filling
   something. ``0075`` deliberately back-fills nothing.
2. A cross-table guard: binding a batch to a mapping version id that does not exist must be
   REFUSED by the FK. Without this the column would be free text with extra steps, which is
   precisely what the amended REQ-INT-001 clause (2) bans.

**Why this migration gets a harness and ``0074`` does not, stated so the asymmetry is not read as
an omission:** ``0074`` CREATES a table, so there are no pre-existing rows and a populated-DB proof
would be vacuous. Its DDL is proven by a schema-reading PG test instead
(``test_ingest_mapping_pg.py``). Claiming a P17 harness for a create-table migration would be
paperwork, not evidence.

Destructive by design — point it ONLY at a disposable validation database:

    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \\
        python scripts/migration_0075_p17_check.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

_PRE_MIGRATION_COLUMNS = (
    "filename",
    "content_type",
    "byte_size",
    "status",
    "scan_status",
    "row_count",
    "staged_count",
    "failed_count",
)


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (a DISPOSABLE validation database)", file=sys.stderr)
        return 2

    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0074_ingestion_mapping_version"],
        check=True,
    )

    from irp_shared.db.session import make_engine

    engine = make_engine(url, poolclass=NullPool)

    tenant = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    bound_batch, untouched_batch = str(uuid.uuid4()), str(uuid.uuid4())

    # RAW inserts, deliberately: this reproduces the PRE-0075 world, in which no mapping version
    # could be referenced because the column did not exist. The migration owner bypasses RLS here —
    # exactly the migration's own execution posture, stated rather than left as a surprise.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO data_source (id, tenant_id, code, name, source_type, is_active, "
                "record_version, valid_from, created_at, updated_at) VALUES "
                "(:s, :t, 'P17-CUSTODIAN', 'p17 custodian feed', 'upload', true, 1, "
                "now(), now(), now())"
            ),
            {"s": source_id, "t": tenant},
        )
        conn.execute(
            text(
                "INSERT INTO ingestion_batch (id, tenant_id, system_from, data_source_id, "
                "filename, content_type, byte_size, status, scan_status, row_count, "
                "staged_count, failed_count, started_at) VALUES "
                "(:b, :t, now(), :s, 'p17-bound.csv', 'text/csv', 2048, 'COMPLETED', "
                "'SKIPPED', 7, 7, 0, now()), "
                "(:u, :t, now(), :s, 'p17-untouched.csv', 'text/csv', 512, "
                "'COMPLETED', 'SKIPPED', 3, 3, 1, now())"
            ),
            {"b": bound_batch, "u": untouched_batch, "t": tenant, "s": source_id},
        )
        before = {
            row[0]: row[1:]
            for row in conn.execute(
                text(
                    f"SELECT id, {', '.join(_PRE_MIGRATION_COLUMNS)} FROM ingestion_batch "  # noqa: S608
                    "WHERE tenant_id = CAST(:t AS uuid) ORDER BY filename"
                ),
                {"t": tenant},
            ).fetchall()
        }

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    with engine.begin() as conn:
        after = {
            row[0]: row[1:]
            for row in conn.execute(
                text(
                    f"SELECT id, {', '.join(_PRE_MIGRATION_COLUMNS)} FROM ingestion_batch "  # noqa: S608
                    "WHERE tenant_id = CAST(:t AS uuid) ORDER BY filename"
                ),
                {"t": tenant},
            ).fetchall()
        }
        nulls = conn.execute(
            text(
                "SELECT id, mapping_version_id, lookup_as_of FROM ingestion_batch "
                "WHERE tenant_id = CAST(:t AS uuid)"
            ),
            {"t": tenant},
        ).fetchall()

    if {str(k) for k in before} != {str(k) for k in after}:
        raise RuntimeError(f"batch rows changed identity across the upgrade: {before} -> {after}")
    for key, values in before.items():
        if after[key] != values:
            raise RuntimeError(
                f"a PRE-EXISTING batch's own columns changed across 0075: "
                f"{key}: {values} -> {after[key]}"
            )
    if any(row[1] is not None or row[2] is not None for row in nulls):
        raise RuntimeError(
            f"0075 back-filled something — pre-existing batches must stay honestly NULL: {nulls}"
        )

    # The FK is LIVE: bind the pre-existing batch to a real mapping version...
    mapping_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ingestion_mapping_version (id, tenant_id, system_from, "
                "data_source_id, source_type, version_label, status, operations, "
                "operations_hash, authorship, proposed_by_actor_id, proposed_at) VALUES "
                "(:m, :t, now(), :s, 'POSITIONS', 'p17-v1', 'RATIFIED', '[]', "
                "'0000000000000000000000000000000000000000000000000000000000000000', "
                "'HAND_AUTHORED', 'p17@irp', now())"
            ),
            {"m": mapping_id, "t": tenant, "s": source_id},
        )
        conn.execute(
            text(
                "UPDATE ingestion_batch SET mapping_version_id = CAST(:m AS uuid), "
                "lookup_as_of = now() WHERE id = CAST(:b AS uuid)"
            ),
            {"m": mapping_id, "b": bound_batch},
        )
        bound = conn.execute(
            text(
                "SELECT mapping_version_id IS NOT NULL, lookup_as_of IS NOT NULL "
                "FROM ingestion_batch WHERE id = CAST(:b AS uuid)"
            ),
            {"b": bound_batch},
        ).one()
        # NEGATIVE CONTROL 1: the sibling stays NULL, so a populated column cannot be an artefact.
        still_null = conn.execute(
            text(
                "SELECT mapping_version_id, lookup_as_of FROM ingestion_batch "
                "WHERE id = CAST(:u AS uuid)"
            ),
            {"u": untouched_batch},
        ).one()

    if bound != (True, True):
        raise RuntimeError(f"the pre-existing batch did not bind its mapping version: {bound}")
    if still_null != (None, None):
        raise RuntimeError(f"the untouched sibling batch was modified: {still_null}")

    # NEGATIVE CONTROL 2: the FK REFUSES an id that does not exist. A hard FK is the whole point of
    # the amended clause (2) — "never a free-text field" — so this is what makes the column an
    # attribution rather than a string that happens to look like one.
    refused = False
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE ingestion_batch SET mapping_version_id = CAST(:m AS uuid) "
                    "WHERE id = CAST(:u AS uuid)"
                ),
                {"m": str(uuid.uuid4()), "u": untouched_batch},
            )
    except IntegrityError:
        refused = True
    if not refused:
        raise RuntimeError(
            "a NON-EXISTENT mapping version id was accepted — the FK is not enforcing, so the "
            "column is free text with extra steps"
        )

    # THE WIDENING, proven over a row that already existed. `ingestion_batch.status` was
    # varchar(20) from migration 0007 while the vocabulary declared the 23-character
    # COMPLETED_WITH_WARNINGS, so a batch finishing with a DQ warning could not be stored on
    # PostgreSQL at all. This is the data-path half of that fix: the value goes into a
    # PRE-EXISTING row and reads back whole.
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ingestion_batch SET status = 'COMPLETED_WITH_WARNINGS' "
                "WHERE id = CAST(:u AS uuid)"
            ),
            {"u": untouched_batch},
        )
        widened = conn.execute(
            text("SELECT status FROM ingestion_batch WHERE id = CAST(:u AS uuid)"),
            {"u": untouched_batch},
        ).scalar_one()
    if widened != "COMPLETED_WITH_WARNINGS":
        raise RuntimeError(f"the widened status column truncated its own vocabulary: {widened!r}")

    engine.dispose()
    print(
        f"P17 OK: {len(before)} pre-existing batch row(s) survived 0075 unchanged and NULL; "
        f"the FK binds a real mapping version and REFUSES a non-existent one; "
        f"status widened to hold COMPLETED_WITH_WARNINGS"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
