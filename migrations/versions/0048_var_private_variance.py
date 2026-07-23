"""PPF-3: the ``var_result`` unified-VaR decomposition columns (the §2.1 arc's final slice — the
UNIFIED public+private VaR, the twentieth governed number ``risk.var.parametric_unified``).

TWO additive, NULLABLE columns on the EXISTING ``var_result`` table (no new table, no RLS/policy
change — ``var_result`` already carries the symmetric loop + the append-only trigger from 0026):

- ``private_variance`` (``NUMERIC(38,20)``, the covariance/variance scale) — the pure-private
  systematic leg ``p'(Ω_pp/d_t)·p`` (base-currency²) a ``VAR_PARAMETRIC_UNIFIED`` run adds: the
  co-movement of the portfolio's private funds' pure-private returns (PPF-2's Ω_pp block REPLACES
  those funds' independent diagonal residual — the REPARTITION, so ``residual_variance`` on a
  unified row is the leg-3 sum over NON-private-segment members only). NULL on every prior/
  parametric/total/HS row. Evidence: ``σ_public² = sigma² − residual_variance − private_variance``.
- ``private_covariance_run_id`` (``GUID`` FK → ``calculation_run.run_id``, indexed) — the consumed
  PPF-2 Ω_pp (``COVARIANCE_PRIVATE``) run, a hard-FK PROVENANCE column (run_id is unique + never
  deleted — the ``covariance_run_id`` precedent). NULL on every non-unified row.

Both columns are EXCLUDED from ``var_result_content`` (the 0038/0040 false-drift landmine rule — a
new pin key re-mints every historical ``var_result`` pin, breaking BT-1/BT-2 reproducibility). The
``ck_var_result_parametric_not_null`` CHECK (0028, widened 0041) is ALREADY satisfied by a
``VAR_PARAMETRIC_UNIFIED`` row (it carries z_score/sigma/covariance_run_id) — NO CHECK change. No
new table, no new audit code (``RISK.VAR_CREATE`` RESERVED), NO new permission (``risk.run``/
``risk.view`` REUSED — a unified-VaR run is a NEW registered ``model_version``). Every DDL
identifier <= 63 chars (the FK convention name ``fk_var_result_private_covariance_run_id_
calculation_run`` = 55).

Revision ID: 0048_var_private_variance
Revises: 0047_private_factor_return
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID

revision: str = "0048_var_private_variance"
down_revision: str | None = "0047_private_factor_return"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "fk_var_result_private_covariance_run_id_calculation_run"
_IX_NAME = "ix_var_result_private_covariance_run_id"
_IDENTIFIERS = ("private_variance", "private_covariance_run_id", _FK_NAME, _IX_NAME)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.add_column(
        "var_result",
        sa.Column("private_variance", sa.Numeric(precision=38, scale=20), nullable=True),
    )
    op.add_column(
        "var_result",
        sa.Column(
            "private_covariance_run_id",
            GUID(),
            sa.ForeignKey("calculation_run.run_id", name=_FK_NAME),
            nullable=True,
        ),
    )
    op.create_index(_IX_NAME, "var_result", ["private_covariance_run_id"])


def downgrade() -> None:
    op.drop_index(_IX_NAME, table_name="var_result")
    op.drop_column("var_result", "private_covariance_run_id")
    op.drop_column("var_result", "private_variance")
