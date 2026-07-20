"""BT-3: the additive ``var_backtest_result.es_value`` evidence column (the SIXTEENTH governed
number — the Acerbi-Szekely ES backtest).

ONE additive, NULLABLE column on the EXISTING ``var_backtest_result`` table (ENT-055 — no new
table, no RLS/policy change: the table already carries the symmetric loop + the append-only
trigger from 0033):

- ``es_value`` (``NUMERIC(28,6)``, the base-currency money scale) — the per-pair ES-forecast
  echo an ``ES_EXCEPTION_INDICATOR`` row carries (the evidence surface must show what was tested
  against, beside the existing ``realized_pnl``/``var_value`` echoes); NULL on every BT-1/BT-2
  row class and on the ES summary rows.

The NEW metric_type values (``ES_EXCEPTION_INDICATOR``/``ES_PAIR_COUNT``/``AS_Z2``/``AS_Z1`` +
the Christoffersen ``LR_IND``/``LR_CC``) need NO schema change — ``metric_type`` is an
unconstrained ``String(30)`` (the BT-2 zero-schema precedent) and the run-grain UNIQUE already
admits them. No snapshot serializer pins ENT-055 rows, so ``es_value`` creates NO pin-key
false-drift surface (structural — test-pinned).

Downgrade semantics, explicit (the planning verifier's fold): ``drop_column`` — the ROWS survive
representable (no CHECK / ORM validator anywhere on the downgrade path rejects the new
metric_type literals; NO destructive RLS sandwich is needed) **but the column drop DESTROYS
every stored ``es_value`` echo**, and a downgrade→re-upgrade cycle leaves ES_EXCEPTION_INDICATOR
rows with NULL ``es_value`` — a state the binder can never produce, distinguishable from fresh
runs.

No new table, no new audit code (``RISK.ES_BACKTEST_CREATE`` RESERVED), NO new permission
(``risk.run``/``risk.view`` REUSED — the BT-1 precedent). Every DDL identifier <= 63 chars.

Revision ID: 0043_es_backtest
Revises: 0042_desmoothing_estimated_alpha
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_es_backtest"
down_revision: str | None = "0042_desmoothing_estimated_alpha"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTIFIERS = ("es_value",)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.add_column(
        "var_backtest_result",
        sa.Column("es_value", sa.Numeric(precision=28, scale=6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("var_backtest_result", "es_value")
