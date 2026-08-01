"""CAL-1b: the holiday-aware ``BUSINESS_MONTH_END`` cadence — the DDL half of the atomic
convention move (OQ-CAL-1-3/4/5; `cal_1_decision_record.md`).

Four additive pieces plus two CHECK amendments, all on shipped tables:

- ``schedule.calendar_id`` — the bound holiday calendar (nullable UUID FK → ``calendar.id`` +
  index): REQUIRED for the new kind, FORBIDDEN for the legacy kinds (the new kind-gated CHECK),
  CREATE-ONLY at the service (the frozen-grid doctrine). The SECOND symmetric→hybrid FK (after
  0056's assignment→scheme); PG FK checks bypass RLS, so the own-OR-SYSTEM guard lives at
  ``create_schedule``.
- ``calendar.holidays_complete_through`` — the DECLARED coverage horizon (never a derived MAX —
  a MAX cannot represent a gap), set only by ``refresh_calendar_holidays``; ticks and v2 perf
  runs beyond it refuse fail-closed.
- ``scheduled_run.period_key`` (``YYYY-MM``, NULL for legacy kinds) + the PARTIAL UNIQUE
  ``uq_scheduled_run_schedule_period`` — the MONTH-grain idempotency backstop: the exact-instant
  ``uq_scheduled_run_schedule_tick`` cannot collide when a holiday refresh re-values the tick
  instant between concurrent polls (READ COMMITTED), so without this key one economic month can
  fire twice with zero evidence. Additive-nullable: the table is IA append-only (P0001 trigger) —
  no backfill is possible or wanted.
- The two 0053 cadence CHECKs are TOTAL enumerations and are re-created WIDENED (the vocab gains
  ``BUSINESS_MONTH_END``; the interval CHECK gains its interval-less arm, the 36_525 envelope
  preserved verbatim). ``ck_schedule_model_version_by_family`` is family-keyed and unchanged.

**The ck expansion asymmetry (the 0058 lesson):** ``ck`` is the only NAMING_CONVENTION entry
keyed on ``%(constraint_name)s`` — alembic EXPANDS what you pass on ``drop_constraint`` exactly
as on ``create_check_constraint``, so both are called with the SUFFIX below, while the FK/index
ops take literal catalog names. ``_IDENTIFIERS`` asserts the EXPANDED forms.

Downgrade is honestly destructive for rows only the new schema can represent: a
``BUSINESS_MONTH_END`` schedule (and its append-only ``scheduled_run`` children, FK NO ACTION)
cannot exist under the restored total enumerations — the deletes are sandwiched (FORCE RLS binds
the owner; the children carry the P0001 trigger), the 0053/0058 precedent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0059_business_month_end"
down_revision: str | None = "0058_limit_dimension_selector"
branch_labels: str | None = None
depends_on: str | None = None

_INTERVAL = "INTERVAL"
_MONTH_END = "CALENDAR_MONTH_END"
_BUSINESS = "BUSINESS_MONTH_END"
_MAX_INTERVAL_DAYS = 36_525  # the 0053 envelope, preserved verbatim

#: ck names are SUFFIX-ONLY (the convention expands ``ck_schedule_<name>``); fk/ix/uq literal.
_CHECK_INTERVAL = "interval_days_by_cadence"
_CHECK_CADENCE = "cadence_kind_vocab"
_CHECK_CALENDAR = "calendar_id_by_cadence"
_FK_CALENDAR = "fk_schedule_calendar_id_calendar"
_IX_CALENDAR = "ix_schedule_calendar_id"
_UQ_PERIOD = "uq_scheduled_run_schedule_period"
_IDENTIFIERS = (
    f"ck_schedule_{_CHECK_INTERVAL}",
    f"ck_schedule_{_CHECK_CADENCE}",
    f"ck_schedule_{_CHECK_CALENDAR}",
    _FK_CALENDAR,
    _IX_CALENDAR,
    _UQ_PERIOD,
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]

#: The 0053 CHECK bodies, verbatim — what downgrade restores (and upgrade replaces).
_INTERVAL_SQL_0053 = (
    f"(cadence_kind = '{_INTERVAL}' AND interval_days IS NOT NULL"
    f" AND interval_days > 0 AND interval_days <= {_MAX_INTERVAL_DAYS})"
    f" OR (cadence_kind = '{_MONTH_END}' AND interval_days IS NULL)"
)
_CADENCE_SQL_0053 = f"cadence_kind IN ('{_INTERVAL}', '{_MONTH_END}')"

#: The widened bodies (CAL-1b) — still TOTAL enumerations, failing closed.
_INTERVAL_SQL = (
    f"(cadence_kind = '{_INTERVAL}' AND interval_days IS NOT NULL"
    f" AND interval_days > 0 AND interval_days <= {_MAX_INTERVAL_DAYS})"
    f" OR (cadence_kind IN ('{_MONTH_END}', '{_BUSINESS}') AND interval_days IS NULL)"
)
_CADENCE_SQL = f"cadence_kind IN ('{_INTERVAL}', '{_MONTH_END}', '{_BUSINESS}')"
_CALENDAR_SQL = (
    f"(cadence_kind = '{_BUSINESS}' AND calendar_id IS NOT NULL)"
    f" OR (cadence_kind IN ('{_INTERVAL}', '{_MONTH_END}') AND calendar_id IS NULL)"
)


def upgrade() -> None:
    # --- schedule: the calendar binding -----------------------------------------------------
    op.add_column(
        "schedule",
        sa.Column("calendar_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(_FK_CALENDAR, "schedule", "calendar", ["calendar_id"], ["id"])
    op.create_index(_IX_CALENDAR, "schedule", ["calendar_id"])

    # --- calendar: the declared coverage horizon --------------------------------------------
    op.add_column("calendar", sa.Column("holidays_complete_through", sa.Date(), nullable=True))

    # --- scheduled_run: the month-grain idempotency key -------------------------------------
    op.add_column("scheduled_run", sa.Column("period_key", sa.String(length=7), nullable=True))
    op.create_index(
        _UQ_PERIOD,
        "scheduled_run",
        ["schedule_id", "period_key"],
        unique=True,
        postgresql_where=sa.text("period_key IS NOT NULL"),
    )

    # --- the widened cadence CHECKs (suffix-only names; alembic expands) ---------------------
    op.drop_constraint(_CHECK_INTERVAL, "schedule", type_="check")
    op.drop_constraint(_CHECK_CADENCE, "schedule", type_="check")
    op.create_check_constraint(_CHECK_INTERVAL, "schedule", _INTERVAL_SQL)
    op.create_check_constraint(_CHECK_CADENCE, "schedule", _CADENCE_SQL)
    op.create_check_constraint(_CHECK_CALENDAR, "schedule", _CALENDAR_SQL)


def downgrade() -> None:
    # Restore the 0053 total enumerations — BUSINESS_MONTH_END rows are unrepresentable under
    # them, so they (and their append-only children, FK NO ACTION) are honestly DELETED first,
    # sandwiched exactly like 0053/0058 (FORCE RLS binds the owner; the P0001 trigger blocks
    # the child delete).
    op.drop_constraint(_CHECK_CALENDAR, "schedule", type_="check")
    op.drop_constraint(_CHECK_CADENCE, "schedule", type_="check")
    op.drop_constraint(_CHECK_INTERVAL, "schedule", type_="check")

    op.execute("ALTER TABLE scheduled_run DISABLE TRIGGER scheduled_run_append_only")
    op.execute("ALTER TABLE scheduled_run DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schedule DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DELETE FROM scheduled_run WHERE schedule_id IN "
        f"(SELECT id FROM schedule WHERE cadence_kind = '{_BUSINESS}')"
    )
    op.execute(f"DELETE FROM schedule WHERE cadence_kind = '{_BUSINESS}'")
    op.execute("ALTER TABLE schedule ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schedule FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_run ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_run FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_run ENABLE TRIGGER scheduled_run_append_only")

    op.create_check_constraint(_CHECK_INTERVAL, "schedule", _INTERVAL_SQL_0053)
    op.create_check_constraint(_CHECK_CADENCE, "schedule", _CADENCE_SQL_0053)

    op.drop_index(_UQ_PERIOD, table_name="scheduled_run")
    op.drop_column("scheduled_run", "period_key")
    op.drop_column("calendar", "holidays_complete_through")
    op.drop_index(_IX_CALENDAR, table_name="schedule")
    op.drop_constraint(_FK_CALENDAR, "schedule", type_="foreignkey")
    op.drop_column("schedule", "calendar_id")
