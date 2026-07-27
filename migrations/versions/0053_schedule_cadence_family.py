"""SCH-2: relax ``schedule.model_version_id`` + ``interval_days``, gated by per-family CHECKs.

The scheduler ships its SECOND family (``EXPOSURE_AGGREGATE``) and its SECOND cadence
(``CALENDAR_MONTH_END``), discharging the SCH-1 family-agnostic deferral the Wave-11 close parked
for "whichever slice first ships family 2". Two header columns cannot stay NOT NULL:

- ``model_version_id`` — ``run_exposure`` is the MODEL-LESS deterministic rollup (it takes no
  ``model_version_id`` at all), so an EXPOSURE schedule cannot honestly nominate one.
- ``interval_days`` — meaningless under a calendar-generated grid.

Neither becomes a blanket nullable. ``model_version_id`` is a CTRL-003 inventory-before-use
affordance, so both are gated by **TOTAL-ENUMERATION** CHECKs (verifier M1): the implication form
``(type <> 'VAR' OR mv IS NOT NULL) AND (type <> 'EXPOSURE_AGGREGATE' OR mv IS NULL)`` FAILS OPEN
for any family not enumerated — a future family satisfies both conjuncts with either value. The
exclusive-exhaustive form below fails CLOSED, which makes admitting family 3 require a migration.
That is deliberate: the DB becomes a genuine third gate, agreeing with the registry by
construction. (The classic NULL trap — a CHECK passing when it evaluates to NULL — does not bite
here because both discriminators are themselves NOT NULL.) The cadence CHECK also carries the
``interval_days > 0`` rule the DB never had (it lived only in the service).

The ``cadence_kind`` CHECK is new too: it had NO DB constraint and was validated only at create,
never at dispatch or update — and an unresolvable ``cadence_kind`` reaching the poll path is the
one input that can abort a tenant's whole operational tick (see ``service.current_tick``, which now
fails closed).

**Downgrade is a TWO-TABLE cascade and is honestly destructive.** ``fk_scheduled_run_schedule_id_
schedule`` has no ``ON DELETE`` clause (NO ACTION), so a schedule that has ever fired cannot be
deleted while its children exist; and those children live on ``scheduled_run``, which carries BOTH
FORCE RLS **and** the P0001 append-only trigger. So the sandwich needs the trigger leg AND RLS
toggles on BOTH tables — children first. Deleting them destroys **IA append-only governed ledger
evidence** (ENT-062) and leaves the ``calculation_run`` rows those ticks produced orphaned of their
tick provenance (the FK is a one-way soft reference). Disclosed, not implied — the 0041/0042
precedent. FORCE RLS binds even the table OWNER, so an unsandwiched DELETE under a non-superuser
migration role silently matches ZERO rows (0041:60-65, proven live).

No new table, no new audit code, no permission, no governed number. Counts unchanged.
``audit/service.py`` FROZEN.

Revision ID: 0053_schedule_cadence_family
Revises: 0052_breach_notification
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_schedule_cadence_family"
down_revision: str | None = "0052_breach_notification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The family key IS the real ``calculation_run.run_type`` (OQ-SCH-2-8=A) — not a parallel
#: vocabulary. ``target_run_type`` already ships on ``limit_definition``/``breach`` holding real
#: run_types and is rendered in the OPS-1 UI; a short ``"EXPOSURE"`` here would put two meanings
#: behind one column name across three entities.
_VAR = "VAR"
_EXPOSURE = "EXPOSURE_AGGREGATE"
_INTERVAL = "INTERVAL"
_MONTH_END = "CALENDAR_MONTH_END"

#: Runaway ENVELOPE on ``interval_days``, mirroring ``scheduling.service.MAX_INTERVAL_DAYS`` (a
#: century). Not a business rule: the column is a 32-bit Integer, but Python's ``timedelta`` caps at
#: 999,999,999 days, so every value between the two limits made the grid arithmetic raise
#: ``OverflowError`` — not a ``ScheduleError``, therefore escaping the poll loop's skip-and-report
#: and killing the tenant's whole tick cycle. The DB is the layer that also covers a row written by
#: something other than ``create_schedule``.
_MAX_INTERVAL_DAYS = 36_525

#: Every identifier this migration mints, checked at import (the P3-8/BT-1 63-char lesson). The
#: convention expands to ``ck_schedule_<name>`` (db/base.py naming_convention).
_CHECK_MODEL_VERSION = "model_version_by_family"
_CHECK_INTERVAL = "interval_days_by_cadence"
_CHECK_CADENCE = "cadence_kind_vocab"
_IDENTIFIERS = (
    f"ck_schedule_{_CHECK_MODEL_VERSION}",
    f"ck_schedule_{_CHECK_INTERVAL}",
    f"ck_schedule_{_CHECK_CADENCE}",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.alter_column(
        "schedule",
        "model_version_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=False),
        nullable=True,
    )
    op.alter_column(
        "schedule",
        "interval_days",
        existing_type=sa.Integer(),
        nullable=True,
    )
    # TOTAL ENUMERATION, not implication — fails CLOSED for an unenumerated family/cadence.
    op.create_check_constraint(
        _CHECK_MODEL_VERSION,
        "schedule",
        f"(target_run_type = '{_VAR}' AND model_version_id IS NOT NULL)"
        f" OR (target_run_type = '{_EXPOSURE}' AND model_version_id IS NULL)",
    )
    op.create_check_constraint(
        _CHECK_INTERVAL,
        "schedule",
        f"(cadence_kind = '{_INTERVAL}' AND interval_days IS NOT NULL"
        f" AND interval_days > 0 AND interval_days <= {_MAX_INTERVAL_DAYS})"
        f" OR (cadence_kind = '{_MONTH_END}' AND interval_days IS NULL)",
    )
    op.create_check_constraint(
        _CHECK_CADENCE,
        "schedule",
        f"cadence_kind IN ('{_INTERVAL}', '{_MONTH_END}')",
    )


def downgrade() -> None:
    # Honestly destructive (see the module docstring): rows unrepresentable under the re-tightened
    # schema are DELETED, and their append-only ``scheduled_run`` children go first because the FK
    # is NO ACTION. Both DELETEs are sandwiched — FORCE RLS binds the owner, and the children carry
    # the P0001 append-only trigger.
    for name in (_CHECK_CADENCE, _CHECK_INTERVAL, _CHECK_MODEL_VERSION):
        op.execute(f"ALTER TABLE schedule DROP CONSTRAINT IF EXISTS ck_schedule_{name}")

    op.execute("ALTER TABLE scheduled_run DISABLE TRIGGER scheduled_run_append_only")
    op.execute("ALTER TABLE scheduled_run DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schedule DISABLE ROW LEVEL SECURITY")

    # The two relaxations are INDEPENDENT — a VAR + CALENDAR_MONTH_END schedule is unrepresentable
    # via the cadence leg alone, so the predicate is an OR.
    _unrepresentable = "model_version_id IS NULL OR interval_days IS NULL"
    op.execute(
        "DELETE FROM scheduled_run WHERE schedule_id IN "
        f"(SELECT id FROM schedule WHERE {_unrepresentable})"
    )
    op.execute(f"DELETE FROM schedule WHERE {_unrepresentable}")

    op.execute("ALTER TABLE schedule ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schedule FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_run ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_run FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_run ENABLE TRIGGER scheduled_run_append_only")

    op.alter_column(
        "schedule",
        "interval_days",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "schedule",
        "model_version_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=False),
        nullable=False,
    )
