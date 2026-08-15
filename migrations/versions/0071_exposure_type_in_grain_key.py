"""STRUCT-1 (REQ-PPM-006, Wave 18): ``exposure_type`` into the exposure uniqueness key.

**The defect this pays.** ``exposure_aggregate.exposure_type`` has existed since migration 0018 and
``uq_exposure_aggregate_run_grain`` has never included it, so two measures for one holding in one
run collide at the DB. The requirement row states this verbatim. With the STRUCT-1 second measure
(NOTIONAL beside MARKET_VALUE, one row per measure in the SAME run) the old key is not merely
narrow — it makes the ratified run shape impossible.

**Collision-free by construction, not by assertion.** The narrow key being widened is a strict
SUBSET of the wide one, and it is still ENFORCED at ALTER time — any row set satisfying the narrow
uniqueness satisfies the wide one a fortiori, so the create cannot fail on data the old constraint
admitted. An earlier draft carried a pre-ALTER duplicate SELECT; the review refuted it as a guard
that cannot fire (the old constraint forecloses every duplicate it could find, and under FORCE RLS
a non-superuser runner's SELECT sees zero rows regardless) — the platform's own Wave-17 class, so
it was deleted rather than shipped as assertion theater.

**Lockstep.** The ORM ``UniqueConstraint`` in ``irp_shared/exposure/models.py`` was widened in the
same commit — the two definitions are byte-equivalent in column order. The append-only trigger
(``irp_prevent_mutation``, migration 0018) polices row mutation, not constraints, and is untouched.

Downgrade restores the narrow key. It will FAIL if multi-measure rows exist by then — correctly:
narrowing a key under data that needs the wide one is a data-loss decision, not a rollback.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0071_exposure_type_in_grain_key"
down_revision: str | None = "0070_app_role"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLE = "exposure_aggregate"
_NAME = "uq_exposure_aggregate_run_grain"
_OLD_COLS = ["calculation_run_id", "portfolio_id", "instrument_id", "base_currency"]
_NEW_COLS = [*_OLD_COLS, "exposure_type"]


def upgrade() -> None:
    op.drop_constraint(_NAME, _TABLE, type_="unique")
    op.create_unique_constraint(_NAME, _TABLE, _NEW_COLS)


def downgrade() -> None:
    op.drop_constraint(_NAME, _TABLE, type_="unique")
    op.create_unique_constraint(_NAME, _TABLE, _OLD_COLS)
