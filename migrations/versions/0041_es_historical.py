"""ES-HS-1: widen the 0028 metric-conditional CHECK for ``ES_HISTORICAL`` rows.

``metric_type='ES_HISTORICAL'`` rows (OD-ES-HS-1-A) carry the exact ``VAR_HISTORICAL`` NULL
shape — no ``z_score`` (no normal quantile exists), no ``sigma`` (no volatility estimate), no
``covariance_run_id`` (no covariance run is consumed) — but the 0028 CHECK exempts only the
literal ``'VAR_HISTORICAL'``, so the row violates it in PG while passing the whole SQLite
battery (the CHECK is migration-only and ORM-invisible; ES-1 Part 3 item 4 pre-recorded this
exact migration). PG cannot alter a CHECK expression in place: drop + recreate under the SAME
short name (``parametric_not_null`` — the deployed ``ck_var_result_parametric_not_null`` name
is cited by tests/docs and must survive). CHECK-only: NO column, NO nullability change in
either direction, NO pin-serializer key (the 0038/0040 false-drift landmine does not trip —
``var_result_content``'s frozen key set is already None-tolerant for the trio).

No new audit code, permission, or entity. ``audit/service.py`` FROZEN.

Revision ID: 0041_es_historical
Revises: 0040_var_estimate_age
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0041_es_historical"
down_revision: str | None = "0040_var_estimate_age"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTIFIERS = ("parametric_not_null", "ck_var_result_parametric_not_null")
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]

#: The 0028 expression, verbatim — recreated by the downgrade.
_NARROW_CHECK = (
    "metric_type = 'VAR_HISTORICAL' OR "
    "(z_score IS NOT NULL AND sigma IS NOT NULL AND covariance_run_id IS NOT NULL)"
)
#: The widened expression: both empirical metrics exempt, everything else stays forced.
#: (PG normalizes the IN-list to ``= ANY (ARRAY[...])`` in pg_get_constraintdef — nothing
#: reads the reflected text; decided and pinned at planning, OD-ES-HS-1-C.)
_WIDE_CHECK = (
    "metric_type IN ('VAR_HISTORICAL', 'ES_HISTORICAL') OR "
    "(z_score IS NOT NULL AND sigma IS NOT NULL AND covariance_run_id IS NOT NULL)"
)


def upgrade() -> None:
    op.drop_constraint("parametric_not_null", "var_result", type_="check")
    op.create_check_constraint("parametric_not_null", "var_result", _WIDE_CHECK)


def downgrade() -> None:
    # ES_HISTORICAL rows are UNREPRESENTABLE under the 0028-form CHECK: the downgrade REMOVES
    # them (the 0028 destructive precedent, extended by ratification OQ-ES-HS-1-3). The delete
    # runs BEFORE the narrow CHECK is re-added (PG validates existing rows at ADD CONSTRAINT).
    # The 6-statement sandwich is 0028's verbatim: the P0001 append-only trigger protects
    # business mutation, not migrations; FORCE RLS binds even the table OWNER, so under any
    # non-superuser migration role an unsandwiched DELETE silently matches ZERO rows (the
    # recorded 0028 lesson — CI's green smoke proves only the container-superuser path; the
    # ES-HS-1 PG suite drives this body under an owner-via-membership non-superuser role).
    # Both toggles are transactional (env.py wraps the migration in one transaction).
    op.drop_constraint("parametric_not_null", "var_result", type_="check")
    op.execute("ALTER TABLE var_result DISABLE TRIGGER var_result_append_only")
    op.execute("ALTER TABLE var_result DISABLE ROW LEVEL SECURITY")
    op.execute("DELETE FROM var_result WHERE metric_type = 'ES_HISTORICAL'")
    op.execute("ALTER TABLE var_result ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE var_result FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE var_result ENABLE TRIGGER var_result_append_only")
    op.create_check_constraint("parametric_not_null", "var_result", _NARROW_CHECK)
