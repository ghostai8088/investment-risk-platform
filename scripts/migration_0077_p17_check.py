"""The P17 populated-database exercise for migration 0077 (W19-S3b) — a COMMITTED harness.

``0077`` ALTERs ``position``, a table populated on every live deployment since ``0014``. The
full-PG battery migrates an EMPTY schema and cannot exercise the data path at all — a green battery
over an empty database says nothing about a migration's behaviour over rows (CI caught ``0069``
exactly that way).

**What it proves, positively:** a holding captured BEFORE the mapping spine survives the upgrade
with every one of its own columns unchanged and ``mapping_version_id`` NULL — the honest state,
because it really was captured before a mapping version could exist. Then the FK is proven live by
binding that pre-existing row to a real mapping version.

**Three negative controls:**

1. A SECOND pre-existing holding that nothing binds stays NULL, so "the column is populated" cannot
   be an artefact of the migration back-filling something. ``0077`` back-fills nothing.
2. A non-existent mapping version id is REFUSED by the FK. Without this the column would be free
   text with extra steps, which is exactly what the amended REQ-INT-001 clause (2) bans.
3. **The permission delivery arm**: the three mapping codes must be present in ``permission`` AFTER
   the upgrade and ABSENT before it. Appending to ``bootstrap.PERMISSIONS`` is not a mint — a
   database already running never sees a code added afterwards, and every from-empty test passes
   over the gap because ``0002`` seeds from the live constants. That is the whole reason P17 exists,
   and it is the arm a harness copied from ``0075`` would not have.

Destructive by design — point it ONLY at a disposable validation database:

    DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \\
        python scripts/migration_0077_p17_check.py
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
    "quantity",
    "cost_basis",
    "quantity_unit",
    "position_source",
    "record_version",
)

_MINTED_CODES = ("ingest.mapping.propose", "ingest.mapping.ratify", "ingest.mapping.view")


def _codes_present(conn) -> set[str]:  # noqa: ANN001
    rows = conn.execute(
        text("SELECT code FROM permission WHERE code = ANY(:codes)"),
        {"codes": list(_MINTED_CODES)},
    ).fetchall()
    return {r[0] for r in rows}


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required (a DISPOSABLE validation database)", file=sys.stderr)
        return 2

    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0076_mapping_ratification"], check=True
    )

    from irp_shared.db.session import make_engine

    engine = make_engine(url, poolclass=NullPool)

    tenant = str(uuid.uuid4())
    portfolio_id, instrument_id_a, instrument_id_b = (str(uuid.uuid4()) for _ in range(3))
    bound_row, untouched_row = str(uuid.uuid4()), str(uuid.uuid4())
    source_id, mapping_id = str(uuid.uuid4()), str(uuid.uuid4())

    # RAW inserts: this reproduces the PRE-0077 world, in which no mapping version could be
    # referenced because the column did not exist. The migration owner bypasses RLS here — the
    # migration's own execution posture, stated rather than left as a surprise.
    with engine.begin() as conn:
        # CONSTRUCT the pre-existing-database state, because the migration chain CANNOT produce
        # it — and that is a fact about this repo, not a shortcut.
        #
        # A database that has been running since before this mint has 0077's ancestors and NOT the
        # three codes. But `0002` seeds `permission` from the LIVE `bootstrap.PERMISSIONS`
        # constant at upgrade time, and this slice added the codes to that constant — so ANY
        # database built from empty today already has them at revision 0076, whatever route it
        # took. There is no reachable starting state in which `before_codes` is naturally empty.
        #
        # This was found by a different-engine review AFTER an exit-0 run of this harness had been
        # quoted as evidence. That run was real, but the database it ran against had executed
        # `0002` BEFORE the constant changed — a state nobody can rebuild from the repository. An
        # unreproducible green is not evidence, and the harness now says so by building the state
        # it needs rather than depending on one that happened to exist.
        conn.execute(
            text(
                "DELETE FROM role_permission WHERE permission_id IN "
                "(SELECT id FROM permission WHERE code = ANY(:codes))"
            ),
            {"codes": list(_MINTED_CODES)},
        )
        conn.execute(
            text("DELETE FROM permission WHERE code = ANY(:codes)"),
            {"codes": list(_MINTED_CODES)},
        )
        before_codes = _codes_present(conn)
        conn.execute(
            text(
                "INSERT INTO portfolio (id, tenant_id, code, name, node_type, status, "
                "record_version, valid_from, created_at, updated_at) VALUES "
                "(:p, :t, 'P17-BOOK', 'p17 book', 'FUND', 'ACTIVE', 1, now(), now(), now())"
            ),
            {"p": portfolio_id, "t": tenant},
        )
        for iid, code in ((instrument_id_a, "P17-A"), (instrument_id_b, "P17-B")):
            conn.execute(
                text(
                    "INSERT INTO instrument (id, tenant_id, code, name, asset_class, is_active, "
                    "record_version, valid_from, created_at, updated_at) VALUES "
                    "(:i, :t, :c, 'p17 instrument', 'EQUITY', true, 1, now(), now(), now())"
                ),
                {"i": iid, "t": tenant, "c": code},
            )
        conn.execute(
            text(
                "INSERT INTO data_source (id, tenant_id, code, name, source_type, is_active, "
                "record_version, valid_from, created_at, updated_at) VALUES "
                "(:s, :t, 'P17-FEED', 'p17 feed', 'upload', true, 1, now(), now(), now())"
            ),
            {"s": source_id, "t": tenant},
        )
        conn.execute(
            text(
                "INSERT INTO ingestion_mapping_version (id, tenant_id, system_from, "
                "data_source_id, source_type, version_label, status, operations, "
                "operations_hash, authorship, proposed_by_actor_id, proposed_at) VALUES "
                "(:m, :t, now(), :s, 'POSITIONS', 'p17-v1', 'RATIFIED', '[]', :h, "
                "'HAND_AUTHORED', 'p17@irp', now())"
            ),
            {"m": mapping_id, "t": tenant, "s": source_id, "h": "0" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO position (id, tenant_id, portfolio_id, instrument_id, quantity, "
                "cost_basis, quantity_unit, record_version, valid_from, system_from, "
                "created_at, updated_at) VALUES "
                "(:a, :t, :p, :ia, 100.5, 250.25, 'SHARES', 1, now(), now(), now(), now()), "
                "(:b, :t, :p, :ib, -42.0, -80.00, 'SHARES', 1, now(), now(), now(), now())"
            ),
            {
                "a": bound_row,
                "b": untouched_row,
                "t": tenant,
                "p": portfolio_id,
                "ia": instrument_id_a,
                "ib": instrument_id_b,
            },
        )
        before = {
            row[0]: row[1:]
            for row in conn.execute(
                text(
                    f"SELECT id, {', '.join(_PRE_MIGRATION_COLUMNS)} FROM position "  # noqa: S608
                    "WHERE tenant_id = CAST(:t AS uuid) ORDER BY id"
                ),
                {"t": tenant},
            ).fetchall()
        }

    if before_codes:
        raise RuntimeError(
            f"the mapping codes are STILL present after being deleted: {sorted(before_codes)} — "
            "the delivery arm below would pass vacuously, which is the one thing it must not do"
        )

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    with engine.begin() as conn:
        after = {
            row[0]: row[1:]
            for row in conn.execute(
                text(
                    f"SELECT id, {', '.join(_PRE_MIGRATION_COLUMNS)} FROM position "  # noqa: S608
                    "WHERE tenant_id = CAST(:t AS uuid) ORDER BY id"
                ),
                {"t": tenant},
            ).fetchall()
        }
        nulls = conn.execute(
            text("SELECT id, mapping_version_id FROM position WHERE tenant_id = CAST(:t AS uuid)"),
            {"t": tenant},
        ).fetchall()
        after_codes = _codes_present(conn)

    if {str(k) for k in before} != {str(k) for k in after}:
        raise RuntimeError(
            f"position rows changed identity across the upgrade: {before} -> {after}"
        )
    for key, values in before.items():
        if after[key] != values:
            raise RuntimeError(
                f"a PRE-EXISTING holding's own columns changed across 0077: "
                f"{key}: {values} -> {after[key]}"
            )
    if any(row[1] is not None for row in nulls):
        raise RuntimeError(
            f"0077 back-filled something — rows captured before the spine must stay honestly NULL, "
            f"because inventing a mapping version for them would be a false provenance record: "
            f"{nulls}"
        )

    # NEGATIVE CONTROL 3, and the one a harness copied from 0075 would not have: the codes are
    # DELIVERED to this already-running database. Appending to the catalog constant is not a mint.
    missing = set(_MINTED_CODES) - after_codes
    if missing:
        raise RuntimeError(
            f"0077 did not deliver {sorted(missing)} to a running database — deny-by-default would "
            f"403 every holder in production while every from-empty test passed (P17)"
        )

    # The FK is LIVE: bind a PRE-EXISTING holding to a real mapping version.
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE position SET mapping_version_id = CAST(:m AS uuid) "
                "WHERE id = CAST(:a AS uuid)"
            ),
            {"m": mapping_id, "a": bound_row},
        )
        bound = conn.execute(
            text("SELECT mapping_version_id IS NOT NULL FROM position WHERE id = CAST(:a AS uuid)"),
            {"a": bound_row},
        ).scalar_one()
        # NEGATIVE CONTROL 1: the sibling stays NULL.
        still_null = conn.execute(
            text("SELECT mapping_version_id FROM position WHERE id = CAST(:b AS uuid)"),
            {"b": untouched_row},
        ).scalar_one()

    if bound is not True:
        raise RuntimeError("the pre-existing holding did not bind its mapping version")
    if still_null is not None:
        raise RuntimeError(f"the untouched sibling holding was modified: {still_null}")

    # NEGATIVE CONTROL 2: the FK REFUSES an id that does not exist.
    refused = False
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE position SET mapping_version_id = CAST(:m AS uuid) "
                    "WHERE id = CAST(:b AS uuid)"
                ),
                {"m": str(uuid.uuid4()), "b": untouched_row},
            )
    except IntegrityError:
        refused = True
    if not refused:
        raise RuntimeError(
            "a NON-EXISTENT mapping version id was accepted — the FK is not enforcing, so the "
            "column is free text with extra steps and clause (2)'s 'never free text' is not met"
        )

    engine.dispose()
    print(
        f"P17 OK: {len(before)} pre-existing holding(s) survived 0077 unchanged and NULL; the FK "
        f"binds a real mapping version and REFUSES a non-existent one; "
        f"{len(_MINTED_CODES)} permission code(s) delivered to a running database"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
