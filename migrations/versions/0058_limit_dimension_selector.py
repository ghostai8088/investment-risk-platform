"""LIM-2: the dimensional limit selector — additive columns on ``limit_definition`` + ``breach``.

**The wave's highest-risk migration** (delivery roadmap, Wave-14 slice 2): a DOUBLE-table ALTER
where one table carries the ``irp_prevent_mutation()`` P0001 append-only trigger and BOTH receive
their first CHECK constraints.

Two disciplines are load-bearing here and are stated rather than assumed:

1. **NO backfill DML on ``breach``.** 0050 puts ``breach`` alone in its ``APPEND_ONLY_TABLES`` and
   creates ``breach_append_only BEFORE UPDATE OR DELETE``, so any ``UPDATE`` raises P0001. Every
   column added here is NULLABLE and left NULL on existing rows — which is the HONEST value: those
   breaches are VAR/ACTIVE_RISK and have no dimension. The precedent is settled, not novel:
   ``var_result`` is append-only (0026) and was widened three times (0038/0040/0048), every column
   nullable, none backfilled.

2. **CHECK names are SUFFIX-ONLY — and the identifier asymmetry cuts BOTH ways.** ``ck`` is the
   ONLY entry in ``db/base.py``'s ``NAMING_CONVENTION`` keyed on ``%(constraint_name)s``
   (``"ck": "ck_%(table_name)s_%(constraint_name)s"``); ``ix``/``uq``/``fk``/``pk`` all substitute
   column and table names instead. So a CHECK name is the only identifier alembic EXPANDS from what
   you pass — on ``drop_constraint`` exactly as on ``create_check_constraint`` — while FK and index
   operations take the literal catalog name. Passing an expanded CHECK name to either call yields
   ``ck_<table>_ck_<table>_<name>``: past 63 chars PG truncates it (the CON-1 0057 defect, which
   three reading lanes missed by comparing migration text to ORM text); under 63 chars it simply
   does not exist, which is how the P4 dry run caught it here — **the upgrade path was correct and
   verified against the live catalog, and only executing the DOWNGRADE exposed the bug.** The
   ``_IDENTIFIERS`` assert below checks the EXPANDED names, because the expanded name is what PG
   stores and truncates.

**Departure from a standing rule, recorded rather than assumed (operating instructions, the
Genericity rule: "type/scheme/status columns are controlled-vocab strings (no enum/CHECK) ... new
families extend by value, never a migration").** Three of the five CHECKs below are SHAPE
constraints, which that rule does not reach. Two are VOCABULARY CHECKs and ARE a departure:
``dimension_kind_vocab`` and ``denominator_basis_vocab``. Taken deliberately, with prior art one and
four slices old (0057's ``ck_concentration_result_dimension_kind``; 0053's
``ck_schedule_cadence_kind_vocab``), because the extensibility the Genericity rule protects is
exactly what must NOT exist here: adding a denominator basis changes what every threshold written
against the old one MEANS, so it has to cost a migration and a governed decision, not a new string.

Revision ID: 0058_limit_dimension_selector
Revises: 0057_concentration_result
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID

revision: str = "0058_limit_dimension_selector"
down_revision: str | None = "0057_concentration_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIMIT = "limit_definition"
_BREACH = "breach"

#: CHECK suffixes — the convention expands each to ``ck_<table>_<suffix>``.
_CK_SHAPE = "concentration_shape"
_CK_ISSUER_ONLY = "issuer_only"
_CK_SCHEME_BY_DIM = "scheme_by_dimension"
_CK_BASIS_VOCAB = "denominator_basis_vocab"
_CK_DIM_VOCAB = "dimension_kind_vocab"

#: The EXPANDED identifiers — what PostgreSQL actually stores and truncates (the 0057 lesson).
_IDENTIFIERS = (
    f"ck_{_LIMIT}_{_CK_SHAPE}",
    f"ck_{_LIMIT}_{_CK_ISSUER_ONLY}",
    f"ck_{_LIMIT}_{_CK_SCHEME_BY_DIM}",
    f"ck_{_LIMIT}_{_CK_BASIS_VOCAB}",
    f"ck_{_LIMIT}_{_CK_DIM_VOCAB}",
    "ix_limit_definition_issuer_id",
    "fk_limit_definition_issuer_id_issuer",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]

#: Mirrors ``concentration.models.CONCENTRATION_DIMENSION_KINDS`` and ``DENOMINATOR_BASES``. A
#: divergence is caught by the live-catalog test, not by reading these two lines.
_DIMENSION_KINDS = ("ISSUER", "SECTOR_INDUSTRY", "COUNTRY_OF_RISK")
_CLASSIFICATION_KINDS = ("SECTOR_INDUSTRY", "COUNTRY_OF_RISK")
_BASES = ("INVESTED_LONG",)
_CONCENTRATION = "CONCENTRATION"

_DIM_SQL = ", ".join(f"'{k}'" for k in _DIMENSION_KINDS)
_CLASSIFICATION_SQL = ", ".join(f"'{k}'" for k in _CLASSIFICATION_KINDS)
_BASES_SQL = ", ".join(f"'{b}'" for b in _BASES)


def upgrade() -> None:
    # --- limit_definition: five additive nullable FROZEN-identity columns ---
    op.add_column(_LIMIT, sa.Column("dimension_kind", sa.String(30), nullable=True))
    op.add_column(_LIMIT, sa.Column("bucket_code", sa.String(100), nullable=True))
    op.add_column(_LIMIT, sa.Column("issuer_id", GUID(), nullable=True))
    op.add_column(_LIMIT, sa.Column("scheme_family", sa.String(50), nullable=True))
    # NO FK: classification_scheme is HYBRID and a PG referential check bypasses RLS, so an FK
    # would let a proprietary row reference a scheme its own USING clause cannot see (OQ-CON-1-14).
    op.add_column(_LIMIT, sa.Column("authored_scheme_id", GUID(), nullable=True))
    op.add_column(_LIMIT, sa.Column("denominator_basis", sa.String(30), nullable=True))

    # issuer IS same-tenant proprietary, so this FK is legal (the concentration_result precedent).
    op.create_foreign_key(
        "fk_limit_definition_issuer_id_issuer", _LIMIT, "issuer", ["issuer_id"], ["id"]
    )
    op.create_index("ix_limit_definition_issuer_id", _LIMIT, ["issuer_id"])

    # --- limit_definition: the table's FIRST CHECK constraints ---
    # 1. The dimension columns exist iff this is a concentration limit. Total enumeration in both
    #    directions, so a non-concentration family can never carry a stray dimension.
    op.create_check_constraint(
        _CK_SHAPE,
        _LIMIT,
        f"(target_run_type = '{_CONCENTRATION}' AND dimension_kind IS NOT NULL"
        f" AND denominator_basis IS NOT NULL)"
        f" OR (target_run_type <> '{_CONCENTRATION}' AND dimension_kind IS NULL"
        f" AND bucket_code IS NULL AND issuer_id IS NULL AND scheme_family IS NULL"
        f" AND authored_scheme_id IS NULL AND denominator_basis IS NULL)",
    )
    # 2. The DISCLOSURE fence, structural. Mirrors concentration_result's
    #    ``issuer_only_on_issuer_rows``: issuer identity may exist ONLY on an ISSUER-dimension row.
    #    This is what makes the read fence enforceable — the reads key on `issuer_id IS NOT NULL`.
    op.create_check_constraint(
        _CK_ISSUER_ONLY, _LIMIT, "issuer_id IS NULL OR dimension_kind = 'ISSUER'"
    )
    # 3. A classification dimension carries its scheme family; ISSUER never does.
    op.create_check_constraint(
        _CK_SCHEME_BY_DIM,
        _LIMIT,
        f"dimension_kind IS NULL"
        f" OR ((dimension_kind IN ({_CLASSIFICATION_SQL})) = (scheme_family IS NOT NULL))",
    )
    # 4. VOCABULARY (a recorded Genericity departure — see the module docstring): the
    #    definition-time half of the basis discipline. A limit declaring a NAV basis is refused
    #    because no such value exists yet.
    op.create_check_constraint(
        _CK_BASIS_VOCAB,
        _LIMIT,
        f"denominator_basis IS NULL OR denominator_basis IN ({_BASES_SQL})",
    )
    # 5. VOCABULARY (same departure): total enumeration, failing CLOSED on an unenumerated kind.
    op.create_check_constraint(
        _CK_DIM_VOCAB, _LIMIT, f"dimension_kind IS NULL OR dimension_kind IN ({_DIM_SQL})"
    )

    # --- breach: additive nullable echoes, NO backfill (P0001 forbids UPDATE) ---
    # These echo what was MEASURED. `resolved_scheme_id` is deliberately the scheme the EVALUATED
    # run used, not the limit's `authored_scheme_id` — the pair is what makes a scheme-drift breach
    # provable from the rows alone rather than merely flagged live.
    op.add_column(_BREACH, sa.Column("dimension_kind", sa.String(30), nullable=True))
    op.add_column(_BREACH, sa.Column("bucket_code", sa.String(100), nullable=True))
    op.add_column(_BREACH, sa.Column("issuer_id", GUID(), nullable=True))
    op.add_column(_BREACH, sa.Column("scheme_family", sa.String(50), nullable=True))
    op.add_column(_BREACH, sa.Column("resolved_scheme_id", GUID(), nullable=True))
    op.add_column(_BREACH, sa.Column("denominator_basis", sa.String(30), nullable=True))
    # The pre-existing LOW paid here (wave_14_planning fact 4): breach echoed the metric identity
    # but never the portfolio scope, so a breach row was not fully self-describing.
    op.add_column(_BREACH, sa.Column("scope_portfolio_id", GUID(), nullable=True))


def downgrade() -> None:
    # --- the destructive downgrade leg: found by the P4 dry run, corrected by the review ---
    # This migration is NOT in the 0046 "additive column, no DML, no zero-row trap" class, and the
    # difference is the CHECK. Dropping these columns destroys the dimension data while LEAVING the
    # rows with `target_run_type = 'CONCENTRATION'`. A later re-upgrade then re-adds the columns as
    # NULL and `concentration_shape` rejects exactly those rows — so a completed downgrade leaves a
    # database that CANNOT be upgraded again without manual data repair. The dry run reproduced
    # that: downgrade succeeded, re-upgrade died with a CheckViolation on 4 rows.
    #
    # **This REVERSES the refusal the P4 dry run originally shipped, for two reasons found by the
    # adversarial review — recorded here rather than swapped in quietly.**
    #
    # (1) The refusal was RLS-BLIND, and would have destroyed the data it existed to protect.
    #     `limit_definition` carries FORCE ROW LEVEL SECURITY (0050) keyed on the
    #     `app.current_tenant` GUC, which a migration never sets. FORCE binds the table OWNER too,
    #     so as the non-superuser owner a real deployment runs as, the count returned ZERO, the
    #     guard fell through, and six governed selector columns were dropped anyway. It "passed"
    #     the dry run only because the postgres image's `irp` is a SUPERUSER, which RLS exempts —
    #     the guard was proven by the one role that cannot exercise it.
    #
    # (2) Its stated remedy was UNACHIEVABLE. "Retire those limits first" is impossible once a
    #     limit has breached: `breach` FKs `limit_definition`, and `breach` carries the P0001
    #     append-only trigger, so the rows can be neither deleted nor orphaned by any application
    #     path. A guard whose only escape does not exist is a permanent block, not a control.
    #
    # So this follows the repo's OWN precedent for a downgrade that would strand data (0053's
    # two-table cascade, and 0028/0041/0042): SANDWICH the destructive DML — disable the
    # append-only trigger and RLS, delete, then restore BOTH `ENABLE` and `FORCE` (enable without
    # force is a silent security regression). A downgrade is a schema-level rollback, and this
    # codebase has already accepted that one may destroy append-only evidence; what it must never
    # do is destroy it SILENTLY or leave the database un-upgradeable.
    op.execute("ALTER TABLE breach DISABLE TRIGGER breach_append_only")
    op.execute("ALTER TABLE breach DISABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_LIMIT} DISABLE ROW LEVEL SECURITY")

    # Children first (the FK is NO ACTION), then the limits whose selector columns are about to
    # vanish. Tenant-blind BY DESIGN: a migration is database-wide, so filtering by any single
    # tenant GUC would under-delete and leave exactly the un-upgradeable rows behind.
    op.execute(
        f"DELETE FROM {_BREACH} WHERE limit_definition_id IN "
        f"(SELECT id FROM {_LIMIT} WHERE target_run_type = '{_CONCENTRATION}')"
    )
    op.execute(f"DELETE FROM {_LIMIT} WHERE target_run_type = '{_CONCENTRATION}'")

    op.execute(f"ALTER TABLE {_LIMIT} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_LIMIT} FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE breach ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE breach FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE breach ENABLE TRIGGER breach_append_only")

    for column in (
        "scope_portfolio_id",
        "denominator_basis",
        "resolved_scheme_id",
        "scheme_family",
        "issuer_id",
        "bucket_code",
        "dimension_kind",
    ):
        op.drop_column(_BREACH, column)

    # SUFFIXES, not expanded names — and this asymmetry is the trap the P4 dry run caught (see the
    # module docstring's "the identifier asymmetry" note). `ck` is the ONLY naming convention keyed
    # on %(constraint_name)s, so alembic expands whatever is passed here into
    # `ck_<table>_<passed>`; passing the catalog name yields
    # `ck_limit_definition_ck_limit_definition_dimension_kind_vocab`, which does not exist. The FK
    # and index drops below take LITERAL catalog names, because their conventions substitute
    # column/table names and have no %(constraint_name)s to expand.
    for name in (_CK_DIM_VOCAB, _CK_BASIS_VOCAB, _CK_SCHEME_BY_DIM, _CK_ISSUER_ONLY, _CK_SHAPE):
        op.drop_constraint(name, _LIMIT, type_="check")

    op.drop_index("ix_limit_definition_issuer_id", table_name=_LIMIT)
    op.drop_constraint("fk_limit_definition_issuer_id_issuer", _LIMIT, type_="foreignkey")
    for column in (
        "denominator_basis",
        "authored_scheme_id",
        "scheme_family",
        "issuer_id",
        "bucket_code",
        "dimension_kind",
    ):
        op.drop_column(_LIMIT, column)
