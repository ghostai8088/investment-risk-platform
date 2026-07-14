"""PA-4: the additive ``var_result.residual_variance`` evidence column (ENT-057 consumer — the
thirteenth governed number, total parametric VaR = factor + idiosyncratic residual variance).

ONE additive, NULLABLE column on the EXISTING ``var_result`` table (no new table, no RLS/policy
change — ``var_result`` already carries the symmetric loop + the append-only trigger from 0026):

- ``residual_variance`` (``NUMERIC(38,20)``, the covariance/variance scale) — the idiosyncratic
  leg ``Σ_i (MV_i · σ_e,i,daily)²`` (base-currency²) that a ``VAR_PARAMETRIC_TOTAL`` run adds to the
  factor variance ``x'Σx``; NULL on every prior/parametric/HS row (only the new total family writes
  it). Persisted as EVIDENCE so a reader decomposes total vs factor risk without recomputing:
  ``σ_factor² = sigma² − residual_variance`` (``sigma`` holds the TOTAL σ on a total-family row).

No new table, no new audit code (``RISK.VAR_CREATE`` RESERVED), NO new permission (``risk.run``/
``risk.view`` REUSED — a total-VaR run is a NEW registered ``model_version``, dispatched through the
SAME parametric binder, the VAR-HS-1/PA-2 precedent). Every DDL identifier <= 63 chars.

Revision ID: 0038_var_residual_variance
Revises: 0037_proxy_weight_estimate
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_var_residual_variance"
down_revision: str | None = "0037_proxy_weight_estimate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTIFIERS = ("residual_variance",)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.add_column(
        "var_result",
        sa.Column("residual_variance", sa.Numeric(precision=38, scale=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("var_result", "residual_variance")
