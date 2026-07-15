"""BT-2: the additive ``var_result.estimate_age_days`` evidence column (the estimate-staleness
register item's ECHO half — "nothing … records estimate age at total-VaR time", wave-4 close).

ONE additive, NULLABLE column on the EXISTING ``var_result`` table (no new table, no RLS/policy
change — ``var_result`` already carries the symmetric loop + the append-only trigger from 0026;
the exact ``0038_var_residual_variance`` precedent):

- ``estimate_age_days`` (``INTEGER``) — on a ``VAR_PARAMETRIC_TOTAL`` row, how stale the cited
  PA-3 residual estimates were AT THE RUN'S OWN economic as-of: the pinned covariance
  ``window_end`` MINUS the cited estimation run's PROXY_WEIGHT_INPUT snapshot header
  ``as_of_valuation_date`` (= the regression span end — what data the σ_e actually saw), taken as
  the **MAX across cited estimates** (the binding constraint). NULL on every parametric/HS row,
  on a total run citing NO estimates (the zero-proxied byte-invariance case), and on an ungated
  grandfathered v1 bind whose estimation-snapshot header cannot be resolved (a grandfathered path
  must not gain a new refusal — the echo is EVIDENCE, the gate is POLICY; OD-BT-2-D). Negative
  values are legal and meaningful (a look-ahead estimate; recorded as ungated in v1).

**Landmine rule carried from 0038** (``snapshot/serialize.py``): this column is DELIBERATELY
EXCLUDED from ``var_result_content`` — adding a key to the pinned content would change the
recomputed bytes of every ALREADY-PINNED ``var_result`` component and make ``verify_snapshot``
report false drift on historical snapshots. A test pins the serializer's key set.

No new table, no new audit code (``RISK.VAR_CREATE`` stays RESERVED), NO new permission
(``risk.run``/``risk.view`` REUSED). Every DDL identifier <= 63 chars.

Revision ID: 0040_var_estimate_age
Revises: 0039_model_validation
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_var_estimate_age"
down_revision: str | None = "0039_model_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTIFIERS = ("estimate_age_days",)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.add_column("var_result", sa.Column("estimate_age_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("var_result", "estimate_age_days")
