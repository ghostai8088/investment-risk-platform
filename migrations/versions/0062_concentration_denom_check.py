"""Wave-14 close fold: the CHECK `concentration_result.denominator_basis` never had.

CON-1 shipped ``denominator_basis`` described as a "controlled vocabulary" with six CHECK
constraints on the table and not one touching this column — while both sibling tables minted in
the same wave constrain theirs (0058's ``denominator_basis_vocab`` on ``limit_definition``, 0061's
``denominator_basis`` on ``liquidity_result``). The close's executed reproduction inserted
``'TOTAL_ASSETS_BOGUS'`` into a clone cleanly, with a working negative control on
``dimension_kind`` proving the probe itself sound. The finding was killed 2-of-3 on severity and
overturned at re-adjudication: the facts were never contradicted.

The vocabulary is single-valued by ratified design (CON-1's stopping rule after two refuted
denominator foundations); widening it is a MIGRATION by construction, which is the point.

**Downgrade:** drops the constraint only — no data movement either way. The P4 dry run verifies
the LIVE-CATALOG name (the 0057 double-prefix defect is invisible to text comparison), proves the
refusal fires on a staged bogus row, and proves the downgrade restores writability of that row.
"""

from __future__ import annotations

from alembic import op

revision: str = "0062_concentration_denom_check"  # <=32 chars: alembic_version.version_num is varchar(32)
down_revision: str | None = "0061_liquidity_result"
branch_labels: str | None = None
depends_on: str | None = None

#: Every DDL identifier this migration mints — asserted ≤ 63 at import (the P3-8/BT-1 lesson).
#: The FINAL name: ``op.create_check_constraint`` receives the SUFFIX and the naming convention
#: prepends ``ck_<table>_`` — verified against pg_constraint in the dry run, not assumed.
_IDENTIFIERS = ("ck_concentration_result_denominator_basis",)
assert all(len(n) <= 63 for n in _IDENTIFIERS)


def upgrade() -> None:
    op.create_check_constraint(
        "denominator_basis",  # SUFFIX only — the convention prepends ck_concentration_result_
        "concentration_result",
        "denominator_basis IN ('INVESTED_LONG')",
    )


def downgrade() -> None:
    # SUFFIX only, exactly like the create side: the naming convention wraps drop_constraint's
    # name too. The first draft passed the FULL name here and the dry run failed hunting
    # ck_concentration_result_ck_concentration_result_denomin_594c — trap T1, in the DOWNGRADE,
    # of the migration whose own docstring warns about trap T1. Text-vs-text review could never
    # see it: the create side was correct and symmetric. Only the executed round-trip caught it.
    op.drop_constraint("denominator_basis", "concentration_result", type_="check")
