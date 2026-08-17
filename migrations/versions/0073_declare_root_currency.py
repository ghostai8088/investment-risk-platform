"""STRUCT-4 (REQ-PPM-010, DP-11): backfill the reporting-currency declaration on undeclared ROOTS.

DP-11 as ratified: keep ``portfolio.base_currency_code``, BACKFILL, remove the silent USD default —
an undeclared node INHERITS its parent, an undeclared ROOT REFUSES. Every pre-STRUCT-4 governed
number on an undeclared book was computed under the silent ``or DEFAULT_BASE`` (USD) tail, so the
honest backfill stamps exactly that: each ROOT (``parent_portfolio_id IS NULL``) whose
``base_currency_code`` is NULL becomes an EXPLICIT ``'USD'`` declaration — the semantics those
books already had, now stated instead of defaulted. Non-root nodes are deliberately NOT touched:
NULL there now MEANS "inherit the parent" (DP-11), which is the correct reading of every existing
NULL child.

Data-only migration (no schema change — migration ``0073`` is "conditional" per the plan and the
condition is met by this backfill). Each touched head gets ``record_version + 1`` and one appended
ENT-076 history row stamped ``source='0073_BACKFILL'`` at the migration instant — the same
recorded-history-vs-honest-reconstruction distinction 0072 minted. The history INSERT is lawful
(the ``irp_prevent_mutation`` trigger blocks UPDATE/DELETE, never INSERT) and satisfies
``uq_portfolio_hierarchy_version_node_version`` because the head version was bumped first.

``portfolio`` and ``portfolio_hierarchy_version`` have carried FORCE RLS since their own
migrations, so this backfill CANNOT be ordered before an RLS block the way 0072's was — it runs
under a role that bypasses RLS (every current runner is a PG superuser; a hardened NOSUPERUSER
migration owner without BYPASSRLS would see zero rows and no-op silently, which the printed
row count makes visible).

``downgrade`` is a deliberate NO-OP: the appended history rows are IA append-only (trigger-
guarded), and un-declaring a currency would re-create the silent-default books DP-11 exists to
kill. (Re-upgrading after a downgrade is idempotent — the ``WHERE base_currency_code IS NULL``
predicate finds nothing to touch a second time.)

**Verify-status consequence (review fold C4, BY DESIGN):** any pre-0073 snapshot that pinned a
previously-undeclared root will report PORTFOLIO-component DRIFT on ``verify_snapshot`` after
this migration — the live head's ``base_currency_code`` and ``record_version`` both changed,
which is exactly what verify exists to say (an EV amend IS drift). Reproduction is unaffected:
the reproduction adapters read pins only, never the live head. The first post-deploy verify red
on an old snapshot is this, not a reproduction failure.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0073_declare_root_currency"  # <=32 chars: alembic_version is varchar(32)
down_revision: str | None = "0072_portfolio_hierarchy_version"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        new_id = "gen_random_uuid()"
        now = "now()"
    else:
        # SQLite (unit tier creates via create_all; this branch covers a migrated SQLite file).
        new_id = (
            "lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || "
            "substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab', abs(random()) % 4 + 1, 1)"
            " || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))"
        )
        now = "CURRENT_TIMESTAMP"

    roots = bind.execute(
        sa.text(
            "SELECT id FROM portfolio "
            "WHERE parent_portfolio_id IS NULL AND base_currency_code IS NULL"
        )
    ).fetchall()
    for (root_id,) in roots:
        bind.execute(
            sa.text(
                "UPDATE portfolio SET base_currency_code = 'USD', "
                "record_version = record_version + 1 WHERE id = :id"
            ),
            {"id": root_id},
        )
        bind.execute(
            sa.text(
                f"INSERT INTO portfolio_hierarchy_version "  # noqa: S608 - constants above
                f"(id, tenant_id, portfolio_id, parent_portfolio_id, node_type, name, status, "
                f"base_currency_code, record_version, effective_at, system_from, source) "
                f"SELECT {new_id}, tenant_id, id, parent_portfolio_id, node_type, name, status, "
                f"base_currency_code, record_version, {now}, {now}, '0073_BACKFILL' "
                f"FROM portfolio WHERE id = :id"
            ),
            {"id": root_id},
        )
    print(  # noqa: T201 - migration console output
        f"0073: declared 'USD' on {len(roots)} previously-undeclared root(s) "
        "(the silent default those books computed under, now stated)"
    )


def downgrade() -> None:
    # Deliberate no-op — see the module docstring (append-only history; un-declaring would
    # resurrect the silent-default books DP-11 kills).
    pass
