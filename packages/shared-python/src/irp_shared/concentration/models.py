"""ENT-069 ``concentration_result`` — the 23rd governed number family (CON-1, Wave-14 slice 1).

Dimensional concentration over a pinned exposure run: per-bucket ``share_invested_long`` DETAIL
rows and run-level SUMMARY metrics (MAX share / HHI / CR-N), discriminated by ``row_kind`` with a
single always-filled ``bucket_code`` key — the ratified v6 grain (CON-1 record OQ-CON-1-23): every
key column NOT NULL, partial unique indexes declared for BOTH dialects, ``issuer_id``/``scheme_id``
echoed OUTSIDE the keys and gated by row-kind-qualified CHECKs.

The share is deliberately NOT any regulatory ratio (no NAV/total-assets denominator is computable
on this schema); every row carries ``denominator_basis`` so a future basis is additive, never a
reinterpretation. ``_METRIC_MAP`` registration is DEFERRED to LIM-2 (OQ-CON-1-15 reversal): no
limit can bind these metrics until the basis machinery lands there.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, event, text
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass

#: Row kinds — the discriminator the v3 grain was missing (two jointly-unsatisfiable CHECKs).
ROW_KIND_DETAIL = "DETAIL"
ROW_KIND_SUMMARY = "SUMMARY"
ROW_KINDS: tuple[str, ...] = (ROW_KIND_DETAIL, ROW_KIND_SUMMARY)

#: Dimension kinds. ``ISSUER`` is CON-1-OWNED — deliberately NOT in
#: ``classification.DIMENSION_KINDS`` (no assignment row can carry it; pinned by a test).
DIMENSION_KIND_ISSUER = "ISSUER"
CONCENTRATION_DIMENSION_KINDS: tuple[str, ...] = (
    DIMENSION_KIND_ISSUER,
    "SECTOR_INDUSTRY",
    "COUNTRY_OF_RISK",
)

#: Dunder ``bucket_code`` sentinels — dunder-delimited BECAUSE the column shares its namespace
#: with taxonomy node codes (a vendor scheme could legally code a node ``UNCLASSIFIED``);
#: ``create_node`` refuses ``__*__`` codes at capture, closing the collision at both ends.
BUCKET_UNCLASSIFIED = "__UNCLASSIFIED__"
BUCKET_UNCLASSIFIABLE = "__UNCLASSIFIABLE__"
BUCKET_SUMMARY = "__SUMMARY__"
BUCKET_SENTINELS: tuple[str, ...] = (BUCKET_UNCLASSIFIED, BUCKET_UNCLASSIFIABLE, BUCKET_SUMMARY)

#: The v1 denominator basis — the ONLY value; a NAV/total-assets basis is a future ADDITIVE value.
DENOMINATOR_BASIS_INVESTED_LONG = "INVESTED_LONG"
DENOMINATOR_BASES: tuple[str, ...] = (DENOMINATOR_BASIS_INVESTED_LONG,)

#: The exact metric vocabulary (OQ-CON-1-13) — measured longest 25 <= String(30); the census test
#: asserts set equality on BOTH tuples. Detail rows carry only ``SHARE``.
METRIC_TYPE_SHARE = "SHARE"
SUMMARY_METRIC_TYPES: tuple[str, ...] = (
    "MAX_SHARE_ISSUER",
    "MAX_SHARE_SECTOR_INDUSTRY",
    "MAX_SHARE_COUNTRY_OF_RISK",
    "HHI_ISSUER",
    "HHI_SECTOR_INDUSTRY",
    "HHI_COUNTRY_OF_RISK",
    "CR_5_ISSUER",
    "CR_5_SECTOR_INDUSTRY",
    "CR_5_COUNTRY_OF_RISK",
)
CONCENTRATION_METRIC_TYPES: tuple[str, ...] = (METRIC_TYPE_SHARE, *SUMMARY_METRIC_TYPES)

#: The classification-dimension summary metrics (scheme_id NOT NULL); the issuer trio takes NULL.
_CLASSIFICATION_SUMMARY_METRICS: tuple[str, ...] = tuple(
    m for m in SUMMARY_METRIC_TYPES if not m.endswith("_ISSUER")
)

_SUMMARY_METRICS_SQL = ", ".join(f"'{m}'" for m in SUMMARY_METRIC_TYPES)
_CLASSIFICATION_SUMMARY_SQL = ", ".join(f"'{m}'" for m in _CLASSIFICATION_SUMMARY_METRICS)


class ConcentrationResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """ENT-069 (IA true append-only): one DETAIL row per (run, dimension, bucket) plus one SUMMARY
    row per (run, metric). Created once, never mutated."""

    __tablename__ = "concentration_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # The two ratified grains — PARTIAL unique indexes, BOTH dialects (the shipped
        # sqlite_where convention; the "SQLite is blind" claim was refuted at v5).
        Index(
            "uq_concentration_summary",
            "calculation_run_id",
            "metric_type",
            unique=True,
            postgresql_where=text("row_kind = 'SUMMARY'"),
            sqlite_where=text("row_kind = 'SUMMARY'"),
        ),
        Index(
            "uq_concentration_detail",
            "calculation_run_id",
            "dimension_kind",
            "bucket_code",
            unique=True,
            postgresql_where=text("row_kind = 'DETAIL'"),
            sqlite_where=text("row_kind = 'DETAIL'"),
        ),
        # Total-enumeration row-kind census (fails CLOSED for an unenumerated kind).
        CheckConstraint(
            "row_kind IN ('DETAIL', 'SUMMARY')",
            name="row_kind",  # ck_ SUFFIX only (the 0055 naming-convention note)
        ),
        # SUMMARY rows: sentinel bucket, no issuer identity, metric_type IN the NINE summary
        # names (SHARE refused on summary rows — the v6 junk-SHARE-summary hole), scheme echo
        # decided by the name (classification six NOT NULL, issuer trio NULL).
        CheckConstraint(
            "row_kind != 'SUMMARY' OR ("
            "bucket_code = '__SUMMARY__' AND issuer_id IS NULL "
            f"AND metric_type IN ({_SUMMARY_METRICS_SQL}) "
            f"AND ((metric_type IN ({_CLASSIFICATION_SUMMARY_SQL})) = (scheme_id IS NOT NULL))"
            ")",
            name="summary_shape",  # ck_ SUFFIX only (the 0055 naming-convention note)
        ),
        # DETAIL rows: metric_type = SHARE; scheme echo decided BY dimension (ISSUER => NULL,
        # classification kinds => NOT NULL); a real ISSUER bucket carries its issuer FK.
        CheckConstraint(
            "row_kind != 'DETAIL' OR ("
            "metric_type = 'SHARE' AND bucket_code != '__SUMMARY__' "
            "AND ((dimension_kind = 'ISSUER') = (scheme_id IS NULL))"
            ")",
            name="detail_shape",  # ck_ SUFFIX only (the 0055 naming-convention note)
        ),
        CheckConstraint(
            "NOT (row_kind = 'DETAIL' AND dimension_kind = 'ISSUER' "
            "AND bucket_code NOT IN ('__UNCLASSIFIED__', '__UNCLASSIFIABLE__')) "
            "OR issuer_id IS NOT NULL",
            name="issuer_bucket",  # ck_ SUFFIX only (the 0055 naming-convention note)
        ),
        # The DISCLOSURE fence, structural (review). ``issuer_bucket`` above requires an issuer on
        # real ISSUER buckets but never FORBIDS one elsewhere, so a SECTOR_INDUSTRY DETAIL row
        # carrying ``issuer_id`` was schema-legal — and it would sail through the
        # ``concentration.view`` exclusion (which keys on (ISSUER, DETAIL)) carrying proprietary
        # issuer identity to a caller who holds no ``concentration.issuer.view``. Only binder
        # discipline kept that row class nonexistent; now the engine does.
        CheckConstraint(
            "issuer_id IS NULL OR dimension_kind = 'ISSUER'",
            name="issuer_only_on_issuer_rows",  # ck_ SUFFIX only (the 0055 note)
        ),
        CheckConstraint(
            "dimension_kind IN ('ISSUER', 'SECTOR_INDUSTRY', 'COUNTRY_OF_RISK')",
            name="dimension_kind",  # ck_ SUFFIX only (the 0055 naming-convention note)
        ),
        # Wave-14 close fold (migration 0062): the "controlled vocabulary" claim finally gets its
        # constraint. CON-1 shipped denominator_basis as prose-controlled while BOTH sibling
        # tables minted in the same wave constrain theirs (0058's limit_definition, 0061's
        # liquidity_result) — the close's reproduction inserted 'TOTAL_ASSETS_BOGUS' cleanly.
        # Single-valued by ratified design (OQ-CON-1); widening it is a migration, deliberately.
        CheckConstraint(
            "denominator_basis IN ('INVESTED_LONG')",
            name="denominator_basis",  # ck_ SUFFIX only (the 0055 note)
        ),
    )

    # Run-bound + snapshot-gated + model-bound (all NOT NULL — AD-014 at the DB).
    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    #: The run's aggregation scope (= the upstream run's scope_portfolio_id; a NULL-scope
    #: upstream run is refused PRE-BUILD — the OD-API-1b-D honest NULL cannot reach this column).
    portfolio_id: Mapped[str] = mapped_column(GUID, nullable=False, index=True)

    # The grain (every key column NOT NULL).
    row_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    dimension_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    bucket_code: Mapped[str] = mapped_column(String(100), nullable=False)

    # Echoes OUTSIDE the keys, CHECK-gated by row kind/dimension. issuer is same-tenant
    # proprietary (FK legal); scheme is HYBRID — NO FK (referential checks bypass RLS, OQ-14).
    issuer_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("issuer.id"), nullable=True, index=True
    )
    scheme_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    #: The basis echo for classification dimensions (OQ-CON-1-26); NOT_APPLICABLE elsewhere.
    basis: Mapped[str] = mapped_column(String(50), nullable=False)
    denominator_basis: Mapped[str] = mapped_column(
        String(30), nullable=False, default=DENOMINATOR_BASIS_INVESTED_LONG
    )

    # Kernel-computed evidence from the signed atoms (the LONG predicate: exposure_amount > 0).
    gross_amount: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    long_amount: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    short_amount: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    #: DETAIL rows: the share (6dp); SUMMARY rows: the metric value. Nullable on the other kind.
    share_invested_long: Mapped[Decimal | None] = mapped_column(
        PreciseDecimal(20, 6), nullable=True
    )
    metric_value: Mapped[Decimal | None] = mapped_column(PreciseDecimal(20, 6), nullable=True)
    #: Per-dimension coverage pair (SUMMARY rows; NULL on detail rows).
    coverage_ratio: Mapped[Decimal | None] = mapped_column(PreciseDecimal(20, 6), nullable=True)
    coverage_classifiable: Mapped[Decimal | None] = mapped_column(
        PreciseDecimal(20, 6), nullable=True
    )


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


event.listen(ConcentrationResult, "before_update", _block_mutation)
event.listen(ConcentrationResult, "before_delete", _block_mutation)
